# views/import_view.py
"""
Pagina Import Date: încarcă un fișier CSV exportat dintr-un soft vechi
de bibliotecă, permite maparea coloanelor CSV la câmpurile modelului de
carte (prin dropdown-uri), apoi rulează importul masiv într-un thread
separat.

Clasificarea categoriei, per rând importat:
1. Dacă fișierul CSV are o coloană de categorie și utilizatorul o
   mapează, acea categorie este folosită direct (util pentru a construi
   rapid un set de antrenare etichetat manual în sursă).
2. Altfel, textul (titlu + descriere) este trecut prin clasificatorul
   ML, care funcționează integral offline.
3. Opțional („Îmbogățește cu date online”), dacă rândul nu are deja o
   descriere, se încearcă întâi completarea ei din Google Books / Open
   Library (după ISBN, sau după titlu+autor dacă ISBN-ul lipsește ori nu
   are rezultate) — text mai bogat înseamnă predicții ML mai sigure. Dacă
   totuși ML rămâne nesigur, se încearcă drept ultimă soluție categoria
   sugerată chiar de API (dacă una dintre surse a oferit-o).
"""

import csv
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

import api_service
from config import UNCONFIRMED_CATEGORY, suggest_czu, COLOR_DANGER_BG, COLOR_DANGER_BG_HOVER
from utils import style_treeview, TREEVIEW_STYLE_NAME

TARGET_FIELDS = [
    ("isbn", "ISBN"),
    ("title", "Titlu *"),
    ("author", "Autor"),
    ("pub_year", "An publicare"),
    ("publisher", "Editură"),
    ("pub_place", "Loc apariție"),
    ("price", "Preț"),
    ("copies", "Nr. exemplare"),
    ("czu", "CZU"),
    ("desc", "Descriere"),
    ("category", "Categorie (opțional)"),
]

GUESS_KEYWORDS = {
    "isbn": ["isbn"],
    "title": ["titlu", "title", "denumire", "nume carte"],
    "author": ["autor", "author", "scriitor"],
    "pub_year": ["an", "year", "publicare", "aparitie"],
    "publisher": ["editura", "editură", "publisher"],
    "pub_place": ["loc aparitie", "loc apariție", "localitate", "place"],
    "price": ["pret", "preț", "price", "cost"],
    "copies": ["exemplare", "cantitate", "copies", "buc"],
    "czu": ["czu", "udc", "clasificare"],
    "desc": ["descriere", "desc", "description", "rezumat", "sinopsis"],
    "category": ["categorie", "category", "gen", "domeniu"],
}

IGNORE_OPTION = "-- ignoră --"


class ImportPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.csv_path = None
        self.csv_headers = []
        self.csv_rows_preview = []
        self.dialect = csv.excel
        self.mapping_menus = {}
        self._progress_queue = queue.Queue()
        self._train_queue = queue.Queue()
        self._importing = False
        self._cancel_event = threading.Event()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text="Import Date (CSV)", font=("", 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 10)
        )

        # --- Pas 1: selectare fișier ---
        file_row = ctk.CTkFrame(self, fg_color="transparent")
        file_row.grid(row=1, column=0, sticky="ew", padx=24)
        ctk.CTkButton(file_row, text="Selectează fișier CSV", command=self._select_file).grid(
            row=0, column=0
        )
        self.file_label = ctk.CTkLabel(file_row, text="Niciun fișier selectat.")
        self._file_label_default_color = self.file_label.cget("text_color")
        self.file_label.configure(text_color="gray")
        self.file_label.grid(row=0, column=1, padx=12)

        # --- Pas 2: mapare coloane ---
        self.mapping_frame = ctk.CTkFrame(self, corner_radius=12)
        self.mapping_frame.grid(row=2, column=0, sticky="ew", padx=24, pady=12)
        ctk.CTkLabel(self.mapping_frame, text="Mapare coloane CSV → câmpuri carte",
                     font=("", 15, "bold")).grid(row=0, column=0, columnspan=4, sticky="w",
                                                  padx=12, pady=(10, 6))
        self._build_mapping_widgets()

        # --- Previzualizare ---
        preview_frame = ctk.CTkFrame(self, corner_radius=12)
        preview_frame.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 12))
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(preview_frame, text="Previzualizare (primele 5 rânduri)",
                     font=("", 14, "bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        style_treeview()
        self.preview_tree = ttk.Treeview(preview_frame, show="headings", style=TREEVIEW_STYLE_NAME)
        self.preview_tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        preview_scroll = ttk.Scrollbar(preview_frame, orient="horizontal",
                                        command=self.preview_tree.xview)
        self.preview_tree.configure(xscrollcommand=preview_scroll.set)
        preview_scroll.grid(row=2, column=0, sticky="ew", padx=8)

        # --- Opțiune: îmbogățire online înainte de clasificare ML ---
        enrich_row = ctk.CTkFrame(self, fg_color="transparent")
        enrich_row.grid(row=4, column=0, sticky="w", padx=24, pady=(0, 4))
        self.enrich_online_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            enrich_row, text="Îmbogățește cu date online (Google Books / Open Library) înainte de clasificare",
            variable=self.enrich_online_var,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            enrich_row,
            text="Completează descrierea lipsă (după ISBN sau titlu+autor) — necesită internet, importul devine mai lent.",
            text_color="gray", font=("", 11),
        ).grid(row=1, column=0, sticky="w", padx=(28, 0))

        # --- Pas 3: import ---
        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.grid(row=5, column=0, sticky="ew", padx=24, pady=(0, 20))
        action_row.grid_columnconfigure(1, weight=1)

        self.import_button = ctk.CTkButton(
            action_row, text="Începe Import", state="disabled", command=self._start_import
        )
        self.import_button.grid(row=0, column=0, padx=(0, 12))

        self.cancel_button = ctk.CTkButton(
            action_row, text="Anulează Import", fg_color=COLOR_DANGER_BG, hover_color=COLOR_DANGER_BG_HOVER,
            command=self._cancel_import,
        )
        self.cancel_button.grid(row=0, column=0, padx=(0, 12))
        self.cancel_button.grid_remove()  # vizibil doar cât timp rulează un import

        self.progress_bar = ctk.CTkProgressBar(action_row)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, sticky="ew")

        self.progress_label = ctk.CTkLabel(action_row, text="", text_color="gray")
        self.progress_label.grid(row=0, column=2, padx=12)

        self.train_button = ctk.CTkButton(
            action_row, text="Antrenează modelul ML", fg_color="gray40",
            command=self._train_model
        )
        self.train_button.grid(row=0, column=3, padx=(12, 0))

        self.after(200, self._poll_train_queue)

    # ------------------------------------------------------------------
    def _build_mapping_widgets(self):
        for i, (field_key, field_label) in enumerate(TARGET_FIELDS, start=1):
            ctk.CTkLabel(self.mapping_frame, text=field_label).grid(
                row=i, column=0, sticky="w", padx=12, pady=4
            )
            menu = ctk.CTkOptionMenu(self.mapping_frame, values=[IGNORE_OPTION], width=220)
            menu.grid(row=i, column=1, sticky="w", padx=12, pady=4)
            self.mapping_menus[field_key] = menu

    def _guess_mapping(self):
        for field_key, _ in TARGET_FIELDS:
            keywords = GUESS_KEYWORDS[field_key]
            best = IGNORE_OPTION
            for header in self.csv_headers:
                if any(kw in header.lower() for kw in keywords):
                    best = header
                    break
            self.mapping_menus[field_key].set(best)

    # ------------------------------------------------------------------
    def _select_file(self):
        path = filedialog.askopenfilename(
            title="Selectează fișier CSV", filetypes=[("Fișiere CSV", "*.csv"), ("Toate fișierele", "*.*")]
        )
        if not path:
            return

        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    self.dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    self.dialect = csv.excel
                reader = csv.reader(f, self.dialect)
                rows = list(reader)
        except Exception as exc:
            messagebox.showerror("Eroare citire fișier", str(exc), parent=self)
            return

        if not rows:
            messagebox.showwarning("Fișier gol", "Fișierul CSV selectat nu conține date.", parent=self)
            return

        self.csv_path = path
        self.csv_headers = rows[0]
        self.csv_rows_preview = rows[1:6]
        self.file_label.configure(text=path, text_color=self._file_label_default_color)

        for menu in self.mapping_menus.values():
            menu.configure(values=[IGNORE_OPTION] + self.csv_headers)
        self._guess_mapping()

        self._render_preview()
        self.import_button.configure(state="normal")

    def _render_preview(self):
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.preview_tree["columns"] = self.csv_headers
        for header in self.csv_headers:
            self.preview_tree.heading(header, text=header)
            self.preview_tree.column(header, width=140, anchor="w")
        for row in self.csv_rows_preview:
            self.preview_tree.insert("", "end", values=row)

    # ------------------------------------------------------------------
    def _start_import(self):
        if self._importing:
            return
        mapping = {key: menu.get() for key, menu in self.mapping_menus.items()}
        if mapping["title"] == IGNORE_OPTION:
            messagebox.showwarning(
                "Mapare incompletă", "Câmpul Titlu trebuie mapat la o coloană CSV.", parent=self
            )
            return

        if not messagebox.askyesno(
            "Confirmare import", f"Pornești importul din:\n{self.csv_path}?", parent=self
        ):
            return

        self._importing = True
        self._cancel_event.clear()
        self.import_button.grid_remove()
        self.cancel_button.grid()
        self.progress_bar.set(0)
        self.progress_label.configure(text="Se importă...")

        enrich_online = self.enrich_online_var.get()
        threading.Thread(
            target=self._import_worker,
            args=(self.csv_path, dict(mapping), self.dialect, enrich_online),
            daemon=True,
        ).start()
        self.after(150, self._poll_progress_queue)

    def _cancel_import(self):
        self._cancel_event.set()
        self.cancel_button.configure(state="disabled", text="Se anulează...")

    def _import_worker(self, path, mapping, dialect, enrich_online):
        db = self.app.db
        classifier = self.app.classifier
        success, errors = 0, 0
        cancelled = False

        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, dialect=dialect)
                rows = list(reader)
        except Exception as exc:
            self._progress_queue.put(("done", 0, 1, f"Eroare la citirea fișierului: {exc}"))
            return

        total = len(rows)
        for i, row in enumerate(rows, start=1):
            if self._cancel_event.is_set():
                cancelled = True
                break
            try:
                isbn = row.get(mapping["isbn"], "").strip() if mapping["isbn"] != IGNORE_OPTION else ""
                title = row.get(mapping["title"], "").strip()
                author = row.get(mapping["author"], "").strip() if mapping["author"] != IGNORE_OPTION else ""
                desc = row.get(mapping["desc"], "").strip() if mapping["desc"] != IGNORE_OPTION else ""
                year_raw = row.get(mapping["pub_year"], "").strip() if mapping["pub_year"] != IGNORE_OPTION else ""
                pub_year = int(year_raw) if year_raw.isdigit() else None
                publisher = row.get(mapping["publisher"], "").strip() if mapping["publisher"] != IGNORE_OPTION else ""
                pub_place = row.get(mapping["pub_place"], "").strip() if mapping["pub_place"] != IGNORE_OPTION else ""
                czu = row.get(mapping["czu"], "").strip() if mapping["czu"] != IGNORE_OPTION else ""

                price_raw = row.get(mapping["price"], "").strip() if mapping["price"] != IGNORE_OPTION else ""
                price = None
                if price_raw:
                    try:
                        price = float(price_raw.replace(",", "."))
                    except ValueError:
                        price = None

                copies_raw = row.get(mapping["copies"], "").strip() if mapping["copies"] != IGNORE_OPTION else ""
                copies = int(copies_raw) if copies_raw.isdigit() and int(copies_raw) > 0 else 1

                if not title:
                    errors += 1
                    continue

                category_from_csv = (
                    row.get(mapping["category"], "").strip()
                    if mapping["category"] != IGNORE_OPTION else ""
                )

                api_category_hint = None
                if enrich_online:
                    # Îmbogățirea (ISBN, descriere, an, autor, editură, loc
                    # apariție) rulează indiferent dacă rândul are deja o
                    # categorie din CSV — sunt lucruri independente. Doar
                    # sugestia de categorie din API (api_category_hint) e
                    # relevantă exclusiv când NU avem deja o categorie
                    # explicită din sursă.
                    self._progress_queue.put(("status", f"{i}/{total}: căutare online pentru „{title}”..."))
                    online = api_service.fetch_book_metadata(isbn=isbn, title=title, author=author)
                    if online:
                        if online.get("desc") and len(online["desc"]) > len(desc):
                            desc = online["desc"]
                        if not isbn and online.get("isbn"):
                            isbn = online["isbn"]
                        if not author and online.get("author"):
                            author = online["author"]
                        if not pub_year and online.get("pub_year"):
                            pub_year = online["pub_year"]
                        if not publisher and online.get("publisher"):
                            publisher = online["publisher"]
                        if not pub_place and online.get("pub_place"):
                            pub_place = online["pub_place"]
                        if not category_from_csv:
                            api_category_hint = online.get("category_hint")

                if category_from_csv:
                    # Categoria vine explicit din sursă — folosită direct, fără ML.
                    category_id = db.get_or_create_category(category_from_csv)
                    category_name = category_from_csv
                else:
                    category_name, _ = classifier.predict(f"{title} {desc}".strip())
                    if category_name == UNCONFIRMED_CATEGORY and api_category_hint:
                        category_name = api_category_hint
                    category_id = db.get_or_create_category(category_name)

                if not czu:
                    czu = suggest_czu(category_name)

                db.add_book(
                    isbn, title, author, pub_year, desc, category_id,
                    price=price, publisher=publisher, copies=copies,
                    pub_place=pub_place, czu=czu,
                )
                success += 1
            except Exception:
                errors += 1
            finally:
                self._progress_queue.put(("progress", i, total))

        message = "Import anulat." if cancelled else "Import finalizat."
        self._progress_queue.put(("done", success, errors, message))

    def _poll_progress_queue(self):
        try:
            while True:
                item = self._progress_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, i, total = item
                    self.progress_bar.set(i / total if total else 1)
                    self.progress_label.configure(text=f"{i}/{total} rânduri procesate")
                elif kind == "status":
                    self.progress_label.configure(text=item[1])
                elif kind == "done":
                    _, success, errors, message = item
                    cancelled = message.startswith("Import anulat")
                    self._importing = False
                    self.cancel_button.grid_remove()
                    self.cancel_button.configure(state="normal", text="Anulează Import")
                    self.import_button.grid()
                    self.import_button.configure(state="normal")
                    self.progress_label.configure(text=f"{message} ({success} importate, {errors} erori)")
                    if cancelled:
                        messagebox.showinfo(
                            "Import anulat",
                            f"Import oprit de utilizator.\n{success} cărți importate până la anulare.",
                            parent=self,
                        )
                    else:
                        messagebox.showinfo(
                            "Import finalizat",
                            f"{success} cărți importate cu succes.\n{errors} rânduri au fost ignorate (erori).",
                            parent=self,
                        )
                    catalog = self.app.pages.get("catalog")
                    if catalog:
                        catalog.refresh()
                    dashboard = self.app.pages.get("dashboard")
                    if dashboard:
                        dashboard.refresh()
        except queue.Empty:
            pass

        if self._importing:
            self.after(150, self._poll_progress_queue)

    # ------------------------------------------------------------------
    def _train_model(self):
        self.train_button.configure(state="disabled", text="Se antrenează...")
        threading.Thread(target=self._train_worker, daemon=True).start()

    def _train_worker(self):
        success, message = self.app.classifier.train_from_db(self.app.db)
        self._train_queue.put((success, message))

    def _poll_train_queue(self):
        try:
            success, message = self._train_queue.get_nowait()
            self._on_train_done(success, message)
        except queue.Empty:
            pass
        self.after(200, self._poll_train_queue)

    def _on_train_done(self, success, message):
        self.train_button.configure(state="normal", text="Antrenează modelul ML")
        if success:
            messagebox.showinfo("Antrenare ML", message, parent=self)
        else:
            messagebox.showwarning("Antrenare ML", message, parent=self)
