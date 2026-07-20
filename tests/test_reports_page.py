"""
Teste pentru pagina Rapoarte (views/reports.py): cardurile de statistici
de împrumut, rândurile pe categorie (cu numărul de împrumuturi), panoul
"Cele mai împrumutate cărți" și faptul că un click pe o carte din acel
panou deschide dialogul de editare cu datele corecte.
"""

import customtkinter as ctk
import pytest

from database import Database
from ml_classifier import BookClassifier
from utils import today_iso, due_date_iso
from views.reports import ReportsPage


class FakeApp:
    def __init__(self, db_path):
        self.db = Database(db_path=str(db_path))
        self.classifier = BookClassifier()
        self.classifier.load()
        self.opened_dialogs = []
        self.pages = {}

    def show_page(self, key):
        pass


@pytest.fixture(scope="module")
def root():
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def app(tmp_path):
    return FakeApp(tmp_path / "test_reports.db")


def _add_book(app, title, category_name, author=None):
    cat_id = app.db.get_or_create_category(category_name)
    return app.db.add_book(None, title, author, None, "", cat_id)


def _add_loan(app, book_id, borrower_id, returned=False):
    # Scadent departe în viitor -- ca un împrumut activ nereturnat să nu
    # fie confundat cu unul restant, indiferent de data reală la care
    # rulează testul.
    loan_id = app.db.add_loan(book_id, borrower_id, today_iso(), due_date_iso(365))
    if returned:
        app.db.return_loan(loan_id, today_iso())
    return loan_id


def test_stat_cards_show_correct_values(root, app):
    borrower_id = app.db.add_borrower("Ion", "", "")
    book1 = _add_book(app, "Carte 1", "Test")
    book2 = _add_book(app, "Carte 2", "Test")
    _add_loan(app, book1, borrower_id, returned=True)
    _add_loan(app, book2, borrower_id, returned=False)

    page = ReportsPage(root, app)
    page.refresh()

    assert page.total_loans_card.value_label.cget("text") == "2"
    assert page.active_loans_card.value_label.cget("text") == "1"
    assert page.overdue_loans_card.value_label.cget("text") == "0"


def test_category_row_shows_book_count_and_loan_count(root, app):
    borrower_id = app.db.add_borrower("Ion", "", "")
    book1 = _add_book(app, "Carte 1", "Fictiune")
    book2 = _add_book(app, "Carte 2", "Fictiune")
    _add_loan(app, book1, borrower_id, returned=True)
    _add_loan(app, book2, borrower_id, returned=True)
    _add_loan(app, book2, borrower_id, returned=False)

    page = ReportsPage(root, app)
    page.refresh()

    texts = []
    for child in page.category_scroll.winfo_children():
        for label in child.winfo_children():
            texts.append(label.cget("text"))

    assert any("2 cărți · 3 împrumuturi" in t for t in texts)


def test_top_books_panel_lists_most_borrowed_first(root, app):
    borrower_id = app.db.add_borrower("Ion", "", "")
    popular = _add_book(app, "Foarte Populara", "Test", author="Autor Popular")
    less_popular = _add_book(app, "Mediu Populara", "Test")
    for _ in range(4):
        _add_loan(app, popular, borrower_id, returned=True)
    _add_loan(app, less_popular, borrower_id, returned=True)

    page = ReportsPage(root, app)
    page.refresh()

    texts = []
    for child in page.top_books_scroll.winfo_children():
        for label in child.winfo_children():
            texts.append(label.cget("text"))

    joined = " | ".join(texts)
    assert "Foarte Populara" in joined
    assert joined.index("Foarte Populara") < joined.index("Mediu Populara")
    assert "4×" in texts
    assert "Autor Popular" in " ".join(texts)


def test_never_borrowed_book_not_in_top_books_panel(root, app):
    borrower_id = app.db.add_borrower("Ion", "", "")
    borrowed = _add_book(app, "Imprumutata", "Test")
    _add_loan(app, borrowed, borrower_id, returned=True)
    _add_book(app, "Niciodata Imprumutata", "Test")

    page = ReportsPage(root, app)
    page.refresh()

    texts = []
    for child in page.top_books_scroll.winfo_children():
        for label in child.winfo_children():
            texts.append(label.cget("text"))
    assert not any("Niciodata Imprumutata" in t for t in texts)


def test_empty_top_books_shows_placeholder(root, app):
    page = ReportsPage(root, app)
    page.refresh()

    texts = [
        label.cget("text")
        for child in page.top_books_scroll.winfo_children()
        for label in ([child] if isinstance(child, ctk.CTkLabel) else child.winfo_children())
    ]
    assert any("Nicio carte împrumutată" in t for t in texts)


def test_clicking_top_book_opens_edit_dialog_with_correct_book(root, app, monkeypatch):
    borrower_id = app.db.add_borrower("Ion", "", "")
    book_id = _add_book(app, "Cartea De Editat", "Test", author="Un Autor")
    _add_loan(app, book_id, borrower_id, returned=True)

    page = ReportsPage(root, app)
    page.refresh()

    opened = []
    monkeypatch.setattr(
        "views.reports.BookDialog",
        lambda master, app, book=None, on_saved=None: opened.append(book),
    )

    page._edit_book(book_id)

    assert len(opened) == 1
    assert opened[0]["title"] == "Cartea De Editat"
