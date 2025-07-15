import json
from models import Movie
from database import get_db

def get_movie_by_id(movie_id, db):
        return db.query(Movie).filter(Movie.id == movie_id).first()


def get_all_movies_except(exclude_id, db):
        return db.query(Movie).filter(
            Movie.id != exclude_id,
            Movie.titlewords.isnot(None),
            Movie.titlewords != '[]',
            Movie.titlewords != ''
        ).all()


def recommend_movies_by_titles(base_movie, candidate_movies, limit: int = 5):
    try:
        base_titlewords = set(json.loads(base_movie.titlewords))
        if not base_titlewords:
            print("The movie has no titlewords.")
            return []
    except Exception as e:
        print(f"Failed to fetch titlewords for the movie: {e}")
        return []

    recommendations = []
    for movie in candidate_movies:
        try:
            other_titlewords = set(json.loads(movie.titlewords))
            if not other_titlewords:
                continue
        except Exception:
            continue

        overlap = base_titlewords & other_titlewords
        if overlap:
            recommendations.append((len(overlap), movie, overlap))

    if not recommendations:
        print("No recommendations based on titleword overlap.")

    return sorted(recommendations, key=lambda x: x[0], reverse=True)[:limit]





def recommend(movie_id: int, limit: int, db):

        base_movie = get_movie_by_id(movie_id, db)
        if not base_movie:
            print(f" Movie with ID {movie_id} not found.")
            return

        print(f"\n Selected Movie: {base_movie.title}\n")

        candidates = get_all_movies_except(movie_id, db)
        if not candidates:
            print("No candidate movies found in the database.")
            return

        recommendations = recommend_movies_by_titles(base_movie, candidates, limit)
    
        if not recommendations:
            print("No recommendations found.")
            return []

        for count, movie, overlap in recommendations:
            print(f"{movie.title} ----> Common titlewords ({count}): {', '.join(overlap)}")

        # take only movies from the tuple, save the sorting
        rec_movies = [rec[1] for rec in recommendations]

        return rec_movies if rec_movies else []






def main():
    try:
        movie_id = int(input("Enter movie ID: "))
    except ValueError:
        print("Invalid input. Please enter a numeric movie ID.")
        return

    try:
        with get_db() as db:
            limit = 10
            recommend(movie_id, limit, db)
    except Exception as e:
        print(f"Failed to recommend by Title Overlap: {e}")


if __name__ == "__main__":
    main()