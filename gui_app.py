# gui_app.py
"""
Fereastra principală a aplicației (View + Controller de nivel înalt din
structura MVC). Construiește layout-ul general — meniu lateral (sidebar)
de navigare stil Fluent Design/Windows 11 și o zonă de conținut în care
paginile (Dashboard, Catalog, Împrumuturi, Rapoarte, Import) sunt
comutate cu `tkraise()` — și cablează serviciile de fundal (baza de
date, clasificatorul ML și scanner-ul GM65) către paginile care au
nevoie de ele.
"""

import queue
import tkinter.messagebox as messagebox

import customtkinter as ctk

from config import (
    APP_TITLE, APP_GEOMETRY, APPEARANCE_MODE, COLOR_THEME, SCANNER_POLL_INTERVAL_MS,
    COLOR_SUCCESS, ICON_PATH,
)
from database import Database
from ml_classifier import BookClassifier
from scanner_service import ScannerService
from settings_service import maybe_run_auto_backup

from views.dashboard import DashboardPage
from views.catalog import CatalogPage
from views.loans import LoansPage
from views.reports import ReportsPage
from views.inventory import InventoryPage
from views.import_view import ImportPage
from views.settings import SettingsPage

NAV_ITEMS = [
    ("dashboard", "🏠  Dashboard", DashboardPage),
    ("catalog", "📚  Catalog Cărți", CatalogPage),
    ("loans", "🔄  Împrumuturi active", LoansPage),
    ("reports", "📊  Rapoarte", ReportsPage),
    ("inventory", "📋  Inventar", InventoryPage),
    ("import", "📥  Import Date", ImportPage),
    ("settings", "⚙️  Setări", SettingsPage),
]


def style_nav_buttons(nav_buttons, active_key):
    """Aplică accentul temei curente (același albastru ca butoanele de
    acțiune) elementului activ din sidebar, restul revenind la stilul
    neutru transparent. Separată de App.show_page() ca să poată fi
    testată fără o instanță completă de App (care ar deschide baza de
    date reală a aplicației)."""
    active_fg = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
    active_text = ctk.ThemeManager.theme["CTkButton"]["text_color"]
    for k, btn in nav_buttons.items():
        if k == active_key:
            btn.configure(fg_color=active_fg, text_color=active_text)
        else:
            btn.configure(fg_color="transparent", text_color=("gray10", "gray90"))


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode(APPEARANCE_MODE)
        ctk.set_default_color_theme(COLOR_THEME)

        self.title(APP_TITLE)
        self.geometry(APP_GEOMETRY)
        self.minsize(1000, 640)
        try:
            # Fără asta, Tkinter arată iconița implicită ("pana") în
            # bara de titlu/taskbar, chiar dacă executabilul are alta.
            self.iconbitmap(ICON_PATH)
        except Exception:
            pass  # iconița e cosmetică -- nu trebuie să blocheze pornirea

        # --- Servicii partajate (Model + servicii de fundal) ---
        self.db = Database()
        self.classifier = BookClassifier()
        self.classifier.load()
        self.scanner = ScannerService()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.pages = {}
        self.nav_buttons = {}
        self.current_page = None

        self._build_sidebar()
        self._build_content()
        self.show_page("dashboard")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(SCANNER_POLL_INTERVAL_MS, self._poll_scanner_queue)

    # ------------------------------------------------------------------
    # Sidebar de navigare
    # ------------------------------------------------------------------
    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_rowconfigure(len(NAV_ITEMS) + 3, weight=1)

        ctk.CTkLabel(
            sidebar, text="📖 Biblioteca", font=("", 20, "bold")
        ).grid(row=0, column=0, padx=20, pady=(24, 20), sticky="w")

        for i, (key, label, _) in enumerate(NAV_ITEMS, start=1):
            btn = ctk.CTkButton(
                sidebar, text=label, anchor="w", fg_color="transparent",
                text_color=("gray10", "gray90"), hover_color=("gray80", "gray30"),
                height=40, font=("", 14),
                command=lambda k=key: self.show_page(k),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=12, pady=6)
            self.nav_buttons[key] = btn

        # --- Secțiune scanner GM65 ---
        scanner_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        scanner_frame.grid(row=len(NAV_ITEMS) + 4, column=0, sticky="ew", padx=16, pady=(10, 4))
        scanner_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(scanner_frame, text="Scanner GM65", font=("", 12, "bold"),
                     text_color="gray").grid(row=0, column=0, sticky="w")

        self.port_menu = ctk.CTkOptionMenu(scanner_frame, values=["(niciun port)"], width=170)
        self.port_menu.grid(row=1, column=0, sticky="ew", pady=(4, 4))

        btn_row = ctk.CTkFrame(scanner_frame, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew")
        btn_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btn_row, text="↻", width=32, command=self._refresh_ports).grid(
            row=0, column=0, padx=(0, 4)
        )
        self.scanner_toggle_btn = ctk.CTkButton(
            btn_row, text="Conectează", command=self._toggle_scanner
        )
        self.scanner_toggle_btn.grid(row=0, column=1, sticky="ew")

        self.scanner_status_label = ctk.CTkLabel(
            scanner_frame, text="neconectat", text_color="gray", font=("", 11)
        )
        self.scanner_status_label.grid(row=3, column=0, sticky="w", pady=(4, 0))

        self._refresh_ports()

        # --- Comutator temă Dark/Light ---
        appearance_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        appearance_row.grid(row=len(NAV_ITEMS) + 5, column=0, sticky="ew", padx=16, pady=(8, 20))
        ctk.CTkLabel(appearance_row, text="Temă:").grid(row=0, column=0, sticky="w")
        self.appearance_menu = ctk.CTkOptionMenu(
            appearance_row, values=["System", "Light", "Dark"], width=110,
            command=self._change_appearance,
        )
        self.appearance_menu.set(APPEARANCE_MODE)
        self.appearance_menu.grid(row=0, column=1, sticky="e", padx=(8, 0))

    def _change_appearance(self, mode):
        ctk.set_appearance_mode(mode)
        for page in self.pages.values():
            if hasattr(page, "refresh"):
                page.refresh()

    # ------------------------------------------------------------------
    # Zona de conținut (pagini)
    # ------------------------------------------------------------------
    def _build_content(self):
        container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        container.grid(row=0, column=1, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        for key, _, page_class in NAV_ITEMS:
            page = page_class(container, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

    def show_page(self, key):
        page = self.pages[key]
        page.tkraise()
        self.current_page = key
        style_nav_buttons(self.nav_buttons, key)
        if hasattr(page, "on_show"):
            page.on_show()

    # ------------------------------------------------------------------
    # Scanner GM65
    # ------------------------------------------------------------------
    def _refresh_ports(self):
        ports = self.scanner.list_ports()
        values = ports or ["(niciun port)"]
        self.port_menu.configure(values=values)
        self.port_menu.set(values[0])

    def _toggle_scanner(self):
        if self.scanner.connected:
            self.scanner.disconnect()
            self.scanner_toggle_btn.configure(text="Conectează")
            self.scanner_status_label.configure(text="neconectat", text_color="gray")
            return

        port = self.port_menu.get()
        if not port or port.startswith("("):
            messagebox.showwarning("Niciun port", "Niciun port serial disponibil.", parent=self)
            return
        try:
            self.scanner.connect(port)
            self.scanner_toggle_btn.configure(text="Deconectează")
            self.scanner_status_label.configure(text=f"conectat pe {port}", text_color=COLOR_SUCCESS)
        except Exception as exc:
            messagebox.showerror("Eroare conectare scanner", str(exc), parent=self)

    def _poll_scanner_queue(self):
        try:
            while True:
                code = self.scanner.queue.get_nowait()
                self._handle_scanned_code(code)
        except queue.Empty:
            pass
        self.after(SCANNER_POLL_INTERVAL_MS, self._poll_scanner_queue)

    def _handle_scanned_code(self, code):
        catalog_page = self.pages.get("catalog")
        if catalog_page:
            self.show_page("catalog")
            catalog_page.handle_scanned_isbn(code)

    # ------------------------------------------------------------------
    def _on_close(self):
        self.scanner.disconnect()
        maybe_run_auto_backup(self.db)
        self.destroy()
