-- 1. movies
CREATE TABLE movies (
    tmdb_id           INTEGER PRIMARY KEY,
    imdb_id           VARCHAR(20) UNIQUE,
    title             VARCHAR(255) NOT NULL,
    release_date      DATE,
    budget            BIGINT CHECK (budget > 0),
    revenue           BIGINT CHECK (revenue > 0),
    runtime           NUMERIC(6, 1) CHECK (runtime > 0),
    original_language VARCHAR(10),
    vote_average      NUMERIC(3, 1) CHECK (vote_average >= 0 AND vote_average <= 10),
    vote_count        INTEGER CHECK (vote_count >= 0),
    popularity        NUMERIC(10, 4) CHECK (popularity >= 0)
);

-- 2. genres
CREATE TABLE genres (
    genre_id          INTEGER PRIMARY KEY,
    name              VARCHAR(100) NOT NULL UNIQUE
);

-- 3. movie_genres
CREATE TABLE movie_genres (
    tmdb_id           INTEGER NOT NULL,
    genre_id          INTEGER NOT NULL,
    PRIMARY KEY (tmdb_id, genre_id),
    CONSTRAINT fk_movie_genres_movie
        FOREIGN KEY (tmdb_id) REFERENCES movies(tmdb_id) ON DELETE CASCADE,
    CONSTRAINT fk_movie_genres_genre
        FOREIGN KEY (genre_id) REFERENCES genres(genre_id) ON DELETE RESTRICT
);

-- 4. people
CREATE TABLE people (
    person_id         INTEGER PRIMARY KEY,
    name              VARCHAR(255) NOT NULL,
    gender            SMALLINT CHECK (gender IN (0, 1, 2, 3))
);

-- 5. movie_credits
CREATE TABLE movie_credits (
    credit_id         VARCHAR(50) PRIMARY KEY,
    tmdb_id           INTEGER NOT NULL,
    person_id         INTEGER NOT NULL,
    role_type         VARCHAR(10) NOT NULL CHECK (role_type IN ('cast', 'crew')),
    job_or_character  VARCHAR(255),
    CONSTRAINT fk_credits_movie
        FOREIGN KEY (tmdb_id) REFERENCES movies(tmdb_id) ON DELETE CASCADE,
    CONSTRAINT fk_credits_person
        FOREIGN KEY (person_id) REFERENCES people(person_id) ON DELETE RESTRICT
);

-- 6. ratings
CREATE TABLE ratings (
    user_id           INTEGER NOT NULL,
    tmdb_id           INTEGER NOT NULL,
    rating            NUMERIC(2, 1) NOT NULL CHECK (rating >= 0.5 AND rating <= 5.0),
    rated_at          TIMESTAMP NOT NULL,
    PRIMARY KEY (user_id, tmdb_id),
    CONSTRAINT fk_ratings_movie
        FOREIGN KEY (tmdb_id) REFERENCES movies(tmdb_id) ON DELETE CASCADE
);