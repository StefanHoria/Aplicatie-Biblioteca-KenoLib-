# views/catalog.py
"""
Pagina Catalog Cărți: tabel cu toate cărțile, căutare universală rapidă
(după titlu, autor, ISBN sau categorie) și butoane de Adăugare / Editare
/ Ștergere. Este și punctul de intrare pentru scanner-ul GM65: când o
fereastră de adăugare/editare carte este deschisă, codurile scanate sunt
direcționate automat către acel formular.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from config import (
    UNCONFIRMED_CATEGORY, COLOR_DANGER_BG, COLOR_DANGER_BG_HOVER,
    COLOR_UNCONFIRMED_TEXT, COLOR_UNCONFIRMED_BG, COLOR_ROW_HIGHLIGHT_FG,
)
from utils import style_treeview, TREEVIEW_STYLE_NAME, stripe_color
from views.dialogs import BookDialog


class CatalogPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.active_dialog = None  # dialogul curent deschis (pentru scanner)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Catalog Cărți", font=("", 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 10)
        )

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
        toolbar.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            toolbar, placeholder_text="Căutare rapidă: titlu, autor, ISBN sau categorie..."
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", lambda e: self.refresh())

        ctk.CTkButton(toolbar, text="+ Adaugă", width=100, command=self._add_book).grid(
            row=0, column=1, padx=4
        )
        ctk.CTkButton(toolbar, text="Editează", width=100, command=self._edit_book).grid(
            row=0, column=2, padx=4
        )
        ctk.CTkButton(
            toolbar, text="Șterge", width=100, fg_color=COLOR_DANGER_BG, hover_color=COLOR_DANGER_BG_HOVER,
            command=self._delete_book
        ).grid(row=0, column=3, padx=4)

        self.legend_label = ctk.CTkLabel(
            toolbar, text="   ● De Confirmat (categorie nesigură)", text_color=COLOR_UNCONFIRMED_TEXT
        )
        self.legend_label.grid(row=0, column=4, padx=(16, 0))

        table_frame = ctk.CTkFrame(self, corner_radius=12)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 24))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        style_treeview()
        columns = (
            "isbn", "title", "author", "year", "publisher", "pub_place",
            "price", "copies", "czu", "category",
        )
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", style=TREEVIEW_STYLE_NAME
        )
        headings = {
            "isbn": "ISBN", "title": "Titlu", "author": "Autor", "year": "An",
            "publisher": "Editură", "pub_place": "Loc apariție", "price": "Preț",
            "copies": "Nr. ex.", "czu": "CZU", "category": "Categorie",
        }
        widths = {
            "isbn": 120, "title": 220, "author": 150, "year": 55,
            "publisher": 130, "pub_place": 100, "price": 70,
            "copies": 60, "czu": 90, "category": 130,
        }
        for col in columns:
            self.tree.heading(col, text=headings[col], anchor="center")
            self.tree.column(col, width=widths[col], anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))

        v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        v_scrollbar.grid(row=0, column=1, sticky="ns", pady=(8, 0))
        h_scrollbar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        self.tree.bind("<Double-1>", lambda e: self._edit_book())
        # Scurtături de tastatură, legate de tabel (nu de pagină) ca să NU
        # prindă „+”/Delete tastate în câmpul de căutare: „+” (inclusiv cel de
        # pe blocul numeric) deschide adăugarea; Delete șterge cartea selectată
        # (fără efect dacă nu e nimic selectat).
        self.tree.bind("<plus>", lambda e: self._add_book())
        self.tree.bind("<KP_Add>", lambda e: self._add_book())
        self.tree.bind("<Delete>", lambda e: self._delete_book() if self._selected_book() else None)
        self.tree.tag_configure(
            "unconfirmed", foreground=COLOR_ROW_HIGHLIGHT_FG, background=COLOR_UNCONFIRMED_BG
        )

        self._book_by_iid = {}

    # ------------------------------------------------------------------
    def on_show(self):
        self.refresh()

    def refresh(self):
        style_treeview()
        self.tree.tag_configure("oddrow", background=stripe_color())
        for row in self.tree.get_children():
            self.tree.delete(row)
        self._book_by_iid.clear()

        search = self.search_entry.get().strip() or None
        books = self.app.db.get_all_books(search)
        for i, book in enumerate(books):
            iid = str(book["id"])
            price_display = f"{book['price']:.2f}" if book.get("price") is not None else ""
            if book["category_name"] == UNCONFIRMED_CATEGORY:
                tags = ("unconfirmed",)
            elif i % 2 == 1:
                tags = ("oddrow",)
            else:
                tags = ()
            self.tree.insert(
                "", "end", iid=iid, tags=tags,
                values=(
                    book["isbn"] or "", book["title"], book["author"] or "",
                    book["pub_year"] or "", book.get("publisher") or "",
                    book.get("pub_place") or "", price_display,
                    book.get("copies") or 1, book.get("czu") or "",
                    book["category_name"] or "-",
                ),
            )
            self._book_by_iid[iid] = book

    def _selected_book(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self._book_by_iid.get(selection[0])

    # ------------------------------------------------------------------
    def _add_book(self):
        self._open_dialog(book=None)

    def _edit_book(self):
        book = self._selected_book()
        if not book:
            messagebox.showinfo("Selecție necesară", "Selectează o carte din tabel.", parent=self)
            return
        full_book = self.app.db.get_book(book["id"])
        self._open_dialog(book=full_book)

    def _open_dialog(self, book):
        dialog = BookDialog(self, self.app, book=book, on_saved=self.refresh)
        self.active_dialog = dialog
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._on_dialog_close(dialog))

    def _on_dialog_close(self, dialog):
        if self.active_dialog is dialog:
            self.active_dialog = None
        dialog.close()

    def _delete_book(self):
        book = self._selected_book()
        if not book:
            messagebox.showinfo("Selecție necesară", "Selectează o carte din tabel.", parent=self)
            return
        if messagebox.askyesno(
            "Confirmare ștergere", f"Ștergi cartea „{book['title']}”?", parent=self
        ):
            self.app.db.delete_book(book["id"])
            self.refresh()

    # ------------------------------------------------------------------
    # Apelat de App atunci când scannerul GM65 trimite un cod nou
    def handle_scanned_isbn(self, code):
        if self.active_dialog is not None and self.active_dialog.winfo_exists():
            self.active_dialog.set_isbn_and_lookup(code)
        else:
            self._open_dialog(book=None)
            self.active_dialog.set_isbn_and_lookup(code)
