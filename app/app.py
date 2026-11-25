import os
import psycopg2
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(page_title="Project B — Movies SQL Dashboard", layout="wide")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "movies_db"),          # Replace with your actual DB name
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "your_password"),  # Replace with your actual password
    "options": "-c lc_messages=C",
}


def run_query(sql, params=None):
    """Execute pure PostgreSQL query and return (column_names, rows)."""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            conn.set_client_encoding("UTF8")
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                cols = [desc[0] for desc in cur.description] if cur.description else []
                rows = cur.fetchall() if cur.description else []
                return cols, rows
    except UnicodeDecodeError:
        st.error(
            "Database connection failed: Please check your dbname, user, and password in DB_CONFIG."
        )
        return [], []
    except Exception as e:
        st.error(f"Database query error: {e}")
        return [], []


def show_sql_table(cols, rows):
    """Display raw SQL result rows as an interactive table without pandas."""
    with st.expander("📋 View SQL Result Table"):
        data = [dict(zip(cols, row)) for row in rows]
        st.dataframe(data, use_container_width=True)


def test_transaction_insert(test_rating):
    """Sumin Hwang - Query 5: Execute INSERT ... RETURNING inside a transaction and immediately ROLLBACK."""
    sql_insert = """
        WITH new_rating AS (
            SELECT
                u.user_id,
                m.tmdb_id
            FROM (
                SELECT DISTINCT user_id
                FROM ratings
                LIMIT 50
            ) u
            CROSS JOIN movies m
            WHERE NOT EXISTS (
                SELECT 1
                FROM ratings r
                WHERE r.user_id = u.user_id
                  AND r.tmdb_id = m.tmdb_id
            )
            ORDER BY u.user_id, m.tmdb_id
            LIMIT 1
        )
        INSERT INTO ratings (user_id, tmdb_id, rating, rated_at)
        SELECT
            user_id,
            tmdb_id,
            %s,
            CURRENT_TIMESTAMP
        FROM new_rating
        RETURNING user_id, tmdb_id, rating, rated_at;
    """
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_client_encoding("UTF8")
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ratings;")
            before_cnt = cur.fetchone()[0]

            cur.execute(sql_insert, (test_rating,))
            inserted_row = cur.fetchone()

            # Immediately rollback so the database remains unchanged
            conn.rollback()

            cur.execute("SELECT COUNT(*) FROM ratings;")
            after_cnt = cur.fetchone()[0]

        return inserted_row, before_cnt, after_cnt
    except UnicodeDecodeError:
        st.error(
            "Database connection failed: Please check your dbname, user, and password in DB_CONFIG."
        )
        return None, 0, 0
    except Exception as e:
        if conn:
            conn.rollback()
        st.error(f"Transaction test error: {e}")
        return None, 0, 0
    finally:
        if conn:
            conn.close()


# --- Header ---
st.title("🎬 The Movies Dataset — PostgreSQL Analytics Dashboard")
st.caption(
    "All joins, filtering, aggregations, and rankings are executed 100% in PostgreSQL SQL (no pandas / NumPy)."
)

# --- Sidebar Interactive Filters ---
st.sidebar.header("🔎 SQL Filter Parameters")

_, genre_rows = run_query("SELECT name FROM genres ORDER BY name ASC;")
genre_list = [r[0] for r in genre_rows] if genre_rows else ["Drama"]

selected_genre = st.sidebar.selectbox("Select Genre (M1-Q3)", genre_list)
min_rating_cnt = st.sidebar.slider("Min Rating Count (M1-Q1, Q2, Q3)", 5, 100, 20, step=5)
top_n_limit = st.sidebar.slider("Top N Limit (M1-Q2, Q3, Q4)", 3, 20, 10)
min_genre_movies = st.sidebar.slider("Min Sample Size per Genre (M2)", 10, 300, 50, step=10)
decade_range = st.sidebar.slider("Decade Range (M2-Q5)", 1920, 2010, (1950, 2010), step=10)

# Tabs: Sumin Hwang / Chaejin Jung
tab1, tab2 = st.tabs(["📊 Sumin Hwang Queries (Q1 – Q5)", "📈 Chaejin Jung Queries (Q1 – Q5)"])

# ==============================================================================
# TAB 1: Sumin Hwang QUERIES
# ==============================================================================
with tab1:
    c1, c2 = st.columns(2)

    # --- M1 Query 1: Average Rating by Movie Genre ---
    with c1:
        st.subheader(f"Q1. Average Rating by Movie Genre")
        sql_m1_q1 = """
            SELECT
                g.name AS genre,
                COUNT(r.rating) AS total_ratings,
                ROUND(AVG(r.rating), 2) AS average_rating
            FROM genres g
            JOIN movie_genres mg ON g.genre_id = mg.genre_id
            JOIN ratings r ON mg.tmdb_id = r.tmdb_id
            GROUP BY g.genre_id, g.name
            ORDER BY average_rating DESC;
        """
        cols_m1_q1, rows_m1_q1 = run_query(sql_m1_q1, (min_rating_cnt,))
        if rows_m1_q1:
            fig = go.Figure(
                go.Bar(
                    x=[r[0] for r in rows_m1_q1],
                    y=[float(r[2]) for r in rows_m1_q1],
                    text=[f"{r[2]} ({r[1]})" for r in rows_m1_q1],
                    textposition="auto",
                    marker_color="#4C78A8",
                )
            )
            fig.update_layout(
                xaxis_title="Genre",
                yaxis_title="Average Rating (out of 5)",
                yaxis=dict(range=[0, 5]),
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)
            show_sql_table(cols_m1_q1, rows_m1_q1)
        else:
            st.info("No genres match the current filter criteria.")

    # --- M1 Query 2: Movies Rated Above the Overall Average ---
    with c2:
        st.subheader(f"Q2. Movies Above Overall Average")
        sql_m1_q2 = """
            SELECT
                m.tmdb_id,
                m.title,
            COUNT(r.rating) AS total_ratings,
            ROUND(AVG(r.rating), 2) AS average_rating
            FROM movies m
            JOIN ratings r ON m.tmdb_id = r.tmdb_id
            GROUP BY m.tmdb_id, m.title
            HAVING AVG(r.rating) > (
                SELECT AVG(rating)
                FROM ratings
            )
            AND COUNT(r.rating) >= 10
            ORDER BY average_rating DESC, total_ratings DESC
            LIMIT 20;
        """
        cols_m1_q2, rows_m1_q2 = run_query(sql_m1_q2, (min_rating_cnt, top_n_limit))
        if rows_m1_q2:
            fig = go.Figure(
                go.Bar(
                    x=[float(r[3]) for r in rows_m1_q2],
                    y=[r[1] for r in rows_m1_q2],
                    orientation="h",
                    text=[f"{r[3]} ({r[2]} ratings)" for r in rows_m1_q2],
                    textposition="auto",
                    marker_color="#F58518",
                )
            )
            fig.update_layout(
                xaxis_title="Average Rating",
                yaxis_title="Movie Title",
                xaxis=dict(range=[0, 5.2]),
                yaxis=dict(autorange="reversed"),
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)
            show_sql_table(cols_m1_q2, rows_m1_q2)
        else:
            st.info("No movies match the current filter criteria.")

    st.divider()
    c3, c4 = st.columns(2)

    # --- M1 Query 3: Ranking Movies Within Each Genre ---
    with c3:
        st.subheader(f"Q3. Ranking Movies Within Each Genre")
        sql_m1_q3 = """
            WITH ranked_genre_movies AS (
    SELECT
        g.name AS genre,
        m.title,
        COUNT(r.rating) AS rating_count,
        ROUND(AVG(r.rating)::numeric, 2) AS average_rating,
        RANK() OVER (
            PARTITION BY g.name
            ORDER BY AVG(r.rating) DESC, COUNT(r.rating) DESC
        ) AS genre_rank
    FROM movies m
    JOIN ratings r ON m.tmdb_id = r.tmdb_id
    JOIN movie_genres mg ON m.tmdb_id = mg.tmdb_id
    JOIN genres g ON mg.genre_id = g.genre_id
    GROUP BY g.name, m.tmdb_id, m.title
    HAVING COUNT(r.rating) >= 20  
)
SELECT
    genre,
    genre_rank,
    title,
    rating_count,
    average_rating
FROM ranked_genre_movies
WHERE genre_rank <= 5  
ORDER BY genre, genre_rank, title;
        """
        cols_m1_q3, rows_m1_q3 = run_query(
            sql_m1_q3, (selected_genre, min_rating_cnt, top_n_limit)
        )
        if rows_m1_q3:
            fig = go.Figure(
                go.Bar(
                    x=[float(r[4]) for r in rows_m1_q3],
                    y=[f"#{r[1]} {r[2]}" for r in rows_m1_q3],
                    orientation="h",
                    text=[f"{r[4]} ({r[3]} ratings)" for r in rows_m1_q3],
                    textposition="auto",
                    marker_color="#54A24B",
                )
            )
            fig.update_layout(
                xaxis_title="Average Rating",
                yaxis_title="Rank & Title",
                xaxis=dict(range=[0, 5.2]),
                yaxis=dict(autorange="reversed"),
                height=420,
            )
            st.plotly_chart(fig, use_container_width=True)
            show_sql_table(cols_m1_q3, rows_m1_q3)
        else:
            st.info("No movies found for the selected criteria. Try lowering the Min Rating Count.")

    # --- M1 Query 4: Most Active Users Using a CTE ---
    with c4:
        st.subheader(f"Q4. Most Active Users (CTE)")
        sql_m1_q4 = """
            WITH user_activity AS (
    SELECT
        user_id,
        COUNT(*) AS ratings_given,
        ROUND(AVG(rating), 2) AS average_rating
    FROM ratings
    GROUP BY user_id
)
SELECT
    user_id,
    ratings_given,
    average_rating
FROM user_activity
ORDER BY ratings_given DESC
LIMIT 10;
        """
        cols_m1_q4, rows_m1_q4 = run_query(sql_m1_q4, (top_n_limit,))
        if rows_m1_q4:
            users = [f"User {r[0]}" for r in rows_m1_q4]
            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=users,
                    y=[int(r[1]) for r in rows_m1_q4],
                    name="Ratings Given",
                    marker_color="#72B7B2",
                    yaxis="y1",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=users,
                    y=[float(r[2]) for r in rows_m1_q4],
                    name="Average Rating",
                    mode="lines+markers",
                    line=dict(color="#E45756", width=3),
                    yaxis="y2",
                )
            )
            fig.update_layout(
                xaxis_title="User",
                yaxis=dict(title="Ratings Given (Count)"),
                yaxis2=dict(title="Average Rating", overlaying="y", side="right", range=[0, 5.2]),
                legend=dict(orientation="h", y=1.12),
                height=420,
            )
            st.plotly_chart(fig, use_container_width=True)
            show_sql_table(cols_m1_q4, rows_m1_q4)

    st.divider()

    # --- M1 Query 5: Transaction INSERT + ROLLBACK Demo ---
    st.subheader("Q5. Insert a New Movie Rating Using a Transaction (INSERT & ROLLBACK)")
    t_col1, t_col2 = st.columns([1, 2])
    with t_col1:
        sample_score = st.slider("Select Test Rating Value", 0.5, 5.0, 5.0, step=0.5)
        run_tx = st.button("🚀 Run Transaction (INSERT → RETURNING → ROLLBACK)")
    with t_col2:
        if run_tx:
            inserted, before_c, after_c = test_transaction_insert(sample_score)
            if inserted:
                st.success(
                    "INSERT succeeded inside transaction and was safely ROLLED BACK!"
                )
                st.json(
                    {
                        "inserted_user_id": inserted[0],
                        "inserted_tmdb_id": inserted[1],
                        "inserted_rating": float(inserted[2]),
                        "rated_at": str(inserted[3]),
                        "ratings_count_before": before_c,
                        "ratings_count_after_rollback": after_c,
                    }
                )

# ==============================================================================
# TAB 2: Sumin Hwang QUERIES
# ==============================================================================
with tab2:
    m2_c1, m2_c2 = st.columns(2)

    # --- M2 Query 1: Average Budget by Genre ---
    with m2_c1:
        st.subheader("Q1. Average Production Budget Rank by Genre")
        sql_m2_q1 = """
            SELECT
    RANK() OVER (ORDER BY AVG(movies.budget) DESC) AS budget_rank,
    genres.name,
    COUNT(movies.tmdb_id) AS movie_count,
    ROUND(AVG(movies.budget), 2) AS avg_budget
FROM movies
JOIN movie_genres ON movies.tmdb_id = movie_genres.tmdb_id
JOIN genres ON movie_genres.genre_id = genres.genre_id
WHERE movies.budget IS NOT NULL
GROUP BY genres.genre_id, genres.name
ORDER BY avg_budget DESC;

        """
        cols_m2_q1, rows_m2_q1 = run_query(sql_m2_q1, (min_genre_movies,))
        if rows_m2_q1:
            fig = go.Figure(
                go.Bar(
                    x=[float(r[3]) for r in rows_m2_q1],
                    y=[r[1] for r in rows_m2_q1],
                    orientation="h",
                    text=[f"${float(r[3]):,.0f}" for r in rows_m2_q1],
                    textposition="auto",
                    marker_color="#4C78A8",
                )
            )
            fig.update_layout(
                xaxis_title="Average Budget ($)",
                yaxis_title="Genre",
                yaxis=dict(autorange="reversed"),
                height=450,
            )
            st.plotly_chart(fig, use_container_width=True)
            show_sql_table(cols_m2_q1, rows_m2_q1)
        else:
            st.info("No genres match the minimum sample size.")

    # --- M2 Query 2: Most Frequent Actor per Genre ---
    with m2_c2:
        st.subheader("Q2. Most Frequent Actor per Genre (#1 Rank)")
        sql_m2_q2 = """
            WITH actor_genre_counts AS (
    SELECT
        g.name AS genre_name,
        p.person_id,
        p.name AS actor_name,
        COUNT(DISTINCT mc.tmdb_id) AS movie_count,
        RANK() OVER (
            PARTITION BY g.genre_id
            ORDER BY COUNT(DISTINCT mc.tmdb_id) DESC
        ) AS rnk
    FROM genres g
    JOIN movie_genres mg ON g.genre_id = mg.genre_id
    JOIN movie_credits mc ON mg.tmdb_id = mc.tmdb_id
    JOIN people p ON mc.person_id = p.person_id
    WHERE mc.role_type = 'cast'
    GROUP BY g.genre_id, g.name, p.person_id, p.name
)
SELECT
    genre_name,
    actor_name,
    movie_count
FROM actor_genre_counts
WHERE rnk = 1
ORDER BY genre_name ASC, movie_count DESC, actor_name ASC;

        """
        cols_m2_q2, rows_m2_q2 = run_query(sql_m2_q2)
        if rows_m2_q2:
            fig = go.Figure(
                go.Bar(
                    x=[int(r[2]) for r in rows_m2_q2],
                    y=[r[0] for r in rows_m2_q2],
                    orientation="h",
                    text=[f"{r[1]} ({r[2]} movies)" for r in rows_m2_q2],
                    textposition="auto",
                    marker_color="#54A24B",
                )
            )
            fig.update_layout(
                xaxis_title="Movie Appearances",
                yaxis_title="Genre",
                yaxis=dict(autorange="reversed"),
                height=450,
            )
            st.plotly_chart(fig, use_container_width=True)
            show_sql_table(cols_m2_q2, rows_m2_q2)

    st.divider()
    m2_c3, m2_c4 = st.columns(2)

    # --- M2 Query 3: Most Popular Movie Genres ---
    with m2_c3:
        st.subheader("Q3. Average Popularity by Movie Genre")
        sql_m2_q3 = """
            SELECT
    RANK() OVER (ORDER BY AVG(m.popularity) DESC) AS popularity_rank,
    g.name AS genre_name,
    COUNT(m.tmdb_id) AS movie_count,
    ROUND(AVG(m.popularity), 2) AS avg_popularity
FROM genres g
JOIN movie_genres mg ON g.genre_id = mg.genre_id
JOIN movies m ON mg.tmdb_id = m.tmdb_id
WHERE m.popularity IS NOT NULL
GROUP BY g.genre_id, g.name
ORDER BY popularity_rank ASC;

        """
        cols_m2_q3, rows_m2_q3 = run_query(sql_m2_q3, (min_genre_movies,))
        if rows_m2_q3:
            fig = go.Figure(
                go.Bar(
                    x=[r[1] for r in rows_m2_q3],
                    y=[float(r[3]) for r in rows_m2_q3],
                    text=[f"{r[3]}" for r in rows_m2_q3],
                    textposition="auto",
                    marker_color="#B279A2",
                )
            )
            fig.update_layout(
                xaxis_title="Genre",
                yaxis_title="Average Popularity",
                height=420,
            )
            st.plotly_chart(fig, use_container_width=True)
            show_sql_table(cols_m2_q3, rows_m2_q3)
        else:
            st.info("No genres match the minimum sample size.")

    # --- M2 Query 4: Female Cast Ratio by Genre ---
    with m2_c4:
        st.subheader("Q4. Female Cast Ratio by Genre (%)")
        sql_m2_q4 = """
            SELECT
    RANK() OVER (
        ORDER BY
            COUNT(*) FILTER (WHERE p.gender = 1)::NUMERIC / COUNT(*) DESC
    ) AS female_ratio_rank,
    g.name AS genre_name,
    COUNT(*) FILTER (WHERE p.gender = 1) AS female_cast_count,
    COUNT(*) AS known_gender_cast_count,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE p.gender = 1) / COUNT(*),
        2
    ) AS female_ratio_pct
FROM genres g
JOIN movie_genres mg ON g.genre_id = mg.genre_id
JOIN movie_credits mc ON mg.tmdb_id = mc.tmdb_id
JOIN people p ON mc.person_id = p.person_id
WHERE mc.role_type = 'cast'
  AND p.gender IN (1, 2, 3)  
GROUP BY g.genre_id, g.name
HAVING COUNT(*) >= 100      
ORDER BY female_ratio_rank ASC;

        """
        cols_m2_q4, rows_m2_q4 = run_query(sql_m2_q4, (min_genre_movies * 2,))
        if rows_m2_q4:
            fig = go.Figure(
                go.Bar(
                    x=[float(r[4]) for r in rows_m2_q4],
                    y=[r[1] for r in rows_m2_q4],
                    orientation="h",
                    text=[f"{r[4]}%" for r in rows_m2_q4],
                    textposition="auto",
                    marker_color="#E45756",
                )
            )
            fig.update_layout(
                xaxis_title="Female Cast Ratio (%)",
                yaxis_title="Genre",
                yaxis=dict(autorange="reversed"),
                height=420,
            )
            st.plotly_chart(fig, use_container_width=True)
            show_sql_table(cols_m2_q4, rows_m2_q4)
        else:
            st.info("No genres match the minimum sample size.")

    st.divider()

    # --- M2 Query 5: Movie Production & Average Revenue Trend by Decade ---
    st.subheader("Q5. Movie Production & Average Revenue Trend by Decade (with LAG Growth %)")
    sql_m2_q5 = """
        WITH decade_stats AS (
    SELECT
        (FLOOR(EXTRACT(YEAR FROM release_date) / 10) * 10)::INTEGER AS decade,
        COUNT(*) AS total_movies,
        COUNT(revenue) AS movies_with_revenue,
        ROUND(AVG(revenue), 0) AS avg_revenue
    FROM movies
    WHERE release_date IS NOT NULL
    GROUP BY FLOOR(EXTRACT(YEAR FROM release_date) / 10) * 10
    HAVING COUNT(revenue) >= 10  
)
SELECT
    decade,
    total_movies,
    movies_with_revenue,
    avg_revenue,
    ROUND(
        100.0 * (avg_revenue - LAG(avg_revenue) OVER (ORDER BY decade))
        / NULLIF(LAG(avg_revenue) OVER (ORDER BY decade), 0),
        2
    ) AS revenue_growth_pct
FROM decade_stats
ORDER BY decade ASC;

    """
    cols_m2_q5, rows_m2_q5 = run_query(sql_m2_q5, (decade_range[0], decade_range[1]))
    if rows_m2_q5:
        decades = [f"{r[0]}s" for r in rows_m2_q5]
        growth_texts = [
            f"Growth: {r[4]}%" if r[4] is not None else "Baseline Decade"
            for r in rows_m2_q5
        ]
        fig5 = go.Figure()
        fig5.add_trace(
            go.Bar(
                x=decades,
                y=[int(r[1]) for r in rows_m2_q5],
                name="Total Movies Produced",
                marker_color="#72B7B2",
                yaxis="y1",
            )
        )
        fig5.add_trace(
            go.Scatter(
                x=decades,
                y=[float(r[3]) for r in rows_m2_q5],
                name="Average Revenue ($)",
                text=growth_texts,
                hovertemplate="%{x}<br>Avg Revenue: $%{y:,.0f}<br>%{text}<extra></extra>",
                mode="lines+markers",
                line=dict(color="#F58518", width=3),
                yaxis="y2",
            )
        )
        fig5.update_layout(
            xaxis_title="Decade",
            yaxis=dict(title="Movies Produced"),
            yaxis2=dict(title="Average Revenue ($)", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.12),
            height=430,
        )
        st.plotly_chart(fig5, use_container_width=True)
        show_sql_table(cols_m2_q5, rows_m2_q5)
    else:
        st.info("No data available for the selected decade range.")

