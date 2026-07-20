"""
Teste pentru fluxul "Caută online" din BookDialog (views/dialogs.py) --
varianta permanentă a celor 3 scenarii de regresie descoperite din
rapoarte reale de utilizare:

1. O primă căutare (doar ISBN) cu descriere scurtă trebuie să declanșeze
   automat o a doua căutare (ISBN+titlu), fără al doilea click manual.
2. O căutare nouă, pentru un ISBN diferit, trebuie să înlocuiască
   necondiționat datele vechi din formular (descriere/editură/loc).
3. Titlul/autorul rămase în formular de la cartea anterioară NU trebuie
   trimise mai departe într-o căutare nouă (ar contamina rezultatul).

Rulează fără rețea reală -- api_service.fetch_book_metadata e simulat.
Nu deschide efectiv o fereastră vizibilă (root.withdraw()).
"""

import time

import customtkinter as ctk
import pytest

import api_service
from database import Database
from ml_classifier import BookClassifier
from views.dialogs import BookDialog

LONG_DUNE_DESC = (
    "Dune is a 1965 science fiction novel by American author Frank Herbert, "
    "originally published as two separate serials in Analog magazine. It tied "
    "with Roger Zelazny's This Immortal for the Hugo Award in 1966 and it won "
    "the inaugural Nebula Award for Best Novel."
)


class FakeApp:
    def __init__(self, db_path):
        self.db = Database(db_path=str(db_path))
        self.classifier = BookClassifier()
        self.classifier.load()


@pytest.fixture(scope="module")
def root():
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def app(tmp_path):
    return FakeApp(tmp_path / "test_lookup.db")


def pump(root, seconds=3.0):
    """Rulează bucla de evenimente Tk suficient cât să se termine
    thread-urile de fundal și poll-ul de coadă (`.after`)."""
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def test_short_description_triggers_automatic_followup(root, app, monkeypatch):
    def fake_metadata(isbn=None, title=None, author=None):
        if not title:
            # Prima căutare, doar ISBN: descriere scurtă dar nevidă +
            # categorie -- înainte de fix, asta conta greșit ca "nu e
            # subțire" și follow-up-ul automat nu se declanșa.
            return {
                "title": "Dune", "author": "Frank Herbert", "pub_year": 1965,
                "isbn": isbn, "desc": "A science fiction novel.",
                "publisher": "Ace Books", "pub_place": "New York",
                "category_hint": "Fantezie & SF", "source": "Test-ISBN-only",
            }
        return {
            "title": "Dune", "author": "Frank Herbert", "pub_year": 1965,
            "isbn": isbn, "desc": LONG_DUNE_DESC,
            "publisher": "Ace Books", "pub_place": "New York",
            "category_hint": "Fantezie & SF", "source": "Test-ISBN+title",
        }

    monkeypatch.setattr(api_service, "fetch_book_metadata", fake_metadata)

    dlg = BookDialog(root, app)
    dlg.isbn_entry.insert(0, "9780441172719")
    dlg._lookup_online()
    pump(root, 3.0)

    desc = dlg.desc_text.get("1.0", "end").strip()
    assert dlg._did_followup_search is True
    assert len(desc) > 150
    dlg.close()


def test_fresh_isbn_search_replaces_stale_data(root, app, monkeypatch):
    def fake_metadata(isbn=None, title=None, author=None):
        return {
            "title": "1984", "author": "George Orwell", "pub_year": 1949,
            "isbn": isbn, "desc": "A dystopian novel.",
            "publisher": "Secker & Warburg", "pub_place": "London",
            "category_hint": "Literatură străină", "source": "Test-New-ISBN",
        }

    dlg = BookDialog(root, app)
    # Formularul are deja datele unei cărți anterioare complet completate.
    dlg.title_entry.insert(0, "Dune")
    dlg.author_entry.insert(0, "Frank Herbert")
    dlg.desc_text.insert("1.0", LONG_DUNE_DESC)
    dlg.publisher_entry.insert(0, "Ace Books")
    dlg.pub_place_entry.insert(0, "New York")

    dlg.isbn_entry.delete(0, "end")
    dlg.isbn_entry.insert(0, "9780451524935")

    monkeypatch.setattr(api_service, "fetch_book_metadata", fake_metadata)
    dlg._lookup_online()
    pump(root, 2.0)

    assert dlg.title_entry.get().strip() == "1984"
    assert dlg.desc_text.get("1.0", "end").strip() == "A dystopian novel."
    assert dlg.publisher_entry.get().strip() == "Secker & Warburg"
    assert dlg.pub_place_entry.get().strip() == "London"
    dlg.close()


def test_stale_title_does_not_contaminate_new_isbn_search(root, app, monkeypatch):
    def fake_metadata(isbn=None, title=None, author=None):
        assert title != "Dune", (
            f"stale title 'Dune' leaked into a fresh ISBN search (title={title!r})"
        )
        return {
            "title": "1984", "author": "George Orwell", "pub_year": 1949,
            "isbn": isbn, "desc": "A dystopian novel.",
            "publisher": "Secker & Warburg", "pub_place": "London",
            "category_hint": "Literatură străină", "source": "Test-New-ISBN-stale-title",
        }

    dlg = BookDialog(root, app)
    dlg.isbn_entry.insert(0, "9780441172719")
    dlg.title_entry.insert(0, "Dune")
    dlg.author_entry.insert(0, "Frank Herbert")
    dlg.desc_text.insert("1.0", LONG_DUNE_DESC)
    dlg.publisher_entry.insert(0, "Ace Books")
    dlg.pub_place_entry.insert(0, "New York")

    # Utilizatorul atinge DOAR câmpul ISBN.
    dlg.isbn_entry.delete(0, "end")
    dlg.isbn_entry.insert(0, "9780451524935")

    monkeypatch.setattr(api_service, "fetch_book_metadata", fake_metadata)
    dlg._lookup_online()
    pump(root, 2.0)

    assert dlg.title_entry.get().strip() == "1984"
    assert dlg.desc_text.get("1.0", "end").strip() == "A dystopian novel."
    dlg.close()
