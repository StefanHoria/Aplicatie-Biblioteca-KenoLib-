# views/dashboard.py
"""
Pagina Dashboard: panou cu statistici rapide (total cărți, cărți
împrumutate, restanțieri) și lista activităților recente (împrumuturi
și returnări), utilă bibliotecarului pentru o privire de ansamblu.
"""

import customtkinter as ctk

from config import COLOR_DANGER_TEXT, COLOR_SUCCESS, BRAND_ACCENT
from utils import format_date_ro
from views.widgets import SmoothScrollableFrame


class StatCard(ctk.CTkFrame):
    def __init__(self, master, title, value_color=None, icon=None, accent=None):
        super().__init__(master, corner_radius=10)
        # Coloana 0 = bară-accent colorată (identitatea vizuală dusă în carduri:
        # codează dintr-o privire tipul statisticii); coloana 1 = text.
        self.grid_columnconfigure(1, weight=1)
        if accent:
            # height=1 e esențial: un CTkFrame fără height are implicit 200px,
            # iar cu sticky="ns" ar întinde tot cardul la ~200px. Cu height=1,
            # bara se întinde în schimb doar cât conținutul (title + value),
            # lăsând cardul compact.
            bar = ctk.CTkFrame(self, width=4, height=1, corner_radius=2, fg_color=accent)
            bar.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(12, 0), pady=12)
        text_padx = (12, 18) if accent else (18, 18)
        display_title = f"{icon}  {title}" if icon else title
        self.title_label = ctk.CTkLabel(self, text=display_title, font=("", 13), text_color="gray")
        self.title_label.grid(row=0, column=1, padx=text_padx, pady=(12, 0), sticky="w")
        self.value_label = ctk.CTkLabel(
            self, text="0", font=("", 26, "bold"), text_color=value_color
        )
        self.value_label.grid(row=1, column=1, padx=text_padx, pady=(2, 12), sticky="w")

    def set_value(self, value):
        self.value_label.configure(text=str(value))


class DashboardPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure((0, 1, 2), weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Dashboard", font=("", 24, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=24, pady=(20, 10)
        )

        self.total_card = StatCard(self, "Total cărți în catalog", icon="📚", accent=BRAND_ACCENT)
        self.total_card.grid(row=1, column=0, sticky="ew", padx=(24, 8), pady=8)

        self.borrowed_card = StatCard(
            self, "Cărți împrumutate în acest moment", icon="🔄", accent=COLOR_SUCCESS
        )
        self.borrowed_card.grid(row=1, column=1, sticky="ew", padx=8, pady=8)

        self.overdue_card = StatCard(
            self, "Restanțieri (termen depășit)", value_color=COLOR_DANGER_TEXT,
            icon="⚠️", accent=COLOR_DANGER_TEXT
        )
        self.overdue_card.grid(row=1, column=2, sticky="ew", padx=(8, 24), pady=8)

        activity_frame = ctk.CTkFrame(self, corner_radius=12)
        activity_frame.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=24, pady=(8, 24))
        activity_frame.grid_columnconfigure(0, weight=1)
        activity_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(activity_frame, text="Activitate recentă", font=("", 16, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4)
        )

        self.activity_scroll = SmoothScrollableFrame(activity_frame, fg_color="transparent")
        self.activity_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))
        self.activity_scroll.grid_columnconfigure(0, weight=1)

    def on_show(self):
        self.refresh()

    def refresh(self):
        stats = self.app.db.get_dashboard_stats()
        self.total_card.set_value(stats["total_books"])
        self.borrowed_card.set_value(stats["borrowed_count"])
        self.overdue_card.set_value(stats["overdue_count"])

        for widget in self.activity_scroll.winfo_children():
            widget.destroy()

        activity = self.app.db.get_recent_activity(limit=15)
        if not activity:
            ctk.CTkLabel(self.activity_scroll, text="Nicio activitate încă.", text_color="gray").grid(
                row=0, column=0, sticky="w", padx=8, pady=8
            )
            return

        for i, item in enumerate(activity):
            if item["return_date"]:
                text = (
                    f"↩ Returnat: „{item['book_title']}” de la {item['borrower_name']} "
                    f"pe {format_date_ro(item['return_date'])}"
                )
                color = COLOR_SUCCESS
            else:
                text = (
                    f"📕 Împrumutat: „{item['book_title']}” către {item['borrower_name']} "
                    f"(scadent {format_date_ro(item['due_date'])})"
                )
                color = None
            ctk.CTkLabel(
                self.activity_scroll, text=text, anchor="w", text_color=color, justify="left"
            ).grid(row=i, column=0, sticky="ew", padx=8, pady=4)
