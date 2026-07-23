# config.py
"""
Configurări globale ale aplicației.
Centralizează toate constantele (căi fișiere, URL-uri API, praguri ML,
parametri serial) astfel încât să poată fi modificate dintr-un singur loc.
"""

import os
import sys

# Când aplicația rulează ca executabil PyInstaller (`sys.frozen`), datele
# scrise de utilizator (bază de date, setări, model ML) NU trebuie ținute
# lângă executabil: dacă aplicația e instalată cu installerul (ex. în
# Program Files), acel folder este doar-citire pentru un utilizator obișnuit,
# iar scrierile ar eșua. De aceea, în modul instalat folosim o locație
# per-utilizator, garantat inscriptibilă, care SUPRAVIEȚUIEȘTE
# dezinstalării/actualizării aplicației: %LOCALAPPDATA%\KenoLib (astfel,
# reinstalarea sau o versiune nouă nu șterg catalogul bibliotecii).
#
# Nota: `sys._MEIPASS` (folderul temporar de extracție) este șters/recreat la
# fiecare pornire — nu e potrivit pentru date persistente; e folosit doar
# pentru resurse doar-citire împachetate (iconiță, model ML de pornire).
if getattr(sys, "frozen", False):
    _local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    DATA_DIR = os.path.join(_local, "KenoLib")
    os.makedirs(DATA_DIR, exist_ok=True)
    APP_DIR = os.path.dirname(sys.executable)      # folderul programului (doar-citire)
else:
    # În dezvoltare (rulare din surse), totul rămâne în folderul proiectului,
    # ca până acum — comod pentru teste și depanare.
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = DATA_DIR

# Nume păstrat pentru compatibilitate cu restul codului (referă folderul de date).
BASE_DIR = DATA_DIR

# --- Bază de date ---
DB_PATH = os.path.join(DATA_DIR, "library.db")

# --- Setări persistente (profil, locația folderului de backup, etc.) ---
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

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
# Modelul antrenabil/rescriabil stă în folderul de date (inscriptibil).
ML_MODEL_PATH = os.path.join(DATA_DIR, "ml_model.joblib")
# Model pre-antrenat, împachetat în executabil (doar-citire). La prima
# pornire e copiat în ML_MODEL_PATH (vezi bootstrap_data_dir), ca aplicația
# să pornească deja cu clasificare funcțională, apoi să-l poată re-antrena.
if getattr(sys, "frozen", False):
    ML_MODEL_SEED = os.path.join(sys._MEIPASS, "ml_model.joblib")
else:
    ML_MODEL_SEED = None


def bootstrap_data_dir():
    """Pregătește folderul de date la pornirea versiunii INSTALATE:
    1) copiază modelul ML pre-antrenat împachetat, dacă lipsește din DATA_DIR;
    2) migrează o eventuală bază de date/setări dintr-o rulare PORTABILĂ
       anterioară (fișiere aflate lângă executabil), ca datele existente ale
       utilizatorului să nu pară pierdute după trecerea la versiunea instalată.
    Nu are niciun efect când aplicația rulează din surse (dezvoltare)."""
    if not getattr(sys, "frozen", False):
        return
    import shutil

    legacy_dir = os.path.dirname(sys.executable)
    if os.path.abspath(legacy_dir) != os.path.abspath(DATA_DIR):
        for name in ("library.db", "settings.json"):
            src = os.path.join(legacy_dir, name)
            dst = os.path.join(DATA_DIR, name)
            if os.path.exists(src) and not os.path.exists(dst):
                try:
                    shutil.copy2(src, dst)
                except OSError:
                    pass

    if ML_MODEL_SEED and os.path.exists(ML_MODEL_SEED) and not os.path.exists(ML_MODEL_PATH):
        try:
            shutil.copy2(ML_MODEL_SEED, ML_MODEL_PATH)
        except OSError:
            pass
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
APP_TITLE = "KenoLib"
APP_GEOMETRY = "1250x760"
APPEARANCE_MODE = "System"       # "System" | "Dark" | "Light"
COLOR_THEME = "blue"             # temă CTk de bază; accentul e apoi rescris cu culorile de brand de mai jos

# --- Identitate vizuală (accent de brand, derivat din iconița KenoLib) ---
# Albastrul din fundalul iconiței devine accentul întregii aplicații, în locul
# albastrului standard CustomTkinter -- aplicat consecvent la butoane, meniuri,
# bara de progres, indicatorul din sidebar, selecția din tabele etc.
# Perechile sunt [mod_luminos, mod_întunecat]: nuanța vie pentru fundal deschis,
# una mai adâncă pentru fundal întunecat / stare hover.
BRAND_ACCENT = "#3e8ede"           # albastrul iconiței (accent principal, mod luminos)
BRAND_ACCENT_DARK = "#2e6fb0"      # varianta mai adâncă (mod întunecat / hover în mod luminos)
BRAND_ACCENT_DARKER = "#245a93"    # hover în mod întunecat
BRAND_ROW_SELECT_LIGHT = "#cfe3f9"  # fundal rând selectat în tabel (mod luminos)
BRAND_ROW_SELECT_DARK = "#1e4d78"   # fundal rând selectat în tabel (mod întunecat)

# Font distinctiv, „funky”, pentru titlul textual „KenoLib” (sidebar / ecran de
# încărcare / bun-venit) -- Cooper Black e un display font gros, retro-prietenos,
# livrat cu Windows. Dacă lipsește, Tkinter cade elegant pe fontul implicit.
BRAND_TITLE_FONT = "Cooper Black"

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
