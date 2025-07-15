from sqlalchemy import func
from sqlalchemy.orm import joinedload
from models import Movie, Genre
from database import get_db


def get_movie_by_id(movie_id, db):
    return (db.query(Movie).
            options(joinedload(Movie.genres_rel)). #to load not one by one record but together in same JOIN
            filter(Movie.id == movie_id)
            .first())


def recommend(movie_id: int, limit: int, db):
    base_movie = get_movie_by_id(movie_id, db)
    if not base_movie:
        print(f"Movie with ID {movie_id} not found.")
        return []

    print(f"\nSelected Movie: {base_movie.title}\n")

    base_genres = base_movie.genres_rel
    base_genre_ids = [genre.id for genre in base_genres]

    if not base_genre_ids:
        print("Base movie has no genres.")
        return []

    print(f"The movie {base_movie.title} has genres:")
    for genre in base_genres:
        print(f"{genre.name}")

    # to access the association table between movies and genres
    MovieGenre = Movie.genres_rel.property.secondary

    # use subquery to count how many genres each candidate movie shares with the base movie
    subq = (
        db.query(
            Movie.id.label("movie_id"),
            func.count(MovieGenre.c.genre_id)  #c. - to get columns
            .label("common_genres")
        )
        .join(MovieGenre, Movie.id == MovieGenre.c.movie_id)
        .filter(
            Movie.id != movie_id,
            MovieGenre.c.genre_id.in_(base_genre_ids)
        )
        .group_by(Movie.id)
        .order_by(func.count(MovieGenre.c.genre_id).desc())   #sort descending by number of genres
        .limit(limit)
        .subquery()
    )

    # join with main Movie table to get full movie data
    recommendations = (
        db.query(Movie)
        .join(subq, Movie.id == subq.c.movie_id)
        .options(joinedload(Movie.genres_rel))  # to avoid N+1 query number
        .all()
    )

    if not recommendations:
        print("No recommendations found.")
        return []

    print("\nRecommended Movies:")
    for movie in recommendations:
        overlapping_genres = [g.name for g in movie.genres_rel if g.id in base_genre_ids]
        genre_names = ", ".join(overlapping_genres)
        print(f"- {movie.title} ----> Shared genres: {genre_names}")

    return recommendations


def main():
    try:
        movie_id = int(input("Enter movie ID: "))
    except ValueError:
        print("Invalid input. Please enter a numeric movie ID.")
        return

    try:
        with get_db() as db:
            limit = 40
            recommend(movie_id, limit, db)
    except Exception as e:
        print(f"Failed to recommend movies: {e}")


if __name__ == "__main__":
    main()