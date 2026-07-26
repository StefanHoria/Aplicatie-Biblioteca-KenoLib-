# database.py
"""
Stratul de acces la date (Model din MVC).

Încapsulează toată logica SQLite: crearea automată a schemei la prima
rulare, seed-ul categoriilor implicite și operațiile CRUD pentru
categorii, cărți, împrumutători (borrowers) și împrumuturi (loans).

Se folosește câte o conexiune SQLite per thread (via `threading.local`)
deoarece aplicația accesează baza de date atât din thread-ul principal
(GUI), cât și din thread-uri secundare (import CSV, antrenare ML).
sqlite3 nu permite partajarea aceleiași conexiuni între thread-uri fără
`check_same_thread=False`, iar conexiunile separate per thread evită
coruperea cursoarelor concurente.
"""

import sqlite3
import threading
from datetime import date

from config import DB_PATH, DEFAULT_CATEGORIES, UNCONFIRMED_CATEGORY

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS books (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    isbn        TEXT,
    title       TEXT NOT NULL,
    author      TEXT,
    pub_year    INTEGER,
    desc        TEXT,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL
    -- price, publisher, copies, pub_place, czu: adăugate ulterior prin
    -- migrare (vezi _migrate_schema), ca bazele de date existente ale
    -- utilizatorilor să nu își piardă datele la actualizarea aplicației.
);

CREATE TABLE IF NOT EXISTS borrowers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    student_class   TEXT,
    address         TEXT,
    registered_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    borrower_id INTEGER NOT NULL REFERENCES borrowers(id) ON DELETE CASCADE,
    loan_date   TEXT NOT NULL,
    due_date    TEXT NOT NULL,
    return_date TEXT
);

-- Rezervări: un cititor "se pune la coadă" pentru o carte ale cărei
-- exemplare sunt toate împrumutate acum. fulfilled_date NULL = rezervare
-- activă (în așteptare); completat = onorată/închisă. CREATE ... IF NOT
-- EXISTS => se adaugă automat și la bazele de date create cu versiuni mai
-- vechi, la prima pornire (executescript rulează la fiecare inițializare).
CREATE TABLE IF NOT EXISTS reservations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id        INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    borrower_id    INTEGER NOT NULL REFERENCES borrowers(id) ON DELETE CASCADE,
    reserved_date  TEXT NOT NULL,
    fulfilled_date TEXT
);
"""


# Coloane adăugate ulterior schemei inițiale a tabelului "books".
# _migrate_schema() le adaugă prin ALTER TABLE dacă lipsesc, păstrând
# datele existente ale utilizatorului (nu se recreează tabelul).
BOOKS_NEW_COLUMNS = [
    ("price", "REAL"),
    ("publisher", "TEXT"),
    ("copies", "INTEGER NOT NULL DEFAULT 1"),
    ("pub_place", "TEXT"),
    ("czu", "TEXT"),
]

# Idem pentru tabelul "borrowers": clasa cititorului (biblioteca fiind
# școlară) a fost adăugată ulterior; se pune prin ALTER TABLE la bazele de
# date mai vechi, fără să atingă cititorii deja înregistrați.
BORROWERS_NEW_COLUMNS = [
    ("student_class", "TEXT"),
    ("address", "TEXT"),
]


def _row_to_dict(row):
    return dict(row) if row is not None else None


def _rows_to_list(rows):
    return [dict(r) for r in rows]


class Database:
    """Wrapper subțire peste sqlite3 cu conexiune per thread."""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._init_schema()

    # ------------------------------------------------------------------
    # Conexiune / inițializare
    # ------------------------------------------------------------------
    def _connect(self):
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self):
        conn = self._connect()
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        self._migrate_schema()
        self._seed_default_categories()

    def _migrate_schema(self):
        """Adaugă coloanele noi la 'books'/'borrowers' dacă lipsesc (bază de
        date creată cu o versiune mai veche a aplicației), fără să șteargă
        datele existente."""
        conn = self._connect()
        for table, new_columns in (("books", BOOKS_NEW_COLUMNS),
                                   ("borrowers", BORROWERS_NEW_COLUMNS)):
            existing_columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column_name, column_def in new_columns:
                if column_name not in existing_columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def}")
        conn.commit()

    def close(self):
        """Închide conexiunea SQLite a thread-ului curent (dacă există).
        Folosit înainte de a înlocui fișierul bazei de date de pe disc cu
        unul restaurat dintr-un backup, ca să nu rămână un handle deschis
        pe fișierul vechi în timp ce acesta e suprascris."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn

    def backup_to(self, dest_path):
        """Creează o copie completă și consistentă a bazei de date la
        `dest_path`, folosind API-ul de backup online al SQLite
        (conn.backup), nu o simplă copiere de fișier — sigur chiar dacă
        aplicația are o tranzacție în curs în alt thread în acel moment."""
        conn = self._connect()
        dest_conn = sqlite3.connect(dest_path)
        try:
            with self._write_lock:
                conn.backup(dest_conn)
        finally:
            dest_conn.close()

    def _seed_default_categories(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM categories")
        if cur.fetchone()[0] == 0:
            with self._write_lock:
                for name in DEFAULT_CATEGORIES:
                    conn.execute(
                        "INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,)
                    )
                conn.commit()

    # ------------------------------------------------------------------
    # Categorii
    # ------------------------------------------------------------------
    def get_all_categories(self):
        conn = self._connect()
        rows = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
        return _rows_to_list(rows)

    def get_category_by_name(self, name):
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM categories WHERE name = ?", (name,)
        ).fetchone()
        return _row_to_dict(row)

    def get_or_create_category(self, name):
        """Returnează id-ul categoriei cu acest nume, creând-o dacă nu există."""
        name = (name or UNCONFIRMED_CATEGORY).strip() or UNCONFIRMED_CATEGORY
        existing = self.get_category_by_name(name)
        if existing:
            return existing["id"]
        with self._write_lock:
            conn = self._connect()
            cur = conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
            conn.commit()
            return cur.lastrowid

    # ------------------------------------------------------------------
    # Cărți
    # ------------------------------------------------------------------
    def get_all_books(self, search=None):
        conn = self._connect()
        base = """
            SELECT books.*, categories.name AS category_name
            FROM books
            LEFT JOIN categories ON categories.id = books.category_id
        """
        if search:
            like = f"%{search}%"
            rows = conn.execute(
                base + """
                WHERE books.title LIKE ? OR books.author LIKE ?
                   OR books.isbn LIKE ? OR categories.name LIKE ?
                ORDER BY books.title
                """,
                (like, like, like, like),
            ).fetchall()
        else:
            rows = conn.execute(base + " ORDER BY books.title").fetchall()
        return _rows_to_list(rows)

    def get_available_books(self, search=None):
        """Cărți cu cel puțin un exemplar liber acum. Respectă numărul de
        exemplare (`copies`): o carte cu N exemplare poate fi împrumutată de
        N ori simultan, nu doar o dată. `available_copies` = exemplare - nr.
        împrumuturi active."""
        conn = self._connect()
        base = """
            SELECT books.*, categories.name AS category_name,
                   books.copies - COALESCE(active.cnt, 0) AS available_copies
            FROM books
            LEFT JOIN categories ON categories.id = books.category_id
            LEFT JOIN (
                SELECT book_id, COUNT(*) AS cnt
                FROM loans WHERE return_date IS NULL
                GROUP BY book_id
            ) AS active ON active.book_id = books.id
            WHERE books.copies - COALESCE(active.cnt, 0) > 0
        """
        if search:
            like = f"%{search}%"
            rows = conn.execute(
                base + " AND (books.title LIKE ? OR books.author LIKE ? OR books.isbn LIKE ?) ORDER BY books.title",
                (like, like, like),
            ).fetchall()
        else:
            rows = conn.execute(base + " ORDER BY books.title").fetchall()
        return _rows_to_list(rows)

    def get_unavailable_books(self, search=None):
        """Cărți fără niciun exemplar liber acum (toate exemplarele
        împrumutate) -- candidatele naturale pentru o rezervare."""
        conn = self._connect()
        base = """
            SELECT books.*, categories.name AS category_name,
                   books.copies - COALESCE(active.cnt, 0) AS available_copies
            FROM books
            LEFT JOIN categories ON categories.id = books.category_id
            LEFT JOIN (
                SELECT book_id, COUNT(*) AS cnt
                FROM loans WHERE return_date IS NULL
                GROUP BY book_id
            ) AS active ON active.book_id = books.id
            WHERE books.copies - COALESCE(active.cnt, 0) <= 0
        """
        if search:
            like = f"%{search}%"
            rows = conn.execute(
                base + " AND (books.title LIKE ? OR books.author LIKE ? OR books.isbn LIKE ?) ORDER BY books.title",
                (like, like, like),
            ).fetchall()
        else:
            rows = conn.execute(base + " ORDER BY books.title").fetchall()
        return _rows_to_list(rows)

    def get_book(self, book_id):
        conn = self._connect()
        row = conn.execute(
            """
            SELECT books.*, categories.name AS category_name
            FROM books LEFT JOIN categories ON categories.id = books.category_id
            WHERE books.id = ?
            """,
            (book_id,),
        ).fetchone()
        return _row_to_dict(row)

    def add_book(self, isbn, title, author, pub_year, desc, category_id,
                 price=None, publisher="", copies=1, pub_place="", czu=""):
        with self._write_lock:
            conn = self._connect()
            cur = conn.execute(
                """INSERT INTO books
                   (isbn, title, author, pub_year, desc, category_id,
                    price, publisher, copies, pub_place, czu)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (isbn, title, author, pub_year, desc, category_id,
                 price, publisher, copies, pub_place, czu),
            )
            conn.commit()
            return cur.lastrowid

    def update_book(self, book_id, isbn, title, author, pub_year, desc, category_id,
                     price=None, publisher="", copies=1, pub_place="", czu=""):
        with self._write_lock:
            conn = self._connect()
            conn.execute(
                """UPDATE books SET isbn=?, title=?, author=?, pub_year=?, desc=?, category_id=?,
                   price=?, publisher=?, copies=?, pub_place=?, czu=?
                   WHERE id=?""",
                (isbn, title, author, pub_year, desc, category_id,
                 price, publisher, copies, pub_place, czu, book_id),
            )
            conn.commit()

    def delete_book(self, book_id):
        with self._write_lock:
            conn = self._connect()
            conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
            conn.commit()

    # ------------------------------------------------------------------
    # Împrumutători (borrowers)
    # ------------------------------------------------------------------
    def get_all_borrowers(self, search=None):
        conn = self._connect()
        if search:
            like = f"%{search}%"
            rows = conn.execute(
                """SELECT * FROM borrowers
                   WHERE name LIKE ? OR email LIKE ? OR phone LIKE ? OR student_class LIKE ?
                   ORDER BY name""",
                (like, like, like, like),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM borrowers ORDER BY name").fetchall()
        return _rows_to_list(rows)

    def get_borrower(self, borrower_id):
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM borrowers WHERE id = ?", (borrower_id,)
        ).fetchone()
        return _row_to_dict(row)

    def get_borrowers_with_stats(self, search=None):
        """Cititorii, fiecare cu numărul de cărți împrumutate acum
        (`active_count`) și câte dintre ele sunt restante (`overdue_count`)
        -- pentru pagina de gestiune a cititorilor, fără N interogări
        separate. Subinterogările corelate numără per cititor, deci un
        cititor fără împrumuturi apare corect cu 0/0."""
        conn = self._connect()
        today = date.today().isoformat()
        # `today` alimentează ?-ul din subinterogarea overdue_count (apare
        # primul în SQL); parametrii de căutare (dacă există) vin după.
        params = [today]
        where = ""
        if search:
            like = f"%{search}%"
            where = "WHERE b.name LIKE ? OR b.email LIKE ? OR b.phone LIKE ? OR b.student_class LIKE ?"
            params += [like, like, like, like]
        rows = conn.execute(
            f"""
            SELECT b.*,
                (SELECT COUNT(*) FROM loans l
                 WHERE l.borrower_id = b.id AND l.return_date IS NULL) AS active_count,
                (SELECT COUNT(*) FROM loans l
                 WHERE l.borrower_id = b.id AND l.return_date IS NULL AND l.due_date < ?)
                 AS overdue_count
            FROM borrowers b
            {where}
            ORDER BY b.name
            """,
            params,
        ).fetchall()
        return _rows_to_list(rows)

    def get_loans_for_borrower(self, borrower_id):
        """Toate împrumuturile unui cititor (active + returnate), cu titlul
        cărții. Cele active (nereturnate) sunt primele, apoi după scadență."""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT loans.*, books.title AS book_title, books.author AS book_author
            FROM loans
            JOIN books ON books.id = loans.book_id
            WHERE loans.borrower_id = ?
            ORDER BY (loans.return_date IS NOT NULL), loans.due_date ASC, loans.loan_date DESC
            """,
            (borrower_id,),
        ).fetchall()
        return _rows_to_list(rows)

    def add_borrower(self, name, email, phone, student_class=None, address=None,
                     registered_date=None):
        registered_date = registered_date or date.today().isoformat()
        with self._write_lock:
            conn = self._connect()
            cur = conn.execute(
                "INSERT INTO borrowers (name, email, phone, student_class, address, registered_date) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, email, phone, student_class, address, registered_date),
            )
            conn.commit()
            return cur.lastrowid

    def update_borrower(self, borrower_id, name, email, phone, student_class=None, address=None):
        with self._write_lock:
            conn = self._connect()
            conn.execute(
                "UPDATE borrowers SET name=?, email=?, phone=?, student_class=?, address=? WHERE id=?",
                (name, email, phone, student_class, address, borrower_id),
            )
            conn.commit()

    def delete_borrower(self, borrower_id):
        with self._write_lock:
            conn = self._connect()
            conn.execute("DELETE FROM borrowers WHERE id = ?", (borrower_id,))
            conn.commit()

    # ------------------------------------------------------------------
    # Împrumuturi (loans)
    # ------------------------------------------------------------------
    def get_active_loans(self):
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT loans.*, books.title AS book_title, books.author AS book_author,
                   borrowers.name AS borrower_name
            FROM loans
            JOIN books ON books.id = loans.book_id
            JOIN borrowers ON borrowers.id = loans.borrower_id
            WHERE loans.return_date IS NULL
            ORDER BY loans.due_date ASC
            """
        ).fetchall()
        return _rows_to_list(rows)

    def get_overdue_loans(self):
        today = date.today().isoformat()
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT loans.*, books.title AS book_title, borrowers.name AS borrower_name
            FROM loans
            JOIN books ON books.id = loans.book_id
            JOIN borrowers ON borrowers.id = loans.borrower_id
            WHERE loans.return_date IS NULL AND loans.due_date < ?
            ORDER BY loans.due_date ASC
            """,
            (today,),
        ).fetchall()
        return _rows_to_list(rows)

    def get_all_loans(self):
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT loans.*, books.title AS book_title, borrowers.name AS borrower_name
            FROM loans
            JOIN books ON books.id = loans.book_id
            JOIN borrowers ON borrowers.id = loans.borrower_id
            ORDER BY loans.loan_date DESC
            """
        ).fetchall()
        return _rows_to_list(rows)

    def add_loan(self, book_id, borrower_id, loan_date, due_date):
        with self._write_lock:
            conn = self._connect()
            cur = conn.execute(
                """INSERT INTO loans (book_id, borrower_id, loan_date, due_date, return_date)
                   VALUES (?, ?, ?, ?, NULL)""",
                (book_id, borrower_id, loan_date, due_date),
            )
            conn.commit()
            return cur.lastrowid

    def return_loan(self, loan_id, return_date=None):
        return_date = return_date or date.today().isoformat()
        with self._write_lock:
            conn = self._connect()
            conn.execute(
                "UPDATE loans SET return_date = ? WHERE id = ?", (return_date, loan_id)
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Rezervări (reservations)
    # ------------------------------------------------------------------
    def add_reservation(self, book_id, borrower_id, reserved_date=None):
        reserved_date = reserved_date or date.today().isoformat()
        with self._write_lock:
            conn = self._connect()
            cur = conn.execute(
                """INSERT INTO reservations (book_id, borrower_id, reserved_date, fulfilled_date)
                   VALUES (?, ?, ?, NULL)""",
                (book_id, borrower_id, reserved_date),
            )
            conn.commit()
            return cur.lastrowid

    def has_active_reservation(self, book_id, borrower_id):
        """True dacă acest cititor are deja o rezervare activă la această
        carte (previne duplicatele)."""
        conn = self._connect()
        row = conn.execute(
            """SELECT 1 FROM reservations
               WHERE book_id = ? AND borrower_id = ? AND fulfilled_date IS NULL LIMIT 1""",
            (book_id, borrower_id),
        ).fetchone()
        return row is not None

    def get_active_reservations(self):
        """Toate rezervările active (în așteptare), în ordinea în care au fost
        făcute (coada). `available_copies > 0` marchează rezervările a căror
        carte tocmai s-a eliberat -- gata de onorat."""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT r.*, books.title AS book_title, books.copies AS copies,
                   borrowers.name AS borrower_name,
                   books.copies - COALESCE(active.cnt, 0) AS available_copies
            FROM reservations r
            JOIN books ON books.id = r.book_id
            JOIN borrowers ON borrowers.id = r.borrower_id
            LEFT JOIN (
                SELECT book_id, COUNT(*) AS cnt
                FROM loans WHERE return_date IS NULL
                GROUP BY book_id
            ) AS active ON active.book_id = r.book_id
            WHERE r.fulfilled_date IS NULL
            ORDER BY r.reserved_date ASC, r.id ASC
            """
        ).fetchall()
        return _rows_to_list(rows)

    def get_reservations_for_book(self, book_id):
        """Coada de rezervări active pentru o carte (prima = următorul la rând)."""
        conn = self._connect()
        rows = conn.execute(
            """SELECT r.*, borrowers.name AS borrower_name
               FROM reservations r JOIN borrowers ON borrowers.id = r.borrower_id
               WHERE r.book_id = ? AND r.fulfilled_date IS NULL
               ORDER BY r.reserved_date ASC, r.id ASC""",
            (book_id,),
        ).fetchall()
        return _rows_to_list(rows)

    def cancel_reservation(self, reservation_id):
        with self._write_lock:
            conn = self._connect()
            conn.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))
            conn.commit()

    def fulfill_reservation(self, reservation_id, fulfilled_date=None):
        """Marchează o rezervare drept onorată (cartea i-a fost dată)."""
        fulfilled_date = fulfilled_date or date.today().isoformat()
        with self._write_lock:
            conn = self._connect()
            conn.execute(
                "UPDATE reservations SET fulfilled_date = ? WHERE id = ?",
                (fulfilled_date, reservation_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Statistici / Rapoarte
    # ------------------------------------------------------------------
    def get_dashboard_stats(self):
        conn = self._connect()
        total_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        total_loans = conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
        borrowed = conn.execute(
            "SELECT COUNT(*) FROM loans WHERE return_date IS NULL"
        ).fetchone()[0]
        today = date.today().isoformat()
        overdue = conn.execute(
            "SELECT COUNT(*) FROM loans WHERE return_date IS NULL AND due_date < ?",
            (today,),
        ).fetchone()[0]
        return {
            "total_books": total_books,
            "total_loans": total_loans,
            "borrowed_count": borrowed,
            "overdue_count": overdue,
        }

    def get_recent_activity(self, limit=10):
        """Ultimele evenimente (împrumut sau retur), pentru panoul de Dashboard."""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT loans.*, books.title AS book_title, borrowers.name AS borrower_name
            FROM loans
            JOIN books ON books.id = loans.book_id
            JOIN borrowers ON borrowers.id = loans.borrower_id
            ORDER BY COALESCE(loans.return_date, loans.loan_date) DESC, loans.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return _rows_to_list(rows)

    def get_inventory(self, group_by_category=False):
        """
        Listă completă a cărților pentru raportul de inventar — fie
        sortată strict alfabetic după titlu, fie grupată pe categorie
        (și alfabetic în interiorul fiecărei categorii).
        """
        conn = self._connect()
        order = "categories.name, books.title" if group_by_category else "books.title"
        rows = conn.execute(
            f"""
            SELECT books.*, categories.name AS category_name
            FROM books
            LEFT JOIN categories ON categories.id = books.category_id
            ORDER BY {order}
            """
        ).fetchall()
        return _rows_to_list(rows)

    def get_books_per_category(self):
        """Pentru fiecare categorie: câte cărți conține (book_count) și de
        câte ori s-au împrumutat cărțile din ea, în total, vreodată
        (loan_count) -- util pentru a vedea care categorii circulă cel
        mai mult, nu doar câte cărți au în catalog."""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT categories.name AS category_name,
                   COUNT(DISTINCT books.id) AS book_count,
                   COUNT(loans.id) AS loan_count
            FROM categories
            LEFT JOIN books ON books.category_id = categories.id
            LEFT JOIN loans ON loans.book_id = books.id
            GROUP BY categories.id
            ORDER BY categories.name
            """
        ).fetchall()
        return _rows_to_list(rows)

    def get_top_borrowed_books(self, limit=10):
        """Cărțile împrumutate de cele mai multe ori vreodată (istoric
        complet, nu doar împrumuturile active), cu numărul de împrumuturi
        pentru fiecare. Cărțile niciodată împrumutate nu apar în listă --
        un clasament al celor "mai populare" nu are sens pentru ele."""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT books.id, books.title, books.author,
                   categories.name AS category_name,
                   COUNT(loans.id) AS loan_count
            FROM books
            JOIN loans ON loans.book_id = books.id
            LEFT JOIN categories ON categories.id = books.category_id
            GROUP BY books.id
            ORDER BY loan_count DESC, books.title ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return _rows_to_list(rows)

    def get_training_dataset(self):
        """Text (titlu + descriere) și eticheta categoriei, pentru antrenarea ML.
        Exclude cărțile fără categorie și cele marcate 'De Confirmat'."""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT books.title, books.desc, categories.name AS category_name
            FROM books
            JOIN categories ON categories.id = books.category_id
            WHERE categories.name != ?
            """,
            (UNCONFIRMED_CATEGORY,),
        ).fetchall()
        samples = []
        for r in rows:
            text = f"{r['title'] or ''} {r['desc'] or ''}".strip()
            if text:
                samples.append((text, r["category_name"]))
        return samples
