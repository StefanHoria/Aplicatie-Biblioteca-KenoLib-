# config.py
"""
Configurări globale ale aplicației.
Centralizează toate constantele (căi fișiere, URL-uri API, praguri ML,
parametri serial) astfel încât să poată fi modificate dintr-un singur loc.
"""

import os
import sys

# Când aplicația rulează ca executabil PyInstaller (`sys.frozen`), fișierele
# de date (bază de date, model ML) trebuie scrise lângă executabil, nu în
# folderul temporar de extracție (`sys._MEIPASS`), care este șters/recreat
# la fiecare pornire — altfel datele s-ar pierde de la o rulare la alta.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Bază de date ---
DB_PATH = os.path.join(BASE_DIR, "library.db")

# --- Setări persistente (ex. locația folderului de backup) ---
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")

# --- Iconiță aplicație ---
# Spre deosebire de BASE_DIR (folosit pentru date scrise de utilizator,
# care trebuie să stea lângă executabil ca să nu se piardă la o
# reconstruire), iconița e un fișier static, needitabil -- e potrivit
# să fie inclusă direct în pachetul PyInstaller (extras în sys._MEIPASS
# la rulare), nu copiată manual lângă exe.
if getattr(sys, "frozen", False):
    ICON_PATH = os.path.join(sys._MEIPASS, "app_icon.ico")
else:
    ICON_PATH = os.path.join(BASE_DIR, "app_icon.ico")

# --- Machine Learning ---
ML_MODEL_PATH = os.path.join(BASE_DIR, "ml_model.joblib")
# Pragul de încredere sub care categoria devine "De Confirmat" se calculează
# relativ la numărul de categorii, nu ca o valoare fixă: cu N categorii,
# șansa aleatoare este 1/N, iar probabilitatea maximă tinde să scadă pe
# măsură ce sunt mai multe categorii (masa de probabilitate se împarte).
# O valoare fixă (ex. 0.45) ar respinge aproape orice predicție corectă
# într-o bibliotecă cu multe categorii. Pragul efectiv folosit e
# max(ML_MIN_CONFIDENCE, ML_CONFIDENCE_RATIO / nr_categorii).
ML_CONFIDENCE_RATIO = 1.9
ML_MIN_CONFIDENCE = 0.08
ML_MIN_SAMPLES = 4               # minim de cărți etichetate necesare pentru antrenare
ML_MIN_CLASSES = 2               # minim de categorii distincte necesare pentru antrenare
UNCONFIRMED_CATEGORY = "De Confirmat"

# --- Scanner GM65 (serial) ---
SERIAL_BAUDRATE = 9600
SERIAL_READ_TIMEOUT = 1          # secunde
SCANNER_POLL_INTERVAL_MS = 300   # interval polling coadă scanner in GUI (ms)

# --- API-uri cărți ---
GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
GOOGLE_BOOKS_SEARCH_API = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_API = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
OPEN_LIBRARY_SEARCH_API = "https://openlibrary.org/search.json"
API_TIMEOUT = 6                  # secunde

# --- Împrumuturi ---
DEFAULT_LOAN_DAYS = 14

# --- Categorii implicite (create automat la prima rulare) ---
DEFAULT_CATEGORIES = [
    "Literatură română", "Literatură străină", "Poezie", "Teatru",
    "Fantezie & SF", "Thriller & Mister", "Non-ficțiune", "Știință",
    "Istorie", "Biografie", "Filozofie", "Psihologie",
    "Economie & Afaceri", "Copii", "Tehnologie", "Artă",
    UNCONFIRMED_CATEGORY,
]

# --- Interfață ---
APP_TITLE = "Sistem de Gestiune Bibliotecă"
APP_GEOMETRY = "1250x760"
APPEARANCE_MODE = "System"       # "System" | "Dark" | "Light"
COLOR_THEME = "blue"

# --- Culori de stare (folosite consecvent în toate paginile) ---
# Fiecare stare are, unde e cazul, două variante: "TEXT" (mai deschisă,
# citeață ca text simplu pe fundalul paginii) și "BG" (mai închisă,
# pentru fundalul solid al unui rând de tabel sau al unui buton, cu text
# alb deasupra) -- centralizate aici ca să nu apară nuanțe ușor diferite
# ale aceleiași culori, presărate prin fișiere diferite.
COLOR_SUCCESS = "#2fa84f"          # confirmări, retur reușit, conexiuni active
COLOR_SUCCESS_HOVER = "#238040"
COLOR_DANGER_TEXT = "#e04444"      # avertismente/erori/restanțe, ca text
COLOR_DANGER_BG = "#b3261e"        # ștergere, fundal rând restant
COLOR_DANGER_BG_HOVER = "#8c1d17"
COLOR_WARNING_BG = "#b3401f"       # acțiuni distructive dar intenționate (restaurare backup)
COLOR_WARNING_BG_HOVER = "#8f3018"
COLOR_UNCONFIRMED_TEXT = "#d69a1f"  # cărți "De Confirmat" (categorie nesigură), ca text
COLOR_UNCONFIRMED_BG = "#8a6d1f"    # fundal rând pentru cărți "De Confirmat"
COLOR_ROW_HIGHLIGHT_FG = "#ffffff"  # culoarea textului pe un rând cu fundal solid (restant/nesigur)

# --- CZU (Clasificarea Zecimală Universală / UDC) ---
# Sugestii de pornire, NU o catalogare oficială: CZU are subdiviziuni mult
# mai fine decât poate acoperi o mapare simplă categorie -> cod (ex. limbi,
# perioade istorice, sub-genuri). Codurile de mai jos sunt clasele generale
# UDC, bine documentate și stabile (0-9 sunt cele 10 clase principale ale
# schemei UDC; 821.135.1 = literatură română, 821-1/-2/-3 = poezie/teatru/
# proză ca formă literară — auxiliare standard, independente de limbă).
# Bibliotecarul ar trebui să verifice/rafineze codul folosind tabelele
# oficiale CZU pentru o catalogare completă.
CZU_SUGGESTIONS = {
    "Literatură română": "821.135.1",
    "Literatură străină": "821",
    "Poezie": "821-1",
    "Teatru": "821-2",
    "Fantezie & SF": "821-31",
    "Thriller & Mister": "821-31",
    "Non-ficțiune": "0",
    "Știință": "5",
    "Istorie": "94",
    "Biografie": "929",
    "Filozofie": "1",
    "Psihologie": "159.9",
    "Economie & Afaceri": "33",
    "Copii": "821-93",
    "Tehnologie": "004",
    "Artă": "7",
}


def suggest_czu(category_name):
    """Returnează un cod CZU de pornire pentru o categorie, sau "" dacă nu există."""
    return CZU_SUGGESTIONS.get(category_name, "")
