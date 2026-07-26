"""
Teste pentru validările câmpurilor din formularele de carte și cititor
(utils.is_plausible_*): trebuie să respingă greșelile evidente de tastare,
dar să accepte datele reale, scrise în formatele uzuale.

Regresia pe care o previn: înainte, un An sau un Nr. exemplare scris greșit
era ignorat în tăcere la salvare (an -> None, exemplare -> 1), fără ca
bibliotecarul să afle că datele introduse nu s-au păstrat.
"""

from datetime import date

import pytest

from utils import (
    MIN_PUB_YEAR,
    is_plausible_czu,
    is_plausible_email,
    is_plausible_phone,
    is_plausible_pub_year,
)


# --------------------------------------------------------------------------
# Câmpurile opționale goale trec toate validările
# --------------------------------------------------------------------------
@pytest.mark.parametrize("validator", [
    is_plausible_pub_year, is_plausible_phone, is_plausible_email, is_plausible_czu,
])
@pytest.mark.parametrize("empty", ["", "   ", None])
def test_empty_values_are_accepted(validator, empty):
    assert validator(empty)


# --------------------------------------------------------------------------
# An apariție
# --------------------------------------------------------------------------
@pytest.mark.parametrize("year", ["1998", "2024", str(MIN_PUB_YEAR), str(date.today().year + 1)])
def test_valid_years_accepted(year):
    assert is_plausible_pub_year(year)


@pytest.mark.parametrize("year", [
    "abc",          # litere
    "19x8",         # cifre amestecate cu litere
    "800",          # înainte de tipar
    "-1998",        # negativ
    "19.98",        # zecimal
    str(date.today().year + 5),   # prea în viitor
])
def test_invalid_years_rejected(year):
    assert not is_plausible_pub_year(year)


# --------------------------------------------------------------------------
# Telefon
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phone", [
    "0722123456", "0722 123 456", "+40 722 123 456", "0264-123.456", "(0264) 123456",
])
def test_valid_phones_accepted(phone):
    assert is_plausible_phone(phone)


@pytest.mark.parametrize("phone", [
    "nu are telefon",   # text
    "0722abc456",       # litere printre cifre
    "12345",            # prea puține cifre
    "telefon: 0722123456",
])
def test_invalid_phones_rejected(phone):
    assert not is_plausible_phone(phone)


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------
@pytest.mark.parametrize("email", ["nume@scoala.ro", "a.b-c@sub.domeniu.com"])
def test_valid_emails_accepted(email):
    assert is_plausible_email(email)


@pytest.mark.parametrize("email", [
    "nume", "nume@", "@scoala.ro", "nume@scoala", "nume @scoala.ro", "a@b@c.ro",
])
def test_invalid_emails_rejected(email):
    assert not is_plausible_email(email)


# --------------------------------------------------------------------------
# CZU -- trebuie să accepte codurile sugerate de aplicație (config.CZU_SUGGESTIONS)
# --------------------------------------------------------------------------
def test_all_suggested_czu_codes_are_valid():
    from config import CZU_SUGGESTIONS

    for category, code in CZU_SUGGESTIONS.items():
        assert is_plausible_czu(code), f"cod respins pentru {category}: {code}"


@pytest.mark.parametrize("czu", ["821.135.1", "004", "821-31", "(498)", "159.9", "82/89"])
def test_valid_czu_accepted(czu):
    assert is_plausible_czu(czu)


@pytest.mark.parametrize("czu", [
    "literatura",       # text
    "821.135.1 romana",  # cod + text
    "...",              # fără nicio cifră
])
def test_invalid_czu_rejected(czu):
    assert not is_plausible_czu(czu)
