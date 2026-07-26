# views/dialogs.py
"""
Ferestre modale (CTkToplevel) pentru adăugare/editare:
- BookDialog: formular carte, cu auto-completare din scanner GM65 +
  Google Books / Open Library, și sugestie automată de categorie (ML).
- BorrowerDialog: formular împrumutător.
- LoanDialog: formular pentru crearea unui împrumut nou.

Toate ferestrele sunt modale (grab_set) și comunică rezultatul către
pagina care le-a deschis printr-un callback `on_saved`.
"""

import queue
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

import api_service
from config import UNCONFIRMED_CATEGORY, suggest_czu, COLOR_DANGER_TEXT, BRAND_ACCENT, BRAND_TITLE_FONT
from settings_service import get_default_loan_days, get_profile, set_profile
from utils import today_iso, due_date_iso, is_valid_isbn, normalize_isbn, make_logo_icon


class BaseDialog(ctk.CTkToplevel):
    """Fereastră modală de bază: se centrează și capturează focusul."""

    def __init__(self, master, title, width=460, height=560):
        super().__init__(master)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        self.transient(master)
        self.after(50, self.grab_set)
        self.grid_columnconfigure(0, weight=1)


class ProfileDialog(BaseDialog):
    """Configurarea profilului bibliotecii la prima pornire: numele și școala
    de care aparține. Reutilizabil ca fereastră de bun-venit (welcome=True)."""

    def __init__(self, master, app, on_saved=None, welcome=True):
        title = "Bun venit în KenoLib" if welcome else "Editează profilul bibliotecii"
        super().__init__(master, title, width=480, height=400)
        self.app = app
        self.on_saved = on_saved
        profile = get_profile()

        row = 0
        if welcome:
            head = ctk.CTkFrame(self, fg_color="transparent")
            head.grid(row=row, column=0, sticky="w", padx=20, pady=(20, 2))
            make_logo_icon(head, 40).grid(row=0, column=0, padx=(0, 10))
            ctk.CTkLabel(
                head, text="Bun venit în KenoLib!",
                font=(BRAND_TITLE_FONT, 20), text_color=BRAND_ACCENT,
            ).grid(row=0, column=1)
            row += 1
            ctk.CTkLabel(
                self,
                text="Completează datele bibliotecii ca să începi.\n"
                     "Le poți schimba oricând din pagina Setări.",
                text_color="gray", justify="left",
            ).grid(row=row, column=0, sticky="w", padx=20, pady=(0, 14))
            row += 1

        ctk.CTkLabel(self, text="Nume bibliotecă / bibliotecar *").grid(
            row=row, column=0, sticky="w", padx=20, pady=(6, 0)
        )
        row += 1
        self.name_entry = ctk.CTkEntry(self, placeholder_text="ex: Biblioteca „Ion Creangă”")
        self.name_entry.insert(0, profile["name"])
        self.name_entry.grid(row=row, column=0, sticky="ew", padx=20)
        row += 1

        ctk.CTkLabel(self, text="Școala de care aparține biblioteca *").grid(
            row=row, column=0, sticky="w", padx=20, pady=(12, 0)
        )
        row += 1
        self.school_entry = ctk.CTkEntry(
            self, placeholder_text="ex: Școala Gimnazială Nr. 5, Cluj-Napoca"
        )
        self.school_entry.insert(0, profile["school"])
        self.school_entry.grid(row=row, column=0, sticky="ew", padx=20)
        row += 1

        ctk.CTkButton(
            self, text="Salvează și continuă" if welcome else "Salvează",
            command=self._save,
        ).grid(row=row, column=0, sticky="ew", padx=20, pady=(22, 16))

        self.name_entry.focus()

    def _save(self):
        name = self.name_entry.get().strip()
        school = self.school_entry.get().strip()
        if not name or not school:
            messagebox.showwarning(
                "Date incomplete",
                "Completează atât numele bibliotecii, cât și școala.", parent=self,
            )
            return
        set_profile(name, school)
        if self.on_saved:
            self.on_saved()
        self.destroy()


class BookDialog(BaseDialog):
    """Formular de adăugare / editare carte, cu scanner + API + sugestie ML."""

    def __init__(self, master, app, book=None, on_saved=None):
        mode = "Editează carte" if book else "Adaugă carte"
        super().__init__(master, mode, width=520, height=860)
        self.app = app
        self.book = book
        self.on_saved = on_saved
        self._api_queue = queue.Queue()
        self._polling = True
        self._last_category_hint = None
        self._did_followup_search = False

        pad = {"padx": 16, "pady": (10, 0)}

        # --- ISBN + căutare online ---
        ctk.CTkLabel(self, text="ISBN").grid(row=0, column=0, sticky="w", **pad)
        isbn_row = ctk.CTkFrame(self, fg_color="transparent")
        isbn_row.grid(row=1, column=0, sticky="ew", padx=16)
        isbn_row.grid_columnconfigure(0, weight=1)
        self.isbn_entry = ctk.CTkEntry(isbn_row, placeholder_text="ex: 9789734620974")
        self.isbn_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(isbn_row, text="Caută online", width=110,
                      command=self._lookup_online).grid(row=0, column=1, padx=(8, 0))

        self.scanner_status = ctk.CTkLabel(
            self, text="Scanner: neconectat", text_color="gray", font=("", 11)
        )
        self.scanner_status.grid(row=2, column=0, sticky="w", padx=16, pady=(2, 0))

        # --- Titlu ---
        ctk.CTkLabel(self, text="Titlu *").grid(row=3, column=0, sticky="w", **pad)
        self.title_entry = ctk.CTkEntry(self)
        self.title_entry.grid(row=4, column=0, sticky="ew", padx=16)

        # --- Autor ---
        ctk.CTkLabel(self, text="Autor").grid(row=5, column=0, sticky="w", **pad)
        self.author_entry = ctk.CTkEntry(self)
        self.author_entry.grid(row=6, column=0, sticky="ew", padx=16)

        # --- An publicare + Nr. cărți ---
        year_copies_row = ctk.CTkFrame(self, fg_color="transparent")
        year_copies_row.grid(row=7, column=0, sticky="ew", padx=16, pady=(10, 0))
        year_copies_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(year_copies_row, text="An publicare").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(year_copies_row, text="Nr. exemplare").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.year_entry = ctk.CTkEntry(year_copies_row)
        self.year_entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.copies_entry = ctk.CTkEntry(year_copies_row)
        self.copies_entry.insert(0, "1")
        self.copies_entry.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(2, 0))

        # --- Editură + Loc apariție ---
        publisher_row = ctk.CTkFrame(self, fg_color="transparent")
        publisher_row.grid(row=8, column=0, sticky="ew", padx=16, pady=(10, 0))
        publisher_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(publisher_row, text="Editură").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(publisher_row, text="Loc apariție").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.publisher_entry = ctk.CTkEntry(publisher_row)
        self.publisher_entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.pub_place_entry = ctk.CTkEntry(publisher_row)
        self.pub_place_entry.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(2, 0))

        # --- Preț + CZU ---
        price_czu_row = ctk.CTkFrame(self, fg_color="transparent")
        price_czu_row.grid(row=9, column=0, sticky="ew", padx=16, pady=(10, 0))
        price_czu_row.grid_columnconfigure(0, weight=1)
        price_czu_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(price_czu_row, text="Preț (lei)").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(price_czu_row, text="CZU").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.price_entry = ctk.CTkEntry(price_czu_row)
        self.price_entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        czu_input_row = ctk.CTkFrame(price_czu_row, fg_color="transparent")
        czu_input_row.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(2, 0))
        czu_input_row.grid_columnconfigure(0, weight=1)
        self.czu_entry = ctk.CTkEntry(czu_input_row)
        self.czu_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(czu_input_row, text="Sugerează", width=70,
                      command=self._suggest_czu).grid(row=0, column=1, padx=(6, 0))

        # --- Descriere ---
        ctk.CTkLabel(self, text="Descriere").grid(row=10, column=0, sticky="w", **pad)
        self.desc_text = ctk.CTkTextbox(self, height=100)
        self.desc_text.grid(row=11, column=0, sticky="ew", padx=16)

        # --- Categorie + sugestie ML ---
        ctk.CTkLabel(self, text="Categorie").grid(row=12, column=0, sticky="w", **pad)
        cat_row = ctk.CTkFrame(self, fg_color="transparent")
        cat_row.grid(row=13, column=0, sticky="ew", padx=16)
        cat_row.grid_columnconfigure(0, weight=1)
        category_names = [c["name"] for c in self.app.db.get_all_categories()]
        self.category_combo = ctk.CTkComboBox(cat_row, values=category_names)
        self.category_combo.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(cat_row, text="Sugerează (ML)", width=120,
                      command=self._suggest_category).grid(row=0, column=1, padx=(8, 0))

        self.ml_confidence_label = ctk.CTkLabel(self, text="", text_color="gray", font=("", 11))
        self.ml_confidence_label.grid(row=14, column=0, sticky="w", padx=16, pady=(2, 0))

        # --- Butoane ---
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=15, column=0, sticky="ew", padx=16, pady=16)
        btn_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btn_row, text="Anulează", fg_color="gray40",
                      command=self.close).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Salvează", command=self._save).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

        if book:
            self._fill_from_book(book)
        else:
            self.category_combo.set(UNCONFIRMED_CATEGORY)

        self.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_api_queue()

    # ------------------------------------------------------------------
    def _fill_from_book(self, book):
        self.isbn_entry.insert(0, book.get("isbn") or "")
        self.title_entry.insert(0, book.get("title") or "")
        self.author_entry.insert(0, book.get("author") or "")
        if book.get("pub_year"):
            self.year_entry.insert(0, str(book["pub_year"]))
        if book.get("desc"):
            self.desc_text.insert("1.0", book["desc"])
        self.publisher_entry.insert(0, book.get("publisher") or "")
        self.pub_place_entry.insert(0, book.get("pub_place") or "")
        self.czu_entry.insert(0, book.get("czu") or "")
        self.copies_entry.delete(0, "end")
        self.copies_entry.insert(0, str(book.get("copies") or 1))
        if book.get("price") is not None:
            self.price_entry.insert(0, str(book["price"]))
        self.category_combo.set(book.get("category_name") or UNCONFIRMED_CATEGORY)

    # ------------------------------------------------------------------
    # Scanner GM65: apelat din CatalogPage când sosește un cod nou
    def set_isbn_and_lookup(self, isbn):
        self.isbn_entry.delete(0, "end")
        self.isbn_entry.insert(0, isbn)
        self.scanner_status.configure(text=f"Scanner: cod primit ({isbn})", text_color="green")
        self._lookup_online()

    def _lookup_online(self):
        isbn = self.isbn_entry.get().strip()
        title = self.title_entry.get().strip()
        author = self.author_entry.get().strip()

        if isbn and not is_valid_isbn(isbn):
            self.scanner_status.configure(
                text=f"ISBN invalid ({isbn}) — se încearcă după titlu/autor, dacă sunt completate.",
                text_color=COLOR_DANGER_TEXT,
            )
            isbn = ""

        if not isbn and not title:
            messagebox.showwarning(
                "Date insuficiente",
                "Introdu un ISBN valid sau completează cel puțin titlul cărții.",
                parent=self,
            )
            return

        # O căutare nouă, pornită explicit (buton/scanner) — resetează
        # starea de la o căutare anterioară, ca să permită un nou follow-up.
        self._last_category_hint = None
        self._did_followup_search = False
        self.scanner_status.configure(text="Se caută online...", text_color="gray")

        # Dacă există un ISBN, prima căutare se face STRICT după el, fără
        # titlul/autorul curente din formular — acelea pot fi rămase de la
        # o carte anterioară (ex. utilizatorul a schimbat ISBN-ul unei
        # cărți deja completate) și ar contamina căutarea cu date greșite
        # (rezultatul combinat ISBN+titlu ar putea favoriza descrierea mai
        # bogată a cărții vechi, dând impresia că "nu se schimbă nimic").
        # Titlul corect al noului ISBN vine din rezultat, iar follow-up-ul
        # automat de mai jos (dacă răspunsul e "subțire") va folosi apoi
        # titlul corect pentru o căutare combinată mai bogată.
        search_title = "" if isbn else title
        search_author = "" if isbn else author
        threading.Thread(
            target=self._fetch_worker,
            args=(normalize_isbn(isbn), search_title, search_author, False),
            daemon=True,
        ).start()

    def _fetch_worker(self, isbn, title, author, is_followup):
        result = api_service.fetch_book_metadata(isbn=isbn, title=title, author=author)
        self._api_queue.put((is_followup, result))

    def _poll_api_queue(self):
        if not self._polling:
            return
        try:
            is_followup, result = self._api_queue.get_nowait()
            self._apply_api_result(result, is_followup=is_followup)
        except queue.Empty:
            pass
        self.after(200, self._poll_api_queue)

    def _apply_api_result(self, result, is_followup=False):
        if not result:
            if not is_followup:
                messagebox.showinfo(
                    "Fără rezultate", "Nu s-au găsit informații online pentru această carte.",
                    parent=self,
                )
            return

        # La follow-up (declanșat automat, vezi mai jos), titlul/autorul/
        # anul deja completate de prima căutare NU se suprascriu (ar putea
        # înlocui un titlu românesc corect cu unul într-o altă limbă) —
        # dar dacă rămăseseră goale, se completează normal din follow-up.
        if result.get("title") and (not is_followup or not self.title_entry.get().strip()):
            self.title_entry.delete(0, "end")
            self.title_entry.insert(0, result["title"])
        if result.get("author") and (not is_followup or not self.author_entry.get().strip()):
            self.author_entry.delete(0, "end")
            self.author_entry.insert(0, result["author"])
        if result.get("pub_year") and (not is_followup or not self.year_entry.get().strip()):
            self.year_entry.delete(0, "end")
            self.year_entry.insert(0, str(result["pub_year"]))

        # La o căutare nouă (is_followup=False) datele vechi din formular
        # aparțin altei cărți și trebuie înlocuite necondiționat. Doar la
        # follow-up-ul automat (aceeași căutare, date suplimentare) se
        # păstrează regulile "mai bun decât ce am deja".
        new_desc = result.get("desc") or ""
        current_desc = self.desc_text.get("1.0", "end").strip()
        if new_desc and (not is_followup or len(new_desc) > len(current_desc)):
            self.desc_text.delete("1.0", "end")
            self.desc_text.insert("1.0", new_desc)

        if result.get("isbn") and not self.isbn_entry.get().strip():
            # ISBN descoperit prin căutare după titlu/autor — util pentru
            # cărțile vechi care nu aveau ISBN completat inițial.
            self.isbn_entry.delete(0, "end")
            self.isbn_entry.insert(0, result["isbn"])
        if result.get("publisher") and (not is_followup or not self.publisher_entry.get().strip()):
            self.publisher_entry.delete(0, "end")
            self.publisher_entry.insert(0, result["publisher"])
        if result.get("pub_place") and (not is_followup or not self.pub_place_entry.get().strip()):
            self.pub_place_entry.delete(0, "end")
            self.pub_place_entry.insert(0, result["pub_place"])
        # Păstrat pentru _suggest_category(): folosit ca failsafe (dacă ML
        # rămâne nesigur) doar atunci când există conexiune la internet și
        # una dintre surse a oferit o categorie generică proprie.
        if result.get("category_hint"):
            self._last_category_hint = result["category_hint"]

        # Rezultatul inițial (adesea doar din ISBN) e uneori "subțire" —
        # fără descriere, cu o descriere prea scurtă ca să fie utilă, sau
        # fără sugestie de categorie — mai ales pentru ediții mai puțin
        # documentate. O descriere scurtă (ex. 40 caractere) tot conta ca
        # "nu e subțire" dacă exista o categorie, deci follow-up-ul automat
        # nu se declanșa și utilizatorul trebuia să caute manual a doua
        # oară ca să obțină descrierea lungă. Acum că titlul e completat,
        # se încearcă automat, o singură dată, și o căutare combinată
        # ISBN+titlu (vezi api_service.fetch_book_metadata), care găsește
        # adesea date mult mai bogate (ex. o ediție într-o altă limbă).
        MIN_USEFUL_DESC_LEN = 150
        is_thin = len(new_desc) < MIN_USEFUL_DESC_LEN or not self._last_category_hint
        isbn_now = self.isbn_entry.get().strip()
        title_now = self.title_entry.get().strip()
        if is_thin and not is_followup and not self._did_followup_search and isbn_now and title_now:
            self._did_followup_search = True
            self.scanner_status.configure(
                text=f"Date completate din {result.get('source', 'API')} — se caută date suplimentare...",
                text_color="gray",
            )
            threading.Thread(
                target=self._fetch_worker,
                args=(normalize_isbn(isbn_now), title_now, self.author_entry.get().strip(), True),
                daemon=True,
            ).start()
            return

        self.scanner_status.configure(
            text=f"Date completate din {result.get('source', 'API')}", text_color="green"
        )
        self._suggest_category()

    # ------------------------------------------------------------------
    def _suggest_category(self):
        text = f"{self.title_entry.get()} {self.desc_text.get('1.0', 'end')}".strip()
        category, confidence = self.app.classifier.predict(text)

        if category == UNCONFIRMED_CATEGORY and self._last_category_hint:
            # Failsafe online: ML nu e sigur, dar o căutare online anterioară
            # a oferit o categorie generică (ex. Google Books) — mai bine
            # decât "De Confirmat", deși mai puțin sigură decât o predicție
            # ML cu încredere suficientă.
            self.category_combo.set(self._last_category_hint)
            self.ml_confidence_label.configure(
                text=f"ML nesigur — categorie preluată online: {self._last_category_hint}"
            )
            return

        self.category_combo.set(category)
        if confidence > 0:
            self.ml_confidence_label.configure(
                text=f"Sugestie ML: {category} (încredere {confidence * 100:.0f}%)"
            )
        else:
            self.ml_confidence_label.configure(
                text="Model ML neantrenat încă — categorie implicită."
            )

    def _suggest_czu(self):
        """
        Completează un cod CZU de pornire pe baza categoriei curente.
        Doar o sugestie generală (clasele principale UDC) — nu înlocuiește
        o catalogare CZU completă, făcută cu tabelele oficiale.
        """
        category_name = self.category_combo.get().strip()
        czu = suggest_czu(category_name)
        if czu:
            self.czu_entry.delete(0, "end")
            self.czu_entry.insert(0, czu)
        elif category_name == UNCONFIRMED_CATEGORY or not category_name:
            # Cazul cel mai frecvent: cartea nu are încă o categorie reală
            # (ML nesigur, fără internet la momentul căutării etc.) — nu e
            # o eroare, dar mesajul anterior ("fără sugestie") era confuz.
            messagebox.showinfo(
                "Alege întâi o categorie",
                "Cartea este momentan „De Confirmat” — alege o categorie reală "
                "din listă (sau apasă „Sugerează (ML)”) înainte de a cere o "
                "sugestie CZU.",
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Fără sugestie",
                f"Nu există o sugestie CZU predefinită pentru categoria „{category_name}” "
                "(probabil o categorie proprie, adăugată manual).",
                parent=self,
            )

    # ------------------------------------------------------------------
    def _save(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("Titlu lipsă", "Titlul este obligatoriu.", parent=self)
            return

        isbn = self.isbn_entry.get().strip()
        author = self.author_entry.get().strip()
        desc = self.desc_text.get("1.0", "end").strip()
        year_raw = self.year_entry.get().strip()
        pub_year = int(year_raw) if year_raw.isdigit() else None
        category_name = self.category_combo.get().strip() or UNCONFIRMED_CATEGORY
        category_id = self.app.db.get_or_create_category(category_name)

        publisher = self.publisher_entry.get().strip()
        pub_place = self.pub_place_entry.get().strip()
        czu = self.czu_entry.get().strip()

        price_raw = self.price_entry.get().strip().replace(",", ".")
        price = None
        if price_raw:
            try:
                price = float(price_raw)
            except ValueError:
                messagebox.showwarning(
                    "Preț invalid", "Prețul trebuie să fie un număr (ex: 39.99).", parent=self
                )
                return

        copies_raw = self.copies_entry.get().strip()
        copies = int(copies_raw) if copies_raw.isdigit() and int(copies_raw) > 0 else 1

        if self.book:
            self.app.db.update_book(
                self.book["id"], isbn, title, author, pub_year, desc, category_id,
                price=price, publisher=publisher, copies=copies, pub_place=pub_place, czu=czu,
            )
        else:
            self.app.db.add_book(
                isbn, title, author, pub_year, desc, category_id,
                price=price, publisher=publisher, copies=copies, pub_place=pub_place, czu=czu,
            )

        if self.on_saved:
            self.on_saved()
        self.close()

    def close(self):
        self._polling = False
        self.destroy()


class BorrowerDialog(BaseDialog):
    """Formular de adăugare / editare împrumutător."""

    def __init__(self, master, app, borrower=None, on_saved=None):
        mode = "Editează împrumutător" if borrower else "Adaugă împrumutător"
        super().__init__(master, mode, width=420, height=390)
        self.app = app
        self.borrower = borrower
        self.on_saved = on_saved

        pad = {"padx": 16, "pady": (10, 0)}

        ctk.CTkLabel(self, text="Nume *").grid(row=0, column=0, sticky="w", **pad)
        self.name_entry = ctk.CTkEntry(self)
        self.name_entry.grid(row=1, column=0, sticky="ew", padx=16)

        # Clasa: relevantă într-o bibliotecă școlară; pusă imediat sub nume,
        # înaintea datelor de contact (mai importantă decât email/telefon
        # pentru un elev). Rămâne opțională -- profesorii n-au clasă.
        ctk.CTkLabel(self, text="Clasa").grid(row=2, column=0, sticky="w", **pad)
        self.class_entry = ctk.CTkEntry(self, placeholder_text="ex.: 9 A")
        self.class_entry.grid(row=3, column=0, sticky="ew", padx=16)

        ctk.CTkLabel(self, text="Email").grid(row=4, column=0, sticky="w", **pad)
        self.email_entry = ctk.CTkEntry(self)
        self.email_entry.grid(row=5, column=0, sticky="ew", padx=16)

        ctk.CTkLabel(self, text="Telefon").grid(row=6, column=0, sticky="w", **pad)
        self.phone_entry = ctk.CTkEntry(self)
        self.phone_entry.grid(row=7, column=0, sticky="ew", padx=16)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=8, column=0, sticky="ew", padx=16, pady=20)
        btn_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btn_row, text="Anulează", fg_color="gray40",
                      command=self.destroy).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Salvează", command=self._save).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

        if borrower:
            self.name_entry.insert(0, borrower.get("name") or "")
            self.class_entry.insert(0, borrower.get("student_class") or "")
            self.email_entry.insert(0, borrower.get("email") or "")
            self.phone_entry.insert(0, borrower.get("phone") or "")

    def _save(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("Nume lipsă", "Numele este obligatoriu.", parent=self)
            return
        student_class = self.class_entry.get().strip()
        email = self.email_entry.get().strip()
        phone = self.phone_entry.get().strip()

        if self.borrower:
            self.app.db.update_borrower(self.borrower["id"], name, email, phone, student_class)
            borrower_id = self.borrower["id"]
        else:
            borrower_id = self.app.db.add_borrower(name, email, phone, student_class)

        if self.on_saved:
            self.on_saved(borrower_id)
        self.destroy()


class LoanDialog(BaseDialog):
    """Formular pentru înregistrarea unui împrumut nou."""

    def __init__(self, master, app, on_saved=None):
        super().__init__(master, "Efectuează împrumut", width=480, height=420)
        self.app = app
        self.on_saved = on_saved
        self._book_map = {}
        self._borrower_map = {}

        pad = {"padx": 16, "pady": (10, 0)}

        ctk.CTkLabel(self, text="Caută carte disponibilă").grid(row=0, column=0, sticky="w", **pad)
        self.book_search = ctk.CTkEntry(self, placeholder_text="titlu, autor sau ISBN...")
        self.book_search.grid(row=1, column=0, sticky="ew", padx=16)
        self.book_search.bind("<KeyRelease>", lambda e: self._refresh_books())

        self.book_combo = ctk.CTkComboBox(self, values=[])
        self.book_combo.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 0))

        ctk.CTkLabel(self, text="Caută împrumutător").grid(row=3, column=0, sticky="w", **pad)
        self.borrower_search = ctk.CTkEntry(self, placeholder_text="nume, email sau telefon...")
        self.borrower_search.grid(row=4, column=0, sticky="ew", padx=16)
        self.borrower_search.bind("<KeyRelease>", lambda e: self._refresh_borrowers())

        borrower_row = ctk.CTkFrame(self, fg_color="transparent")
        borrower_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(6, 0))
        borrower_row.grid_columnconfigure(0, weight=1)
        self.borrower_combo = ctk.CTkComboBox(borrower_row, values=[])
        self.borrower_combo.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(borrower_row, text="+ Nou", width=70,
                      command=self._add_new_borrower).grid(row=0, column=1, padx=(8, 0))

        ctk.CTkLabel(self, text="Dată împrumut").grid(row=6, column=0, sticky="w", **pad)
        self.loan_date_entry = ctk.CTkEntry(self)
        self.loan_date_entry.insert(0, today_iso())
        self.loan_date_entry.grid(row=7, column=0, sticky="ew", padx=16)

        ctk.CTkLabel(self, text="Dată scadentă").grid(row=8, column=0, sticky="w", **pad)
        self.due_date_entry = ctk.CTkEntry(self)
        self.due_date_entry.insert(0, due_date_iso(get_default_loan_days()))
        self.due_date_entry.grid(row=9, column=0, sticky="ew", padx=16)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=10, column=0, sticky="ew", padx=16, pady=20)
        btn_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btn_row, text="Anulează", fg_color="gray40",
                      command=self.destroy).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Confirmă împrumut", command=self._save).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

        self._refresh_books()
        self._refresh_borrowers()

    def _refresh_books(self):
        search = self.book_search.get().strip() or None
        books = self.app.db.get_available_books(search)
        # Arată câte exemplare mai sunt libere doar când cartea are mai multe
        # (la un singur exemplar, "1 liber" e evident și doar aglomerează).
        def _label(b):
            base = f"{b['title']} — {b['author'] or 'necunoscut'} (ISBN {b['isbn'] or '-'})"
            if b.get("copies", 1) > 1:
                base += f" · {b['available_copies']} libere"
            return base
        self._book_map = {_label(b): b["id"] for b in books}
        values = list(self._book_map.keys()) or ["Nicio carte disponibilă"]
        self.book_combo.configure(values=values)
        self.book_combo.set(values[0])

    def _refresh_borrowers(self):
        search = self.borrower_search.get().strip() or None
        borrowers = self.app.db.get_all_borrowers(search)
        self._borrower_map = {
            f"{b['name']} ({b['email'] or b['phone'] or 'fără contact'})": b["id"]
            for b in borrowers
        }
        values = list(self._borrower_map.keys()) or ["Niciun împrumutător înregistrat"]
        self.borrower_combo.configure(values=values)
        self.borrower_combo.set(values[0])

    def _add_new_borrower(self):
        BorrowerDialog(self, self.app, on_saved=self._on_borrower_added)

    def _on_borrower_added(self, borrower_id):
        self.borrower_search.delete(0, "end")
        self._refresh_borrowers()
        for label, bid in self._borrower_map.items():
            if bid == borrower_id:
                self.borrower_combo.set(label)
                break

    def _save(self):
        book_key = self.book_combo.get()
        borrower_key = self.borrower_combo.get()
        book_id = self._book_map.get(book_key)
        borrower_id = self._borrower_map.get(borrower_key)

        if not book_id or not borrower_id:
            messagebox.showwarning(
                "Selecție invalidă", "Selectează o carte disponibilă și un împrumutător.",
                parent=self,
            )
            return

        loan_date = self.loan_date_entry.get().strip() or today_iso()
        due_date = self.due_date_entry.get().strip() or due_date_iso(get_default_loan_days())

        self.app.db.add_loan(book_id, borrower_id, loan_date, due_date)

        if self.on_saved:
            self.on_saved()
        self.destroy()


class ReservationDialog(BaseDialog):
    """Formular de rezervare: pune un cititor la coadă pentru o carte ale
    cărei exemplare sunt toate împrumutate acum."""

    def __init__(self, master, app, on_saved=None):
        super().__init__(master, "Rezervă o carte", width=480, height=340)
        self.app = app
        self.on_saved = on_saved
        self._book_map = {}
        self._borrower_map = {}

        pad = {"padx": 16, "pady": (10, 0)}

        ctk.CTkLabel(self, text="Caută carte indisponibilă (toate exemplarele împrumutate)").grid(
            row=0, column=0, sticky="w", **pad
        )
        self.book_search = ctk.CTkEntry(self, placeholder_text="titlu, autor sau ISBN...")
        self.book_search.grid(row=1, column=0, sticky="ew", padx=16)
        self.book_search.bind("<KeyRelease>", lambda e: self._refresh_books())
        self.book_combo = ctk.CTkComboBox(self, values=[])
        self.book_combo.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 0))

        ctk.CTkLabel(self, text="Caută cititor").grid(row=3, column=0, sticky="w", **pad)
        self.borrower_search = ctk.CTkEntry(self, placeholder_text="nume, email sau telefon...")
        self.borrower_search.grid(row=4, column=0, sticky="ew", padx=16)
        self.borrower_search.bind("<KeyRelease>", lambda e: self._refresh_borrowers())

        borrower_row = ctk.CTkFrame(self, fg_color="transparent")
        borrower_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(6, 0))
        borrower_row.grid_columnconfigure(0, weight=1)
        self.borrower_combo = ctk.CTkComboBox(borrower_row, values=[])
        self.borrower_combo.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(borrower_row, text="+ Nou", width=70,
                      command=self._add_new_borrower).grid(row=0, column=1, padx=(8, 0))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=6, column=0, sticky="ew", padx=16, pady=20)
        btn_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btn_row, text="Anulează", fg_color="gray40",
                      command=self.destroy).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Confirmă rezervarea", command=self._save).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

        self._refresh_books()
        self._refresh_borrowers()

    def _refresh_books(self):
        search = self.book_search.get().strip() or None
        books = self.app.db.get_unavailable_books(search)
        self._book_map = {
            f"{b['title']} — {b['author'] or 'necunoscut'} (ISBN {b['isbn'] or '-'})": b["id"]
            for b in books
        }
        values = list(self._book_map.keys()) or ["Nicio carte indisponibilă acum"]
        self.book_combo.configure(values=values)
        self.book_combo.set(values[0])

    def _refresh_borrowers(self):
        search = self.borrower_search.get().strip() or None
        borrowers = self.app.db.get_all_borrowers(search)
        self._borrower_map = {
            f"{b['name']} ({b['email'] or b['phone'] or 'fără contact'})": b["id"]
            for b in borrowers
        }
        values = list(self._borrower_map.keys()) or ["Niciun cititor înregistrat"]
        self.borrower_combo.configure(values=values)
        self.borrower_combo.set(values[0])

    def _add_new_borrower(self):
        BorrowerDialog(self, self.app, on_saved=self._on_borrower_added)

    def _on_borrower_added(self, borrower_id):
        self.borrower_search.delete(0, "end")
        self._refresh_borrowers()
        for label, bid in self._borrower_map.items():
            if bid == borrower_id:
                self.borrower_combo.set(label)
                break

    def _save(self):
        book_id = self._book_map.get(self.book_combo.get())
        borrower_id = self._borrower_map.get(self.borrower_combo.get())
        if not book_id or not borrower_id:
            messagebox.showwarning(
                "Selecție invalidă",
                "Selectează o carte indisponibilă și un cititor.", parent=self,
            )
            return
        if self.app.db.has_active_reservation(book_id, borrower_id):
            messagebox.showinfo(
                "Rezervare existentă",
                "Acest cititor are deja o rezervare activă pentru această carte.",
                parent=self,
            )
            return

        self.app.db.add_reservation(book_id, borrower_id)
        if self.on_saved:
            self.on_saved()
        self.destroy()
