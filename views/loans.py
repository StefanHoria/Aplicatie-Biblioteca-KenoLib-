# views/loans.py
"""
Pagina Împrumuturi active: listează toate împrumuturile nereturnate,
evidențiind cu roșu pe cele care au depășit data scadentă (restanțe).
Permite efectuarea unui împrumut nou și returnarea unei cărți.
"""

from tkinter import messagebox, ttk

import customtkinter as ctk

from config import COLOR_SUCCESS, COLOR_SUCCESS_HOVER, COLOR_DANGER_TEXT, COLOR_DANGER_BG, COLOR_ROW_HIGHLIGHT_FG
from utils import style_treeview, TREEVIEW_STYLE_NAME, format_date_ro, is_overdue, today_iso, stripe_color
from views.dialogs import LoanDialog


class LoansPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Împrumuturi active", font=("", 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 10)
        )

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))

        ctk.CTkButton(toolbar, text="Efectuează Împrumut", command=self._new_loan).grid(
            row=0, column=0, padx=(0, 8)
        )
        ctk.CTkButton(
            toolbar, text="Returnează Carte", fg_color=COLOR_SUCCESS, hover_color=COLOR_SUCCESS_HOVER,
            command=self._return_book
        ).grid(row=0, column=1, padx=8)

        self.legend_label = ctk.CTkLabel(
            toolbar, text="   ● Roșu = termen depășit (restanță)", text_color=COLOR_DANGER_TEXT
        )
        self.legend_label.grid(row=0, column=2, padx=16)

        table_frame = ctk.CTkFrame(self, corner_radius=12)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 24))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        style_treeview()
        columns = ("book", "borrower", "loan_date", "due_date")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", style=TREEVIEW_STYLE_NAME
        )
        headings = {
            "book": "Carte", "borrower": "Împrumutat de",
            "loan_date": "Data împrumut", "due_date": "Data scadentă",
        }
        widths = {"book": 320, "borrower": 220, "loan_date": 130, "due_date": 130}
        for col in columns:
            self.tree.heading(col, text=headings[col], anchor="center")
            self.tree.column(col, width=widths[col], anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)

        self.tree.tag_configure("overdue", foreground=COLOR_ROW_HIGHLIGHT_FG, background=COLOR_DANGER_BG)

        self._loan_by_iid = {}

    # ------------------------------------------------------------------
    def on_show(self):
        self.refresh()

    def refresh(self):
        style_treeview()
        self.tree.tag_configure("oddrow", background=stripe_color())
        for row in self.tree.get_children():
            self.tree.delete(row)
        self._loan_by_iid.clear()

        loans = self.app.db.get_active_loans()
        for i, loan in enumerate(loans):
            iid = str(loan["id"])
            if is_overdue(loan["due_date"], loan["return_date"]):
                tags = ("overdue",)
            elif i % 2 == 1:
                tags = ("oddrow",)
            else:
                tags = ()
            self.tree.insert(
                "", "end", iid=iid, tags=tags,
                values=(
                    loan["book_title"], loan["borrower_name"],
                    format_date_ro(loan["loan_date"]), format_date_ro(loan["due_date"]),
                ),
            )
            self._loan_by_iid[iid] = loan

    def _selected_loan(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self._loan_by_iid.get(selection[0])

    # ------------------------------------------------------------------
    def _new_loan(self):
        LoanDialog(self, self.app, on_saved=self._on_loan_change)

    def _return_book(self):
        loan = self._selected_loan()
        if not loan:
            messagebox.showinfo("Selecție necesară", "Selectează un împrumut din tabel.", parent=self)
            return
        if messagebox.askyesno(
            "Confirmare retur",
            f"Marchezi cartea „{loan['book_title']}” ca returnată de {loan['borrower_name']}?",
            parent=self,
        ):
            self.app.db.return_loan(loan["id"], today_iso())
            self._notify_reservations(loan)
            self._on_loan_change()

    def _notify_reservations(self, loan):
        """Dacă tocmai returnata carte are rezervări active, anunță
        bibliotecarul cine e următorul la rând (coada, în ordine)."""
        reservations = self.app.db.get_reservations_for_book(loan["book_id"])
        if not reservations:
            return
        next_person = reservations[0]["borrower_name"]
        extra = f" (+{len(reservations) - 1} în coadă)" if len(reservations) > 1 else ""
        messagebox.showinfo(
            "Carte rezervată",
            f"„{loan['book_title']}” are {len(reservations)} rezervare(ări) activă(e).\n"
            f"Următorul la rând: {next_person}{extra}.\n\n"
            "Poți marca rezervarea ca onorată din pagina Rezervări.",
            parent=self,
        )

    def _on_loan_change(self):
        self.refresh()
        dashboard = self.app.pages.get("dashboard")
        if dashboard:
            dashboard.refresh()
