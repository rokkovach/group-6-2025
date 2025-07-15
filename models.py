from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, Table, JSON, DateTime, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import func

Base = declarative_base()

# Association tables for many-to-many relationships
movie_genre = Table(
    'movie_genre',
    Base.metadata,
    Column('movie_id', Integer, ForeignKey('movies.id')),
    Column('genre_id', Integer, ForeignKey('genres.id'))
)

movie_actor = Table(
    'movie_actor',
    Base.metadata,
    Column('movie_id', Integer, ForeignKey('movies.id')),
    Column('actor_id', Integer, ForeignKey('actors.id'))
)

class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, index=True)
    imdb_id = Column(String, unique=True, index=True)
    title = Column(String, index=True)
    synopsis = Column(Text)
    genres = Column(String, index=True)  # Added index for genre filtering
    overview = Column(Text)
    release_date = Column(String)
    vote_average = Column(Float, index=True)  # Added index for rating queries
    vote_count = Column(Integer)
    poster_path = Column(String, nullable=True)
    titlewords = Column(Text)
    embedding_vector = Column(Text, nullable=True)  # OpenAI embedding vector as JSON string
    
    # Relationships
    genres_rel = relationship("Genre", secondary=movie_genre, back_populates="movies")
    actors = relationship("Actor", secondary=movie_actor, back_populates="movies")
    ratings = relationship("Rating", back_populates="movie")

    def to_dict(self):
        # Format genres as comma-separated string
        if self.genres_rel:
            genres_str = ", ".join([genre.name for genre in self.genres_rel])
        elif self.genres:
            if isinstance(self.genres, str):
                genres_str = self.genres.replace('|', ', ')
            else:
                genres_str = ", ".join(self.genres)
        else:
            genres_str = ""
            
        # Format actors as comma-separated string
        actors_str = ", ".join([actor.name for actor in self.actors]) if self.actors else ""
        
        return {
            "id": self.id,
            "title": self.title,
            "synopsis": self.synopsis,
            "poster_path": self.poster_path,
            "genres": genres_str,
            "actors": actors_str,
            "average_rating": self.vote_average,
            "vote_count": self.vote_count,
            "release_date": self.release_date if self.release_date else None,
            "overview": self.overview if self.overview else None,
            "titlewords": self.titlewords,
            "embedding_vector": self.embedding_vector
        }

# Add composite indexes for better performance
Index('idx_movies_actors_genres', Movie.id, Movie.genres)
Index('idx_movies_title_lower', func.lower(Movie.title))

class Genre(Base):
    __tablename__ = "genres"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, index=True)
    movies = relationship("Movie", secondary=movie_genre, back_populates="genres_rel")

class Actor(Base):
    __tablename__ = "actors"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, index=True)
    movies = relationship("Movie", secondary=movie_actor, back_populates="actors")

class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    movie_id = Column(Integer, ForeignKey('movies.id'), index=True)
    rating = Column(Float, index=True)
    movie = relationship("Movie", back_populates="ratings") 