# views/inventory.py
"""
Pagina Inventar: generează lista completă a cărților din catalog, fie
sortată strict alfabetic (după titlu), fie grupată pe categorie (și
alfabetic în interiorul fiecărei categorii), cu posibilitatea de a
filtra pe o singură categorie — un raport tipic de inventariere pentru
o bibliotecă, exportabil ca fișier CSV.
"""

import csv
import os
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

import pdf_service
from config import UNCONFIRMED_CATEGORY, COLOR_UNCONFIRMED_TEXT, COLOR_UNCONFIRMED_BG, COLOR_ROW_HIGHLIGHT_FG
from utils import style_treeview, TREEVIEW_STYLE_NAME, stripe_color
from views.dialogs import BookDialog

ALL_CATEGORIES_OPTION = "Toate categoriile"

COLUMNS = (
    "nr", "isbn", "title", "author", "year", "publisher",
    "pub_place", "price", "copies", "czu", "category",
)
HEADINGS = {
    "nr": "Nr. crt.", "isbn": "ISBN", "title": "Titlu", "author": "Autor",
    "year": "An", "publisher": "Editură", "pub_place": "Loc apariție",
    "price": "Preț", "copies": "Nr. ex.", "czu": "CZU", "category": "Categorie",
}
WIDTHS = {
    "nr": 55, "isbn": 120, "title": 240, "author": 150, "year": 55,
    "publisher": 130, "pub_place": 100, "price": 70, "copies": 60,
    "czu": 90, "category": 130,
}


class InventoryPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._current_rows = []
        self._book_by_iid = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Inventar", font=("", 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 10)
        )

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))

        ctk.CTkLabel(toolbar, text="Sortare:").grid(row=0, column=0, padx=(0, 8))
        self.sort_mode = ctk.CTkSegmentedButton(
            toolbar, values=["Alfabetic", "Pe categorii"], command=lambda _: self.refresh()
        )
        self.sort_mode.set("Alfabetic")
        self.sort_mode.grid(row=0, column=1, padx=(0, 16))

        ctk.CTkLabel(toolbar, text="Categorie:").grid(row=0, column=2, padx=(0, 8))
        # state="readonly": valoarea se alege DOAR din listă. Fără asta, câmpul
        # e editabil, iar un text tastat manual nu corespunde niciunei categorii,
        # deci filtrul n-ar returna nimic, fără explicație.
        self.category_filter = ctk.CTkComboBox(
            toolbar, values=[ALL_CATEGORIES_OPTION], width=180,
            state="readonly", command=lambda _: self.refresh(),
        )
        self.category_filter.set(ALL_CATEGORIES_OPTION)
        self.category_filter.grid(row=0, column=3, padx=(0, 16))

        # Un singur meniu „Acțiuni” în locul a patru butoane -- degajă bara de
        # sus. Se comportă ca un buton-meniu: după alegere, eticheta revine la
        # „Acțiuni” (nu păstrează ultima opțiune ca un selector obișnuit).
        self._actions = {
            "Generează lista": self.refresh,
            "Exportă CSV": self._export_csv,
            "Exportă PDF": self._export_pdf,
            "Etichete de raft (PDF)": self._print_labels,
        }
        self.actions_menu = ctk.CTkOptionMenu(
            toolbar, width=150, values=list(self._actions.keys()),
            command=self._on_action,
        )
        self.actions_menu.set("Acțiuni")
        self.actions_menu.grid(row=0, column=4, padx=4)

        self.summary_label = ctk.CTkLabel(toolbar, text="", text_color="gray")
        self.summary_label.grid(row=0, column=5, padx=16)

        self.legend_label = ctk.CTkLabel(
            toolbar, text="● De Confirmat", text_color=COLOR_UNCONFIRMED_TEXT
        )
        self.legend_label.grid(row=0, column=6, padx=(0, 4))

        table_frame = ctk.CTkFrame(self, corner_radius=12)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 24))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        style_treeview()
        self.tree = ttk.Treeview(
            table_frame, columns=COLUMNS, show="headings", style=TREEVIEW_STYLE_NAME
        )
        for col in COLUMNS:
            self.tree.heading(col, text=HEADINGS[col], anchor="center")
            self.tree.column(col, width=WIDTHS[col], anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))

        v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        v_scrollbar.grid(row=0, column=1, sticky="ns", pady=(8, 0))
        h_scrollbar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        self.tree.bind("<Double-1>", lambda e: self._edit_selected_book())
        self.tree.tag_configure(
            "unconfirmed", foreground=COLOR_ROW_HIGHLIGHT_FG, background=COLOR_UNCONFIRMED_BG
        )

    # ------------------------------------------------------------------
    def _on_action(self, choice):
        # revenim la eticheta neutră ca meniul să nu „rămână” pe ultima alegere
        self.actions_menu.set("Acțiuni")
        action = self._actions.get(choice)
        if action:
            action()

    def on_show(self):
        self._refresh_category_filter_values()
        self.refresh()

    def show_category(self, category_name):
        """Apelat din altă pagină (Rapoarte) pentru a deschide Inventarul
        pre-filtrat pe o anumită categorie."""
        self._refresh_category_filter_values()
        self.category_filter.set(category_name)
        self.refresh()

    def _refresh_category_filter_values(self):
        current = self.category_filter.get()
        names = [c["name"] for c in self.app.db.get_all_categories()]
        values = [ALL_CATEGORIES_OPTION] + names
        self.category_filter.configure(values=values)
        if current not in values:
            self.category_filter.set(ALL_CATEGORIES_OPTION)

    def refresh(self):
        style_treeview()
        self.tree.tag_configure("oddrow", background=stripe_color())
        group_by_category = self.sort_mode.get() == "Pe categorii"
        books = self.app.db.get_inventory(group_by_category=group_by_category)

        selected_category = self.category_filter.get()
        if selected_category and selected_category != ALL_CATEGORIES_OPTION:
            books = [b for b in books if (b["category_name"] or "-") == selected_category]

        self._current_rows = books
        self._book_by_iid.clear()

        for row in self.tree.get_children():
            self.tree.delete(row)

        total_value = 0.0
        total_copies = 0
        for i, book in enumerate(books, start=1):
            price = book.get("price")
            copies = book.get("copies") or 1
            total_copies += copies
            if price is not None:
                total_value += price * copies
            iid = str(book["id"])
            if book["category_name"] == UNCONFIRMED_CATEGORY:
                tags = ("unconfirmed",)
            elif i % 2 == 0:
                tags = ("oddrow",)
            else:
                tags = ()
            self.tree.insert(
                "", "end", iid=iid, tags=tags,
                values=(
                    i, book["isbn"] or "", book["title"], book["author"] or "",
                    book["pub_year"] or "", book.get("publisher") or "",
                    book.get("pub_place") or "", f"{price:.2f}" if price is not None else "",
                    copies, book.get("czu") or "", book["category_name"] or "-",
                ),
            )
            self._book_by_iid[iid] = book

        self.summary_label.configure(
            text=f"{len(books)} titluri, {total_copies} exemplare, valoare totală {total_value:.2f} lei"
        )

    def _edit_selected_book(self):
        selection = self.tree.selection()
        if not selection:
            return
        book = self._book_by_iid.get(selection[0])
        if not book:
            return
        full_book = self.app.db.get_book(book["id"])
        BookDialog(self, self.app, book=full_book, on_saved=self.refresh)

    # ------------------------------------------------------------------
    def _export_csv(self):
        if not self._current_rows:
            messagebox.showinfo("Inventar gol", "Nu există cărți de exportat.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            title="Exportă inventar", defaultextension=".csv",
            filetypes=[("Fișiere CSV", "*.csv")],
            initialfile="inventar.csv",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([HEADINGS[c] for c in COLUMNS])
                for i, book in enumerate(self._current_rows, start=1):
                    price = book.get("price")
                    writer.writerow([
                        i, book["isbn"] or "", book["title"], book["author"] or "",
                        book["pub_year"] or "", book.get("publisher") or "",
                        book.get("pub_place") or "", f"{price:.2f}" if price is not None else "",
                        book.get("copies") or 1, book.get("czu") or "",
                        book["category_name"] or "-",
                    ])
        except Exception as exc:
            messagebox.showerror("Eroare export", str(exc), parent=self)
            return

        messagebox.showinfo("Export reușit", f"Inventarul a fost salvat în:\n{path}", parent=self)

    def _export_pdf(self):
        if not self._current_rows:
            messagebox.showinfo("Inventar gol", "Nu există cărți de exportat.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            title="Exportă inventar (PDF)", defaultextension=".pdf",
            filetypes=[("Fișiere PDF", "*.pdf")], initialfile="inventar.pdf",
        )
        if not path:
            return
        try:
            pdf_service.export_inventory_pdf(
                path, self._current_rows, summary_text=self.summary_label.cget("text")
            )
        except Exception as exc:
            messagebox.showerror("Eroare export PDF", str(exc), parent=self)
            return
        self._offer_open(path, "Inventarul a fost salvat")

    def _print_labels(self):
        if not self._current_rows:
            messagebox.showinfo("Inventar gol", "Nu există cărți pentru etichete.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            title="Etichete de raft (PDF)", defaultextension=".pdf",
            filetypes=[("Fișiere PDF", "*.pdf")], initialfile="etichete.pdf",
        )
        if not path:
            return
        try:
            pdf_service.generate_labels_pdf(path, self._current_rows)
        except Exception as exc:
            messagebox.showerror("Eroare generare etichete", str(exc), parent=self)
            return
        self._offer_open(path, f"{len(self._current_rows)} etichete au fost generate")

    def _offer_open(self, path, message):
        """Deschide PDF-ul generat în vizualizatorul implicit (dacă se poate);
        altfel doar confirmă calea."""
        opened = False
        try:
            os.startfile(path)  # doar pe Windows -- exact platforma țintă
            opened = True
        except Exception:
            pass
        if not opened:
            messagebox.showinfo("Gata", f"{message} în:\n{path}", parent=self)
