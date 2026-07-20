"""
Teste pentru pagina Setări (views/settings.py): fluxurile de backup și
restaurare din interfață -- prima apăsare pe backup cere folderul și îl
reține, apăsările următoare nu mai întreabă, "Schimbă locația"
suprascrie alegerea, iar restaurarea cere confirmare, validează
fișierul, face un backup de siguranță și înlocuiește baza de date doar
dacă toți pașii anteriori reușesc.

Dialogurile native (askdirectory/askopenfilename/messagebox) sunt
simulate -- nu se deschide nimic vizibil.
"""

import sqlite3
from datetime import datetime

import customtkinter as ctk
import pytest

import settings_service
from database import Database
from ml_classifier import BookClassifier
from views import settings as settings_module
from views.settings import SettingsPage


class FakeApp:
    def __init__(self, db_path):
        self.db = Database(db_path=str(db_path))
        self.classifier = BookClassifier()
        self.classifier.load()
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


@pytest.fixture(scope="module")
def root():
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture(autouse=True)
def isolated_settings_file(tmp_path, monkeypatch):
    # settings_module.get_backup_dir/set_backup_dir sunt aceleași funcții
    # importate din settings_service -- ele citesc SETTINGS_PATH din
    # namespace-ul lor de definiție (settings_service), deci patch-uind
    # doar acolo e suficient ca să izoleze fiecare test.
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_service, "SETTINGS_PATH", str(settings_path))
    yield


@pytest.fixture
def app(tmp_path):
    return FakeApp(tmp_path / "test_settings.db")


def test_first_backup_prompts_for_folder_and_remembers_it(root, app, tmp_path, monkeypatch):
    chosen_dir = str(tmp_path / "MyBackups")
    ask_calls = []

    def fake_askdirectory(**kwargs):
        ask_calls.append(kwargs)
        return chosen_dir

    monkeypatch.setattr(settings_module.filedialog, "askdirectory", fake_askdirectory)
    monkeypatch.setattr(settings_module.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(settings_module.messagebox, "showerror", lambda *a, **k: None)

    page = SettingsPage(root, app)
    assert settings_service.get_backup_dir() == ""

    page._backup_now()

    assert len(ask_calls) == 1, "prima apăsare trebuie să ceară folderul"
    assert settings_service.get_backup_dir() == chosen_dir
    assert "Ultimul backup:" in page.last_backup_label.cget("text")


def test_second_backup_does_not_ask_again(root, app, tmp_path, monkeypatch):
    chosen_dir = str(tmp_path / "MyBackups")
    settings_service.set_backup_dir(chosen_dir)

    ask_calls = []
    monkeypatch.setattr(
        settings_module.filedialog, "askdirectory",
        lambda **kwargs: ask_calls.append(kwargs) or chosen_dir,
    )
    monkeypatch.setattr(settings_module.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(settings_module.messagebox, "showerror", lambda *a, **k: None)

    page = SettingsPage(root, app)
    page._backup_now()

    assert len(ask_calls) == 0, "cu o locație deja salvată, nu trebuie să mai ceară folderul"


def test_backup_creates_a_valid_db_file_with_standard_name(root, app, tmp_path, monkeypatch):
    chosen_dir = tmp_path / "MyBackups"
    monkeypatch.setattr(settings_module.filedialog, "askdirectory", lambda **k: str(chosen_dir))
    monkeypatch.setattr(settings_module.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(settings_module.messagebox, "showerror", lambda *a, **k: None)

    page = SettingsPage(root, app)
    page._backup_now()

    files = list(chosen_dir.glob("biblioteca_backup_*.db"))
    assert len(files) == 1
    conn = sqlite3.connect(str(files[0]))
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_last_backup_label_shows_exact_datetime_and_book_count(root, app, tmp_path, monkeypatch):
    cat_id = app.db.get_or_create_category("Test Category")
    app.db.add_book(None, "Carte A", None, None, "", cat_id)
    app.db.add_book(None, "Carte B", None, None, "", cat_id)

    chosen_dir = str(tmp_path / "MyBackups")
    monkeypatch.setattr(settings_module.filedialog, "askdirectory", lambda **k: chosen_dir)
    monkeypatch.setattr(settings_module.messagebox, "showinfo", lambda *a, **k: None)

    before = datetime.now().replace(microsecond=0)
    page = SettingsPage(root, app)
    page._backup_now()
    after = datetime.now().replace(microsecond=0)

    text = page.last_backup_label.cget("text")
    assert "2 cărți" in text, f"eticheta trebuie să arate numărul de cărți din backup: {text!r}"

    info = settings_service.get_last_backup_info()
    assert info["book_count"] == 2
    recorded = datetime.fromisoformat(info["timestamp"]).replace(microsecond=0)
    assert before <= recorded <= after, "ora salvată trebuie să corespundă momentului real al backup-ului"

    expected_when = recorded.strftime("%d.%m.%Y, ora %H:%M:%S")
    assert expected_when in text


def test_no_backup_yet_shows_placeholder(root, app):
    page = SettingsPage(root, app)
    assert page.last_backup_label.cget("text") == "Niciun backup efectuat încă."


def test_last_backup_info_persists_across_page_reload(root, app, tmp_path, monkeypatch):
    chosen_dir = str(tmp_path / "MyBackups")
    monkeypatch.setattr(settings_module.filedialog, "askdirectory", lambda **k: chosen_dir)
    monkeypatch.setattr(settings_module.messagebox, "showinfo", lambda *a, **k: None)

    page1 = SettingsPage(root, app)
    page1._backup_now()
    text_after_backup = page1.last_backup_label.cget("text")

    # O pagină nouă (ex. repornirea aplicației) trebuie să arate aceeași
    # informație, nu un câmp gol -- e persistată în settings.json, nu doar
    # ținută în memoria paginii curente.
    page2 = SettingsPage(root, app)
    assert page2.last_backup_label.cget("text") == text_after_backup


def test_change_location_overwrites_saved_dir(root, app, tmp_path, monkeypatch):
    old_dir = str(tmp_path / "OldBackups")
    new_dir = str(tmp_path / "NewBackups")
    settings_service.set_backup_dir(old_dir)

    monkeypatch.setattr(settings_module.filedialog, "askdirectory", lambda **k: new_dir)
    monkeypatch.setattr(settings_module.messagebox, "showinfo", lambda *a, **k: None)

    page = SettingsPage(root, app)
    page._change_location()

    assert settings_service.get_backup_dir() == new_dir
    assert new_dir in page.location_label.cget("text")


def test_change_location_cancelled_keeps_old_dir(root, app, tmp_path, monkeypatch):
    old_dir = str(tmp_path / "OldBackups")
    settings_service.set_backup_dir(old_dir)

    # askdirectory returnează "" când utilizatorul apasă Anulează.
    monkeypatch.setattr(settings_module.filedialog, "askdirectory", lambda **k: "")

    page = SettingsPage(root, app)
    page._change_location()

    assert settings_service.get_backup_dir() == old_dir


# ------------------------------------------------------------------
# Restaurare din backup
# ------------------------------------------------------------------
def _book_titles(db_path):
    conn = sqlite3.connect(str(db_path))
    titles = {row[0] for row in conn.execute("SELECT title FROM books")}
    conn.close()
    return titles


def test_restore_cancelled_at_confirmation_does_nothing(root, app, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module.messagebox, "askyesno", lambda *a, **k: False)
    open_calls = []
    monkeypatch.setattr(
        settings_module.filedialog, "askopenfilename",
        lambda **k: open_calls.append(k) or "",
    )

    page = SettingsPage(root, app)
    page._restore_backup()

    assert len(open_calls) == 0, "dacă utilizatorul refuză confirmarea, nu trebuie deschis niciun dialog de fișier"
    assert app.destroyed is False


def test_restore_cancelled_at_file_picker_does_nothing(root, app, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(settings_module.filedialog, "askopenfilename", lambda **k: "")

    page = SettingsPage(root, app)
    page._restore_backup()

    assert app.destroyed is False


def test_restore_rejects_file_missing_expected_tables(root, app, tmp_path, monkeypatch):
    bad_file = tmp_path / "not_a_library_backup.db"
    conn = sqlite3.connect(str(bad_file))
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(settings_module.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(settings_module.filedialog, "askopenfilename", lambda **k: str(bad_file))
    errors = []
    monkeypatch.setattr(
        settings_module.messagebox, "showerror", lambda title, msg, **k: errors.append((title, msg))
    )

    page = SettingsPage(root, app)
    page._restore_backup()

    assert len(errors) == 1
    assert app.destroyed is False


def test_restore_replaces_data_with_safety_backup(root, app, tmp_path, monkeypatch):
    # "app" reprezintă baza de date curentă a aplicației, cu o carte
    # existentă -- trebuie să dispară după restaurare, dar să rămână
    # recuperabilă din backup-ul de siguranță.
    cat_id = app.db.get_or_create_category("Test Category")
    app.db.add_book(None, "Carte Curenta Inainte De Restaurare", None, None, "", cat_id)

    # Fișierul de backup din care se restaurează -- o bază complet
    # separată, cu o altă carte.
    backup_src_path = tmp_path / "old_backup.db"
    backup_src_db = Database(db_path=str(backup_src_path))
    backup_cat_id = backup_src_db.get_or_create_category("Alta Categorie")
    backup_src_db.add_book(None, "Carte Din Backup Restaurat", None, None, "", backup_cat_id)

    safety_dir = tmp_path / "SafetyBackups"
    settings_service.set_backup_dir(str(safety_dir))

    monkeypatch.setattr(settings_module.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(
        settings_module.filedialog, "askopenfilename", lambda **k: str(backup_src_path)
    )
    infos = []
    monkeypatch.setattr(
        settings_module.messagebox, "showinfo", lambda title, msg, **k: infos.append((title, msg))
    )

    page = SettingsPage(root, app)
    page._restore_backup()

    # Aplicația a fost "închisă" (repornire necesară).
    assert app.destroyed is True
    assert len(infos) == 1

    # Fișierul viu al aplicației conține acum datele din backup-ul ales.
    live_titles = _book_titles(app.db.db_path)
    assert live_titles == {"Carte Din Backup Restaurat"}

    # Datele de dinainte de restaurare au fost salvate automat.
    safety_files = list(safety_dir.glob("biblioteca_backup_inainte_de_restaurare_*.db"))
    assert len(safety_files) == 1
    assert _book_titles(safety_files[0]) == {"Carte Curenta Inainte De Restaurare"}


# ------------------------------------------------------------------
# Backup automat (checkbox + retenție) și zile de împrumut implicite
# ------------------------------------------------------------------
def test_auto_backup_checkbox_reflects_saved_state(root, app):
    settings_service.set_auto_backup_enabled(True)
    page = SettingsPage(root, app)
    assert page.auto_backup_var.get() is True


def test_toggling_auto_backup_checkbox_persists(root, app):
    assert settings_service.get_auto_backup_enabled() is False
    page = SettingsPage(root, app)

    page.auto_backup_var.set(True)
    page._toggle_auto_backup()
    assert settings_service.get_auto_backup_enabled() is True

    page.auto_backup_var.set(False)
    page._toggle_auto_backup()
    assert settings_service.get_auto_backup_enabled() is False


def test_save_retention_persists_valid_value(root, app, monkeypatch):
    monkeypatch.setattr(settings_module.messagebox, "showinfo", lambda *a, **k: None)
    page = SettingsPage(root, app)

    page.retention_entry.delete(0, "end")
    page.retention_entry.insert(0, "5")
    page._save_retention()

    assert settings_service.get_auto_backup_retention() == 5


def test_save_retention_rejects_invalid_value(root, app, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        settings_module.messagebox, "showwarning", lambda title, msg, **k: warnings.append(msg)
    )
    page = SettingsPage(root, app)

    page.retention_entry.delete(0, "end")
    page.retention_entry.insert(0, "abc")
    page._save_retention()

    assert len(warnings) == 1
    # valoarea implicită nu a fost schimbată de o intrare invalidă
    assert settings_service.get_auto_backup_retention() == settings_service.DEFAULT_AUTO_BACKUP_RETENTION


def test_default_loan_days_field_reflects_saved_value(root, app):
    settings_service.set_default_loan_days(30)
    page = SettingsPage(root, app)
    assert page.loan_days_entry.get() == "30"


def test_save_default_loan_days_persists_valid_value(root, app, monkeypatch):
    monkeypatch.setattr(settings_module.messagebox, "showinfo", lambda *a, **k: None)
    page = SettingsPage(root, app)

    page.loan_days_entry.delete(0, "end")
    page.loan_days_entry.insert(0, "21")
    page._save_default_loan_days()

    assert settings_service.get_default_loan_days() == 21


def test_save_default_loan_days_rejects_invalid_value(root, app, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        settings_module.messagebox, "showwarning", lambda title, msg, **k: warnings.append(msg)
    )
    original = settings_service.get_default_loan_days()
    page = SettingsPage(root, app)

    page.loan_days_entry.delete(0, "end")
    page.loan_days_entry.insert(0, "0")
    page._save_default_loan_days()

    assert len(warnings) == 1
    assert settings_service.get_default_loan_days() == original
