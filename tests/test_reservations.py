"""
Teste pentru rezervări (coada de așteptare pentru cărți indisponibile) și
pentru get_unavailable_books (candidatele pentru rezervare).
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


def _make_unavailable(db, book, copies=1):
    """Împrumută toate exemplarele unei cărți, ca să devină indisponibilă."""
    borrower = db.add_borrower("Împrumutant", "", "")
    for _ in range(copies):
        db.add_loan(book, borrower, today_iso(), due_date_iso(14))


# --------------------------------------------------------------------------
def test_unavailable_books_lists_only_fully_borrowed(db):
    free = _add_book(db, "Liberă", copies=1)
    out = _add_book(db, "Toată împrumutată", copies=1)
    _make_unavailable(db, out, copies=1)

    ids = [b["id"] for b in db.get_unavailable_books()]
    assert out in ids
    assert free not in ids


def test_add_and_list_active_reservation(db):
    book = _add_book(db, "Carte", copies=1)
    _make_unavailable(db, book, copies=1)
    reader = db.add_borrower("Ana", "ana@test.ro", "")

    db.add_reservation(book, reader)
    active = db.get_active_reservations()
    assert len(active) == 1
    assert active[0]["book_title"] == "Carte"
    assert active[0]["borrower_name"] == "Ana"
    assert active[0]["available_copies"] <= 0  # cartea e încă indisponibilă


def test_duplicate_active_reservation_detected(db):
    book = _add_book(db, "Carte", copies=1)
    _make_unavailable(db, book, copies=1)
    reader = db.add_borrower("Ana", "", "")

    db.add_reservation(book, reader)
    assert db.has_active_reservation(book, reader) is True
    other = db.add_borrower("Ion", "", "")
    assert db.has_active_reservation(book, other) is False


def test_reservation_becomes_available_when_copy_returned(db):
    book = _add_book(db, "Carte", copies=1)
    borrower = db.add_borrower("Împrumutant", "", "")
    loan = db.add_loan(book, borrower, today_iso(), due_date_iso(14))
    reader = db.add_borrower("Ana", "", "")
    db.add_reservation(book, reader)

    assert db.get_active_reservations()[0]["available_copies"] <= 0
    db.return_loan(loan, today_iso())
    assert db.get_active_reservations()[0]["available_copies"] == 1  # gata de ridicat


def test_reservation_queue_order_is_by_insertion(db):
    book = _add_book(db, "Carte", copies=1)
    _make_unavailable(db, book, copies=1)
    first = db.add_borrower("Primul", "", "")
    second = db.add_borrower("Al doilea", "", "")
    db.add_reservation(book, first)
    db.add_reservation(book, second)

    queue = db.get_reservations_for_book(book)
    assert [r["borrower_name"] for r in queue] == ["Primul", "Al doilea"]


def test_cancel_reservation_removes_it(db):
    book = _add_book(db, "Carte", copies=1)
    _make_unavailable(db, book, copies=1)
    reader = db.add_borrower("Ana", "", "")
    res_id = db.add_reservation(book, reader)

    db.cancel_reservation(res_id)
    assert db.get_active_reservations() == []


def test_fulfill_reservation_removes_from_active(db):
    book = _add_book(db, "Carte", copies=1)
    _make_unavailable(db, book, copies=1)
    reader = db.add_borrower("Ana", "", "")
    res_id = db.add_reservation(book, reader)

    db.fulfill_reservation(res_id)
    assert db.get_active_reservations() == []
    # nu mai e activă, dar nici duplicat-guard n-o mai consideră activă
    assert db.has_active_reservation(book, reader) is False
