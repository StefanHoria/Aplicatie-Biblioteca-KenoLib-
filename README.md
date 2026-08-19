# KenoLib — Library Management System

Desktop application (Python + CustomTkinter + SQLite) for running a library: book catalogue,
borrowers, loans (with per-copy tracking) and reservations, reports, inventory with CSV/PDF export
and barcode labels, bulk CSV import, GM65 barcode scanner support and automatic category
classification through machine learning.

> 🇷🇴 Documentul în limba română: [README.ro.md](README.ro.md)
>
> The application interface, the built-in categories and the sample dataset are in Romanian — it was
> built for a Romanian school library.

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.9+.

## Running from source (with Python installed)

```bash
python main.py
```

On first run, `library.db` (SQLite) is created automatically, with the schema and the default
categories.

## Library profile (on first start)

At first start the application asks for a short profile: the **name of the library / librarian** and
the **school the library belongs to**. These appear in the sidebar and in the window title, and can
be changed at any time from **Settings → Library profile**.

## Distribution to other computers (without Python)

The application can be moved to any Windows machine without Python or the libraries in
`requirements.txt`. There are two options; both are built **once**, on the development machine.

> **End users do not have to build anything:** the latest version of the `KenoLib-Setup.exe`
> installer can be downloaded directly from the
> [Releases](https://github.com/StefanHoria/KenoLib-Library-Manager/releases) section.
> The rest of this section is about rebuilding it from source.

### Recommended: single-file installer

```bash
make_installer.bat
```

The script does everything automatically:

1. builds the executable with PyInstaller (Python and all libraries bundled);
2. makes sure **Inno Setup** is present — downloading and installing it automatically from the
   official source (a GitHub release signed by jrsoftware) if missing; needed only on the machine
   where you *build* the installer;
3. compiles the result into `installer\Output\KenoLib-Setup.exe`.

`KenoLib-Setup.exe` is **a single file** (~55 MB) that you copy onto any Windows laptop and run. It
installs the application through a Romanian-language wizard, creates Start menu and desktop
shortcuts and registers an uninstall entry — **with no Python and nothing else to install manually.**
The installation is per-user (no administrator rights required).

### Portable: the `dist` folder

```bash
build_exe.bat
```

(or manually: `pip install -r requirements-build.txt` then
`python -m PyInstaller --noconfirm KenoLib.spec`)

The result appears in `dist\KenoLib\` — a folder with `KenoLib.exe` and its dependencies
(`_internal\`). Copy **the whole folder** (not just the `.exe`) to the target machine and run
`KenoLib.exe` directly, without installing.

### Where the data is stored

In either case, when the executable runs, user data — the `library.db` database, `settings.json` and
the ML model — is stored in the per-user folder:

```
%LOCALAPPDATA%\KenoLib
```

This location is guaranteed writable (unlike `Program Files`, which is read-only for an ordinary
user), so the application behaves the same wherever it is installed. On top of that, **the library
catalogue survives** reinstallation, updates and uninstallation — uninstalling does NOT delete the
data. The pre-trained ML model, bundled inside the executable, is copied here automatically on first
start (and if data from an earlier portable run existed next to the `.exe`, it is migrated
automatically).

The application folder is fairly large (~190 MB) because of the bundled scikit-learn/scipy/numpy
libraries used for ML classification — this is expected.

Note: this is a **Windows** executable (it uses pyserial plus native tkinter); on macOS/Linux the
application has to be run from source with Python.

## Module structure

| File | Role |
|---|---|
| `config.py` | Global constants (paths, API URLs, ML thresholds) |
| `database.py` | Model — SQLite access, schema, CRUD |
| `settings_service.py` | Persists settings and profile (JSON): library profile, backup, loan days |
| `ml_classifier.py` | ML classifier (TF-IDF + Logistic Regression) for category suggestions |
| `scanner_service.py` | Serial port listener (separate thread) for the GM65 scanner |
| `api_service.py` | Google Books / Open Library queries, by ISBN or by title + author |
| `pdf_service.py` | PDF generation: inventory/report export + barcode labels (reportlab) |
| `gui_app.py` | Main window, sidebar, navigation |
| `utils.py` | Shared helpers (ttk table styling, drawn logo icon, ISBN validation, dates) |
| `views/dashboard.py` | Dashboard page (statistics + recent activity) |
| `views/catalog.py` | Book catalogue page (table, search, CRUD) |
| `views/borrowers.py` | Borrowers page (list + per-borrower history and loans) |
| `views/loans.py` | Active loans page (overdue items highlighted in red) |
| `views/reservations.py` | Reservations page (waiting queue for unavailable books) |
| `views/reports.py` | Reports page (books per category, transaction history) + PDF export |
| `views/inventory.py` | Inventory page (full list; CSV/PDF export + barcode labels) |
| `views/import_view.py` | CSV import with column mapping + ML classification |
| `views/settings.py` | Settings page (library profile, backup, auto-backup, retention, loan days) |
| `views/dialogs.py` | Modal windows: profile (first start), book, borrower, loan, reservation |
| `views/widgets.py` | Reusable widgets (e.g. smooth scrollable frame) |
| `main.py` | Entry point |

## Borrowers, loans and reservations

The **Borrowers** page lists everyone who borrows, together with their **class** (the library being
a school one), how many books they currently hold and how many are overdue (highlighted in red).
Selecting a borrower shows, in the right-hand panel, their class, **address** and contact details,
the books they currently have out (with due dates) and their return history. Searching by class is
supported. Class and address are optional (a teacher may not have a class) and are filled in when
adding or editing a borrower; the address appears only in the detail panel, not as a table column.
A borrower who still has unreturned books cannot be deleted (so that open loan records are not
lost).

**Multiple copies.** A book with several copies (`Nr. exemplare`) can be lent out several times at
once — it only becomes "unavailable" when every copy is with a borrower. When creating a loan, only
books with at least one free copy are shown, along with the remaining count.

**Reservations.** For a book whose copies are all on loan, a borrower can be queued from the
**Reservations** page. When the book comes back, the application announces who is next in line and
the reservation is highlighted in green ("Available now"); once handed over, it is marked
"fulfilled".

## Keyboard shortcuts and validation

On the **Book catalogue** and **Borrowers** pages, with the table focused:

| Key | Effect |
|---|---|
| `+` | opens the add form |
| `Delete` | deletes the selected row (with confirmation) |
| `Enter` | in forms: save |

The shortcuts are bound to the table rather than the page, so `+` or `Delete` typed in the search
box behave normally. In the book form, `Enter` in the ISBN field starts the online lookup, while in
Description (a multi-line field) it moves to the next line.

Numeric fields are checked on save, with an explicit message and the cursor moved to the offending
field: **publication year** (between 1450 and next year), **number of copies** (positive integer),
**price**, **UDC code**, **phone** and **email**. An **ISBN** whose check digit does not match asks
for confirmation but does not block saving — old books sometimes carry non-standard codes.

## GM65 scanner

The GM65 scanner (USB-COM mode, keyboard/serial emulation) is detected as a COM port. From the
sidebar, select the port and press "Connect". Codes scanned on the **Book catalogue** page (with the
add-book dialog open, or a new one) automatically fill in the ISBN and trigger the online lookup.

## Online lookup (Google Books / Open Library)

The online lookup (from the book form or during import) tries, in order:

1. **By ISBN** (if valid) — Google Books, then Open Library.
2. **By title + author**, if the ISBN is missing, invalid or returned nothing — useful for older
   books without an ISBN. If one of the sources does find an ISBN for that book, the ISBN field is
   filled in automatically.

From the two sources, the most complete combination is kept — title/author/year from whichever has
the data, and the longest description found (Open Library often has no description at all for
certain editions; in that case only what Google Books found remains, or the other way round).

## ML classification

The model (TF-IDF over character n-grams + Logistic Regression with `class_weight="balanced"`) is
trained from the **Import Data** page ("Train the ML model"), using the already-categorised books in
the database. Character n-grams (rather than word n-grams) were chosen because they generalise
better across Romanian inflected forms ("iubire"/"iubit"/"iubește" share no whole word, but many
character sequences) — validated through cross-validation (~55% raw accuracy, against ~49% with word
n-grams). The confidence threshold below which a book is marked "To Confirm" is adjusted
automatically according to how many categories the library has (`config.py`:
`ML_CONFIDENCE_RATIO`, `ML_MIN_CONFIDENCE`) — calibrated through an evaluation on data held out from
training (not by eye), for a reasonable balance between how often it risks a prediction and how
often it is right when it does.

**Worth keeping in mind**: with a title alone and no description whatsoever, any text classifier has
very little signal to work with — which is why many books (especially those with no description
found online) will stay "To Confirm". That is the intended safe behaviour, not a bug. The more
labelled books a category accumulates (from your own imports, retrained periodically), the more
confident the predictions become.

**The model ships already trained** — `ml_model.joblib` is included in the project and bundled into
the executable, from where it is copied automatically into the data folder
(`%LOCALAPPDATA%\KenoLib`) on first start. The application is therefore ready from its very first
run to suggest categories for any later import, with no extra steps.

### Optional online enrichment during import

The **Import Data** page has an "Enrich with online data" checkbox — when ticked, every book without
a description is first looked up (by ISBN or by title + author) before ML classification, precisely
for the case of an export from some legacy software that only carries title/author/year/ISBN. A
richer description means a more confident ML prediction. It is off by default (it needs an internet
connection and slows the import down); ML classification works entirely offline without it, just
with less textual signal.

If, after enrichment, the ML model is still unsure, a last resort is the generic category offered by
Google Books itself (e.g. "Biography" → Biografie, "Poetry" → Poezie) — used only as a fallback,
never in place of a confident ML prediction. The same failsafe applies when adding a book manually
(the "Search online" button in the form): if the model remains unsure after the lookup, the category
proposed by the online source (if it gave one) is used instead of "To Confirm".

### Categories

`Literatură română`, `Literatură străină`, `Poezie`, `Teatru`, `Fantezie & SF`, `Thriller & Mister`,
`Non-ficțiune`, `Știință`, `Istorie`, `Biografie`, `Filozofie`, `Psihologie`, `Economie & Afaceri`,
`Copii`, `Tehnologie`, `Artă` (plus "De Confirmat" for uncertain cases).

### The training dataset

The file [`carti_exemplu_import.csv`](carti_exemplu_import.csv) contains 373 real books (mostly
Romanian — nearly 50 in Romanian Literature alone, plus Romanian authors under Poetry, Theatre,
Philosophy, History, Children's, and so on, alongside foreign classics), spread across all 16
categories. It also includes foreign books with English descriptions (the rest being described in
Romanian) — so that the model recognises the English text that "online lookup" and import enrichment
frequently return for foreign books, not just Romanian vocabulary.

This is the set used to train the model shipped with the application; it was not imported into the
catalogue itself, so that no "ghost" books you do not own appear — the catalogue starts empty. If
you do want these books in the catalogue as a starting point, you can import them at any time from
the **Import Data** page, like any other CSV.

To retrain the model (for example after adding your own books): **Import Data** page → "Select CSV
file" → columns are mapped automatically (Title, Author, Year, Category, Description) → "Start
import" → "Train the ML model".

## Additional book fields

Beyond title/author/year/description/category, each book also carries: **publisher**
(auto-completed by "Search online", or entered manually), **place of publication**, **price**
(entered manually), **number of copies** (1 by default) and **UDC code**. All of them are available
in the add/edit form, in the CSV import (through column mapping) and in the catalogue table.

Databases created with an older version of the application are upgraded automatically on first
start (new columns are added without deleting existing books).

### UDC (Universal Decimal Classification)

The "Suggest" button next to the UDC field offers a starting code based on the category (e.g.
`821.135.1` for Romanian Literature, `004` for Technology — the main UDC classes, stable and well
documented). **This is not a complete UDC cataloguing** — the UDC system has far finer subdivisions
(language, period, sub-genre) that a simple category→code mapping cannot cover; the suggested code
is a starting point, to be checked and refined by the librarian against the official UDC tables. On
CSV import, if no UDC column is mapped or the cell is empty, the same suggestion is filled in
automatically.

## Inventory, PDF export and labels

The **Inventory** page generates the complete list of books, either sorted alphabetically by title
or grouped by category (and alphabetically within each). It also shows a summary (number of titles,
total copies, total value — computed as price × copies for the books that have a price).

From the page's **"Actions"** menu you can:

- **Export the list as CSV** — for processing in another program;
- **Export the list as PDF** — a formal, printable table (A4);
- **Generate shelf labels (PDF)** — a grid of labels with title, author, UDC code and a **scannable
  Code128 barcode** (the book's ISBN, or an internal `KL…` code for books without one). This closes
  the loop with the GM65 scanner: you scan on intake, but you can also generate labels for your own
  holdings.

The **Reports** page has its own **"Export PDF"** button (statistics + books per category + top
loans). PDF exports use `reportlab` (included in `requirements.txt`) and render Romanian diacritics
correctly.

## Tests

The project has an automated test suite built on `pytest` — **126 tests across 15 files**, covering
the API service, ISBN and field validation, loans and copy availability, reservations, reports,
backup and auto-backup, the settings page and the UI details.

```bash
pip install -r requirements-dev.txt
pytest
```

## Technology stack

| Area | Technologies |
|---|---|
| Language | Python 3.9+ |
| Interface | CustomTkinter, tkinter/ttk |
| Storage | SQLite |
| Machine learning | scikit-learn (TF-IDF + Logistic Regression), joblib |
| External APIs | Google Books, Open Library |
| PDF & barcodes | reportlab (Code128) |
| Hardware | pyserial (GM65 barcode scanner) |
| Testing | pytest |
| Packaging | PyInstaller, Inno Setup |
