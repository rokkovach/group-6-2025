#!/usr/bin/env python3
"""
Working Evaluation Script for Movie Recommendation Algorithms
Tests algorithms that can work with available data (no genres)
"""

import time
import csv
from database import get_db
from models import Movie
import title_overlap_recommend
import genre_similarity_recommend
import overview_similarity_recommend
import composite_ranking_recommend
import embedding_similarity_recommend

MOVIE_IDS = [11397, 603, 10191, 808, 278]
ALGORITHMS = [
    ("Title Overlap", lambda movie_id, db: title_overlap_recommend.recommend(movie_id, 6, db)),
    ("Genre Similarity", lambda movie_id, db: genre_similarity_recommend.recommend(movie_id, 6, db)),
    ("Overview Similarity", lambda movie_id, db: overview_similarity_recommend.recommend(movie_id, 6, db)),
    ("Composite Ranking", lambda movie_id, db: composite_ranking_recommend.recommend(movie_id, 6, db)),
    ("Embedding Similarity", lambda movie_id, db: embedding_similarity_recommend.get_embedding_based_recommendations(movie_id, 6)),
]

CSV_FILE = "evaluation_results.csv"

def get_movie_by_id(movie_id):
    with get_db() as db:
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            return None
        return {
            'id': movie.id,
            'title': movie.title
        }

def run_evaluation():
    results = []
    print("\n================ MOVIE RECOMMENDATION EVALUATION ================\n")
    for movie_id in MOVIE_IDS:
        movie = get_movie_by_id(movie_id)
        if not movie:
            print(f"❌ Movie ID {movie_id} not found in database.")
            continue
        print(f"\n🎬 Evaluating Movie: {movie['title']} (ID: {movie['id']})")
        print("-" * 70)
        for algo_name, algo_func in ALGORITHMS:
            print(f"\n🔹 Algorithm: {algo_name}")
            start = time.time()
            recs_out = []
            if algo_name == "Embedding Similarity":
                recs = algo_func(movie_id, None)
                for rec in recs or []:
                    recs_out.append(rec if isinstance(rec, dict) else {'title': str(rec)})
            else:
                with get_db() as db:
                    recs = algo_func(movie_id, db)
                    for rec in recs or []:
                        if hasattr(rec, 'to_dict'):
                            recs_out.append(rec.to_dict())
                        elif hasattr(rec, 'title'):
                            recs_out.append({'title': rec.title})
                        else:
                            recs_out.append({'title': str(rec)})
            elapsed = time.time() - start
            # Printout with scores if available
            if not recs_out:
                print("   No recommendations generated.")
            else:
                for i, rec in enumerate(recs_out, 1):
                    line = f"   {i}. {rec.get('title', 'Unknown')}"
                    # Print scores if present
                    for key in ['similarity_score', 'score', 'overlap', 'genre_overlap', 'actor_overlap', 'rating_score', 'votes_score', 'overview_overlap', 'titleword_overlap']:
                        if key in rec:
                            line += f" ({key}: {rec[key]})"
                    print(line)
            # Save for CSV
            results.append({
                'movie_id': movie['id'],
                'movie_title': movie['title'],
                'algorithm': algo_name,
                'time': f"{elapsed:.4f}",
                'recommendations': ", ".join([r.get('title', 'Unknown') for r in recs_out])
            })
            print(f"   ⏱️ Time taken: {elapsed:.4f} seconds")
    # Write CSV
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['movie_id', 'movie_title', 'algorithm', 'time', 'recommendations'])
        writer.writeheader()
        for row in results:
            writer.writerow(row)
    # Print summary table per movie
    print("\n================ ALGORITHM TIMING SUMMARY ================\n")
    from collections import defaultdict
    timing_table = defaultdict(dict)
    movie_titles = {}
    for row in results:
        timing_table[row['movie_id']][row['algorithm']] = row['time']
        movie_titles[row['movie_id']] = row['movie_title']
    algos = [a[0] for a in ALGORITHMS]
    header = f"{'Movie ID':<8} {'Movie Title':<35} " + " ".join([f"{algo:<20}" for algo in algos])
    print(header)
    print("-" * len(header))
    for movie_id in MOVIE_IDS:
        title = movie_titles.get(movie_id, "N/A")
        row = f"{movie_id:<8} {title:<35} "
        for algo in algos:
            t = timing_table.get(movie_id, {}).get(algo, "-")
            row += f"{t:<20}"
        print(row)
    print(f"\n✅ Evaluation complete. Results saved to {CSV_FILE}\n")

if __name__ == "__main__":
    run_evaluation() 