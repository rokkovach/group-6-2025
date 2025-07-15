from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from movie_service import search_movies, get_movie_by_id, get_similar_movies, get_movie_poster_url, get_total_movies_count, get_recommendation_section
from models import Movie
import os
from dotenv import load_dotenv
from overview_similarity_recommend import initialize_vectors
from database import get_db


# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup_event():
    print("🚀 SERVER STARTUP: Initializing vectors...")
    try:
        with get_db() as db:
            print("✅ Database connection successful")
            # Check if we have movies in the database
            movie_count = db.query(Movie).count()
            print(f"📊 Database contains {movie_count} movies")
            
            if movie_count == 0:
                print("❌ WARNING: No movies found in database!")
                return
                
            initialize_vectors(db)
            print("✅ Vectors initialized successfully")
    except Exception as e:
        print(f"❌ ERROR during startup: {e}")
        import traceback
        traceback.print_exc()

        
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    print("🏠 Root route accessed - redirecting to /search")
    return RedirectResponse(url="/search")

@app.get("/debug")
async def debug_route(query: str = ""):
    """Debug route to test the search logic"""
    print(f"🔍 DEBUG route called with query: '{query}'")
    has_search_query = bool(query and query.strip())
    
    if has_search_query:
        return {
            "query": query,
            "has_search_query": has_search_query,
            "is_landing": False,
            "recommendations": None,
            "type": "search_results"
        }
    else:
        return {
            "query": query,
            "has_search_query": has_search_query,
            "is_landing": True,
            "recommendations": "6_sections",
            "type": "landing_page"
        }

@app.get("/test", response_class=HTMLResponse)
async def test_route(request: Request):
    """Test route to verify the logic"""
    print("🧪 TEST route accessed")
    return HTMLResponse(f"""
    <h1>Test Results</h1>
    <p>Current time: {__import__('datetime').datetime.now()}</p>
    <p>Test landing page: <a href="/search">/search</a></p>
    <p>Test search: <a href="/search?query=star">/search?query=star</a></p>
    <p>Test movie: <a href="/film/1">/film/1</a></p>
    """)

# Page 1: Search with pagination and recommendations
@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, query: str = "", page: int = 1):
    print(f"🔍 SEARCH PAGE: query='{query}', page={page}")
    limit = 8  # Show 8 movies per page
    
    # Check if this is a search query (not landing page)
    has_search_query = bool(query and query.strip())
    
    print(f"DEBUG: query='{query}', has_search_query={has_search_query}")
    
    try:
        if has_search_query:
            # SEARCH RESULTS: Only show search results with pagination
            print(f"🔍 Performing search for: '{query}'")
            results = list(search_movies(query, limit=limit, page=page))
            total_count = get_total_movies_count(query)
            total_pages = (total_count + limit - 1) // limit
            
            print(f"📊 Search results: {len(results)} movies found, total_count={total_count}")
            
            # NO recommendation sections for search results
            recommendations = None
            is_landing = False
            print(f"DEBUG: Search results - is_landing={is_landing}, recommendations={recommendations}")
        else:
            # LANDING PAGE: Show 20 random movies ONLY (no recommendation sections)
            print("🏠 Loading landing page with random movies")
            results = list(search_movies("", limit=limit, page=page))
            total_count = get_total_movies_count()
            total_pages = (total_count + limit - 1) // limit
            
            print(f"📊 Landing page: {len(results)} movies loaded, total_count={total_count}")
            
            # NO recommendation sections for landing page
            recommendations = None
            is_landing = True
            print(f"DEBUG: Landing page - is_landing={is_landing}, recommendations={recommendations}")
        
        print(f"✅ Successfully loaded {len(results)} movies for template")
        
        return templates.TemplateResponse("search.html", {
            "request": request,
            "results": results,
            "query": query,
            "page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "recommendations": recommendations,
            "is_landing": is_landing,
            "max": max,
            "min": min
        })
    except Exception as e:
        print(f"❌ ERROR in search_page: {e}")
        import traceback
        traceback.print_exc()
        # Return a simple error page
        return HTMLResponse(f"<h1>Error</h1><p>{e}</p>")

# Page 2: Film Details + Recommendations
@app.get("/film/{film_id}", response_class=HTMLResponse)
async def film_detail(request: Request, film_id: int):
    print(f"🎬 FILM DETAIL: Loading film ID {film_id}")
    
    try:
        movie = get_movie_by_id(film_id)
        if not movie:
            print(f"❌ Movie with ID {film_id} not found")
            return RedirectResponse(url="/search")

        print(f"✅ Found movie: {movie.get('title', 'Unknown')}")

        # Get 6 recommendation sections for film detail page
        print("🔍 Loading recommendation sections...")
        recommendations = {
            "random": list(get_recommendation_section("random", limit=4)),
            "algo1": list(get_recommendation_section("algo1", film_id, limit=4)),  # Overview recomendation
            "algo2": list(get_recommendation_section("algo2", film_id, limit=4)),  # Composite ranking
            "algo3": list(get_recommendation_section("algo3", film_id, limit=4)),  # Title Overlap
            "algo4": list(get_recommendation_section("algo4", film_id, limit=4)),  # Genre Similarity
            "algo5": list(get_recommendation_section("algo5", film_id, limit=4))   # Random for testing
        }
        
        print(f"✅ Loaded {len(recommendations)} recommendation sections")
        for section, movies in recommendations.items():
            print(f"  - {section}: {len(movies) if movies else 0} movies")
        
        return templates.TemplateResponse("film_detail.html", {
            "request": request,
            "film": movie,
            "recommendations": recommendations
        })
    except Exception as e:
        print(f"❌ ERROR in film_detail: {e}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(f"<h1>Error</h1><p>{e}</p>")

def get_all_movies(conn, limit=20):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies LIMIT ?", (limit,))
    return cursor.fetchall()
