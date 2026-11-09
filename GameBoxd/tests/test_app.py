import pytest

from app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    app.config["TESTING"] = True
    return app.test_client()


def game_id(client, title):
    import sqlite3
    db = sqlite3.connect(client.application.config["DATABASE"])
    row = db.execute("SELECT id FROM games WHERE title = ?", (title,)).fetchone()
    db.close()
    return row[0]


def played_titles(client, sort):
    html = client.get(f"/played?sort={sort}").get_data(as_text=True)
    titles = ["Hades", "Celeste", "Portal 2"]
    return sorted(titles, key=lambda t: html.index(f">{t}<"))


def test_catalog_is_seeded_and_searchable(client):
    html = client.get("/?q=zelda").get_data(as_text=True)
    assert "Breath of the Wild" in html
    assert "Elden Ring" not in html


def test_rate_with_comment_and_edit(client):
    gid = game_id(client, "Hades")
    client.post(f"/game/{gid}/log", data={"rating": "4.5", "comment": "So good"})
    html = client.get(f"/game/{gid}").get_data(as_text=True)
    assert "So good" in html and "Update review" in html
    client.post(f"/game/{gid}/log", data={"rating": "5", "comment": ""})
    html = client.get("/played").get_data(as_text=True)
    assert "★★★★★" in html and "So good" not in html


def test_comment_is_optional_and_rating_validated(client):
    gid = game_id(client, "Celeste")
    client.post(f"/game/{gid}/log", data={"rating": "3"})
    assert "Celeste" in client.get("/played").get_data(as_text=True)
    other = game_id(client, "Portal 2")
    for bad in ("0", "6", "3.3", "abc", ""):
        client.post(f"/game/{other}/log", data={"rating": bad})
    assert "Portal 2" not in client.get("/played").get_data(as_text=True)


def on_want_list(client, title):
    html = client.get("/want").get_data(as_text=True)
    return f'class="card-title" href="/game/{game_id(client, title)}">{title}<' in html


def test_want_to_play_toggle_and_cleared_when_played(client):
    gid = game_id(client, "Outer Wilds")
    client.post(f"/game/{gid}/want")
    assert on_want_list(client, "Outer Wilds")
    client.post(f"/game/{gid}/want")
    assert not on_want_list(client, "Outer Wilds")
    client.post(f"/game/{gid}/want")
    client.post(f"/game/{gid}/log", data={"rating": "5"})
    assert not on_want_list(client, "Outer Wilds")


def test_sorting(client):
    for title, rating in [("Hades", "4"), ("Celeste", "5"), ("Portal 2", "2.5")]:
        client.post(f"/game/{game_id(client, title)}/log", data={"rating": rating})
    assert played_titles(client, "newest") == ["Portal 2", "Celeste", "Hades"]
    assert played_titles(client, "oldest") == ["Hades", "Celeste", "Portal 2"]
    assert played_titles(client, "highest") == ["Celeste", "Hades", "Portal 2"]
    assert played_titles(client, "lowest") == ["Portal 2", "Hades", "Celeste"]


def test_add_custom_game(client):
    resp = client.post("/games/new", data={"title": "My Indie Game", "year": "2025", "genre": "Puzzle"})
    assert resp.status_code == 302
    assert "My Indie Game" in client.get("/?q=indie").get_data(as_text=True)
    assert client.post("/games/new", data={"title": ""}).status_code == 400
