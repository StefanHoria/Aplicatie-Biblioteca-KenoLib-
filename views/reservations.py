# views/reservations.py
"""
Pagina Rezervări: coada de așteptare pentru cărți ale căror exemplare sunt
toate împrumutate acum. Când o carte rezervată se întoarce (are cel puțin un
exemplar liber), rezervarea e evidențiată verde ("Disponibilă acum") — semnal
că poate fi dată următorului cititor de la coadă, care apoi se marchează
„onorată".
"""

from tkinter import messagebox, ttk

import customtkinter as ctk

from config import COLOR_SUCCESS, COLOR_DANGER_BG, COLOR_DANGER_TEXT
from utils import style_treeview, TREEVIEW_STYLE_NAME, format_date_ro, stripe_color
from views.dialogs import ReservationDialog


class ReservationsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._res_by_iid = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Rezervări", font=("", 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 10)
        )

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))

        ctk.CTkButton(toolbar, text="Adaugă rezervare", command=self._add_reservation).grid(
            row=0, column=0, padx=(0, 8)
        )
        ctk.CTkButton(
            toolbar, text="Marchează onorată", fg_color=COLOR_SUCCESS,
            command=self._fulfill,
        ).grid(row=0, column=1, padx=8)
        ctk.CTkButton(
            toolbar, text="Anulează rezervare", fg_color=COLOR_DANGER_BG,
            hover_color=COLOR_DANGER_TEXT, command=self._cancel,
        ).grid(row=0, column=2, padx=8)

        self.legend_label = ctk.CTkLabel(
            toolbar, text="   ● Verde = disponibilă acum (gata de ridicat)",
            text_color=COLOR_SUCCESS,
        )
        self.legend_label.grid(row=0, column=3, padx=16)

        table_frame = ctk.CTkFrame(self, corner_radius=12)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 24))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        style_treeview()
        columns = ("book", "borrower", "reserved_date", "status")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", style=TREEVIEW_STYLE_NAME
        )
        headings = {"book": "Carte", "borrower": "Rezervat de",
                    "reserved_date": "Data rezervării", "status": "Stare"}
        widths = {"book": 320, "borrower": 220, "reserved_date": 140, "status": 190}
        anchors = {"book": "w", "borrower": "w", "reserved_date": "center", "status": "center"}
        for col in columns:
            self.tree.heading(col, text=headings[col], anchor="center")
            self.tree.column(col, width=widths[col], anchor=anchors[col])
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)

        self.tree.tag_configure("available", foreground=COLOR_SUCCESS)

    # ------------------------------------------------------------------
    def on_show(self):
        self.refresh()

    def refresh(self):
        style_treeview()
        self.tree.tag_configure("oddrow", background=stripe_color())
        for row in self.tree.get_children():
            self.tree.delete(row)
        self._res_by_iid.clear()

        reservations = self.app.db.get_active_reservations()
        for i, r in enumerate(reservations):
            iid = str(r["id"])
            available = r["available_copies"] > 0
            if available:
                status = "✔ Disponibilă acum"
                tags = ("available",)
            else:
                status = "În așteptare"
                tags = ("oddrow",) if i % 2 == 1 else ()
            self.tree.insert(
                "", "end", iid=iid, tags=tags,
                values=(r["book_title"], r["borrower_name"],
                        format_date_ro(r["reserved_date"]), status),
            )
            self._res_by_iid[iid] = r

    def _selected(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self._res_by_iid.get(selection[0])

    # ------------------------------------------------------------------
    def _add_reservation(self):
        ReservationDialog(self, self.app, on_saved=self.refresh)

    def _fulfill(self):
        res = self._selected()
        if not res:
            messagebox.showinfo("Selecție necesară", "Selectează o rezervare din tabel.", parent=self)
            return
        if res["available_copies"] <= 0 and not messagebox.askyesno(
            "Cartea nu e disponibilă",
            f"Cartea „{res['book_title']}” nu are încă niciun exemplar liber. "
            "Marchezi totuși rezervarea ca onorată?",
            parent=self,
        ):
            return
        self.app.db.fulfill_reservation(res["id"])
        self.refresh()

    def _cancel(self):
        res = self._selected()
        if not res:
            messagebox.showinfo("Selecție necesară", "Selectează o rezervare din tabel.", parent=self)
            return
        if messagebox.askyesno(
            "Anulare rezervare",
            f"Anulezi rezervarea lui {res['borrower_name']} pentru „{res['book_title']}”?",
            parent=self,
        ):
            self.app.db.cancel_reservation(res["id"])
            self.refresh()
