#!/usr/bin/env python3
"""
Script to generate OpenAI embeddings for movies based on title, release_date, and overview
"""

import json
import os
import time
import requests
from datetime import datetime, timedelta
from database import get_db
from models import Movie
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("OPENAI_API_KEY loaded:", os.getenv("OPENAI_API_KEY"))

def create_movie_text(movie):
    """Create text for embedding from movie data"""
    text_parts = []
    
    # Add title
    if movie.title:
        text_parts.append(f"Title: {movie.title}")
    
    # Add release date
    if movie.release_date:
        text_parts.append(f"Release Date: {movie.release_date}")
    
    # Add overview
    if movie.overview:
        text_parts.append(f"Overview: {movie.overview}")
    
    return " | ".join(text_parts)

def get_embedding(text, model="text-embedding-3-small"):
    """Get embedding from OpenAI API using requests"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment variables!")
        return None
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "input": text,
        "model": model
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result["data"][0]["embedding"]
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return None

def get_embeddings_bulk(texts, model="text-embedding-3-small"):
    """Get embeddings for multiple texts in one API call"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment variables!")
        return None
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "input": texts,
        "model": model
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return [item["embedding"] for item in result["data"]]
    except Exception as e:
        print(f"Error getting bulk embeddings: {e}")
        return None

def format_time_estimate(seconds):
    """Format time estimate in a human-readable way"""
    if seconds < 60:
        return f"{seconds:.0f} seconds"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f} minutes"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} hours"

def generate_embeddings_for_movies():
    """Generate embeddings for all movies in bulk batches"""
    start_time = time.time()
    print("🚀 Starting bulk embedding generation...")
    print(f"⏰ Started at: {datetime.now().strftime('%H:%M:%S')}")
    
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not found in environment variables!")
        print("Please add your OpenAI API key to .env file:")
        print("OPENAI_API_KEY=your_api_key_here")
        return
    
    with get_db() as db:
        # Get all movies without embeddings
        movies = db.query(Movie).filter(
            Movie.embedding_vector.is_(None)
        ).all()
        
        print(f"📊 Found {len(movies)} movies to process")
        
        if len(movies) == 0:
            print("✅ All movies already have embeddings!")
            return
        
        # Process in batches of 100 (OpenAI allows up to 2048 per request)
        batch_size = 100
        processed_count = 0
        error_count = 0
        
        # Calculate time estimates
        total_batches = (len(movies) + batch_size - 1) // batch_size
        estimated_seconds_per_batch = 2.0  # API call + processing time
        total_estimated_seconds = total_batches * estimated_seconds_per_batch
        estimated_completion = datetime.now() + timedelta(seconds=total_estimated_seconds)
        
        print(f"📈 Estimated time: {format_time_estimate(total_estimated_seconds)}")
        print(f"⏰ Estimated completion: {estimated_completion.strftime('%H:%M:%S')}")
        print(f"🔄 Processing {total_batches} batches of {batch_size} movies each")
        print("-" * 50)
        
        for i in range(0, len(movies), batch_size):
            batch_start_time = time.time()
            batch = movies[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            print(f"🔄 Processing batch {batch_num}/{total_batches} ({len(batch)} movies)...")
            
            # Prepare texts for this batch
            batch_texts = []
            batch_movies = []
            
            for movie in batch:
                movie_text = create_movie_text(movie)
                if movie_text.strip():
                    batch_texts.append(movie_text)
                    batch_movies.append(movie)
                else:
                    print(f"⚠️ Skipping movie {movie.id} ({movie.title}) - no text to embed")
            
            if not batch_texts:
                print(f"⚠️ No valid texts in batch {batch_num}")
                continue
            
            # Get embeddings for the batch
            embeddings = get_embeddings_bulk(batch_texts)
            
            if embeddings and len(embeddings) == len(batch_movies):
                # Save embeddings to database
                for movie, embedding in zip(batch_movies, embeddings):
                    movie.embedding_vector = json.dumps(embedding)
                    processed_count += 1
                
                # Commit the batch
                db.commit()
                
                # Calculate progress and time estimates
                batch_time = time.time() - batch_start_time
                elapsed_time = time.time() - start_time
                remaining_batches = total_batches - batch_num
                avg_time_per_batch = elapsed_time / batch_num
                estimated_remaining = remaining_batches * avg_time_per_batch
                estimated_total = elapsed_time + estimated_remaining
                current_completion = datetime.now() + timedelta(seconds=estimated_remaining)
                
                print(f"✅ Batch {batch_num} completed in {batch_time:.1f}s")
                print(f"📊 Progress: {processed_count}/{len(movies)} movies ({processed_count/len(movies)*100:.1f}%)")
                print(f"⏱️ Elapsed: {format_time_estimate(elapsed_time)} | Remaining: {format_time_estimate(estimated_remaining)}")
                print(f"⏰ Updated completion: {current_completion.strftime('%H:%M:%S')}")
            else:
                error_count += len(batch_movies)
                print(f"❌ Failed to get embeddings for batch {batch_num}")
            
            # Rate limiting - small delay between batches
            time.sleep(0.5)
        
        # Final summary
        total_time = time.time() - start_time
        print("-" * 50)
        print(f"🎉 Bulk embedding generation complete!")
        print(f"⏱️ Total time: {format_time_estimate(total_time)}")
        print(f"✅ Successfully processed: {processed_count} movies")
        print(f"❌ Errors: {error_count} movies")
        
        # Final verification
        total_embeddings = db.query(Movie).filter(
            Movie.embedding_vector.isnot(None)
        ).count()
        total_movies = db.query(Movie).count()
        print(f"📊 Total movies with embeddings: {total_embeddings}/{total_movies}")

def test_embedding():
    """Test embedding generation with a single movie"""
    print("🧪 Testing embedding generation...")
    
    with get_db() as db:
        # Get a sample movie
        movie = db.query(Movie).first()
        if not movie:
            print("❌ No movies found in database")
            return
        
        print(f"Testing with movie: {movie.title}")
        
        # Create text
        movie_text = create_movie_text(movie)
        print(f"Text for embedding: {movie_text[:200]}...")
        
        # Test both single and bulk approaches
        print("\n--- Testing single embedding ---")
        embedding = get_embedding(movie_text)
        if embedding:
            print(f"✅ Single embedding generated successfully! Length: {len(embedding)}")
            print(f"First 5 values: {embedding[:5]}")
        else:
            print("❌ Failed to generate single embedding")
        
        print("\n--- Testing bulk embedding ---")
        embeddings = get_embeddings_bulk([movie_text])
        if embeddings and len(embeddings) == 1:
            print(f"✅ Bulk embedding generated successfully! Length: {len(embeddings[0])}")
            print(f"First 5 values: {embeddings[0][:5]}")
        else:
            print("❌ Failed to generate bulk embedding")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_embedding()
    else:
        generate_embeddings_for_movies() 