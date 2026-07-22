# views/reports.py
"""
Pagina Rapoarte: statistici textuale clare — carduri cu numărul total
de împrumuturi (istoric, active, restanțieri), numărul de cărți și
împrumuturi din fiecare categorie, clasamentul cărților cel mai des
împrumutate, și istoricul complet al tranzacțiilor de împrumut/retur.
"""

import os
from tkinter import ttk, filedialog, messagebox

import customtkinter as ctk

import pdf_service
from config import COLOR_DANGER_TEXT, COLOR_SUCCESS, BRAND_ACCENT
from utils import style_treeview, TREEVIEW_STYLE_NAME, format_date_ro, stripe_color
from views.dashboard import StatCard
from views.dialogs import BookDialog
from views.widgets import SmoothScrollableFrame

TOP_BOOKS_LIMIT = 10


class ReportsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._last_signature = None  # cache: sări reconstrucția dacă datele nu s-au schimbat

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(20, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Rapoarte", font=("", 24, "bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            header, text="Exportă PDF", width=120, command=self._export_pdf,
        ).grid(row=0, column=1, sticky="e", padx=(0, 8))
        ctk.CTkButton(
            header, text="Reîmprospătează", width=140,
            command=lambda: self.refresh(force=True),
        ).grid(row=0, column=2, sticky="e")

        # --- Carduri statistici împrumuturi ---
        stats_row = ctk.CTkFrame(self, fg_color="transparent")
        stats_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 14))
        stats_row.grid_columnconfigure((0, 1, 2), weight=1)

        self.total_loans_card = StatCard(
            stats_row, "Total împrumuturi (istoric)", icon="📖", accent=BRAND_ACCENT
        )
        self.total_loans_card.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.active_loans_card = StatCard(
            stats_row, "Împrumuturi active", icon="🔄", accent=COLOR_SUCCESS
        )
        self.active_loans_card.grid(row=0, column=1, sticky="ew", padx=8)
        self.overdue_loans_card = StatCard(
            stats_row, "Restanțieri", value_color=COLOR_DANGER_TEXT, icon="⚠️",
            accent=COLOR_DANGER_TEXT
        )
        self.overdue_loans_card.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        # --- Cărți pe categorie (+ nr. de împrumuturi din fiecare) ---
        cat_frame = ctk.CTkFrame(self, corner_radius=12)
        cat_frame.grid(row=2, column=0, sticky="nsew", padx=(24, 12), pady=(0, 12))
        cat_frame.grid_columnconfigure(0, weight=1)
        cat_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(cat_frame, text="Cărți pe categorie", font=("", 16, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4)
        )
        self.category_scroll = SmoothScrollableFrame(cat_frame, fg_color="transparent")
        self.category_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))
        self.category_scroll.grid_columnconfigure(0, weight=1)

        # --- Cele mai împrumutate cărți ---
        top_frame = ctk.CTkFrame(self, corner_radius=12)
        top_frame.grid(row=3, column=0, sticky="nsew", padx=(24, 12), pady=(0, 24))
        top_frame.grid_columnconfigure(0, weight=1)
        top_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(top_frame, text="Cele mai împrumutate cărți", font=("", 16, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4)
        )
        self.top_books_scroll = SmoothScrollableFrame(top_frame, fg_color="transparent")
        self.top_books_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))
        self.top_books_scroll.grid_columnconfigure(0, weight=1)

        # --- Istoric tranzacții ---
        hist_frame = ctk.CTkFrame(self, corner_radius=12)
        hist_frame.grid(row=2, column=1, rowspan=2, sticky="nsew", padx=(12, 24), pady=(0, 24))
        hist_frame.grid_columnconfigure(0, weight=1)
        hist_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(hist_frame, text="Istoricul tranzacțiilor", font=("", 16, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4)
        )

        style_treeview()
        columns = ("book", "borrower", "loan_date", "due_date", "return_date", "status")
        self.tree = ttk.Treeview(
            hist_frame, columns=columns, show="headings", style=TREEVIEW_STYLE_NAME
        )
        headings = {
            "book": "Carte", "borrower": "Împrumutat de", "loan_date": "Împrumutat",
            "due_date": "Scadent", "return_date": "Returnat", "status": "Status",
        }
        widths = {"book": 220, "borrower": 150, "loan_date": 100, "due_date": 100,
                  "return_date": 100, "status": 110}
        for col in columns:
            self.tree.heading(col, text=headings[col], anchor="center")
            self.tree.column(col, width=widths[col], anchor="center")
        self.tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        scrollbar = ttk.Scrollbar(hist_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 8))

        self.tree.tag_configure("returned", foreground=COLOR_SUCCESS)

    # ------------------------------------------------------------------
    def on_show(self):
        self.refresh()

    def _export_pdf(self):
        path = filedialog.asksaveasfilename(
            title="Exportă raport (PDF)", defaultextension=".pdf",
            filetypes=[("Fișiere PDF", "*.pdf")], initialfile="raport.pdf",
        )
        if not path:
            return
        try:
            pdf_service.export_report_pdf(
                path,
                self.app.db.get_dashboard_stats(),
                self.app.db.get_books_per_category(),
                self.app.db.get_top_borrowed_books(limit=TOP_BOOKS_LIMIT),
            )
        except Exception as exc:
            messagebox.showerror("Eroare export PDF", str(exc), parent=self)
            return
        try:
            os.startfile(path)  # Windows -- platforma țintă
        except Exception:
            messagebox.showinfo("Gata", f"Raportul a fost salvat în:\n{path}", parent=self)

    def _open_category(self, category_name):
        """Deschide Inventarul, filtrat pe categoria pe care s-a dat click."""
        self.app.show_page("inventory")
        self.app.pages["inventory"].show_category(category_name)

    def _edit_book(self, book_id):
        book = self.app.db.get_book(book_id)
        if book:
            BookDialog(self, self.app, book=book, on_saved=self.refresh)

    def refresh(self, force=False):
        # Stilurile ttk (treeview) se reaplică mereu -- ttk NU se
        # re-stilizează singur la schimbarea temei, spre deosebire de
        # widget-urile CTk. E ieftin și trebuie făcut chiar și când sărim
        # reconstrucția de mai jos (ex. comutare Dark/Light pe date identice).
        style_treeview()
        self.tree.tag_configure("oddrow", background=stripe_color())
        self.tree.tag_configure("returned", foreground=COLOR_SUCCESS)

        stats = self.app.db.get_dashboard_stats()
        categories = self.app.db.get_books_per_category()
        top_books = self.app.db.get_top_borrowed_books(limit=TOP_BOOKS_LIMIT)
        loans = self.app.db.get_all_loans()

        # Reconstruirea widget-urilor CTk (zeci-sute de etichete/frame-uri,
        # fiecare cu desen pe canvas + aplicare temă) e partea cu adevărat
        # scumpă și e singurul motiv pentru care re-intrarea pe pagină avea
        # lag. O sărim complet dacă datele afișate n-au știut nicio schimbare
        # de la ultimul render -- interogările SQLite de mai sus sunt de ordinul
        # microsecundelor, deci verificarea e practic gratuită. Butonul
        # „Reîmprospătează” trece force=True ca să reconstruiască întotdeauna.
        signature = (
            (stats["total_loans"], stats["borrowed_count"], stats["overdue_count"]),
            tuple((c["category_name"], c["book_count"], c["loan_count"]) for c in categories),
            tuple((b["id"], b["title"], b.get("author"), b.get("category_name"),
                   b["loan_count"]) for b in top_books),
            tuple((l["book_title"], l["borrower_name"], l["loan_date"],
                   l["due_date"], l["return_date"]) for l in loans),
        )
        if not force and signature == self._last_signature:
            return
        self._last_signature = signature

        self.total_loans_card.set_value(stats["total_loans"])
        self.active_loans_card.set_value(stats["borrowed_count"])
        self.overdue_loans_card.set_value(stats["overdue_count"])

        for widget in self.category_scroll.winfo_children():
            widget.destroy()
        if not categories:
            ctk.CTkLabel(self.category_scroll, text="Nicio categorie definită.", text_color="gray").grid(
                row=0, column=0, sticky="w", padx=8, pady=8
            )
        else:
            for i, cat in enumerate(categories):
                row = ctk.CTkFrame(self.category_scroll, fg_color="transparent", cursor="hand2")
                row.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
                row.grid_columnconfigure(0, weight=1)
                name_label = ctk.CTkLabel(
                    row, text=cat["category_name"], anchor="w", cursor="hand2"
                )
                name_label.grid(row=0, column=0, sticky="w")
                count_label = ctk.CTkLabel(
                    row,
                    text=f"{cat['book_count']} cărți · {cat['loan_count']} împrumuturi  ›",
                    anchor="w", text_color="gray", font=("", 11), cursor="hand2",
                )
                count_label.grid(row=1, column=0, sticky="w")

                handler = lambda e, name=cat["category_name"]: self._open_category(name)
                row.bind("<Button-1>", handler)
                name_label.bind("<Button-1>", handler)
                count_label.bind("<Button-1>", handler)

        for widget in self.top_books_scroll.winfo_children():
            widget.destroy()
        if not top_books:
            ctk.CTkLabel(
                self.top_books_scroll, text="Nicio carte împrumutată încă.", text_color="gray"
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
        else:
            for i, book in enumerate(top_books):
                row = ctk.CTkFrame(self.top_books_scroll, fg_color="transparent", cursor="hand2")
                row.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
                row.grid_columnconfigure(0, weight=1)
                title_label = ctk.CTkLabel(
                    row, text=f"{i + 1}. {book['title']}", anchor="w", cursor="hand2"
                )
                title_label.grid(row=0, column=0, sticky="w")
                subtitle = " · ".join(filter(None, [book.get("author"), book.get("category_name")]))
                subtitle_label = None
                if subtitle:
                    subtitle_label = ctk.CTkLabel(
                        row, text=subtitle, anchor="w", text_color="gray", font=("", 11), cursor="hand2"
                    )
                    subtitle_label.grid(row=1, column=0, sticky="w")
                count_label = ctk.CTkLabel(
                    row, text=f"{book['loan_count']}×", font=("", 13, "bold"), cursor="hand2"
                )
                count_label.grid(row=0, column=1, rowspan=2, sticky="e", padx=8)

                handler = lambda e, book_id=book["id"]: self._edit_book(book_id)
                row.bind("<Button-1>", handler)
                title_label.bind("<Button-1>", handler)
                count_label.bind("<Button-1>", handler)
                if subtitle_label:
                    subtitle_label.bind("<Button-1>", handler)

        for row in self.tree.get_children():
            self.tree.delete(row)
        for i, loan in enumerate(loans):
            returned = bool(loan["return_date"])
            tags = []
            if i % 2 == 1:
                tags.append("oddrow")
            if returned:
                tags.append("returned")
            self.tree.insert(
                "", "end", tags=tags,
                values=(
                    loan["book_title"], loan["borrower_name"],
                    format_date_ro(loan["loan_date"]), format_date_ro(loan["due_date"]),
                    format_date_ro(loan["return_date"]) if returned else "-",
                    "Returnat" if returned else "Activ",
                ),
            )
