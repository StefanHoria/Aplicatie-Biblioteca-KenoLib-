# settings_service.py
"""
Persistă setările aplicației (ex. locația folderului de backup) într-un
fișier JSON simplu, lângă baza de date. Spre deosebire de constantele din
config.py, aceste valori sunt alese de utilizator la rulare și trebuie să
rămână valabile între porniri ale aplicației (și să nu fie șterse la
reconstruirea executabilului).
"""

import glob
import json
import os
from datetime import date, datetime

from config import SETTINGS_PATH, DEFAULT_LOAN_DAYS

AUTO_BACKUP_PREFIX = "biblioteca_autobackup_"
DEFAULT_AUTO_BACKUP_RETENTION = 10


def load_settings():
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def get_backup_dir():
    return load_settings().get("backup_dir", "")


def set_backup_dir(path):
    settings = load_settings()
    settings["backup_dir"] = path
    save_settings(settings)


def get_last_backup_info():
    """Returnează {"timestamp": iso_str, "book_count": int, "path": str}
    despre cel mai recent backup reușit, sau None dacă nu s-a făcut încă
    niciunul. Persistat (nu doar ținut în memorie) ca eticheta din pagina
    Setări să arate informația corectă și după o repornire a aplicației."""
    return load_settings().get("last_backup")


def set_last_backup_info(info):
    settings = load_settings()
    settings["last_backup"] = info
    save_settings(settings)


# ------------------------------------------------------------------
# Backup automat
# ------------------------------------------------------------------
def get_auto_backup_enabled():
    return load_settings().get("auto_backup_enabled", False)


def set_auto_backup_enabled(value):
    settings = load_settings()
    settings["auto_backup_enabled"] = bool(value)
    save_settings(settings)


def get_auto_backup_retention():
    return load_settings().get("auto_backup_retention", DEFAULT_AUTO_BACKUP_RETENTION)


def set_auto_backup_retention(n):
    settings = load_settings()
    settings["auto_backup_retention"] = max(1, int(n))
    save_settings(settings)


def _get_last_auto_backup_date():
    return load_settings().get("last_auto_backup_date", "")


def _set_last_auto_backup_date(date_str):
    settings = load_settings()
    settings["last_auto_backup_date"] = date_str
    save_settings(settings)


def _cleanup_old_auto_backups(backup_dir):
    """Șterge doar backup-urile AUTOMATE (prefix distinct de cele
    manuale) care depășesc limita de păstrare configurată. Backup-urile
    făcute manual de utilizator (via "Backup acum" sau înainte de o
    restaurare) au alt prefix de fișier și nu sunt atinse niciodată aici."""
    retention = get_auto_backup_retention()
    files = sorted(glob.glob(os.path.join(backup_dir, f"{AUTO_BACKUP_PREFIX}*.db")))
    for old_file in files[:-retention] if retention > 0 else []:
        try:
            os.remove(old_file)
        except OSError:
            pass


def maybe_run_auto_backup(db):
    """Face un backup automat dacă: e activat, există o locație de backup
    configurată, și nu s-a mai făcut deja unul azi (evită să se acumuleze
    zeci de fișiere dacă aplicația e închisă/deschisă de mai multe ori pe
    zi). Eșecurile sunt ignorate silențios -- nu trebuie să blocheze
    închiderea aplicației pentru o problemă de backup."""
    if not get_auto_backup_enabled():
        return
    backup_dir = get_backup_dir()
    if not backup_dir:
        return
    today = date.today().isoformat()
    if _get_last_auto_backup_date() == today:
        return
    try:
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dest_path = os.path.join(backup_dir, f"{AUTO_BACKUP_PREFIX}{timestamp}.db")
        db.backup_to(dest_path)
        _set_last_auto_backup_date(today)
        set_last_backup_info({
            "timestamp": datetime.now().isoformat(),
            "book_count": db.get_dashboard_stats()["total_books"],
        })
        _cleanup_old_auto_backups(backup_dir)
    except Exception:
        pass


# ------------------------------------------------------------------
# Profil bibliotecă (nume + școală) -- cerut la prima pornire, editabil în Setări
# ------------------------------------------------------------------
def get_profile():
    settings = load_settings()
    return {
        "name": settings.get("profile_name", ""),
        "school": settings.get("profile_school", ""),
    }


def set_profile(name, school):
    settings = load_settings()
    settings["profile_name"] = (name or "").strip()
    settings["profile_school"] = (school or "").strip()
    save_settings(settings)


def is_profile_complete():
    """True dacă profilul a fost completat (ambele câmpuri). Fals la prima
    pornire -- declanșează dialogul de configurare."""
    profile = get_profile()
    return bool(profile["name"] and profile["school"])


# ------------------------------------------------------------------
# Împrumuturi
# ------------------------------------------------------------------
def get_default_loan_days():
    return load_settings().get("default_loan_days", DEFAULT_LOAN_DAYS)


def set_default_loan_days(days):
    settings = load_settings()
    settings["default_loan_days"] = max(1, int(days))
    save_settings(settings)
