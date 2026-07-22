# utils.py
"""
Funcții utilitare comune, folosite din mai multe pagini ale interfeței:
- stilizarea widget-urilor ttk.Treeview (tabele) astfel încât să se
  potrivească cu tema CustomTkinter (Dark/Light), lucru pe care
  CustomTkinter nu îl face automat pentru widget-uri ttk clasice;
- conversii simple de date pentru afișare.
"""

import re
from datetime import date, datetime, timedelta
from tkinter import ttk

import customtkinter as ctk

from config import (
    BRAND_ACCENT, BRAND_ACCENT_DARK, BRAND_ROW_SELECT_LIGHT, BRAND_ROW_SELECT_DARK,
)

TREEVIEW_STYLE_NAME = "Custom.Treeview"


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
