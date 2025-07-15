import time
from sqlalchemy.orm import joinedload
from models import Movie
from database import get_db

from gensim.corpora import Dictionary
from gensim.models import TfidfModel
from gensim.similarities import MatrixSimilarity
from gensim.utils import simple_preprocess
import numpy as np

# Global storage
corpus = []
movie_ids = []
dictionary = None
tfidf_model = None
similarity_index = None


def preprocess(text):
    return simple_preprocess(text, deacc=True)


def initialize_vectors(db):
    global corpus, movie_ids, dictionary, tfidf_model, similarity_index

    print("Initializing overview vectors...")
    movies = db.query(Movie)\
        .filter(Movie.overview.isnot(None), Movie.overview != "")\
        .limit(40000)\
        .all()

    if not movies:
        print("No movies with overviews found.")
        return

    documents = [preprocess(movie.overview) for movie in movies]
    movie_ids[:] = [movie.id for movie in movies]

    dictionary = Dictionary(documents)
    bow_corpus = [dictionary.doc2bow(doc) for doc in documents]
    tfidf_model = TfidfModel(bow_corpus)
    tfidf_corpus = tfidf_model[bow_corpus]

    similarity_index = MatrixSimilarity(tfidf_corpus, num_features=len(dictionary))
    corpus[:] = tfidf_corpus

    print("Overview vector initialization complete.")


def get_movie_by_id(movie_id, db):
    return (
        db.query(Movie)
        .options(joinedload(Movie.genres_rel))
        .filter(Movie.id == movie_id)
        .first()
    )
def recommend(movie_id: int, limit: int, db):
    global dictionary, tfidf_model, similarity_index, movie_ids

    if similarity_index is None:
        initialize_vectors(db)

    base_movie = get_movie_by_id(movie_id, db)
    if not base_movie or not base_movie.overview:
        print(f"Movie with ID {movie_id} not found or missing overview.")
        return []

    print(f"\nSelected Movie: {base_movie.title}\n")
    print(f"Overview: {base_movie.overview}\n")

    total_start_time = time.time()

    query_bow = dictionary.doc2bow(preprocess(base_movie.overview))
    query_tfidf = tfidf_model[query_bow]

    sims = similarity_index[query_tfidf]
    ranked_indices = np.argsort(sims)[::-1]

    recommended_ids = []
    for idx in ranked_indices:
        candidate_id = movie_ids[idx]
        if candidate_id != movie_id:
            recommended_ids.append(candidate_id)
        if len(recommended_ids) >= limit:
            break

    if not recommended_ids:
        print("No recommendations found.")
        return []

    # Fetch all recommended movies at once
    fetch_start = time.time()
    recommendations = (
        db.query(Movie)
        .filter(Movie.id.in_(recommended_ids))
        .options(joinedload(Movie.genres_rel))
        .all()
    )
    fetch_end = time.time()

    id_to_movie = {movie.id: movie for movie in recommendations}
    sorted_recommendations = []

    print("\nRecommended Movies:")
    for rid in recommended_ids:
        start = time.time()
        movie = id_to_movie.get(rid)
        end = time.time()
        if movie:
            sorted_recommendations.append(movie)
            print(f"- {movie.title} (Fetched in {end - start:.4f} sec)")
            print(f"  Overview: {movie.overview}\n")

    total_time = time.time() - total_start_time
    print(f"[INFO] Total recommendation generation time: {total_time:.4f} seconds")
    print(f"[INFO] Time spent on DB fetch for top movies: {fetch_end - fetch_start:.4f} seconds")

    return sorted_recommendations


def main():
    try:
        movie_id = int(input("Enter movie ID: "))
    except ValueError:
        print("Invalid input. Please enter a numeric movie ID.")
        return

    try:
        with get_db() as db:
            recommend(movie_id, limit=10, db=db)
    except Exception as e:
        print(f"Failed to recommend movies: {e}")


if __name__ == "__main__":
    main()
