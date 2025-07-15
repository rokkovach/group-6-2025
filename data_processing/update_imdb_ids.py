#!/usr/bin/env python3
"""
Update imdb_id for all movies in the database using metadata and links.csv, preserving all other data.
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/..')
import pandas as pd
from models import Movie
from database import get_db

def load_tmdb_metadata(metadata_path):
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}")
    df = pd.read_csv(metadata_path, low_memory=False)
    tmdb_to_imdbid = {}
    for _, row in df.iterrows():
        tmdb_id = str(row['id'])
        imdb_id = row.get('imdb_id', None)
        if pd.notna(imdb_id) and imdb_id != '':
            tmdb_to_imdbid[tmdb_id] = imdb_id
    return tmdb_to_imdbid

def load_links(links_path):
    if not os.path.exists(links_path):
        raise FileNotFoundError(f"Links file not found: {links_path}")
    df = pd.read_csv(links_path)
    tmdb_to_numeric_imdb = dict(zip(df['tmdbId'], df['imdbId']))
    return tmdb_to_numeric_imdb

def update_imdb_ids():
    metadata_path = "ml-latest-small/movies_metadata.csv"
    links_path = "ml-latest-small/links.csv"
    print(f"Loading TMDB metadata from {metadata_path}")
    tmdb_to_imdbid = load_tmdb_metadata(metadata_path)
    print(f"Loading links from {links_path}")
    tmdb_to_numeric_imdb = load_links(links_path)
    print("Updating imdb_id for all movies in the database...")
    updated = 0
    with get_db() as db:
        movies = db.query(Movie).all()
        for movie in movies:
            tmdb_id_str = str(movie.id)
            imdb_id = None
            # 1. Prefer imdb_id from metadata
            if tmdb_id_str in tmdb_to_imdbid:
                imdb_id = tmdb_to_imdbid[tmdb_id_str]
            # 2. Fallback: use numeric imdbId from links.csv and convert to tt format
            if (not imdb_id or imdb_id == '' or pd.isna(imdb_id)) and movie.id in tmdb_to_numeric_imdb:
                numeric_imdb = tmdb_to_numeric_imdb[movie.id]
                if pd.notna(numeric_imdb):
                    imdb_id = f"tt{int(numeric_imdb):07d}"
            if imdb_id == '' or pd.isna(imdb_id):
                imdb_id = None
            if movie.imdb_id != imdb_id:
                movie.imdb_id = imdb_id
                updated += 1
        db.commit()
    print(f"✅ Updated imdb_id for {updated} movies.")

if __name__ == "__main__":
    update_imdb_ids() 