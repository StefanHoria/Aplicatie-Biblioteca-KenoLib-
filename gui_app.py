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
    BRAND_ACCENT, BRAND_ACCENT_DARK, BRAND_ACCENT_DARKER, BRAND_TITLE_FONT,
)
from utils import get_logo_image
from database import Database
from ml_classifier import BookClassifier
from scanner_service import ScannerService
from settings_service import maybe_run_auto_backup, get_profile, is_profile_complete

from views.dashboard import DashboardPage
from views.catalog import CatalogPage
from views.borrowers import BorrowersPage
from views.loans import LoansPage
from views.reservations import ReservationsPage
from views.reports import ReportsPage
from views.inventory import InventoryPage
from views.import_view import ImportPage
from views.settings import SettingsPage

NAV_INDICATOR_HEIGHT = 24
NAV_BUTTON_HEIGHT = 36  # compact: 9 elemente de navigare + scanner + temă trebuie să încapă și la înălțimea minimă


def apply_brand_theme():
    """Rescrie accentul temei CTk (albastrul standard) cu albastrul din
    identitatea vizuală KenoLib, aplicat consecvent la toate widget-urile cu
    accent. CTk citește culorile din `ThemeManager.theme` la crearea fiecărui
    widget, deci e suficient să modificăm dicționarul temei o singură dată, la
    pornire, înainte de a construi interfața -- inclusiv indicatorul din sidebar
    și butonul activ de navigare, care oricum citesc `CTkButton.fg_color`.
    Butoanele cu culoare explicită (ex. ștergere = roșu) rămân neatinse, fiindcă
    modificăm doar valorile *implicite* ale temei."""
    fg = [BRAND_ACCENT, BRAND_ACCENT_DARK]           # [mod luminos, mod întunecat]
    hover = [BRAND_ACCENT_DARK, BRAND_ACCENT_DARKER]
    hover2 = [BRAND_ACCENT_DARKER, BRAND_ACCENT_DARKER]
    accent_map = {
        "CTkButton": {"fg_color": fg, "hover_color": hover},
        "CTkOptionMenu": {"fg_color": fg, "button_color": hover, "button_hover_color": hover2},
        "CTkComboBox": {"button_color": hover, "button_hover_color": hover2},
        "CTkCheckBox": {"fg_color": fg, "hover_color": hover},
        "CTkRadioButton": {"fg_color": fg, "hover_color": hover},
        "CTkSwitch": {"progress_color": fg},
        "CTkSlider": {"button_color": fg, "button_hover_color": hover, "progress_color": fg},
        "CTkProgressBar": {"progress_color": fg},
        "CTkSegmentedButton": {"selected_color": fg, "selected_hover_color": hover},
    }
    theme = ctk.ThemeManager.theme
    for widget, keys in accent_map.items():
        widget_theme = theme.get(widget)
        if not widget_theme:
            continue
        for key, value in keys.items():
            if key in widget_theme:
                widget_theme[key] = value


NAV_ITEMS = [
    ("dashboard", "🏠  Dashboard", DashboardPage),
    ("catalog", "📚  Catalog Cărți", CatalogPage),
    ("borrowers", "👤  Cititori", BorrowersPage),
    ("loans", "🔄  Împrumuturi active", LoansPage),
    ("reservations", "🔖  Rezervări", ReservationsPage),
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
        apply_brand_theme()  # rescrie accentul cu albastrul de brand KenoLib

        self.title(APP_TITLE)
        self.geometry(APP_GEOMETRY)
        self.minsize(1000, 640)
        try:
            # Fără asta, Tkinter arată iconița implicită ("pana") în
            # bara de titlu/taskbar, chiar dacă executabilul are alta.
            self.iconbitmap(ICON_PATH)
        except Exception:
            pass  # iconița e cosmetică -- nu trebuie să blocheze pornirea

        # Fereastra apare imediat, cu un ecran scurt de încărcare, în loc să
        # rămână goală/înghețată în timp ce baza de date și modelul ML
        # (operații sincrone, pot dura o clipă) se încarcă mai jos.
        loading = self._show_loading_screen()

        # --- Servicii partajate (Model + servicii de fundal) ---
        self.db = Database()
        self.update()
        self.classifier = BookClassifier()
        self.classifier.load()
        self.update()
        self.scanner = ScannerService()

        loading.destroy()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.pages = {}
        self.nav_buttons = {}
        self.current_page = None
        self._nav_anim_id = None
        self._nav_indicator_y = None

        self._build_sidebar()
        self._build_content()

        # Pre-încălzim pagina Rapoarte -- singura suficient de grea (reconstruiește
        # zeci de widget-uri CTk) încât primul ei render (~200ms) să se simtă ca
        # lag. Făcut aici, înainte de prima afișare, costul e absorbit în pornire
        # (sub ecranul de încărcare, invizibil), iar prima intrare pe pagină e un
        # cache-hit instantaneu (vezi ReportsPage.refresh). Vizitele ulterioare
        # rămân instantanee cât timp datele nu se schimbă.
        self.pages["reports"].refresh()

        self.update_idletasks()  # geometria butoanelor trebuie calculată înainte de show_page
        self.show_page("dashboard")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(SCANNER_POLL_INTERVAL_MS, self._poll_scanner_queue)
        # La prima pornire (profil necompletat) cerem numele bibliotecii și
        # școala -- după ce fereastra e complet randată, ca dialogul modal să
        # apară peste o interfață gata, nu peste una goală.
        self.after(400, self._maybe_prompt_profile)

    def _maybe_prompt_profile(self):
        from views.dialogs import ProfileDialog
        if not is_profile_complete():
            ProfileDialog(self, self, on_saved=self._refresh_profile_label, welcome=True)

    def _refresh_profile_label(self):
        """Actualizează eticheta din sidebar și titlul ferestrei cu profilul
        curent (apelat la pornire și după orice modificare din Setări/dialog).
        Fiecare câmp e scurtat pe o singură linie ca antetul să rămână compact;
        valorile complete rămân în titlul ferestrei și în pagina Setări."""
        def _short(text, limit=26):
            return text if len(text) <= limit else text[:limit - 1] + "…"

        profile = get_profile()
        lines = [_short(p) for p in (profile["name"], profile["school"]) if p]
        self.profile_label.configure(text="\n".join(lines))
        self.title(f"{APP_TITLE} — {profile['name']}" if profile["name"] else APP_TITLE)

    def _show_loading_screen(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(
            frame, text=" KenoLib", image=get_logo_image(48), compound="left",
            font=(BRAND_TITLE_FONT, 34), text_color=BRAND_ACCENT,
        ).pack(pady=(0, 18))
        progress = ctk.CTkProgressBar(frame, width=220, mode="indeterminate")
        progress.pack()
        progress.start()
        self.update()
        return frame

    # ------------------------------------------------------------------
    # Animație generică (ease-out), reutilizată de indicatorul din sidebar
    # și de tranziția dintre pagini.
    # ------------------------------------------------------------------
    def _animate(self, duration_ms, on_step, on_done=None, cancel_attr=None):
        steps = max(1, duration_ms // 15)
        interval = max(1, duration_ms // steps)

        def ease_out_cubic(t):
            return 1 - (1 - t) ** 3

        def tick(i):
            on_step(ease_out_cubic(i / steps))
            if i < steps:
                after_id = self.after(interval, lambda: tick(i + 1))
                if cancel_attr:
                    setattr(self, cancel_attr, after_id)
            else:
                if cancel_attr:
                    setattr(self, cancel_attr, None)
                if on_done:
                    on_done()

        if cancel_attr:
            prev_id = getattr(self, cancel_attr, None)
            if prev_id:
                self.after_cancel(prev_id)
        tick(0)

    # ------------------------------------------------------------------
    # Sidebar de navigare
    # ------------------------------------------------------------------
    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_rowconfigure(len(NAV_ITEMS) + 3, weight=1)

        # Antet: logo + profilul bibliotecii (nume/școală) dedesubt.
        header = ctk.CTkFrame(sidebar, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text=" KenoLib", image=get_logo_image(30), compound="left",
            font=(BRAND_TITLE_FONT, 23), text_color=BRAND_ACCENT, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        # wraplength mare = fără wrap; textul e deja scurtat pe câte o linie în
        # _refresh_profile_label, ca înălțimea antetului să rămână previzibilă
        # (contează la înălțimea minimă a ferestrei, unde spațiul e strâns).
        self.profile_label = ctk.CTkLabel(
            header, text="", font=("", 11), text_color="gray",
            anchor="w", justify="left", wraplength=600,
        )
        self.profile_label.grid(row=1, column=0, sticky="w", pady=(1, 0))

        for i, (key, label, _) in enumerate(NAV_ITEMS, start=1):
            btn = ctk.CTkButton(
                sidebar, text=label, anchor="w", fg_color="transparent",
                text_color=("gray10", "gray90"), hover_color=("gray80", "gray30"),
                height=NAV_BUTTON_HEIGHT, font=("", 14),
                command=lambda k=key: self.show_page(k),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=12, pady=3)
            self.nav_buttons[key] = btn

        # Bară de accent care alunecă spre butonul activ la navigare
        # (poziționată exact în show_page/_animate_nav_indicator, odată
        # ce geometria butoanelor e cunoscută).
        self.nav_indicator = ctk.CTkFrame(
            sidebar, width=4, height=NAV_INDICATOR_HEIGHT, corner_radius=2,
            fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
        )

        # Linie subțire de separare între navigare și controalele de jos
        # (scanner + temă) -- structurează sidebar-ul fără să adauge zgomot.
        divider = ctk.CTkFrame(sidebar, height=1, fg_color=("gray75", "gray30"))
        divider.grid(row=len(NAV_ITEMS) + 4, column=0, sticky="ew", padx=16, pady=(0, 10))

        # --- Secțiune scanner GM65 ---
        scanner_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        scanner_frame.grid(row=len(NAV_ITEMS) + 5, column=0, sticky="ew", padx=16, pady=(0, 4))
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
        appearance_row.grid(row=len(NAV_ITEMS) + 6, column=0, sticky="ew", padx=16, pady=(8, 20))
        ctk.CTkLabel(appearance_row, text="Temă:").grid(row=0, column=0, sticky="w")
        self.appearance_menu = ctk.CTkOptionMenu(
            appearance_row, values=["System", "Light", "Dark"], width=110,
            command=self._change_appearance,
        )
        self.appearance_menu.set(APPEARANCE_MODE)
        self.appearance_menu.grid(row=0, column=1, sticky="e", padx=(8, 0))

        self._refresh_profile_label()  # populează numele/școala în antet + titlu

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
        if key == self.current_page:
            return
        page = self.pages[key]
        is_first = self.current_page is None
        style_nav_buttons(self.nav_buttons, key)
        self._move_nav_indicator(key, animate=not is_first)
        self.current_page = key

        # Comutare instantă. Toate paginile sunt deja construite și așezate
        # în aceeași celulă de grid (row 0 / col 0); tkraise() doar schimbă
        # ordinea de stivuire, fără niciun re-layout -- deci e instantaneu și
        # complet lipsit de flicker. Tkinter nu are compozitor / dublu-
        # buffering care să poată *anima* mutarea unei pagini complexe fără
        # flicker sau rămâneri în urmă, așa că o comutare instantă e de fapt
        # cea mai fluidă opțiune posibilă. (Animația fină rămâne doar la bara
        # de accent din sidebar, care e un widget mic și ieftin de mutat.)
        page.tkraise()
        if hasattr(page, "on_show"):
            page.on_show()

    def _move_nav_indicator(self, key, animate):
        # NOTĂ: se folosește place_configure(), nu place() -- CustomTkinter
        # scalează automat x/y trecute prin place() cu factorul de scaling
        # DPI al widget-ului, dar winfo_y()/winfo_height() de mai jos întorc
        # deja poziții reale (post-scalare), iar o a doua scalare peste ele
        # ar plasa bara mult prea jos (eroare crescândă cu poziția din listă).
        btn = self.nav_buttons[key]
        target_y = btn.winfo_y() + (btn.winfo_height() - NAV_INDICATOR_HEIGHT) // 2

        if not animate:
            self.nav_indicator.place_configure(x=0, y=target_y)
            self._nav_indicator_y = target_y
            return

        start_y = self._nav_indicator_y if self._nav_indicator_y is not None else target_y

        def step(t):
            y = int(start_y + (target_y - start_y) * t)
            self.nav_indicator.place_configure(x=0, y=y)
            self._nav_indicator_y = y

        def done():
            self._nav_indicator_y = target_y

        self._animate(160, step, done, cancel_attr="_nav_anim_id")

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
