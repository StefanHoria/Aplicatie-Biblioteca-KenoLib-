# utils.py
"""
Funcții utilitare comune, folosite din mai multe pagini ale interfeței:
- stilizarea widget-urilor ttk.Treeview (tabele) astfel încât să se
  potrivească cu tema CustomTkinter (Dark/Light), lucru pe care
  CustomTkinter nu îl face automat pentru widget-uri ttk clasice;
- conversii simple de date pentru afișare.
"""

import re
import tkinter
from datetime import date, datetime, timedelta
from tkinter import ttk

import customtkinter as ctk

from config import (
    BRAND_ACCENT, BRAND_ACCENT_DARK, BRAND_ROW_SELECT_LIGHT, BRAND_ROW_SELECT_DARK,
)

TREEVIEW_STYLE_NAME = "Custom.Treeview"


def _resolved_bg(widget):
    """Culoarea reală (hex, pentru modul curent) a fundalului pe care stă un
    widget -- urcă la părinte cât timp fundalul e „transparent”. Necesară
    fiindcă tkinter.Canvas nu suportă transparență, deci trebuie să-i dăm
    exact culoarea din spate ca iconița desenată să nu aibă un chenar vizibil."""
    try:
        color = widget.cget("fg_color")
    except Exception:
        color = None
    if color in (None, "transparent"):
        master = getattr(widget, "master", None)
        if master is not None:
            return _resolved_bg(master)
        return "#2b2b2b"
    if hasattr(widget, "_apply_appearance_mode"):
        return widget._apply_appearance_mode(color)
    return color


def make_logo_icon(parent, size=30, color=None):
    """Iconița KenoLib desenată vectorial (o carte deschisă, doar CONTUR) pe un
    tkinter.Canvas -- nu o imagine. Se potrivește cu accentul de brand și e
    crisp la orice dimensiune. Returnează Canvas-ul (are `.set_bg()` pentru a
    reîmprospăta fundalul la schimbarea temei Dark/Light)."""
    color = color or BRAND_ACCENT
    canvas = tkinter.Canvas(
        parent, width=size, height=size, highlightthickness=0, bd=0,
        bg=_resolved_bg(parent),
    )
    k = size / 32.0

    def P(*pts):
        return [round(v * k) for v in pts]

    stroke = max(2, round(2.3 * k))
    thin = max(1, round(1.1 * k))
    # cele două pagini (contur închis) împart cotorul din mijloc
    canvas.create_polygon(*P(16, 8, 5, 10, 5, 25, 16, 27),
                          outline=color, fill="", width=stroke, joinstyle="round")
    canvas.create_polygon(*P(16, 8, 27, 10, 27, 25, 16, 27),
                          outline=color, fill="", width=stroke, joinstyle="round")
    # linii scurte care sugerează textul de pe pagini
    for yy in (14, 18, 22):
        canvas.create_line(*P(8, yy, 13, yy - 0.5), fill=color, width=thin)
        canvas.create_line(*P(19, yy - 0.5, 24, yy), fill=color, width=thin)

    canvas.set_bg = lambda: canvas.configure(bg=_resolved_bg(parent))
    return canvas


def is_dark_mode():
    return ctk.get_appearance_mode() == "Dark"


def style_treeview(style: ttk.Style = None):
    """
    Configurează culorile ttk.Treeview în funcție de modul curent
    (Dark/Light) al CustomTkinter. Trebuie apelată din nou după orice
    schimbare de temă și înainte de a construi/afișa un Treeview.
    """
    style = style or ttk.Style()
    style.theme_use("default")

    # header_fg = accentul de brand: textul antetului preia albastrul KenoLib,
    # legând tabelele de restul identității vizuale (butoane, carduri, sidebar).
    # selected = tot o nuanță de brand, nu albastrul generic dinainte.
    if is_dark_mode():
        bg, fg, field_bg, header_bg = "#2b2b2b", "#dce4ee", "#242424", "#2f2f2f"
        selected = BRAND_ROW_SELECT_DARK
        header_fg = BRAND_ACCENT
    else:
        bg, fg, field_bg, header_bg = "#ffffff", "#1a1a1a", "#f5f5f5", "#eaeaea"
        selected = BRAND_ROW_SELECT_LIGHT
        header_fg = BRAND_ACCENT_DARK

    style.configure(
        TREEVIEW_STYLE_NAME,
        background=field_bg,
        foreground=fg,
        fieldbackground=field_bg,
        borderwidth=0,
        rowheight=38,       # potrivit cu fontul mai mare de mai jos
        font=("", 13),      # aliniat cu textul de corp din restul aplicației (nav 14, etichete 13)
    )
    style.map(TREEVIEW_STYLE_NAME, background=[("selected", selected)])
    style.configure(
        f"{TREEVIEW_STYLE_NAME}.Heading",
        background=header_bg,
        foreground=header_fg,
        borderwidth=0,
        relief="flat",
        padding=(6, 8),
        font=("", 13, "bold"),
    )
    style.map(f"{TREEVIEW_STYLE_NAME}.Heading", background=[("active", header_bg)])
    return style


def stripe_color():
    """Culoare pentru rândurile alternante (zebra striping) dintr-un
    ttk.Treeview -- foarte apropiată de fundalul normal al tabelului
    (style_treeview), ca separarea dintre rânduri să fie subtilă, nu un
    contrast dur. Trebuie recalculată după orice schimbare Dark/Light,
    la fel ca style_treeview()."""
    return "#2b2b2b" if is_dark_mode() else "#ececec"


def today_iso():
    return date.today().isoformat()


def due_date_iso(days_from_today):
    return (date.today() + timedelta(days=days_from_today)).isoformat()


def format_date_ro(iso_str):
    """Convertește 'YYYY-MM-DD' -> 'DD.MM.YYYY' pentru afișare; gol dacă None."""
    if not iso_str:
        return ""
    try:
        return datetime.strptime(iso_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return iso_str


def is_overdue(due_date_str, return_date_str):
    if return_date_str:
        return False
    if not due_date_str:
        return False
    return due_date_str < today_iso()


def normalize_isbn(isbn):
    """Elimină cratimele/spațiile dintr-un cod scanat sau tastat manual."""
    return re.sub(r"[\s-]", "", (isbn or "").strip().upper())


def _is_valid_isbn10(isbn):
    if not isbn[:9].isdigit() or not (isbn[9].isdigit() or isbn[9] == "X"):
        return False
    total = sum((10 - i) * (10 if ch == "X" else int(ch)) for i, ch in enumerate(isbn))
    return total % 11 == 0


def _is_valid_isbn13(isbn):
    # Un ISBN-13 este un caz special de EAN-13, rezervat prefixelor
    # "Bookland" 978/979 — verificarea doar a cifrei de control (mod 10)
    # ar accepta orice cod EAN-13 valid (sau chiar "0000000000000",
    # care trece checksum-ul trivial), de aceea prefixul e obligatoriu.
    if not isbn.isdigit() or not (isbn.startswith("978") or isbn.startswith("979")):
        return False
    total = sum((1 if i % 2 == 0 else 3) * int(ch) for i, ch in enumerate(isbn))
    return total % 10 == 0


def is_valid_isbn(isbn):
    """Validează cifra de control a unui cod ISBN-10 sau ISBN-13."""
    isbn = normalize_isbn(isbn)
    if len(isbn) == 10:
        return _is_valid_isbn10(isbn)
    if len(isbn) == 13:
        return _is_valid_isbn13(isbn)
    return False


# --------------------------------------------------------------------------
# Validări pentru câmpurile din formulare (carte / cititor)
# --------------------------------------------------------------------------
# Scopul lor e să prindă greșelile evidente de tastare -- litere într-un număr
# de telefon, un an aiurea, un CZU cu text -- și să le explice, în loc ca
# valoarea greșită să fie ignorată în tăcere la salvare (comportamentul de
# dinainte pentru An și Nr. exemplare). Sunt intenționat permisive: un catalog
# real conține și date neobișnuite, iar o validare prea strictă ar bloca
# inutil munca bibliotecarului.
#
# Toate acceptă textul gol ca valid -- câmpurile sunt opționale; obligativitatea
# se verifică separat, acolo unde e cazul (titlu, nume).

MIN_PUB_YEAR = 1450          # ~apariția tiparului; orice an mai mic e o greșeală
MIN_PHONE_DIGITS = 6         # sub atât nu e un număr de telefon real

_PHONE_ALLOWED_RE = re.compile(r"^[0-9+()\-./\s]+$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Semnele permise în notația CZU/UDC: separatoare zecimale, intervale (/) și
# auxiliarele comune (paranteze, ghilimele, + : = *).
_CZU_ALLOWED_RE = re.compile(r"^[0-9.\-/()\[\]'\"+:=*\s]+$")


def is_plausible_pub_year(value):
    """Anul apariției: număr întreg între MIN_PUB_YEAR și anul viitor
    (cărțile apărute la sfârșit de an poartă adesea anul următor)."""
    value = (value or "").strip()
    if not value:
        return True
    if not value.isdigit():
        return False
    return MIN_PUB_YEAR <= int(value) <= date.today().year + 1


def is_plausible_phone(value):
    """Număr de telefon: doar cifre și separatoarele uzuale (+ - . / ( ) spațiu),
    cu cel puțin MIN_PHONE_DIGITS cifre. Nu impune un format anume -- se folosesc
    deopotrivă „0722123456”, „0722 123 456”, „+40 722 123 456”."""
    value = (value or "").strip()
    if not value:
        return True
    if not _PHONE_ALLOWED_RE.match(value):
        return False
    return sum(ch.isdigit() for ch in value) >= MIN_PHONE_DIGITS


def is_plausible_email(value):
    """Verificare minimală de formă: ceva@ceva.ceva, fără spații. Validarea
    completă a unui email nu se poate face decât trimițându-i un mesaj."""
    value = (value or "").strip()
    if not value:
        return True
    return bool(_EMAIL_RE.match(value))


def is_plausible_czu(value):
    """Cod CZU: cifre plus semnele din notația UDC, cu cel puțin o cifră.
    Verificare permisivă -- sintaxa CZU completă e mult mai bogată (vezi
    config.CZU_SUGGESTIONS); aici se resping doar codurile cu litere/text."""
    value = (value or "").strip()
    if not value:
        return True
    if not _CZU_ALLOWED_RE.match(value):
        return False
    return any(ch.isdigit() for ch in value)
