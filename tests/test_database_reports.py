"""
Teste pentru statisticile noi de raportare din database.py:
- get_dashboard_stats()["total_loans"] -- total istoric, nu doar active;
- get_books_per_category() -- loan_count per categorie, pe lângă
  book_count existent; verifică în special că JOIN-ul dublu
  (categorii -> cărți -> împrumuturi) nu umflă book_count atunci când o
  carte are mai multe împrumuturi (risc clasic de "fan-out" la JOIN-uri
  multiple pe un singur COUNT);
- get_top_borrowed_books() -- clasament corect, exclude cărțile
  niciodată împrumutate, respectă limita cerută.
"""

import pytest

from database import Database
from utils import today_iso, due_date_iso


@pytest.fixture
def db(tmp_path):
    return Database(db_path=str(tmp_path / "test.db"))


def _add_book(db, title, category_name, author=None):
    cat_id = db.get_or_create_category(category_name)
    book_id = db.add_book(None, title, author, None, "", cat_id)
    return book_id


def _add_loan(db, book_id, borrower_id, returned=False):
    # Scadent departe în viitor -- ca un împrumut activ nereturnat să nu
    # fie confundat cu unul restant, indiferent de data reală la care
    # rulează testul.
    loan_id = db.add_loan(book_id, borrower_id, today_iso(), due_date_iso(365))
    if returned:
        db.return_loan(loan_id, today_iso())
    return loan_id


def test_total_loans_counts_all_loans_regardless_of_return_status(db):
    cat_id = db.get_or_create_category("Test")
    book_id = _add_book(db, "Carte A", "Test")
    borrower_id = db.add_borrower("Ion", "", "")

    _add_loan(db, book_id, borrower_id, returned=True)
    _add_loan(db, book_id, borrower_id, returned=False)

    stats = db.get_dashboard_stats()
    assert stats["total_loans"] == 2
    assert stats["borrowed_count"] == 1  # doar cel nereturnat


def test_books_per_category_loan_count_not_inflated_by_multiple_loans(db):
    # O carte cu 3 împrumuturi -- riscul clasic: un JOIN dublu
    # (categorie->cărți->împrumuturi) ar putea umfla book_count la 3 în
    # loc de 1, dacă nu se folosește COUNT(DISTINCT books.id).
    book_id = _add_book(db, "Carte Populara", "Fictiune")
    borrower_id = db.add_borrower("Ion", "", "")
    for _ in range(3):
        _add_loan(db, book_id, borrower_id, returned=True)

    per_category = {row["category_name"]: row for row in db.get_books_per_category()}
    assert per_category["Fictiune"]["book_count"] == 1
    assert per_category["Fictiune"]["loan_count"] == 3


def test_books_per_category_includes_categories_with_no_books_or_loans(db):
    db.get_or_create_category("Categorie Goala")

    per_category = {row["category_name"]: row for row in db.get_books_per_category()}
    assert per_category["Categorie Goala"]["book_count"] == 0
    assert per_category["Categorie Goala"]["loan_count"] == 0


def test_books_per_category_counts_loans_across_multiple_books(db):
    borrower_id = db.add_borrower("Ion", "", "")
    book1 = _add_book(db, "Carte 1", "Categorie X")
    book2 = _add_book(db, "Carte 2", "Categorie X")
    _add_loan(db, book1, borrower_id, returned=True)
    _add_loan(db, book2, borrower_id, returned=True)
    _add_loan(db, book2, borrower_id, returned=False)

    per_category = {row["category_name"]: row for row in db.get_books_per_category()}
    assert per_category["Categorie X"]["book_count"] == 2
    assert per_category["Categorie X"]["loan_count"] == 3


def test_top_borrowed_books_ranks_by_loan_count_descending(db):
    borrower_id = db.add_borrower("Ion", "", "")
    popular = _add_book(db, "Foarte Populara", "Test")
    medium = _add_book(db, "Mediu Populara", "Test")
    never = _add_book(db, "Niciodata Imprumutata", "Test")

    for _ in range(5):
        _add_loan(db, popular, borrower_id, returned=True)
    for _ in range(2):
        _add_loan(db, medium, borrower_id, returned=True)

    top = db.get_top_borrowed_books(limit=10)
    titles = [row["title"] for row in top]

    assert titles[0] == "Foarte Populara"
    assert titles[1] == "Mediu Populara"
    assert "Niciodata Imprumutata" not in titles, "cărțile niciodată împrumutate nu trebuie să apară"
    assert top[0]["loan_count"] == 5
    assert top[1]["loan_count"] == 2


def test_top_borrowed_books_respects_limit(db):
    borrower_id = db.add_borrower("Ion", "", "")
    for i in range(5):
        book_id = _add_book(db, f"Carte {i}", "Test")
        _add_loan(db, book_id, borrower_id, returned=True)

    top = db.get_top_borrowed_books(limit=3)
    assert len(top) == 3


def test_top_borrowed_books_empty_when_no_loans(db):
    _add_book(db, "Carte Fara Imprumuturi", "Test")
    assert db.get_top_borrowed_books() == []


def test_top_borrowed_books_includes_category_name(db):
    borrower_id = db.add_borrower("Ion", "", "")
    book_id = _add_book(db, "Carte", "Categoria Speciala")
    _add_loan(db, book_id, borrower_id, returned=True)

    top = db.get_top_borrowed_books()
    assert top[0]["category_name"] == "Categoria Speciala"
