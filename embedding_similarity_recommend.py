#!/usr/bin/env python3
"""
Embedding-based movie recommendation using cosine similarity - OPTIMIZED
"""

import json
import numpy as np
from database import get_db
from models import Movie

def cosine_similarity_embeddings(vec1, vec2):
    """Calculate cosine similarity between two vectors using NumPy"""
    try:
        # Convert to numpy arrays if they're not already
        vec1 = np.array(vec1, dtype=np.float64)
        vec2 = np.array(vec2, dtype=np.float64)
        
        # Calculate cosine similarity: dot product / (norm1 * norm2)
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        # Avoid division by zero
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        return float(similarity)
    except Exception as e:
        print(f"Error calculating cosine similarity: {e}")
        return 0.0

def cosine_similarity_matrix(base_embedding, all_embeddings):
    """
    Calculate cosine similarity between base embedding and all other embeddings at once
    This is much faster than pairwise comparisons
    """
    try:
        # Convert to numpy arrays
        base_vec = np.array(base_embedding, dtype=np.float64)
        all_vecs = np.array(all_embeddings, dtype=np.float64)
        
        # Normalize all vectors for efficient cosine similarity
        base_norm = np.linalg.norm(base_vec)
        if base_norm == 0:
            return np.zeros(len(all_embeddings))
        
        # Normalize base vector
        base_vec_normalized = base_vec / base_norm
        
        # Compute norms for all other vectors
        all_norms = np.linalg.norm(all_vecs, axis=1)
        
        # Avoid division by zero
        valid_indices = all_norms > 0
        similarities = np.zeros(len(all_embeddings))
        
        if np.any(valid_indices):
            # Normalize valid vectors
            all_vecs_normalized = all_vecs[valid_indices] / all_norms[valid_indices, np.newaxis]
            
            # Compute cosine similarities (dot product of normalized vectors)
            similarities[valid_indices] = np.dot(all_vecs_normalized, base_vec_normalized)
        
        return similarities
        
    except Exception as e:
        print(f"Error in vectorized cosine similarity: {e}")
        return np.zeros(len(all_embeddings))

def get_embedding_based_recommendations(movie_id, num_recommendations=4):
    """
    Get movie recommendations based on embedding similarity - OPTIMIZED VERSION
    
    Args:
        movie_id: ID of the base movie
        num_recommendations: Number of recommendations to return
    
    Returns:
        List of recommended movies with similarity scores
    """
    with get_db() as db:
        # Get the base movie
        base_movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not base_movie:
            print(f"❌ Movie with ID {movie_id} not found")
            return []
        
        # Check if base movie has embedding
        if not base_movie.embedding_vector:
            print(f"❌ Movie '{base_movie.title}' has no embedding vector")
            return []
        
        try:
            # Parse the base movie's embedding
            base_embedding = json.loads(base_movie.embedding_vector)
        except Exception as e:
            print(f"❌ Error parsing embedding for movie '{base_movie.title}': {e}")
            return []
        
        print(f"🎯 Finding similar movies to: {base_movie.title}")
        print(f"📊 Base movie embedding length: {len(base_embedding)}")
        
        # Get all movies with embeddings (excluding the base movie)
        movies_with_embeddings = db.query(Movie).filter(
            Movie.embedding_vector.isnot(None),
            Movie.id != movie_id
        ).all()
        
        print(f"📊 Found {len(movies_with_embeddings)} movies with embeddings to compare")
        
        if len(movies_with_embeddings) == 0:
            print("❌ No other movies with embeddings found")
            return []
        
        # OPTIMIZATION: Parse all embeddings at once
        print("🔄 Parsing all embeddings...")
        all_embeddings = []
        valid_movies = []
        
        for movie in movies_with_embeddings:
            try:
                movie_embedding = json.loads(movie.embedding_vector)
                all_embeddings.append(movie_embedding)
                valid_movies.append(movie)
            except Exception as e:
                print(f"⚠️ Error parsing embedding for movie '{movie.title}': {e}")
                continue
        
        if not all_embeddings:
            print("❌ No valid embeddings found")
            return []
        
        print(f"✅ Parsed {len(all_embeddings)} valid embeddings")
        
        # OPTIMIZATION: Calculate all similarities at once using vectorized operations
        print("⚡ Computing similarities using vectorized operations...")
        similarities = cosine_similarity_matrix(base_embedding, all_embeddings)
        
        # Create list of (movie, similarity) tuples
        movie_similarities = list(zip(valid_movies, similarities))
        
        # Sort by similarity (highest first)
        movie_similarities.sort(key=lambda x: x[1], reverse=True)
        
        # Get top recommendations
        recommendations = []
        for i, (movie, similarity) in enumerate(movie_similarities[:num_recommendations]):
            recommendations.append({
                'id': movie.id,
                'title': movie.title,
                'similarity_score': similarity,
                'genres': movie.genres if movie.genres else "",
                'overview': movie.overview if movie.overview else "",
                'release_date': movie.release_date if movie.release_date else "",
                'vote_average': movie.vote_average,
                'poster_path': movie.poster_path
            })
            
            print(f"🎬 {i+1}. {movie.title} (Similarity: {similarity:.4f})")
        
        return recommendations

def test_embedding_similarity():
    """Test the embedding similarity algorithm"""
    print("🧪 Testing embedding similarity algorithm...")
    
    with get_db() as db:
        # Find a movie with embedding
        movie_with_embedding = db.query(Movie).filter(
            Movie.embedding_vector.isnot(None)
        ).first()
        
        if not movie_with_embedding:
            print("❌ No movies with embeddings found in database")
            return
        
        print(f"Testing with movie: {movie_with_embedding.title}")
        
        # Get recommendations
        recommendations = get_embedding_based_recommendations(
            movie_with_embedding.id, 
            num_recommendations=3
        )
        
        if recommendations:
            print(f"✅ Found {len(recommendations)} recommendations")
        else:
            print("❌ No recommendations found")

if __name__ == "__main__":
    test_embedding_similarity() 