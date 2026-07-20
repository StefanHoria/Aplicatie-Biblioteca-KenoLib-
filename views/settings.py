# views/settings.py
"""
Pagina Setări: backup și restaurare a bazei de date.

La prima apăsare pe „Backup acum”, dacă nu există încă o locație
salvată, se cere folderul de destinație printr-un dialog și se reține
pentru apăsările următoare (nu se mai cere de fiecare dată). Butonul
„Schimbă locația” permite oricând alegerea unui alt folder.

Numele fișierului de backup e generat automat, într-un format standard
și ușor de dedus: biblioteca_backup_AAAA-LL-ZZ_OO-MM-SS.db

„Restaurează din backup” e o operație distructivă (înlocuiește toate
datele curente), de aceea: cere confirmare explicită, validează că
fișierul ales chiar e o bază de date compatibilă înainte de a atinge
orice, salvează automat un backup de siguranță al datelor curente
înainte de suprascriere, și închide aplicația imediat după — conexiunea
SQLite deschisă în memorie nu mai reflectă fișierul de pe disc odată
înlocuit, deci orice utilizare ulterioară fără repornire ar da date
inconsistente.
"""

import os
import shutil
import sqlite3
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

from config import COLOR_SUCCESS, COLOR_WARNING_BG, COLOR_WARNING_BG_HOVER
from settings_service import (
    get_backup_dir,
    set_backup_dir,
    get_last_backup_info,
    set_last_backup_info,
    get_auto_backup_enabled,
    set_auto_backup_enabled,
    get_auto_backup_retention,
    set_auto_backup_retention,
    get_default_loan_days,
    set_default_loan_days,
)

REQUIRED_TABLES = {"books", "categories", "borrowers", "loans"}


def _is_valid_library_db(path):
    """Verifică minimal că fișierul ales chiar e o bază de date a
    aplicației (are tabelele așteptate), nu un fișier oarecare ales din
    greșeală -- fără asta, o restaurare greșită ar putea înlocui datele
    reale cu un fișier gol/nepotrivit fără niciun avertisment."""
    try:
        conn = sqlite3.connect(path)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        conn.close()
    except sqlite3.Error:
        return False
    return REQUIRED_TABLES.issubset(tables)


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Setări", font=("", 24, "bold")).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 10)
        )

        backup_frame = ctk.CTkFrame(self, corner_radius=12)
        backup_frame.grid(row=1, column=0, sticky="new", padx=24, pady=(0, 24))
        backup_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            backup_frame, text="Backup bază de date", font=("", 16, "bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(
            backup_frame,
            text="Salvează o copie completă a bazei de date (cărți, categorii, "
                 "împrumutători, împrumuturi) într-un fișier separat, ca protecție "
                 "în caz de ștergere accidentală sau problemă de disc.",
            text_color="gray", justify="left", wraplength=560,
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

        self.location_label = ctk.CTkLabel(backup_frame, text="", justify="left")
        self.location_label.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 4))

        self.last_backup_label = ctk.CTkLabel(backup_frame, text="", text_color="gray", justify="left")
        self.last_backup_label.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 10))

        btn_row = ctk.CTkFrame(backup_frame, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="w", padx=16, pady=(0, 6))
        ctk.CTkButton(btn_row, text="Backup acum", command=self._backup_now).grid(
            row=0, column=0, padx=(0, 8)
        )
        ctk.CTkButton(
            btn_row, text="Schimbă locația", fg_color="gray40", command=self._change_location
        ).grid(row=0, column=1)

        self.auto_backup_var = ctk.BooleanVar(value=get_auto_backup_enabled())
        ctk.CTkCheckBox(
            backup_frame, text="Backup automat la închiderea aplicației",
            variable=self.auto_backup_var, command=self._toggle_auto_backup,
        ).grid(row=5, column=0, sticky="w", padx=16, pady=(4, 4))

        retention_row = ctk.CTkFrame(backup_frame, fg_color="transparent")
        retention_row.grid(row=6, column=0, sticky="w", padx=16, pady=(0, 2))
        ctk.CTkLabel(retention_row, text="Păstrează ultimele").grid(row=0, column=0)
        self.retention_entry = ctk.CTkEntry(retention_row, width=50)
        self.retention_entry.insert(0, str(get_auto_backup_retention()))
        self.retention_entry.grid(row=0, column=1, padx=6)
        ctk.CTkLabel(retention_row, text="backup-uri automate").grid(row=0, column=2)
        ctk.CTkButton(
            retention_row, text="Salvează", width=80, command=self._save_retention
        ).grid(row=0, column=3, padx=(8, 0))

        ctk.CTkLabel(
            backup_frame,
            text="Backup-urile automate sunt separate de cele manuale — cele pe care le "
                 "faci tu cu „Backup acum” sau înainte de o restaurare nu sunt niciodată "
                 "șterse automat, doar cele făcute automat, peste limita de mai sus.",
            text_color="gray", justify="left", wraplength=560,
        ).grid(row=7, column=0, sticky="w", padx=16, pady=(0, 10))

        ctk.CTkLabel(
            backup_frame, text="Restaurare din backup", font=("", 16, "bold")
        ).grid(row=8, column=0, sticky="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(
            backup_frame,
            text="Înlocuiește TOATE datele curente cu cele dintr-un fișier de backup ales. "
                 "Se face automat un backup de siguranță al datelor curente înainte.",
            text_color="gray", justify="left", wraplength=560,
        ).grid(row=9, column=0, sticky="w", padx=16, pady=(0, 10))
        ctk.CTkButton(
            backup_frame, text="Restaurează din backup...", fg_color=COLOR_WARNING_BG,
            hover_color=COLOR_WARNING_BG_HOVER, command=self._restore_backup,
        ).grid(row=10, column=0, sticky="w", padx=16, pady=(0, 16))

        loans_frame = ctk.CTkFrame(self, corner_radius=12)
        loans_frame.grid(row=2, column=0, sticky="new", padx=24, pady=(0, 24))
        loans_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            loans_frame, text="Împrumuturi", font=("", 16, "bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(
            loans_frame,
            text="Numărul de zile completat implicit la un împrumut nou (poate fi "
                 "modificat oricând, per împrumut, din formular).",
            text_color="gray", justify="left", wraplength=560,
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

        loan_days_row = ctk.CTkFrame(loans_frame, fg_color="transparent")
        loan_days_row.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 16))
        ctk.CTkLabel(loan_days_row, text="Zile împrumut implicite").grid(row=0, column=0)
        self.loan_days_entry = ctk.CTkEntry(loan_days_row, width=50)
        self.loan_days_entry.insert(0, str(get_default_loan_days()))
        self.loan_days_entry.grid(row=0, column=1, padx=6)
        ctk.CTkButton(
            loan_days_row, text="Salvează", width=80, command=self._save_default_loan_days
        ).grid(row=0, column=2, padx=(8, 0))

        self._refresh_location_label()
        self._refresh_last_backup_label()

    # ------------------------------------------------------------------
    def _refresh_last_backup_label(self):
        info = get_last_backup_info()
        if not info:
            self.last_backup_label.configure(text="Niciun backup efectuat încă.", text_color="gray")
            return
        dt = datetime.fromisoformat(info["timestamp"])
        when = dt.strftime("%d.%m.%Y, ora %H:%M:%S")
        self.last_backup_label.configure(
            text=f"Ultimul backup: {when} — {info['book_count']} cărți",
            text_color=COLOR_SUCCESS,
        )

    def _record_backup(self):
        book_count = self.app.db.get_dashboard_stats()["total_books"]
        set_last_backup_info({
            "timestamp": datetime.now().isoformat(),
            "book_count": book_count,
        })
        self._refresh_last_backup_label()

    def _toggle_auto_backup(self):
        set_auto_backup_enabled(self.auto_backup_var.get())

    def _save_retention(self):
        raw = self.retention_entry.get().strip()
        if not raw.isdigit() or int(raw) < 1:
            messagebox.showwarning(
                "Valoare invalidă", "Introdu un număr întreg mai mare ca 0.", parent=self
            )
            return
        set_auto_backup_retention(int(raw))
        messagebox.showinfo(
            "Salvat", f"Se vor păstra ultimele {raw} backup-uri automate.", parent=self
        )

    def _save_default_loan_days(self):
        raw = self.loan_days_entry.get().strip()
        if not raw.isdigit() or int(raw) < 1:
            messagebox.showwarning(
                "Valoare invalidă", "Introdu un număr întreg de zile mai mare ca 0.", parent=self
            )
            return
        set_default_loan_days(int(raw))
        messagebox.showinfo(
            "Salvat", f"Noile împrumuturi vor avea implicit {raw} zile.", parent=self
        )

    def _refresh_location_label(self):
        backup_dir = get_backup_dir()
        if backup_dir:
            self.location_label.configure(text=f"Locație backup: {backup_dir}")
        else:
            self.location_label.configure(
                text="Locație backup: neconfigurată (se cere la primul backup)"
            )

    def _change_location(self):
        new_dir = filedialog.askdirectory(title="Alege folderul pentru backup", parent=self)
        if not new_dir:
            return
        set_backup_dir(new_dir)
        self._refresh_location_label()
        messagebox.showinfo(
            "Locație salvată", f"Backup-urile viitoare vor fi salvate în:\n{new_dir}", parent=self
        )

    def _backup_now(self):
        backup_dir = get_backup_dir()
        if not backup_dir:
            backup_dir = filedialog.askdirectory(title="Alege folderul pentru backup", parent=self)
            if not backup_dir:
                return
            set_backup_dir(backup_dir)
            self._refresh_location_label()

        try:
            os.makedirs(backup_dir, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "Eroare backup", f"Nu s-a putut folosi folderul:\n{backup_dir}\n\n{exc}", parent=self
            )
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"biblioteca_backup_{timestamp}.db"
        dest_path = os.path.join(backup_dir, filename)

        try:
            self.app.db.backup_to(dest_path)
        except Exception as exc:
            messagebox.showerror("Eroare backup", f"Backup-ul a eșuat:\n{exc}", parent=self)
            return

        self._record_backup()
        messagebox.showinfo("Backup finalizat", f"Backup salvat la:\n{dest_path}", parent=self)

    def _restore_backup(self):
        if not messagebox.askyesno(
            "Confirmă restaurarea",
            "Restaurarea înlocuiește TOATE datele curente (cărți, categorii, "
            "împrumutători, împrumuturi) cu cele din fișierul de backup ales.\n\n"
            "Se salvează automat un backup de siguranță al datelor curente "
            "înainte de suprascriere. Aplicația se va închide imediat după "
            "restaurare — repornește-o pentru a vedea datele restaurate.\n\n"
            "Continui?",
            parent=self,
        ):
            return

        src_path = filedialog.askopenfilename(
            title="Alege fișierul de backup de restaurat",
            initialdir=get_backup_dir() or None,
            filetypes=[("Bază de date Biblioteca", "*.db"), ("Toate fișierele", "*.*")],
            parent=self,
        )
        if not src_path:
            return

        if not _is_valid_library_db(src_path):
            messagebox.showerror(
                "Fișier invalid",
                "Fișierul ales nu pare să fie un backup valid al aplicației "
                "(lipsesc tabelele așteptate: cărți, categorii, împrumutători, "
                "împrumuturi). Restaurarea a fost anulată.",
                parent=self,
            )
            return

        backup_dir = get_backup_dir()
        if not backup_dir:
            backup_dir = filedialog.askdirectory(
                title="Alege folderul pentru backup-ul de siguranță", parent=self
            )
            if not backup_dir:
                return
            set_backup_dir(backup_dir)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safety_path = os.path.join(
            backup_dir, f"biblioteca_backup_inainte_de_restaurare_{timestamp}.db"
        )
        try:
            os.makedirs(backup_dir, exist_ok=True)
            self.app.db.backup_to(safety_path)
            self._record_backup()
        except Exception as exc:
            messagebox.showerror(
                "Restaurare anulată",
                f"Nu s-a putut crea backup-ul de siguranță al datelor curente, "
                f"deci restaurarea NU a fost efectuată:\n{exc}",
                parent=self,
            )
            return

        try:
            self.app.db.close()
            shutil.copy2(src_path, self.app.db.db_path)
        except Exception as exc:
            messagebox.showerror(
                "Eroare restaurare",
                f"Restaurarea a eșuat:\n{exc}\n\n"
                f"Datele curente au fost deja salvate în:\n{safety_path}",
                parent=self,
            )
            return

        messagebox.showinfo(
            "Restaurare completă",
            f"Datele au fost restaurate din:\n{src_path}\n\n"
            f"Backup de siguranță (date dinainte de restaurare):\n{safety_path}\n\n"
            "Aplicația se închide acum — repornește-o pentru a vedea datele restaurate.",
            parent=self,
        )
        self.app.destroy()

    def on_show(self):
        self._refresh_location_label()
        self._refresh_last_backup_label()
