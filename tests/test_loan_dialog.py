"""
Verifică faptul că LoanDialog (views/dialogs.py) folosește zilele de
împrumut implicite configurabile din Setări, nu constanta fixă
config.DEFAULT_LOAN_DAYS -- regresie posibilă dacă cineva reintroduce
importul direct al constantei.
"""

from datetime import date, timedelta

import customtkinter as ctk
import pytest

import settings_service
from database import Database
from ml_classifier import BookClassifier
from views.dialogs import LoanDialog


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


@pytest.fixture(autouse=True)
def isolated_settings_file(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_service, "SETTINGS_PATH", str(settings_path))
    yield


@pytest.fixture
def app(tmp_path):
    return FakeApp(tmp_path / "test_loan_dialog.db")


def test_due_date_defaults_to_configured_loan_days(root, app):
    settings_service.set_default_loan_days(21)

    dlg = LoanDialog(root, app)
    expected = (date.today() + timedelta(days=21)).isoformat()
    assert dlg.due_date_entry.get() == expected
    dlg.destroy()


def test_due_date_uses_config_fallback_when_not_overridden(root, app):
    from config import DEFAULT_LOAN_DAYS

    dlg = LoanDialog(root, app)
    expected = (date.today() + timedelta(days=DEFAULT_LOAN_DAYS)).isoformat()
    assert dlg.due_date_entry.get() == expected
    dlg.destroy()
