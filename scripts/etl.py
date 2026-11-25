import ast
import csv
import os
import sys
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import execute_values

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "movies_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "your_password"),
}

DATA_DIR = "data/raw"
FILES = {
    "movies": os.path.join(DATA_DIR, "movies_metadata.csv"),
    "credits": os.path.join(DATA_DIR, "credits.csv"),
    "links": os.path.join(DATA_DIR, "links_small.csv"),
    "ratings": os.path.join(DATA_DIR, "ratings_small.csv"),
}

stats = {
    "movies_malformed_or_bad_id": 0,
    "movies_duplicate_tmdb_id": 0,
    "movies_missing_title": 0,
    "movies_duplicate_imdb_id_nullified": 0,
    "movies_zero_budget_nullified": 0,
    "movies_zero_revenue_nullified": 0,
    "movies_zero_runtime_nullified": 0,
    "movies_invalid_date_nullified": 0,
    "credits_orphan_or_bad_id": 0,
    "credits_duplicate_credit_id": 0,
    "ratings_unmapped_or_orphan": 0,
    "ratings_duplicate_user_movie": 0,
}


def parse_int(val):
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except ValueError:
        return None


def parse_float(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def parse_date(val):
    if not val:
        return None
    try:
        return datetime.strptime(val.strip(), "%Y-%m-%d").date()
    except ValueError:
        stats["movies_invalid_date_nullified"] += 1
        return None


def parse_movies_and_genres():
    movies = {}
    genres = {}
    genre_names = set()
    movie_genres = set()
    seen_imdb_ids = set()

    with open(FILES["movies"], mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_id = (row.get("id") or "").strip()
            if not raw_id.isdigit():
                stats["movies_malformed_or_bad_id"] += 1
                continue

            tmdb_id = int(raw_id)
            if tmdb_id in movies:
                stats["movies_duplicate_tmdb_id"] += 1
                continue

            title = (row.get("title") or "").strip()
            if not title:
                stats["movies_missing_title"] += 1
                continue

            imdb_id = (row.get("imdb_id") or "").strip() or None
            if imdb_id == "0":
                imdb_id = None
            if imdb_id is not None:
                if imdb_id in seen_imdb_ids:
                    stats["movies_duplicate_imdb_id_nullified"] += 1
                    imdb_id = None
                else:
                    seen_imdb_ids.add(imdb_id)

            budget = parse_int(row.get("budget"))
            if budget is not None and budget <= 0:
                stats["movies_zero_budget_nullified"] += 1
                budget = None

            revenue = parse_int(row.get("revenue"))
            if revenue is not None and revenue <= 0:
                stats["movies_zero_revenue_nullified"] += 1
                revenue = None

            runtime = parse_float(row.get("runtime"))
            if runtime is not None and runtime <= 0:
                stats["movies_zero_runtime_nullified"] += 1
                runtime = None

            vote_avg = parse_float(row.get("vote_average"))
            if vote_avg is not None and not (0.0 <= vote_avg <= 10.0):
                vote_avg = None

            vote_cnt = parse_int(row.get("vote_count"))
            if vote_cnt is not None and vote_cnt < 0:
                vote_cnt = None

            popularity = parse_float(row.get("popularity"))
            if popularity is not None and popularity < 0:
                popularity = None

            orig_lang = (row.get("original_language") or "").strip()[:10] or None

            movies[tmdb_id] = (
                tmdb_id,
                imdb_id,
                title[:255],
                parse_date(row.get("release_date")),
                budget,
                revenue,
                round(runtime, 1) if runtime is not None else None,
                orig_lang,
                round(vote_avg, 1) if vote_avg is not None else None,
                vote_cnt,
                round(popularity, 4) if popularity is not None else None,
            )

            # genres JSON/리스트 파싱
            raw_genres = row.get("genres")
            if raw_genres:
                try:
                    g_list = ast.literal_eval(raw_genres)
                    if isinstance(g_list, list):
                        for g in g_list:
                            gid = g.get("id")
                            gname = (g.get("name") or "").strip()[:100]
                            if isinstance(gid, int) and gname:
                                if gid not in genres and gname not in genre_names:
                                    genres[gid] = (gid, gname)
                                    genre_names.add(gname)
                                if gid in genres:
                                    movie_genres.add((tmdb_id, gid))
                except (ValueError, SyntaxError):
                    pass

    return movies, genres, movie_genres


def parse_credits(valid_tmdb_ids):
    people = {}
    movie_credits = {}

    with open(FILES["credits"], mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_id = (row.get("id") or "").strip()
            if not raw_id.isdigit() or int(raw_id) not in valid_tmdb_ids:
                stats["credits_orphan_or_bad_id"] += 1
                continue
            tmdb_id = int(raw_id)

            for role_type, col_name, detail_key in [
                ("cast", "cast", "character"),
                ("crew", "crew", "job"),
            ]:
                raw_field = row.get(col_name)
                if not raw_field:
                    continue
                try:
                    items = ast.literal_eval(raw_field)
                except (ValueError, SyntaxError):
                    continue

                if not isinstance(items, list):
                    continue

                for item in items:
                    credit_id = (str(item.get("credit_id") or "")).strip()[:50]
                    person_id = item.get("id")
                    name = (item.get("name") or "").strip()[:255]
                    gender = item.get("gender")
                    if gender not in (0, 1, 2, 3):
                        gender = None

                    if not credit_id or not isinstance(person_id, int) or not name:
                        continue

                    if person_id not in people:
                        people[person_id] = (person_id, name, gender)

                    if credit_id in movie_credits:
                        stats["credits_duplicate_credit_id"] += 1
                        continue

                    detail = (str(item.get(detail_key) or "")).strip()[:255] or None
                    movie_credits[credit_id] = (
                        credit_id,
                        tmdb_id,
                        person_id,
                        role_type,
                        detail,
                    )

    return people, movie_credits


def parse_ratings(valid_tmdb_ids):
    # links_small.csv로 movieId -> tmdbId 매핑 생성
    movie_to_tmdb = {}
    with open(FILES["links"], mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mid = parse_int(row.get("movieId"))
            tid = parse_int(row.get("tmdbId"))
            if mid is not None and tid in valid_tmdb_ids:
                movie_to_tmdb[mid] = tid

    ratings = {}
    with open(FILES["ratings"], mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = parse_int(row.get("userId"))
            mid = parse_int(row.get("movieId"))
            rating = parse_float(row.get("rating"))
            ts = parse_int(row.get("timestamp"))

            tmdb_id = movie_to_tmdb.get(mid)
            if uid is None or tmdb_id is None or rating is None or ts is None:
                stats["ratings_unmapped_or_orphan"] += 1
                continue
            if not (0.5 <= rating <= 5.0):
                stats["ratings_unmapped_or_orphan"] += 1
                continue

            key = (uid, tmdb_id)
            if key in ratings:
                stats["ratings_duplicate_user_movie"] += 1
                continue

            rated_at = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            ratings[key] = (uid, tmdb_id, round(rating, 1), rated_at)

    return ratings


def run_etl(test_rollback=False):
    print("1. CSV 파일 파싱 및 정제 중...")
    movies, genres, movie_genres = parse_movies_and_genres()
    valid_tmdb_ids = set(movies.keys())
    people, movie_credits = parse_credits(valid_tmdb_ids)
    ratings = parse_ratings(valid_tmdb_ids)

    print("2. PostgreSQL 단일 트랜잭션 적재 시작...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            # 재실행 시 깔끔하게 비우기
            cur.execute(
                "TRUNCATE TABLE ratings, movie_credits, movie_genres, people, genres, movies CASCADE;"
            )

            execute_values(
                cur,
                """INSERT INTO movies (
                    tmdb_id, imdb_id, title, release_date, budget, revenue,
                    runtime, original_language, vote_average, vote_count, popularity
                ) VALUES %s""",
                list(movies.values()),
                page_size=2000,
            )
            execute_values(
                cur,
                "INSERT INTO genres (genre_id, name) VALUES %s",
                list(genres.values()),
                page_size=1000,
            )
            execute_values(
                cur,
                "INSERT INTO movie_genres (tmdb_id, genre_id) VALUES %s",
                list(movie_genres),
                page_size=2000,
            )
            execute_values(
                cur,
                "INSERT INTO people (person_id, name, gender) VALUES %s",
                list(people.values()),
                page_size=2000,
            )
            execute_values(
                cur,
                """INSERT INTO movie_credits (
                    credit_id, tmdb_id, person_id, role_type, job_or_character
                ) VALUES %s""",
                list(movie_credits.values()),
                page_size=2000,
            )
            execute_values(
                cur,
                """INSERT INTO ratings (
                    user_id, tmdb_id, rating, rated_at
                ) VALUES %s""",
                list(ratings.values()),
                page_size=2000,
            )

            if test_rollback:
                print("[롤백 테스트] 의도적으로 CHECK 제약조건 위반을 발생시킵니다...")
                cur.execute(
                    "INSERT INTO ratings (user_id, tmdb_id, rating, rated_at) VALUES (-1, %s, 9.9, NOW());",
                    (next(iter(valid_tmdb_ids)),),
                )

        conn.commit()
        print("3. COMMIT 완료! 모든 데이터가 정상 적재되었습니다.\n")

        print("=== 적재 행 수 ===")
        print(f"movies        : {len(movies):,}")
        print(f"genres        : {len(genres):,}")
        print(f"movie_genres  : {len(movie_genres):,}")
        print(f"people        : {len(people):,}")
        print(f"movie_credits : {len(movie_credits):,}")
        print(f"ratings       : {len(ratings):,}\n")

        print("=== 정제 규칙별 영향 행 수 (보고서 기록용) ===")
        for k, v in stats.items():
            print(f"{k}: {v:,}")

    except Exception as e:
        conn.rollback()
        print(f"\n[오류 발생 -> ROLLBACK 실행됨]: {e}")
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM movies;")
            cnt = cur.fetchone()[0]
            print(f"롤백 후 movies 테이블 행 수 확인: {cnt} (부분 적재 없음)")
    finally:
        conn.close()


if __name__ == "__main__":
    rollback_flag = "--test-rollback" in sys.argv
    run_etl(test_rollback=rollback_flag)