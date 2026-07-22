"""
Teste pentru:
- disponibilitatea cărților cu mai multe exemplare (get_available_books
  respectă `copies`: o carte cu N exemplare poate fi împrumutată de N ori);
- statisticile per cititor (get_borrowers_with_stats: active/restante) și
  istoricul per cititor (get_loans_for_borrower).
"""

import pytest

from database import Database
from utils import today_iso, due_date_iso


@pytest.fixture
def db(tmp_path):
    return Database(db_path=str(tmp_path / "test.db"))


def _add_book(db, title, copies=1):
    cat_id = db.get_or_create_category("Test")
    return db.add_book(None, title, "Autor", None, "", cat_id, copies=copies)


# --------------------------------------------------------------------------
# Disponibilitate cu mai multe exemplare
# --------------------------------------------------------------------------
def test_single_copy_becomes_unavailable_after_one_loan(db):
    book = _add_book(db, "Carte cu 1 exemplar", copies=1)
    borrower = db.add_borrower("Ion", "", "")

    assert any(b["id"] == book for b in db.get_available_books())
    db.add_loan(book, borrower, today_iso(), due_date_iso(14))
    assert not any(b["id"] == book for b in db.get_available_books())


def test_multi_copy_stays_available_until_all_copies_out(db):
    book = _add_book(db, "Carte cu 3 exemplare", copies=3)
    b1 = db.add_borrower("Ana", "", "")
    b2 = db.add_borrower("Ion", "", "")

    def available_copies():
        for b in db.get_available_books():
            if b["id"] == book:
                return b["available_copies"]
        return 0

    assert available_copies() == 3
    db.add_loan(book, b1, today_iso(), due_date_iso(14))
    assert available_copies() == 2
    db.add_loan(book, b2, today_iso(), due_date_iso(14))
    assert available_copies() == 1
    # Al treilea exemplar împrumutat -> cartea dispare din disponibile.
    db.add_loan(book, b1, today_iso(), due_date_iso(14))
    assert not any(b["id"] == book for b in db.get_available_books())


def test_returning_a_copy_makes_book_available_again(db):
    book = _add_book(db, "Carte cu 2 exemplare", copies=2)
    borrower = db.add_borrower("Ion", "", "")
    loan1 = db.add_loan(book, borrower, today_iso(), due_date_iso(14))
    db.add_loan(book, borrower, today_iso(), due_date_iso(14))
    assert not any(b["id"] == book for b in db.get_available_books())

    db.return_loan(loan1, today_iso())
    match = [b for b in db.get_available_books() if b["id"] == book]
    assert match and match[0]["available_copies"] == 1


# --------------------------------------------------------------------------
# Statistici și istoric per cititor
# --------------------------------------------------------------------------
def test_borrower_stats_count_active_and_overdue(db):
    book1 = _add_book(db, "Carte 1")
    book2 = _add_book(db, "Carte 2")
    book3 = _add_book(db, "Carte 3")
    borrower = db.add_borrower("Maria", "maria@test.ro", "0700")

    db.add_loan(book1, borrower, today_iso(), due_date_iso(14))      # activ, la termen
    db.add_loan(book2, borrower, today_iso(), due_date_iso(-3))      # activ, restant
    loan3 = db.add_loan(book3, borrower, today_iso(), due_date_iso(14))
    db.return_loan(loan3, today_iso())                               # returnat

    stats = {b["id"]: b for b in db.get_borrowers_with_stats()}[borrower]
    assert stats["active_count"] == 2   # doar cele nereturnate
    assert stats["overdue_count"] == 1  # doar cel restant


def test_borrower_with_no_loans_has_zero_stats(db):
    borrower = db.add_borrower("Fără împrumuturi", "", "")
    stats = {b["id"]: b for b in db.get_borrowers_with_stats()}[borrower]
    assert stats["active_count"] == 0
    assert stats["overdue_count"] == 0


def test_borrower_stats_search_filters_by_name(db):
    db.add_borrower("Ana Popescu", "", "")
    db.add_borrower("Ion Ionescu", "", "")
    names = [b["name"] for b in db.get_borrowers_with_stats(search="Ana")]
    assert names == ["Ana Popescu"]


def test_loans_for_borrower_lists_active_first_then_history(db):
    book1 = _add_book(db, "Activă")
    book2 = _add_book(db, "Returnată")
    borrower = db.add_borrower("Ion", "", "")
    returned = db.add_loan(book2, borrower, today_iso(), due_date_iso(14))
    db.return_loan(returned, today_iso())
    db.add_loan(book1, borrower, today_iso(), due_date_iso(14))

    loans = db.get_loans_for_borrower(borrower)
    assert len(loans) == 2
    assert loans[0]["book_title"] == "Activă" and loans[0]["return_date"] is None
    assert loans[1]["book_title"] == "Returnată" and loans[1]["return_date"] is not None
