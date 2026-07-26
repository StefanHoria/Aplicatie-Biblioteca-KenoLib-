# views/borrowers.py
"""
Pagina Cititori: gestiunea persoanelor care împrumută cărți.

Panou stânga = tabelul tuturor cititorilor, cu numărul de cărți pe care le
au acum împrumutate și câte sunt restante (evidențiate roșu). Panou dreapta
= detaliile cititorului selectat: date de contact + cărțile pe care le are
acum la el (cu scadențe) și istoricul returnărilor.

Permite adăugarea, editarea și ștergerea unui cititor. Ștergerea unui cititor
cu împrumuturi active e blocată (ar șterge, prin CASCADE, și înregistrările de
împrumut ale cărților pe care încă nu le-a returnat).
"""

from tkinter import messagebox, ttk

import customtkinter as ctk

from config import COLOR_DANGER_TEXT, COLOR_DANGER_BG, COLOR_ROW_HIGHLIGHT_FG, COLOR_SUCCESS
from utils import (
    style_treeview, TREEVIEW_STYLE_NAME, format_date_ro, is_overdue, stripe_color,
)
from views.dialogs import BorrowerDialog
from views.widgets import SmoothScrollableFrame


class BorrowersPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._borrower_by_iid = {}

        # uniform="cols" forțează un raport strict 3:2 între tabel și panoul de
        # detalii, indiferent de lățimea cerută de conținut -- fără el, lățimea
        # naturală a treeview-ului (coloane fixe) ar înghiți tot spațiul și ar
        # strivi panoul de detalii la câțiva pixeli.
        self.grid_columnconfigure(0, weight=3, uniform="cols")
        self.grid_columnconfigure(1, weight=2, uniform="cols")
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Cititori", font=("", 24, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=24, pady=(20, 10)
        )

        # --- Bară de unelte (căutare + acțiuni) ---
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 10))
        toolbar.grid_columnconfigure(4, weight=1)

        self.search_entry = ctk.CTkEntry(
            toolbar, placeholder_text="caută nume, clasă, email sau telefon...", width=260
        )
        self.search_entry.grid(row=0, column=0, padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda e: self.refresh())

        ctk.CTkButton(toolbar, text="Adaugă cititor", width=130,
                      command=self._add_borrower).grid(row=0, column=1, padx=4)
        ctk.CTkButton(toolbar, text="Editează", width=100,
                      command=self._edit_borrower).grid(row=0, column=2, padx=4)
        ctk.CTkButton(toolbar, text="Șterge", width=90, fg_color=COLOR_DANGER_BG,
                      hover_color=COLOR_DANGER_TEXT, command=self._delete_borrower).grid(
            row=0, column=3, padx=4
        )

        # --- Tabel cititori (stânga) ---
        table_frame = ctk.CTkFrame(self, corner_radius=12)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=(24, 12), pady=(0, 24))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        style_treeview()
        columns = ("name", "sclass", "contact", "active", "overdue")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", style=TREEVIEW_STYLE_NAME
        )
        headings = {"name": "Nume", "sclass": "Clasa", "contact": "Contact",
                    "active": "Împrumutate", "overdue": "Restanțe"}
        widths = {"name": 160, "sclass": 70, "contact": 150, "active": 95, "overdue": 80}
        anchors = {"name": "center", "sclass": "center", "contact": "center",
                   "active": "center", "overdue": "center"}
        for col in columns:
            self.tree.heading(col, text=headings[col], anchor="center")
            self.tree.column(col, width=widths[col], anchor=anchors[col])
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)

        self.tree.tag_configure("overdue", foreground=COLOR_ROW_HIGHLIGHT_FG, background=COLOR_DANGER_BG)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._render_detail())
        self.tree.bind("<Double-1>", lambda e: self._edit_borrower())
        # Scurtături de tastatură, legate de tabel (nu de pagină) ca să NU
        # prindă „+”/Delete tastate în câmpul de căutare: „+” (inclusiv cel de
        # pe blocul numeric) deschide adăugarea; Delete șterge cititorul
        # selectat (fără efect dacă nu e nimic selectat).
        self.tree.bind("<plus>", lambda e: self._add_borrower())
        self.tree.bind("<KP_Add>", lambda e: self._add_borrower())
        self.tree.bind("<Delete>", lambda e: self._delete_borrower() if self._selected_borrower() else None)

        # --- Panou detalii cititor (dreapta) ---
        detail_frame = ctk.CTkFrame(self, corner_radius=12)
        detail_frame.grid(row=2, column=1, sticky="nsew", padx=(12, 24), pady=(0, 24))
        detail_frame.grid_columnconfigure(0, weight=1)
        detail_frame.grid_rowconfigure(1, weight=1)

        self.detail_header = ctk.CTkLabel(
            detail_frame, text="Detalii cititor", font=("", 16, "bold"), anchor="w"
        )
        self.detail_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))

        self.detail_scroll = SmoothScrollableFrame(detail_frame, fg_color="transparent")
        self.detail_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))
        self.detail_scroll.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    def on_show(self):
        self.refresh()

    def refresh(self):
        style_treeview()
        self.tree.tag_configure("oddrow", background=stripe_color())

        previously_selected = None
        selection = self.tree.selection()
        if selection:
            previously_selected = selection[0]

        for row in self.tree.get_children():
            self.tree.delete(row)
        self._borrower_by_iid.clear()

        search = self.search_entry.get().strip() or None
        borrowers = self.app.db.get_borrowers_with_stats(search)
        for i, b in enumerate(borrowers):
            iid = str(b["id"])
            contact = b["email"] or b["phone"] or "—"
            overdue = b["overdue_count"]
            if overdue > 0:
                tags = ("overdue",)
            elif i % 2 == 1:
                tags = ("oddrow",)
            else:
                tags = ()
            self.tree.insert(
                "", "end", iid=iid, tags=tags,
                values=(b["name"], b.get("student_class") or "—", contact,
                        b["active_count"], overdue or "—"),
            )
            self._borrower_by_iid[iid] = b

        # Păstrează selecția peste refresh, dacă cititorul încă există.
        if previously_selected and previously_selected in self._borrower_by_iid:
            self.tree.selection_set(previously_selected)
        self._render_detail()

    # ------------------------------------------------------------------
    def _selected_borrower(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self._borrower_by_iid.get(selection[0])

    def _render_detail(self):
        for widget in self.detail_scroll.winfo_children():
            widget.destroy()

        borrower = self._selected_borrower()
        if not borrower:
            self.detail_header.configure(text="Detalii cititor")
            ctk.CTkLabel(
                self.detail_scroll, text="Selectează un cititor din listă.",
                text_color="gray",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            return

        self.detail_header.configure(text=borrower["name"])

        # Clasa (dacă e completată) + date de contact.
        contact_lines = []
        if borrower.get("student_class"):
            contact_lines.append(f"Clasa: {borrower['student_class']}")
        if borrower["email"]:
            contact_lines.append(f"✉  {borrower['email']}")
        if borrower["phone"]:
            contact_lines.append(f"☎  {borrower['phone']}")
        # Adresa apare doar aici, în detalii -- intenționat NU și în tabel.
        if borrower.get("address"):
            contact_lines.append(f"⌂  {borrower['address']}")
        contact_lines.append(f"Înregistrat: {format_date_ro(borrower['registered_date'])}")
        ctk.CTkLabel(
            self.detail_scroll, text="\n".join(contact_lines), anchor="w",
            justify="left", text_color="gray", font=("", 12),
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 10))

        loans = self.app.db.get_loans_for_borrower(borrower["id"])
        active = [l for l in loans if not l["return_date"]]
        returned = [l for l in loans if l["return_date"]]

        row_i = 1
        # --- Cărți la el acum ---
        ctk.CTkLabel(
            self.detail_scroll, text=f"Împrumutate acum ({len(active)})",
            font=("", 13, "bold"), anchor="w",
        ).grid(row=row_i, column=0, sticky="ew", padx=8, pady=(6, 2))
        row_i += 1

        if not active:
            ctk.CTkLabel(
                self.detail_scroll, text="Nicio carte împrumutată acum.",
                text_color="gray", anchor="w",
            ).grid(row=row_i, column=0, sticky="ew", padx=12, pady=2)
            row_i += 1
        else:
            for loan in active:
                overdue = is_overdue(loan["due_date"], loan["return_date"])
                scadenta = format_date_ro(loan["due_date"])
                suffix = "  · RESTANȚĂ" if overdue else ""
                ctk.CTkLabel(
                    self.detail_scroll,
                    text=f"• {loan['book_title']}  (scadent {scadenta}{suffix})",
                    anchor="w", justify="left",
                    text_color=COLOR_DANGER_TEXT if overdue else None,
                ).grid(row=row_i, column=0, sticky="ew", padx=12, pady=2)
                row_i += 1

        # --- Istoric returnări ---
        ctk.CTkLabel(
            self.detail_scroll, text=f"Istoric returnări ({len(returned)})",
            font=("", 13, "bold"), anchor="w",
        ).grid(row=row_i, column=0, sticky="ew", padx=8, pady=(12, 2))
        row_i += 1

        if not returned:
            ctk.CTkLabel(
                self.detail_scroll, text="Nicio returnare încă.",
                text_color="gray", anchor="w",
            ).grid(row=row_i, column=0, sticky="ew", padx=12, pady=2)
            row_i += 1
        else:
            for loan in returned:
                ctk.CTkLabel(
                    self.detail_scroll,
                    text=f"↩ {loan['book_title']}  (returnat {format_date_ro(loan['return_date'])})",
                    anchor="w", justify="left", text_color=COLOR_SUCCESS,
                ).grid(row=row_i, column=0, sticky="ew", padx=12, pady=2)
                row_i += 1

    # ------------------------------------------------------------------
    def _add_borrower(self):
        BorrowerDialog(self, self.app, on_saved=lambda bid: self.refresh())

    def _edit_borrower(self):
        borrower = self._selected_borrower()
        if not borrower:
            messagebox.showinfo("Selecție necesară", "Selectează un cititor din listă.", parent=self)
            return
        BorrowerDialog(self, self.app, borrower=borrower, on_saved=lambda bid: self.refresh())

    def _delete_borrower(self):
        borrower = self._selected_borrower()
        if not borrower:
            messagebox.showinfo("Selecție necesară", "Selectează un cititor din listă.", parent=self)
            return

        if borrower["active_count"] > 0:
            messagebox.showwarning(
                "Nu se poate șterge",
                f"{borrower['name']} are {borrower['active_count']} carte(cărți) "
                "împrumutate acum. Înregistrează întâi returul lor, apoi poți șterge cititorul.",
                parent=self,
            )
            return

        if messagebox.askyesno(
            "Confirmare ștergere",
            f"Ștergi cititorul „{borrower['name']}”?\n"
            "Se va șterge și istoricul lui de împrumuturi.",
            parent=self,
        ):
            self.app.db.delete_borrower(borrower["id"])
            self.refresh()
