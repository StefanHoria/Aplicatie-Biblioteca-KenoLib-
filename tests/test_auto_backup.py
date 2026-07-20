"""
Teste pentru backup-ul automat (settings_service.maybe_run_auto_backup)
și pentru zilele de împrumut implicite configurabile.

Reguli acoperite:
- nu face nimic dacă e dezactivat sau nu există o locație de backup;
- face UN backup automat pe zi, nu unul de fiecare dată când se închide
  aplicația;
- backup-urile automate au prefix distinct de cele manuale, iar
  curățarea (retenția) nu atinge NICIODATĂ un backup manual;
- get_default_loan_days() are ca implicit config.DEFAULT_LOAN_DAYS dacă
  utilizatorul nu a suprascris nimic.
"""

import sqlite3
from datetime import date, datetime, timedelta

import pytest

import settings_service
from config import DEFAULT_LOAN_DAYS
from database import Database


@pytest.fixture(autouse=True)
def isolated_settings_file(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_service, "SETTINGS_PATH", str(settings_path))
    yield


@pytest.fixture
def db(tmp_path):
    return Database(db_path=str(tmp_path / "test.db"))


# ------------------------------------------------------------------
# maybe_run_auto_backup
# ------------------------------------------------------------------
def test_does_nothing_when_disabled(tmp_path, db):
    backup_dir = tmp_path / "Backups"
    settings_service.set_backup_dir(str(backup_dir))
    # auto_backup_enabled implicit False -- nu s-a apelat set_auto_backup_enabled

    settings_service.maybe_run_auto_backup(db)

    assert not backup_dir.exists() or list(backup_dir.glob("*.db")) == []
    assert settings_service.get_last_backup_info() is None


def test_does_nothing_without_configured_backup_dir(db):
    settings_service.set_auto_backup_enabled(True)
    # niciun get_backup_dir() setat

    settings_service.maybe_run_auto_backup(db)

    assert settings_service.get_last_backup_info() is None


def test_creates_backup_when_enabled_and_dir_set(tmp_path, db):
    backup_dir = tmp_path / "Backups"
    settings_service.set_auto_backup_enabled(True)
    settings_service.set_backup_dir(str(backup_dir))

    settings_service.maybe_run_auto_backup(db)

    files = list(backup_dir.glob("biblioteca_autobackup_*.db"))
    assert len(files) == 1
    conn = sqlite3.connect(str(files[0]))
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()

    info = settings_service.get_last_backup_info()
    assert info is not None
    assert info["book_count"] == 0


def test_does_not_run_twice_the_same_day(tmp_path, db):
    backup_dir = tmp_path / "Backups"
    settings_service.set_auto_backup_enabled(True)
    settings_service.set_backup_dir(str(backup_dir))

    settings_service.maybe_run_auto_backup(db)
    settings_service.maybe_run_auto_backup(db)
    settings_service.maybe_run_auto_backup(db)

    files = list(backup_dir.glob("biblioteca_autobackup_*.db"))
    assert len(files) == 1, "nu trebuie să se acumuleze mai multe backup-uri automate în aceeași zi"


def test_runs_again_on_a_new_day(tmp_path, db, monkeypatch):
    backup_dir = tmp_path / "Backups"
    settings_service.set_auto_backup_enabled(True)
    settings_service.set_backup_dir(str(backup_dir))

    settings_service.maybe_run_auto_backup(db)
    first_files = list(backup_dir.glob("biblioteca_autobackup_*.db"))
    assert len(first_files) == 1

    # Simulează trecerea la ziua următoare -- doar data ultimului backup
    # automat contează pentru decizia "s-a mai făcut azi?". (Nu putem
    # verifica prin numărul de fișiere create: în realitate cele două
    # apeluri sunt separate de ore/zile, deci numele lor -- cu rezoluție
    # de o secundă -- nu ar coincide niciodată; aici le forțăm în aceeași
    # secundă, ceea ce ar coliziona pe disc fără să spună nimic despre
    # bug-ul real vizat. Ce contează e că poarta "o dată pe zi" se
    # resetează și un NOU apel de backup chiar are loc.)
    yesterday_marker = (date.today() - timedelta(days=1)).isoformat()
    settings = settings_service.load_settings()
    settings["last_auto_backup_date"] = yesterday_marker
    settings_service.save_settings(settings)

    before_second_call = datetime.now()
    settings_service.maybe_run_auto_backup(db)

    assert settings_service._get_last_auto_backup_date() == date.today().isoformat()
    info = settings_service.get_last_backup_info()
    assert datetime.fromisoformat(info["timestamp"]) >= before_second_call.replace(microsecond=0)


def test_retention_deletes_only_old_auto_backups_never_manual(tmp_path, db):
    backup_dir = tmp_path / "Backups"
    backup_dir.mkdir()
    settings_service.set_backup_dir(str(backup_dir))
    settings_service.set_auto_backup_enabled(True)
    settings_service.set_auto_backup_retention(2)

    # 3 backup-uri automate "vechi" simulate direct pe disc (nume cu
    # timestamp-uri diferite, sortabile cronologic).
    for i, ts in enumerate(["2026-01-01_10-00-00", "2026-01-02_10-00-00", "2026-01-03_10-00-00"]):
        db.backup_to(str(backup_dir / f"biblioteca_autobackup_{ts}.db"))

    # Un backup MANUAL (prefix diferit) -- nu trebuie atins niciodată.
    manual_path = backup_dir / "biblioteca_backup_2026-01-01_09-00-00.db"
    db.backup_to(str(manual_path))

    settings_service._cleanup_old_auto_backups(str(backup_dir))

    remaining_auto = sorted(p.name for p in backup_dir.glob("biblioteca_autobackup_*.db"))
    assert len(remaining_auto) == 2, "trebuie păstrate doar ultimele 2 (limita configurată)"
    assert remaining_auto == ["biblioteca_autobackup_2026-01-02_10-00-00.db",
                               "biblioteca_autobackup_2026-01-03_10-00-00.db"]
    assert manual_path.exists(), "backup-ul manual nu trebuie șters niciodată de curățarea automată"


def test_failure_is_silent_and_does_not_raise(db, monkeypatch):
    settings_service.set_auto_backup_enabled(True)
    # Un folder care nu poate fi creat (cale invalidă pe Windows) -- nu
    # trebuie să crape închiderea aplicației pentru o eroare de backup.
    settings_service.set_backup_dir("::::invalid::::path::::")

    settings_service.maybe_run_auto_backup(db)  # nu trebuie să arunce excepție


# ------------------------------------------------------------------
# Zile de împrumut implicite
# ------------------------------------------------------------------
def test_default_loan_days_falls_back_to_config_default():
    assert settings_service.get_default_loan_days() == DEFAULT_LOAN_DAYS


def test_default_loan_days_can_be_overridden():
    settings_service.set_default_loan_days(21)
    assert settings_service.get_default_loan_days() == 21


def test_default_loan_days_rejects_non_positive_values():
    settings_service.set_default_loan_days(0)
    assert settings_service.get_default_loan_days() == 1  # clamp la minim 1
