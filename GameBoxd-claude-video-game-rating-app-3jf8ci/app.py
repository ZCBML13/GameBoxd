"""GameBoxd - a Letterboxd-style diary for video games.

Run with:  python app.py   then open http://127.0.0.1:5000
"""

import os
import sqlite3
from datetime import datetime

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

from games_seed import SEED_GAMES

SORT_OPTIONS = {
    "newest": ("Newest", "l.logged_at DESC, l.id DESC"),
    "oldest": ("Oldest", "l.logged_at ASC, l.id ASC"),
    "highest": ("Highest rated", "l.rating DESC, l.logged_at DESC, l.id DESC"),
    "lowest": ("Lowest rated", "l.rating ASC, l.logged_at DESC, l.id DESC"),
}

# Ratings go from half a star up to five stars, in half-star steps.
VALID_RATINGS = [x / 2 for x in range(1, 11)]

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    title     TEXT NOT NULL UNIQUE COLLATE NOCASE,
    year      INTEGER,
    genre     TEXT,
    platforms TEXT
);

-- One diary entry per game: your rating and optional comment.
CREATE TABLE IF NOT EXISTS logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id   INTEGER NOT NULL UNIQUE REFERENCES games(id) ON DELETE CASCADE,
    rating    REAL NOT NULL CHECK (rating >= 0.5 AND rating <= 5),
    comment   TEXT,
    logged_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS want_to_play (
    game_id  INTEGER PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL
);
"""


def now():
    return datetime.now().isoformat(timespec="seconds")


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("GAMEBOXD_SECRET", "dev-secret-change-me")
    app.config["DATABASE"] = db_path or os.environ.get(
        "GAMEBOXD_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "gameboxd.db")
    )

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = sqlite3.connect(app.config["DATABASE"])
        db.executescript(SCHEMA)
        if db.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO games (title, year, genre, platforms) VALUES (?, ?, ?, ?)",
                SEED_GAMES,
            )
        db.commit()
        db.close()

    init_db()

    def get_game(game_id):
        game = get_db().execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        if game is None:
            abort(404)
        return game

    @app.template_filter("stars")
    def stars_filter(rating):
        full = int(rating)
        half = rating - full >= 0.5
        return "★" * full + ("½" if half else "")

    @app.template_filter("prettydate")
    def prettydate_filter(value):
        return datetime.fromisoformat(value).strftime("%b %d, %Y")

    @app.context_processor
    def inject_counts():
        db = get_db()
        return {
            "played_count": db.execute("SELECT COUNT(*) FROM logs").fetchone()[0],
            "want_count": db.execute("SELECT COUNT(*) FROM want_to_play").fetchone()[0],
        }

    # ---------- Browse ----------

    @app.route("/")
    def index():
        q = request.args.get("q", "").strip()
        sql = """
            SELECT g.*, l.rating, (w.game_id IS NOT NULL) AS wanted
            FROM games g
            LEFT JOIN logs l ON l.game_id = g.id
            LEFT JOIN want_to_play w ON w.game_id = g.id
        """
        params = ()
        if q:
            sql += " WHERE g.title LIKE ? OR g.genre LIKE ? OR g.platforms LIKE ?"
            params = (f"%{q}%",) * 3
        sql += " ORDER BY g.title COLLATE NOCASE"
        games = get_db().execute(sql, params).fetchall()
        return render_template("index.html", games=games, q=q)

    @app.route("/games/new", methods=["GET", "POST"])
    def add_game():
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            year = request.form.get("year", "").strip()
            genre = request.form.get("genre", "").strip()
            platforms = request.form.get("platforms", "").strip()
            if not title:
                flash("A game needs a title.", "error")
                return render_template("add_game.html", form=request.form), 400
            if year and not (year.isdigit() and 1950 <= int(year) <= 2100):
                flash("Year should be a 4-digit year.", "error")
                return render_template("add_game.html", form=request.form), 400
            db = get_db()
            existing = db.execute("SELECT id FROM games WHERE title = ?", (title,)).fetchone()
            if existing:
                flash(f"“{title}” is already in the catalog.", "info")
                return redirect(url_for("game_detail", game_id=existing["id"]))
            cur = db.execute(
                "INSERT INTO games (title, year, genre, platforms) VALUES (?, ?, ?, ?)",
                (title, int(year) if year else None, genre or None, platforms or None),
            )
            db.commit()
            flash(f"Added “{title}”.", "success")
            return redirect(url_for("game_detail", game_id=cur.lastrowid))
        return render_template("add_game.html", form={})

    # ---------- A single game: rate, comment, want-to-play ----------

    @app.route("/game/<int:game_id>")
    def game_detail(game_id):
        game = get_game(game_id)
        db = get_db()
        log = db.execute("SELECT * FROM logs WHERE game_id = ?", (game_id,)).fetchone()
        wanted = db.execute(
            "SELECT 1 FROM want_to_play WHERE game_id = ?", (game_id,)
        ).fetchone() is not None
        return render_template(
            "game.html", game=game, log=log, wanted=wanted, ratings=VALID_RATINGS
        )

    @app.route("/game/<int:game_id>/log", methods=["POST"])
    def log_game(game_id):
        game = get_game(game_id)
        try:
            rating = float(request.form.get("rating", ""))
        except ValueError:
            rating = None
        if rating not in VALID_RATINGS:
            flash("Pick a rating between ½ and 5 stars.", "error")
            return redirect(url_for("game_detail", game_id=game_id))
        comment = request.form.get("comment", "").strip() or None

        db = get_db()
        db.execute(
            """
            INSERT INTO logs (game_id, rating, comment, logged_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(game_id) DO UPDATE SET rating = excluded.rating,
                                               comment = excluded.comment
            """,
            (game_id, rating, comment, now()),
        )
        # Once you've played it, it no longer belongs on the want-to-play list.
        db.execute("DELETE FROM want_to_play WHERE game_id = ?", (game_id,))
        db.commit()
        flash(f"Saved your review of “{game['title']}”.", "success")
        return redirect(url_for("game_detail", game_id=game_id))

    @app.route("/game/<int:game_id>/log/delete", methods=["POST"])
    def delete_log(game_id):
        get_game(game_id)
        db = get_db()
        db.execute("DELETE FROM logs WHERE game_id = ?", (game_id,))
        db.commit()
        flash("Review removed.", "info")
        return redirect(url_for("game_detail", game_id=game_id))

    @app.route("/game/<int:game_id>/want", methods=["POST"])
    def toggle_want(game_id):
        game = get_game(game_id)
        db = get_db()
        if db.execute("SELECT 1 FROM want_to_play WHERE game_id = ?", (game_id,)).fetchone():
            db.execute("DELETE FROM want_to_play WHERE game_id = ?", (game_id,))
            flash(f"Removed “{game['title']}” from your Want to Play list.", "info")
        else:
            db.execute(
                "INSERT INTO want_to_play (game_id, added_at) VALUES (?, ?)", (game_id, now())
            )
            flash(f"Added “{game['title']}” to your Want to Play list.", "success")
        db.commit()
        return redirect(request.form.get("next") or url_for("game_detail", game_id=game_id))

    # ---------- Lists ----------

    @app.route("/played")
    def played():
        sort = request.args.get("sort", "newest")
        if sort not in SORT_OPTIONS:
            sort = "newest"
        order_by = SORT_OPTIONS[sort][1]
        entries = get_db().execute(
            f"""
            SELECT g.id, g.title, g.year, g.genre, l.rating, l.comment, l.logged_at
            FROM logs l JOIN games g ON g.id = l.game_id
            ORDER BY {order_by}
            """
        ).fetchall()
        avg = sum(e["rating"] for e in entries) / len(entries) if entries else None
        return render_template(
            "played.html", entries=entries, sort=sort, sort_options=SORT_OPTIONS, avg=avg
        )

    @app.route("/want")
    def want_list():
        games = get_db().execute(
            """
            SELECT g.*, w.added_at FROM want_to_play w JOIN games g ON g.id = w.game_id
            ORDER BY w.added_at DESC, g.title
            """
        ).fetchall()
        return render_template("want.html", games=games)

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
