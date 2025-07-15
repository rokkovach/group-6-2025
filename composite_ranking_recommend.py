from sqlalchemy.orm import joinedload
from models import Movie
from gensim.utils import simple_preprocess
from collections import defaultdict
import numpy as np

def preprocess(text):
    return simple_preprocess(text, deacc=True) if text else []

def parse_set(attr_val):
    if isinstance(attr_val, str):
        return set(s.strip().lower() for s in attr_val.split(","))
    elif isinstance(attr_val, list):
        return set(str(s).strip().lower() for s in attr_val)
    else:
        return set()

def recommend(movie_id, limit, db):
    print("\n>>> COMPOSITE RANKINGS FUNCTION CALLED <<<")

    base_movie = (
        db.query(Movie)
        .options(joinedload(Movie.genres_rel))  # Load genres to avoid N+1 queries
        .filter(Movie.id == movie_id)
        .first()
    )

    if not base_movie:
        print(f"[ERROR] Movie ID {movie_id} not found.")
        return []

    print(f"[COMPOSITE] Selected Movie: {base_movie.title}\n")

    # Use genres_rel relationship instead of empty genres column
    base_genres = set(genre.name.lower() for genre in base_movie.genres_rel) if base_movie.genres_rel else set()
    base_actors = parse_set(base_movie.actors)
    base_rating = base_movie.vote_average or 0.0
    base_votes = base_movie.vote_count or 0
    base_titlewords = parse_set(base_movie.titlewords)
    base_overview_tokens = set(preprocess(base_movie.overview))

    candidates = (
        db.query(Movie)
        .options(joinedload(Movie.genres_rel))  # Load genres to avoid N+1 queries
        .filter(Movie.id != movie_id)
        .limit(45000)
        .all()
    )

    scored_candidates = []

    for candidate in candidates:
        # Use genres_rel relationship instead of empty genres column
        cand_genres = set(genre.name.lower() for genre in candidate.genres_rel) if candidate.genres_rel else set()
        cand_actors = parse_set(candidate.actors)
        cand_rating = candidate.vote_average or 0.0
        cand_votes = candidate.vote_count or 0
        cand_titlewords = parse_set(candidate.titlewords)
        cand_overview_tokens = set(preprocess(candidate.overview))

        genre_score = len(base_genres & cand_genres)
        actor_score = len(base_actors & cand_actors)
        rating_diff = abs(base_rating - cand_rating)
        votes_diff = abs(base_votes - cand_votes)

        rating_score = 1 / (1 + rating_diff)
        votes_score = 1 / (1 + (votes_diff / 1000))

        overview_overlap = len(base_overview_tokens & cand_overview_tokens)
        titleword_overlap = len(base_titlewords & cand_titlewords)

        score = (
            genre_score * 2 +
            actor_score * 3 +
            rating_score * 2 +
            votes_score * 1.5 +
            overview_overlap * 1 +
            titleword_overlap * 1.5
        )

        scored_candidates.append((candidate, score, {
            "genre_overlap": genre_score,
            "actor_overlap": actor_score,
            "rating_score": round(rating_score, 2),
            "votes_score": round(votes_score, 2),
            "overview_overlap": overview_overlap,
            "titleword_overlap": titleword_overlap
        }))

    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    top_recommendations = scored_candidates[:limit]

    print(">>> Top Recommendations:\n")
    for movie, score, details in top_recommendations:
        print(f"- {movie.title} (Score: {score:.2f})")
        print(f"  • Genre overlap: {details['genre_overlap']}")
        print(f"  • Actor overlap: {details['actor_overlap']}")
        print(f"  • Rating similarity score: {details['rating_score']}")
        print(f"  • Vote count similarity score: {details['votes_score']}")
        print(f"  • Overview word overlap: {details['overview_overlap']}")
        print(f"  • Titleword overlap: {details['titleword_overlap']}\n")

    return [movie for movie, _, _ in top_recommendations]
