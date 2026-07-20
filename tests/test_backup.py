"""
Teste pentru funcția de backup: Database.backup_to() (database.py) și
persistența locației alese de utilizator (settings_service.py).
"""

import sqlite3

from database import Database
import settings_service


def test_backup_to_creates_full_consistent_copy(tmp_path):
    src_path = tmp_path / "source.db"
    db = Database(db_path=str(src_path))
    cat_id = db.get_or_create_category("Test Category")
    db.add_book("9780441172719", "Dune", "Frank Herbert", 1965, "desc", cat_id)

    dest_path = tmp_path / "backup.db"
    db.backup_to(str(dest_path))

    assert dest_path.exists()
    conn = sqlite3.connect(str(dest_path))
    cur = conn.cursor()
    assert cur.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert cur.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 1
    assert cur.execute("SELECT title FROM books").fetchone()[0] == "Dune"
    # Categoriile implicite (seed) trebuie să fie prezente în backup la fel
    # ca în original.
    original_categories = db.get_all_categories()
    backup_categories = cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    assert backup_categories == len(original_categories)
    conn.close()


def test_backup_is_independent_snapshot(tmp_path):
    # O modificare făcută în baza originală DUPĂ backup nu trebuie să
    # apară în fișierul de backup deja creat.
    src_path = tmp_path / "source.db"
    db = Database(db_path=str(src_path))
    cat_id = db.get_or_create_category("Test Category")
    db.add_book(None, "Carte inainte de backup", None, None, "", cat_id)

    dest_path = tmp_path / "backup.db"
    db.backup_to(str(dest_path))

    db.add_book(None, "Carte dupa backup", None, None, "", cat_id)

    conn = sqlite3.connect(str(dest_path))
    titles = {row[0] for row in conn.execute("SELECT title FROM books")}
    conn.close()
    assert "Carte inainte de backup" in titles
    assert "Carte dupa backup" not in titles


def test_settings_persist_backup_dir(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_service, "SETTINGS_PATH", str(settings_path))

    assert settings_service.get_backup_dir() == ""

    chosen_dir = str(tmp_path / "MyBackups")
    settings_service.set_backup_dir(chosen_dir)

    assert settings_service.get_backup_dir() == chosen_dir
    assert settings_path.exists()


def test_settings_survive_missing_or_corrupt_file(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_service, "SETTINGS_PATH", str(settings_path))
    # Fișier inexistent -> valoare implicită, nu eroare.
    assert settings_service.get_backup_dir() == ""

    settings_path.write_text("{not valid json", encoding="utf-8")
    assert settings_service.get_backup_dir() == ""
