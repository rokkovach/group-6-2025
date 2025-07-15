#!/usr/bin/env python3
"""
Batch download movie posters to improve performance
"""

import os
import sys
sys.path.append('..')

from movie_service import get_movie_poster_url, TMDB_IMAGE_BASE_URL
from models import Movie
from database import get_db
import requests
from PIL import Image
from io import BytesIO
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def download_poster(movie):
    """Download poster for a single movie"""
    try:
        if not movie.poster_path:
            print(f"⚠️  No poster path for movie {movie.id}: {movie.title}")
            return False
        
        # Check if already exists
        local_path = f"../static/posters/{movie.id}.jpg"
        if os.path.exists(local_path):
            print(f"✅ Poster already exists for movie {movie.id}: {movie.title}")
            return True
        
        # Download poster
        poster_url = f"{TMDB_IMAGE_BASE_URL}{movie.poster_path}"
        response = requests.get(poster_url, timeout=10)
        
        if response.status_code == 200:
            # Save the image
            img = Image.open(BytesIO(response.content))
            img.save(local_path, "JPEG", quality=85)
            print(f"✅ Downloaded poster for movie {movie.id}: {movie.title}")
            return True
        else:
            print(f"❌ Failed to download poster for movie {movie.id}: {movie.title} (HTTP {response.status_code})")
            return False
            
    except Exception as e:
        print(f"❌ Error downloading poster for movie {movie.id}: {movie.title} - {e}")
        return False

def batch_download_posters(limit=100, max_workers=5):
    """Batch download posters for popular movies"""
    print(f"🚀 Starting batch poster download (limit={limit}, max_workers={max_workers})")
    
    # Ensure static/posters directory exists
    os.makedirs("../static/posters", exist_ok=True)
    
    # Get movies with posters, ordered by popularity (vote_count)
    with get_db() as db:
        movies = db.query(Movie).filter(
            Movie.poster_path.isnot(None),
            Movie.poster_path != ""
        ).order_by(Movie.vote_count.desc()).limit(limit).all()
    
    print(f"📋 Found {len(movies)} movies with poster paths")
    
    # Download posters in parallel
    successful = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all download tasks
        future_to_movie = {executor.submit(download_poster, movie): movie for movie in movies}
        
        # Process completed downloads
        for future in as_completed(future_to_movie):
            movie = future_to_movie[future]
            try:
                result = future.result()
                if result:
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"❌ Exception for movie {movie.id}: {e}")
                failed += 1
    
    print(f"\n📊 Download Summary:")
    print(f"  ✅ Successful: {successful}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📁 Total: {successful + failed}")
    
    return successful, failed

def download_popular_posters():
    """Download posters for the most popular movies"""
    print("🎬 Downloading posters for popular movies...")
    return batch_download_posters(limit=500, max_workers=10)

def download_all_posters():
    """Download posters for all movies with poster paths"""
    print("🎬 Downloading posters for all movies...")
    
    with get_db() as db:
        total_movies = db.query(Movie).filter(
            Movie.poster_path.isnot(None),
            Movie.poster_path != ""
        ).count()
    
    print(f"📋 Total movies with poster paths: {total_movies}")
    
    # Download in batches to avoid memory issues
    batch_size = 1000
    total_successful = 0
    total_failed = 0
    
    for i in range(0, total_movies, batch_size):
        print(f"\n📦 Processing batch {i//batch_size + 1} ({i+1}-{min(i+batch_size, total_movies)})")
        successful, failed = batch_download_posters(limit=batch_size, max_workers=5)
        total_successful += successful
        total_failed += failed
        time.sleep(1)  # Small delay between batches
    
    print(f"\n🎉 Final Summary:")
    print(f"  ✅ Total Successful: {total_successful}")
    print(f"  ❌ Total Failed: {total_failed}")
    print(f"  📁 Total Processed: {total_successful + total_failed}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Download movie posters")
    parser.add_argument("--mode", choices=["popular", "all", "test"], default="popular",
                       help="Download mode: popular (500 movies), all (all movies), test (10 movies)")
    parser.add_argument("--limit", type=int, default=500,
                       help="Number of movies to download (for popular mode)")
    parser.add_argument("--workers", type=int, default=10,
                       help="Number of parallel workers")
    
    args = parser.parse_args()
    
    if args.mode == "popular":
        batch_download_posters(limit=args.limit, max_workers=args.workers)
    elif args.mode == "all":
        download_all_posters()
    elif args.mode == "test":
        batch_download_posters(limit=10, max_workers=2) 
