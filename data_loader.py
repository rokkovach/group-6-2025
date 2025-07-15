import os
import pandas as pd
from typing import Dict, Optional
from sqlalchemy.orm import Session
from models import Movie, Genre, Actor, Rating
import ast
import json
import re
import csv
from database import get_db, init_db

class DataLoader:
    def __init__(self, data_dir: str = "ml-latest-small"):
        self.data_dir = data_dir
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        self.movielens_to_tmdb = {}  # Mapping from MovieLens ID to TMDB ID
        self.stopwords = set()  # Set of stop words for title processing

    def load_stop_words(self, csv_file_path: str = "stop_words.csv") -> None:
        """Load stop words from CSV file"""
        if os.path.exists(csv_file_path):
            print(f"Loading stop words from {csv_file_path}...")
            with open(csv_file_path, mode='r', newline='', encoding='utf-8') as csv_file:
                csv_reader = csv.reader(csv_file)
                self.stopwords = set(row[0].lower() for row in csv_reader)
            print(f"Loaded {len(self.stopwords)} stop words")
        else:
            print(f"Stop words file {csv_file_path} not found, using empty set")

    def extract_title_words(self, title: str) -> str:
        """Extract meaningful words from movie title, removing stop words and years"""
        if not title or title.strip() == "":
            return ""
        
        # Remove the year in parentheses at the end of the title
        cleaned_title = re.sub(r'\s*\(\d{4}\)$', '', title)
        
        # Extract words from title
        words = re.findall(r'\b\w+\b', cleaned_title)
        
        # Filter out stop words (case-insensitive and longer than 3 symbols)
        filtered_words = [word for word in words if word.lower() not in self.stopwords and len(word) >= 3]
        
        # Convert to JSON for storage with UTF-8 characters (for French, Italian etc movies)
        return json.dumps(filtered_words, ensure_ascii=False)

    def load_links(self, file_path: str) -> pd.DataFrame:
        """Load links data to map MovieLens IDs to TMDB IDs and IMDB IDs"""
        full_path = os.path.join(self.data_dir, file_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Links file not found: {full_path}")
        
        df = pd.read_csv(full_path)
        # Create mapping dictionary
        self.movielens_to_tmdb = dict(zip(df['movieId'], df['tmdbId']))
        # Create TMDB to numeric IMDB mapping (for fallback)
        self.tmdb_to_numeric_imdb = dict(zip(df['tmdbId'], df['imdbId']))
        return df

    def load_movies(self) -> pd.DataFrame:
        """Load movies from TMDB metadata file"""
        movies_path = os.path.join(self.data_dir, 'movies_metadata.csv')
        if os.path.exists(movies_path):
            print("Loading movies from TMDB metadata...")
            return pd.read_csv(movies_path, low_memory=False)
        else:
            print("TMDB movies_metadata.csv not found, using MovieLens movies.csv...")
            # Fallback to MovieLens movies
            movies_path = os.path.join(self.data_dir, 'movies.csv')
            return pd.read_csv(movies_path)

    def load_ratings(self, file_path: str) -> pd.DataFrame:
        """Load ratings data from CSV file and map to TMDB IDs"""
        full_path = os.path.join(self.data_dir, file_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Ratings file not found: {full_path}")
        
        df = pd.read_csv(full_path)
        # Map MovieLens movieId to TMDB movieId
        df['tmdbId'] = df['movieId'].map(self.movielens_to_tmdb)
        # Only keep ratings that have a valid TMDB mapping
        df = df.dropna(subset=['tmdbId'])
        df['tmdbId'] = df['tmdbId'].astype(int)
        # Drop the original movieId column and rename tmdbId to movieId
        df = df.drop(columns=['movieId']).rename(columns={'tmdbId': 'movieId'})
        return df

    def load_credits(self, file_path: str) -> pd.DataFrame:
        """Load credits data from CSV file"""
        full_path = os.path.join(self.data_dir, file_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Credits file not found: {full_path}")
        
        df = pd.read_csv(full_path, low_memory=False)
        # Ensure id is integer
        df["id"] = df["id"].astype(int)
        return df

    def import_movies(self, db: Session, movies_df: pd.DataFrame) -> None:
        """Import movies into database with proper genre handling and title words, always setting imdb_id"""
        # Remove duplicates based on TMDB ID, keeping the first occurrence
        movies_df = movies_df.drop_duplicates(subset=['id'], keep='first')
        print(f"After removing duplicates: {len(movies_df)} movies")

        # Build TMDB ID to imdb_id mapping from metadata
        tmdb_to_imdbid = {}
        if 'id' in movies_df.columns and 'imdb_id' in movies_df.columns:
            for _, row in movies_df.iterrows():
                tmdb_id = row['id']
                imdb_id = row.get('imdb_id', None)
                if pd.notna(imdb_id) and imdb_id != '':
                    tmdb_to_imdbid[str(tmdb_id)] = imdb_id

        for _, row in movies_df.iterrows():
            try:
                # Use TMDB ID as the movie ID instead of sequential
                movie_id = int(row['id'])
                tmdb_id_str = str(row['id'])
                # Check if movie already exists
                existing_movie = db.query(Movie).filter(Movie.id == movie_id).first()
                if existing_movie:
                    continue
                title = row.get('title', 'Unknown Title')
                overview = row.get('overview', '')
                # Extract release_date from TMDB metadata
                release_date = row.get('release_date', '')
                if pd.isna(release_date) or release_date == '':
                    release_date = None
                # --- IMDB ID LOGIC ---
                imdb_id = None
                # 1. Prefer imdb_id from metadata
                if tmdb_id_str in tmdb_to_imdbid:
                    imdb_id = tmdb_to_imdbid[tmdb_id_str]
                # 2. Fallback: use numeric imdbId from links.csv and convert to tt format
                if (not imdb_id or imdb_id == '' or pd.isna(imdb_id)) and hasattr(self, 'tmdb_to_numeric_imdb'):
                    numeric_imdb = self.tmdb_to_numeric_imdb.get(movie_id)
                    if pd.notna(numeric_imdb):
                        imdb_id = f"tt{int(numeric_imdb):07d}"
                if imdb_id == '' or pd.isna(imdb_id):
                    imdb_id = None
                # Parse genres (preserve original approach)
                genres = []
                if pd.notna(row.get('genres')):
                    try:
                        genres_data = json.loads(row['genres'])
                        genres = [genre['name'] for genre in genres_data if isinstance(genre, dict) and 'name' in genre]
                    except (json.JSONDecodeError, TypeError):
                        pass
                # Get poster path
                poster_path = row.get('poster_path', '')
                # Convert genres list to string for database storage
                genres_str = ", ".join(genres) if genres else ""
                # Extract title words using stop words
                titlewords = self.extract_title_words(title)
                # Create movie with TMDB ID
                movie = Movie(
                    id=movie_id,  # Use TMDB ID directly
                    imdb_id=imdb_id,
                    title=title,
                    overview=overview,
                    release_date=release_date,
                    poster_path=poster_path,
                    genres=genres_str,  # Store as string
                    titlewords=titlewords  # Store extracted title words
                )
                db.add(movie)
            except (ValueError, TypeError) as e:
                # Skip rows with invalid data
                continue
        db.commit()
        print(f"Imported {len(movies_df)} movies with TMDB IDs, genres, and title words (and IMDB IDs)")

    def import_credits(self, db: Session, credits_df: pd.DataFrame) -> None:
        """Import credits (actors) into database"""
        print(f"Starting import_credits with {len(credits_df)} rows")
        
        processed_count = 0
        for _, row in credits_df.iterrows():
            try:
                # Parse cast JSON - handle malformed JSON more gracefully
                if pd.isna(row['cast']) or row['cast'] == '':
                    print(f"Skipping row with empty cast: TMDB id {row['id']}")
                    continue
                # Try to parse as JSON, if it fails, skip this row
                try:
                    # Replace single quotes with double quotes for valid JSON
                    cast_str = row['cast'].replace("'", '"')
                    cast_data = json.loads(cast_str)
                except (json.JSONDecodeError, TypeError):
                    print(f"Failed to parse cast JSON for TMDB id {row['id']}")
                    continue
                # Ensure row['id'] is a valid integer
                try:
                    tmdb_id = int(row['id'])
                except (ValueError, TypeError):
                    print(f"Invalid TMDB id: {row['id']}")
                    continue
                
                # Get movie using TMDB ID directly (movies were imported with TMDB IDs)
                movie = db.query(Movie).filter(Movie.id == tmdb_id).first()
                if not movie:
                    print(f"No movie found in DB for TMDB id {tmdb_id}")
                    continue
                print(f"Processing movie '{movie.title}' (TMDB ID: {tmdb_id}) with {len(cast_data)} cast members")
                # Add actors (limit to first 10 to avoid too many)
                for actor_data in cast_data[:10]:
                    if isinstance(actor_data, dict) and 'name' in actor_data:
                        actor_name = actor_data.get('name', '')
                        if actor_name:
                            actor = db.query(Actor).filter(Actor.name == actor_name).first()
                            if not actor:
                                actor = Actor(name=actor_name)
                                db.add(actor)
                                db.flush()
                                print(f"Created actor: {actor_name}")
                            if actor not in movie.actors:
                                movie.actors.append(actor)
                                print(f"Added actor '{actor_name}' to movie '{movie.title}' (ID: {movie.id})")
                processed_count += 1
            except Exception as e:
                print(f"Exception for TMDB id {row.get('id', 'unknown')}: {e}")
                continue
        
        print(f"Processed credits for {processed_count} movies")
        db.commit()  # Commit all new actors and relationships

    def import_ratings(self, db: Session, ratings_df: pd.DataFrame) -> None:
        """Import ratings into database and update movie statistics"""
        # Reset index to avoid duplicate label issues
        ratings_df = ratings_df.reset_index(drop=True)
        
        # Use a set of movie IDs for filtering
        movie_ids = set(m.id for m in db.query(Movie).all())
        valid_ratings = ratings_df[ratings_df['movieId'].isin(movie_ids)]
        
        # Group ratings by movie to calculate statistics
        movie_stats = valid_ratings.groupby('movieId').agg({
            'rating': ['mean', 'count']
        }).reset_index()
        # Flatten columns
        movie_stats.columns = ['movieId', 'rating_mean', 'rating_count']
        
        # Update movie statistics
        for _, row in movie_stats.iterrows():
            movie = db.query(Movie).filter(Movie.id == row['movieId']).first()
            if movie:
                movie.vote_average = row['rating_mean']
                movie.vote_count = int(row['rating_count'])
        
        # Add individual ratings
        for _, row in valid_ratings.iterrows():
            rating = Rating(
                user_id=row['userId'],
                movie_id=row['movieId'],
                rating=row['rating']
            )
            db.add(rating)

    def update_title_words_for_existing_movies(self, db: Session) -> None:
        """Update title words for all existing movies in the database"""
        print("Updating title words for existing movies...")
        
        # Load stop words if not already loaded
        if not self.stopwords:
            self.load_stop_words()
        
        movies = db.query(Movie).all()
        updated_count = 0
        
        for movie in movies:
            if movie.title:
                titlewords = self.extract_title_words(movie.title)
                movie.titlewords = titlewords
                updated_count += 1
        
        db.commit()
        print(f"Updated title words for {updated_count} movies")

    def load_all_data(self, db: Session) -> None:
        """Load all data from the dataset"""
        try:
            # Load stop words first (needed for title word extraction)
            print("Loading stop words...")
            self.load_stop_words()
            
            # Load links for ID mapping
            print("Loading links...")
            self.load_links("links.csv")
            
            # Load movies
            print("Loading movies...")
            movies_df = self.load_movies()
            self.import_movies(db, movies_df)
            
            # Load credits
            print("Loading credits...")
            credits_path = os.path.join(self.data_dir, 'credits.csv')
            if os.path.exists(credits_path):
                credits_df = pd.read_csv(credits_path, low_memory=False)
                self.import_credits(db, credits_df)
            else:
                print("Credits file not found, skipping...")
            
            # Load ratings
            print("Loading ratings...")
            ratings_df = self.load_ratings("ratings_small.csv")
            self.import_ratings(db, ratings_df)
            
            db.commit()
            print("Data loaded successfully with stop words and title words!")
        except Exception as e:
            db.rollback()
            print(f"Error loading data: {e}")
            raise e

def init_database():
    """Initialize the database and load data"""
    # Create database tables
    init_db()
    
    # Load data
    with get_db() as db:
        loader = DataLoader()
        loader.load_all_data(db)

def update_existing_movies():
    """Update title words for existing movies in the database"""
    with get_db() as db:
        loader = DataLoader()
        loader.update_title_words_for_existing_movies(db)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "update":
        print("🔄 Updating title words for existing movies...")
        update_existing_movies()
    else:
        print("🚀 Initializing database and loading all data...")
        init_database() 