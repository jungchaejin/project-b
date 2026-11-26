import os
import psycopg2
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Project B — Movies SQL Dashboard", layout="wide")

MEMBER_1_NAME = "Sumin Hwang"
MEMBER_2_NAME = "Chaejin Jung"

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


# --- Header ---
st.title("🎬 The Movies Dataset — PostgreSQL Analytics Dashboard")
st.caption(
    "All joins, filtering, aggregations, and rankings are executed 100% in PostgreSQL SQL (no pandas / NumPy)."
)

# --- Sidebar Interactive Filters ---
st.sidebar.header("🔎 SQL Filter Parameters")

min_rating_cnt = st.sidebar.slider(
    f"Min Total Ratings per Genre ({MEMBER_1_NAME} - Q1)", 1, 500, 20, step=10
)
top_n_users = st.sidebar.slider(
    f"Top N Active Users ({MEMBER_1_NAME} - Q4)", 3, 25, 10
)
min_cast_cnt = st.sidebar.slider(
    f"Min Known-Gender Cast per Genre ({MEMBER_2_NAME} - Q4)", 10, 500, 100, step=10
)
decade_range = st.sidebar.slider(
    f"Decade Range ({MEMBER_2_NAME} - Q5)", 1920, 2010, (1950, 2010), step=10
)

# ==============================================================================
# ROW 1: MEMBER 1 — Q1 & Q4
# ==============================================================================
r1_col1, r1_col2 = st.columns(2)

# --- Member 1 - Query 1: Average Rating by Movie Genre ---
with r1_col1:
    st.subheader(
        f"1. [{MEMBER_1_NAME} - Q1] Average Rating by Genre (Min {min_rating_cnt} Ratings)"
    )
    sql_m1_q1 = """
        SELECT
            g.name AS genre,
            COUNT(r.rating) AS total_ratings,
            ROUND(AVG(r.rating), 2) AS average_rating
        FROM genres g
        JOIN movie_genres mg ON g.genre_id = mg.genre_id
        JOIN ratings r ON mg.tmdb_id = r.tmdb_id
        GROUP BY g.genre_id, g.name
        HAVING COUNT(r.rating) >= %s
        ORDER BY average_rating DESC;
    """
    cols_m1_q1, rows_m1_q1 = run_query(sql_m1_q1, (min_rating_cnt,))
    if rows_m1_q1:
        fig1 = go.Figure(
            go.Bar(
                x=[r[0] for r in rows_m1_q1],
                y=[float(r[2]) for r in rows_m1_q1],
                text=[f"{r[2]} ({r[1]})" for r in rows_m1_q1],
                textposition="auto",
                marker_color="#4C78A8",
            )
        )
        fig1.update_layout(
            xaxis_title="Genre",
            yaxis_title="Average Rating (out of 5)",
            yaxis=dict(range=[0, 5]),
            height=420,
        )
        st.plotly_chart(fig1, use_container_width=True)
        show_sql_table(cols_m1_q1, rows_m1_q1)
    else:
        st.info("No genres match the current filter criteria.")

# --- Member 1 - Query 4: Most Active Users Using a CTE ---
with r1_col2:
    st.subheader(f"2. [{MEMBER_1_NAME} - Q4] Top {top_n_users} Most Active Users (CTE)")
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
        LIMIT %s;
    """
    cols_m1_q4, rows_m1_q4 = run_query(sql_m1_q4, (top_n_users,))
    if rows_m1_q4:
        users = [f"User {r[0]}" for r in rows_m1_q4]
        fig2 = go.Figure()
        fig2.add_trace(
            go.Bar(
                x=users,
                y=[int(r[1]) for r in rows_m1_q4],
                name="Ratings Given",
                marker_color="#72B7B2",
                yaxis="y1",
            )
        )
        fig2.add_trace(
            go.Scatter(
                x=users,
                y=[float(r[2]) for r in rows_m1_q4],
                name="Average Rating",
                mode="lines+markers",
                line=dict(color="#E45756", width=3),
                yaxis="y2",
            )
        )
        fig2.update_layout(
            xaxis_title="User",
            yaxis=dict(title="Ratings Given (Count)"),
            yaxis2=dict(
                title="Average Rating", overlaying="y", side="right", range=[0, 5.2]
            ),
            legend=dict(orientation="h", y=1.12),
            height=420,
        )
        st.plotly_chart(fig2, use_container_width=True)
        show_sql_table(cols_m1_q4, rows_m1_q4)
    else:
        st.info("No user activity data available.")

st.divider()

# ==============================================================================
# ROW 2: MEMBER 2 — Q4 & Q5
# ==============================================================================
r2_col1, r2_col2 = st.columns(2)

# --- Member 2 - Query 4: Female Cast Ratio by Genre ---
with r2_col1:
    st.subheader(
        f"3. [{MEMBER_2_NAME} - Q4] Female Cast Ratio by Genre (Min {min_cast_cnt} Cast)"
    )
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
        HAVING COUNT(*) >= %s
        ORDER BY female_ratio_rank ASC;
    """
    cols_m2_q4, rows_m2_q4 = run_query(sql_m2_q4, (min_cast_cnt,))
    if rows_m2_q4:
        fig3 = go.Figure(
            go.Bar(
                x=[float(r[4]) for r in rows_m2_q4],
                y=[r[1] for r in rows_m2_q4],
                orientation="h",
                text=[f"{r[4]}%" for r in rows_m2_q4],
                textposition="auto",
                marker_color="#E45756",
            )
        )
        fig3.update_layout(
            xaxis_title="Female Cast Ratio (%)",
            yaxis_title="Genre",
            yaxis=dict(autorange="reversed"),
            height=430,
        )
        st.plotly_chart(fig3, use_container_width=True)
        show_sql_table(cols_m2_q4, rows_m2_q4)
    else:
        st.info("No genres match the minimum cast sample size.")

# --- Member 2 - Query 5: Movie Production & Average Revenue Trend by Decade ---
with r2_col2:
    st.subheader(
        f"4. [{MEMBER_2_NAME} - Q5] Production & Revenue Trend by Decade (LAG %)"
    )
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
        WHERE decade BETWEEN %s AND %s
        ORDER BY decade ASC;
    """
    cols_m2_q5, rows_m2_q5 = run_query(sql_m2_q5, (decade_range[0], decade_range[1]))
    if rows_m2_q5:
        decades = [f"{r[0]}s" for r in rows_m2_q5]
        growth_texts = [
            f"Growth: {r[4]}%" if r[4] is not None else "Baseline Decade"
            for r in rows_m2_q5
        ]
        fig4 = go.Figure()
        fig4.add_trace(
            go.Bar(
                x=decades,
                y=[int(r[1]) for r in rows_m2_q5],
                name="Total Movies Produced",
                marker_color="#72B7B2",
                yaxis="y1",
            )
        )
        fig4.add_trace(
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
        fig4.update_layout(
            xaxis_title="Decade",
            yaxis=dict(title="Movies Produced"),
            yaxis2=dict(title="Average Revenue ($)", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.12),
            height=430,
        )
        st.plotly_chart(fig4, use_container_width=True)
        show_sql_table(cols_m2_q5, rows_m2_q5)
    else:
        st.info("No data available for the selected decade range.")