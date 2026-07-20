"""
Teste pentru validarea cifrei de control ISBN-10/ISBN-13 (utils.py).

Codurile ISBN de test sunt generate programatic (nu memorate/ghicite) —
în timpul dezvoltării am descoperit că e ușor să greșești o cifră dintr-un
ISBN "știut din memorie", iar un cod astfel greșit ar fi trecut oricum
verificarea checksum-ului fără să testeze ce trebuie. Calculăm cifra de
control cu aceeași formulă ca utils.py, ca testul să fie corect prin
construcție.
"""

from utils import is_valid_isbn, normalize_isbn


def _isbn10_check_digit(digits9):
    total = sum((10 - i) * int(ch) for i, ch in enumerate(digits9))
    check = (11 - total % 11) % 11
    return "X" if check == 10 else str(check)


def _ean13_check_digit(digits12):
    total = sum((1 if i % 2 == 0 else 3) * int(ch) for i, ch in enumerate(digits12))
    return str((10 - total % 10) % 10)


def test_valid_isbn10_accepted():
    base = "014143951"
    isbn = base + _isbn10_check_digit(base)
    assert is_valid_isbn(isbn) is True


def test_isbn10_wrong_checksum_rejected():
    base = "014143951"
    correct = _isbn10_check_digit(base)
    wrong = "X" if correct != "X" else "0"
    assert is_valid_isbn(base + wrong) is False


def test_valid_isbn13_bookland_978_accepted():
    base = "978014143951"
    isbn = base + _ean13_check_digit(base)
    assert is_valid_isbn(isbn) is True


def test_valid_isbn13_bookland_979_accepted():
    base = "979123456789"
    isbn = base + _ean13_check_digit(base)
    assert is_valid_isbn(isbn) is True


def test_all_zero_isbn13_rejected():
    # Regresie: checksum-ul trece trivial pentru "0000000000000" (0 mod 10
    # == 0), dar nu are un prefix Bookland valid (978/979) -- nu e un ISBN
    # real și nu trebuie acceptat.
    assert is_valid_isbn("0000000000000") is False


def test_isbn13_with_correct_checksum_but_wrong_prefix_rejected():
    # Cifră de control corectă (deci un EAN-13 valid), dar cu un prefix
    # care nu e rezervat cărților (978/979) -- nu trebuie acceptat ca ISBN.
    base = "977123456789"
    isbn = base + _ean13_check_digit(base)
    assert is_valid_isbn(isbn) is False


def test_isbn13_wrong_checksum_rejected():
    base = "978014143951"
    correct = _ean13_check_digit(base)
    wrong = str((int(correct) + 1) % 10)
    assert is_valid_isbn(base + wrong) is False


def test_wrong_length_rejected():
    assert is_valid_isbn("123") is False
    assert is_valid_isbn("") is False
    assert is_valid_isbn(None) is False


def test_normalize_isbn_strips_hyphens_and_spaces():
    assert normalize_isbn("978-0-14-143951-8") == "9780141439518"
    assert normalize_isbn(" 978 0 14 143951 8 ") == "9780141439518"


def test_valid_isbn_accepts_hyphenated_input():
    base = "978014143951"
    isbn = base + _ean13_check_digit(base)
    hyphenated = f"{isbn[0:3]}-{isbn[3]}-{isbn[4:6]}-{isbn[6:12]}-{isbn[12]}"
    assert is_valid_isbn(hyphenated) is True
