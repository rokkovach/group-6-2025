from models import Movie
from database import get_db
from sqlalchemy import or_, func
import requests
import os
from PIL import Image
from io import BytesIO
from rapidfuzz import process, fuzz
import random
import title_overlap_recommend, genre_similarity_recommend, overview_similarity_recommend, composite_ranking_recommend, embedding_similarity_recommend
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

def _get_movie_titles():
    """Get cached movie titles for fuzzy search"""
    with get_db() as db:
        movies = db.query(Movie.id, Movie.title).all()
        # Filter out None titles to prevent errors
        return [(m.id, m.title) for m in movies if m.title is not None]

def _get_cached_recommendations(section_name: str, film_id, limit: int = 6):
    """Get recommendations for a section without caching"""
    with get_db() as db:
        if section_name == "random":
            # Simple random selection - no complex filtering
            random_movies = db.query(Movie).order_by(func.random()).limit(limit).all()
                
        elif section_name == "algo1":
            # Algorithm 1: High-rated movies (simplified)
            random_movies = overview_similarity_recommend.recommend(film_id, limit, db)
            
        elif section_name == "algo2":
            # Algorithm 2: Recent movies (by ID) - simplified
            random_movies = composite_ranking_recommend.recommend(film_id, limit, db)

        elif section_name == "algo3":
            # Algorithm 3: Title overlap
            random_movies = title_overlap_recommend.recommend(film_id, limit, db) #sorted

        elif section_name == "algo4":
        # Algorithm 4: Genre similarity
            random_movies = genre_similarity_recommend.recommend(film_id, limit, db)  # sorted

        elif section_name == "algo5":
            # Algorithm 5: Embedding similarity
            recommendations = embedding_similarity_recommend.get_embedding_based_recommendations(film_id, limit)
            if recommendations:
                # Convert recommendations to Movie objects for consistency
                movie_ids = [rec['id'] for rec in recommendations]
                random_movies = db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
                # Sort to match the recommendation order
                id_to_movie = {movie.id: movie for movie in random_movies}
                random_movies = [id_to_movie[movie_id] for movie_id in movie_ids if movie_id in id_to_movie]
            else:
                random_movies = []

        else:
            # Default to random
            random_movies = db.query(Movie).order_by(func.random()).limit(limit).all()

        #if no recommendations
        if not random_movies:
            return []

        # Process movies and add poster URLs
        results = []
        for movie in random_movies:
            movie_dict = movie.to_dict()
            movie_dict['poster_url'] = get_movie_poster_url(movie.id, movie.poster_path)
            results.append(movie_dict)
        
        return results

def get_recommendation_section(section_name: str, film_id: int = 158, limit: int = 6):
    """Get movies for different recommendation sections - no caching."""
    return _get_cached_recommendations(section_name, film_id, limit)

def get_movie_poster_url(movie_id, poster_path):
    """Get the poster URL for a movie, using TMDB API with IMDB ID as primary approach."""
    # Ensure static/posters directory exists
    os.makedirs("static/posters", exist_ok=True)
    
    # Check if we already have the poster locally
    local_path = f"static/posters/{movie_id}.jpg"
    if os.path.exists(local_path):
        return f"/static/posters/{movie_id}.jpg"
    
    # Strategy 1: Try TMDB API with IMDB ID (primary approach)
    if TMDB_API_KEY:
        try:
            # Get movie from database to access IMDB ID
            with get_db() as db:
                movie = db.query(Movie).filter(Movie.id == movie_id).first()
                if movie and movie.imdb_id:
                    url = f"https://api.themoviedb.org/3/find/{movie.imdb_id}?api_key={TMDB_API_KEY}&external_source=imdb_id"
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        results = data.get("movie_results", [])
                        if results:
                            poster_path_from_api = results[0].get("poster_path")
                            if poster_path_from_api:
                                poster_url = f"{TMDB_IMAGE_BASE_URL}{poster_path_from_api}"
                                img_response = requests.get(poster_url, timeout=10)
                                if img_response.status_code == 200:
                                    # Save the image
                                    img = Image.open(BytesIO(img_response.content))
                                    img.save(local_path, "JPEG", quality=85)
                                    return f"/static/posters/{movie_id}.jpg"
                                else:
                                    print(f"❌ Failed to download poster via TMDB API for movie {movie_id}: HTTP {img_response.status_code}")
                            else:
                                print(f"❌ No poster path found in TMDB API response for movie {movie_id}")
                        else:
                            print(f"❌ No movie results found in TMDB API for movie {movie_id}")
                    else:
                        print(f"❌ TMDB API request failed for movie {movie_id}: HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ Error using TMDB API for movie {movie_id}: {e}")
    
    # Strategy 2: Fallback to existing poster_path
    if poster_path:
        try:
            poster_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"
            response = requests.get(poster_url, timeout=10)
            if response.status_code == 200:
                # Save the image
                img = Image.open(BytesIO(response.content))
                img.save(local_path, "JPEG", quality=85)
                return f"/static/posters/{movie_id}.jpg"
            else:
                print(f"❌ Failed to download poster via fallback for movie {movie_id}: HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ Error downloading poster via fallback for movie {movie_id}: {e}")
    
    # Final fallback to default poster
    return "/static/posters/default.jpg"

def _get_cached_search_results(query: str, limit: int, page: int):
    """Get search results without caching"""
    offset = (page - 1) * limit
    
    with get_db() as db:
        if not query:
            # Simple random selection for landing page
            random_movies = db.query(Movie).order_by(func.random()).limit(limit).all()
            
            results = []
            for movie in random_movies:
                movie_dict = movie.to_dict()
                movie_dict['poster_url'] = get_movie_poster_url(movie.id, movie.poster_path)
                results.append(movie_dict)
            return results
        else:
            # Simplified search: exact + fuzzy matching only
            
            # Strategy 1: Exact title matches (case-insensitive)
            exact_matches = db.query(Movie).filter(
                Movie.title.ilike(f"%{query}%")
            ).all()
            
            # Strategy 2: Fuzzy search on titles (case-insensitive)
            movie_titles = _get_movie_titles()
            titles = [title for _, title in movie_titles if title is not None]  # Filter out None values
            
            # Use case-insensitive fuzzy search
            fuzzy_matches = process.extract(query.lower(), [title.lower() for title in titles], scorer=fuzz.WRatio, limit=30)
            fuzzy_titles = [titles[match[2]] for match in fuzzy_matches if match[1] > 50]
            
            # Combine results with simple deduplication
            all_movies = {}
            
            # Add exact matches first (highest priority)
            for movie in exact_matches:
                all_movies[movie.id] = {'movie': movie, 'score': 100, 'type': 'exact'}
            
            # Add fuzzy matches (avoid duplicates)
            for title in fuzzy_titles:
                movie = db.query(Movie).filter(Movie.title == title).first()
                if movie and movie.id not in all_movies:
                    # Find the fuzzy match score
                    for match in fuzzy_matches:
                        if titles[match[2]] == title:
                            all_movies[movie.id] = {'movie': movie, 'score': match[1], 'type': 'fuzzy'}
                            break
            
            # Sort by score (highest first) and then by title
            sorted_movies = sorted(
                all_movies.values(), 
                key=lambda x: (-x['score'], x['movie'].title.lower())
            )
            
            # Apply pagination
            paginated_movies = sorted_movies[offset:offset + limit]
            
            # Return results
            results = []
            for item in paginated_movies:
                movie = item['movie']
                movie_dict = movie.to_dict()
                movie_dict['poster_url'] = get_movie_poster_url(movie.id, movie.poster_path)
                movie_dict['search_score'] = item['score']
                movie_dict['search_type'] = item['type']
                results.append(movie_dict)
            return results

def search_movies(query: str, limit: int = 20, page: int = 1):
    """Simplified search with case-insensitive fuzzy and exact matching - no caching"""
    return _get_cached_search_results(query, limit, page)

def get_total_movies_count(query: str = ""):
    """Get total count of movies for pagination - simplified."""
    with get_db() as db:
        if not query:
            # Simple count for landing page
            count = db.query(Movie).count()
            return count
        else:
            # Simplified count: exact + fuzzy matches only
            movie_ids = set()
            
            # Exact title matches
            exact_matches = db.query(Movie.id).filter(
                Movie.title.ilike(f"%{query}%")
            ).all()
            movie_ids.update([m.id for m in exact_matches])
            
            # Fuzzy search matches (case-insensitive)
            movie_titles = _get_movie_titles()
            titles = [title for _, title in movie_titles if title is not None]  # Filter out None values
            fuzzy_matches = process.extract(query.lower(), [title.lower() for title in titles], scorer=fuzz.WRatio, limit=100)
            fuzzy_titles = [titles[match[2]] for match in fuzzy_matches if match[1] > 50]
            
            for title in fuzzy_titles:
                movie = db.query(Movie.id).filter(Movie.title == title).first()
                if movie:
                    movie_ids.add(movie.id)
            
            count = len(movie_ids)
            return count

def get_movie_by_id(movie_id: int):
    """Get a movie by its ID."""
    with get_db() as db:
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if movie:
            movie_dict = movie.to_dict()
            movie_dict['poster_url'] = get_movie_poster_url(movie.id, movie.poster_path)
            return movie_dict
        else:
            print(f"❌ Movie with ID {movie_id} not found")
            return None

def get_similar_movies(movie_id: int, limit: int = 6):
    """Get similar movies based on multiple criteria - optimized for missing genres."""
    with get_db() as db:
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            return []
        
        # Try to find similar movies using multiple criteria
        similar_movies = []
        
        # First try: movies with similar vote average (within 1.0 range)
        if movie.vote_average:
            similar_movies = db.query(Movie).filter(
                Movie.id != movie_id,
                Movie.vote_average.between(movie.vote_average - 1.0, movie.vote_average + 1.0)
            ).order_by(func.random()).limit(limit).all()
        
        # Second try: if no results, get random movies with similar vote count
        if not similar_movies and movie.vote_count:
            similar_movies = db.query(Movie).filter(
                Movie.id != movie_id,
                Movie.vote_count >= movie.vote_count * 0.5
            ).order_by(func.random()).limit(limit).all()
        
        # Third try: if still no results, get random movies
        if not similar_movies:
            similar_movies = db.query(Movie).filter(
                Movie.id != movie_id
            ).order_by(func.random()).limit(limit).all()
        
        # Add poster URLs to the results
        results = []
        for movie in similar_movies:
            movie_dict = movie.to_dict()
            movie_dict['poster_url'] = get_movie_poster_url(movie.id, movie.poster_path)
            results.append(movie_dict)
        
        return results 