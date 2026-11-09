# GameBoxd

A Letterboxd-style diary for video games, written in Python with Flask.

## Features

- **Browse and search** a catalog of about 70 well-known games by title, genre or platform.
- **Rate games out of 5** (half stars allowed) and **add a comment** if you want to.
  Edit or remove a review at any time.
- **Want to Play list.** Add games you haven't played yet. When you log a game as played, it comes off the list automatically.
- **Played list**, sortable by **Newest**, **Oldest**, **Highest rated** or **Lowest rated**, with your average rating.
- **Add your own games** if one is missing from the catalog.

Your data is saved in a local SQLite file (`gameboxd.db`), which is created on first run.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

## Tests

```bash
pytest
```
