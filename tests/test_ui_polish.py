"""
Teste pentru cele trei retușuri vizuale: accentul temei pe elementul
activ din sidebar, zebra striping în tabele, și iconițele de pe
cardurile de statistici.
"""

import customtkinter as ctk
import pytest

from config import UNCONFIRMED_CATEGORY
from database import Database
from gui_app import style_nav_buttons
from ml_classifier import BookClassifier
from utils import is_dark_mode, stripe_color, today_iso, due_date_iso
from views.catalog import CatalogPage
from views.dashboard import StatCard
from views.inventory import InventoryPage
from views.loans import LoansPage
from views.reports import ReportsPage


@pytest.fixture(scope="module")
def root():
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


# ------------------------------------------------------------------
# Accent sidebar
# ------------------------------------------------------------------
def test_active_nav_button_gets_theme_accent(root):
    buttons = {
        "dashboard": ctk.CTkButton(root, text="Dashboard"),
        "catalog": ctk.CTkButton(root, text="Catalog"),
    }
    expected_fg = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
    expected_text = ctk.ThemeManager.theme["CTkButton"]["text_color"]

    style_nav_buttons(buttons, "catalog")

    assert list(buttons["catalog"].cget("fg_color")) == list(expected_fg)
    assert list(buttons["catalog"].cget("text_color")) == list(expected_text)


def test_inactive_nav_buttons_stay_transparent(root):
    buttons = {
        "dashboard": ctk.CTkButton(root, text="Dashboard"),
        "catalog": ctk.CTkButton(root, text="Catalog"),
        "loans": ctk.CTkButton(root, text="Loans"),
    }
    style_nav_buttons(buttons, "catalog")

    assert buttons["dashboard"].cget("fg_color") == "transparent"
    assert buttons["loans"].cget("fg_color") == "transparent"


def test_switching_active_button_resets_previous(root):
    buttons = {
        "dashboard": ctk.CTkButton(root, text="Dashboard"),
        "catalog": ctk.CTkButton(root, text="Catalog"),
    }
    style_nav_buttons(buttons, "dashboard")
    style_nav_buttons(buttons, "catalog")

    assert buttons["dashboard"].cget("fg_color") == "transparent"
    expected_fg = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
    assert list(buttons["catalog"].cget("fg_color")) == list(expected_fg)


# ------------------------------------------------------------------
# Zebra striping
# ------------------------------------------------------------------
def test_stripe_color_differs_between_dark_and_light():
    ctk.set_appearance_mode("Dark")
    dark = stripe_color()
    ctk.set_appearance_mode("Light")
    light = stripe_color()
    assert dark != light
    assert dark and light


# ------------------------------------------------------------------
# Iconițe pe carduri de statistici
# ------------------------------------------------------------------
def test_stat_card_shows_icon_when_given(root):
    card = StatCard(root, "Total cărți", icon="📚")
    assert "📚" in card.title_label.cget("text")
    assert "Total cărți" in card.title_label.cget("text")


def test_stat_card_shows_plain_title_without_icon(root):
    card = StatCard(root, "Total cărți")
    assert card.title_label.cget("text") == "Total cărți"


# ------------------------------------------------------------------
# Zebra striping aplicată efectiv pe rânduri (nu doar culoarea în sine)
# ------------------------------------------------------------------
class FakeApp:
    def __init__(self, db_path):
        self.db = Database(db_path=str(db_path))
        self.classifier = BookClassifier()
        self.classifier.load()
        self.pages = {}

    def show_page(self, key):
        pass


@pytest.fixture
def app(tmp_path):
    return FakeApp(tmp_path / "test_ui_polish.db")


def _add_book(app, title, category_name):
    cat_id = app.db.get_or_create_category(category_name)
    return app.db.add_book(None, title, None, None, "", cat_id)


def test_catalog_alternates_stripe_on_normal_rows(root, app):
    ids = [_add_book(app, f"Carte {i}", "Fantezie & SF") for i in range(4)]
    page = CatalogPage(root, app)
    page.refresh()

    tags_by_row = [page.tree.item(str(i))["tags"] for i in ids]
    striped = [bool(t) and "oddrow" in t for t in tags_by_row]
    # alternanță strictă: fiecare rând diferă de vecinul lui
    assert all(striped[i] != striped[i + 1] for i in range(len(striped) - 1))


def test_catalog_unconfirmed_row_has_no_stripe_tag(root, app):
    # A doua carte (index impar -> ar primi în mod normal "oddrow")
    # trebuie să primească DOAR "unconfirmed", nu ambele.
    _add_book(app, "Carte 0", "Fantezie & SF")
    unconfirmed_id = _add_book(app, "Carte 1", UNCONFIRMED_CATEGORY)

    page = CatalogPage(root, app)
    page.refresh()

    tags = page.tree.item(str(unconfirmed_id))["tags"]
    assert "unconfirmed" in tags
    assert "oddrow" not in tags


def test_inventory_unconfirmed_row_has_no_stripe_tag(root, app):
    _add_book(app, "Carte 0", "Fantezie & SF")
    unconfirmed_id = _add_book(app, "Carte 1", UNCONFIRMED_CATEGORY)

    page = InventoryPage(root, app)
    page.refresh()

    tags = page.tree.item(str(unconfirmed_id))["tags"]
    assert "unconfirmed" in tags
    assert "oddrow" not in tags


def test_loans_overdue_row_has_no_stripe_tag(root, app):
    borrower_id = app.db.add_borrower("Ion", "", "")
    book1 = _add_book(app, "Carte 0", "Test")
    book2 = _add_book(app, "Carte 1", "Test")
    app.db.add_loan(book1, borrower_id, today_iso(), due_date_iso(365))  # activ, nu restant
    overdue_loan_id = app.db.add_loan(book2, borrower_id, "2020-01-01", "2020-01-15")  # restant

    page = LoansPage(root, app)
    page.refresh()

    tags = page.tree.item(str(overdue_loan_id))["tags"]
    assert "overdue" in tags
    assert "oddrow" not in tags


def test_reports_history_combines_stripe_and_returned_safely(root, app):
    # "returned" schimbă doar culoarea textului (nu fundalul), deci poate
    # coexista cu "oddrow" fără conflict de proprietăți.
    borrower_id = app.db.add_borrower("Ion", "", "")
    book_id = _add_book(app, "Carte", "Test")
    loan_id = app.db.add_loan(book_id, borrower_id, today_iso(), due_date_iso(30))
    app.db.return_loan(loan_id, today_iso())

    page = ReportsPage(root, app)
    page.refresh()

    children = page.tree.get_children()
    assert len(children) == 1
    tags = page.tree.item(children[0])["tags"]
    assert "returned" in tags


# ------------------------------------------------------------------
# Clasa cititorului în interfață (pagina Cititori + dialogul de editare)
# ------------------------------------------------------------------
def test_borrowers_page_shows_class_in_row(root, app):
    from views.borrowers import BorrowersPage

    bid = app.db.add_borrower("Ana Popescu", "", "", student_class="9 A")
    page = BorrowersPage(root, app)
    page.refresh()

    values = [str(v) for v in page.tree.item(str(bid))["values"]]
    assert "9 A" in values


def test_borrower_dialog_prefills_and_saves_class(root, app):
    from views.dialogs import BorrowerDialog

    bid = app.db.add_borrower("Ion", "", "", student_class="7 B")
    borrower = app.db.get_borrower(bid)

    dlg = BorrowerDialog(root, app, borrower=borrower)
    assert dlg.class_entry.get() == "7 B"

    # schimbă clasa și salvează -> se persistă
    dlg.class_entry.delete(0, "end")
    dlg.class_entry.insert(0, "8 C")
    dlg._save()
    assert app.db.get_borrower(bid)["student_class"] == "8 C"


def test_borrower_address_saves_shows_in_detail_not_table(root, app):
    from views.dialogs import BorrowerDialog
    from views.borrowers import BorrowersPage

    bid = app.db.add_borrower("Ion", "", "", student_class="7 B")
    dlg = BorrowerDialog(root, app, borrower=app.db.get_borrower(bid))
    dlg.address_entry.insert(0, "Str. Mare 10")
    dlg._save()
    assert app.db.get_borrower(bid)["address"] == "Str. Mare 10"

    page = BorrowersPage(root, app)
    page.refresh()

    # adresa NU apare în rândul din tabel...
    row_values = [str(v) for v in page.tree.item(str(bid))["values"]]
    assert "Str. Mare 10" not in row_values

    # ...dar apare în panoul de detalii al cititorului selectat
    page.tree.selection_set(str(bid))
    page._render_detail()
    detail_texts = []
    for w in page.detail_scroll.winfo_children():
        try:
            detail_texts.append(w.cget("text"))
        except Exception:
            pass
    assert any("Str. Mare 10" in t for t in detail_texts)


def test_borrower_dialog_has_enter_to_save_binding(root, app):
    from views.dialogs import BorrowerDialog

    dlg = BorrowerDialog(root, app)
    # Enter pe fereastră declanșează salvarea (toate câmpurile sunt pe un rând).
    assert dlg.bind("<Return>")


def test_book_dialog_enter_bindings_save_and_search_not_description(root, app):
    from views.dialogs import BookDialog

    dlg = BookDialog(root, app)
    # câmpurile text au Enter (salvare) și ISBN are Enter (căutare online)...
    assert dlg.title_entry._entry.bind("<Return>")
    assert dlg.isbn_entry._entry.bind("<Return>")
    # ...dar descrierea (multi-linie) rămâne neatinsă: Enter = rând nou, nu salvare
    assert not dlg.desc_text._textbox.bind("<Return>")


def test_selection_comboboxes_are_readonly(root, app):
    """Listele din care se alege o valoare existentă (filtru de categorie,
    carte/cititor la împrumut și rezervare) nu trebuie să fie editabile: un
    text tastat manual nu corespunde niciunei intrări, deci ar duce la un
    filtru gol sau la „Selecție invalidă”, fără explicație."""
    from views.inventory import InventoryPage
    from views.dialogs import LoanDialog, ReservationDialog

    page = InventoryPage(root, app)
    assert page.category_filter.cget("state") == "readonly"

    for dialog_class in (LoanDialog, ReservationDialog):
        dlg = dialog_class(root, app)
        assert dlg.book_combo.cget("state") == "readonly"
        assert dlg.borrower_combo.cget("state") == "readonly"
        dlg.destroy()


def test_book_dialog_category_stays_editable(root, app):
    """Prin contrast, categoria din formularul de carte rămâne editabilă --
    scrierea unui nume nou acolo e singura cale din interfață de a crea o
    categorie nouă (database.get_or_create_category)."""
    from views.dialogs import BookDialog

    dlg = BookDialog(root, app)
    assert dlg.category_combo.cget("state") == "normal"


def test_catalog_page_has_add_delete_key_bindings(root, app):
    from views.catalog import CatalogPage

    page = CatalogPage(root, app)
    assert page.tree.bind("<plus>")
    assert page.tree.bind("<KP_Add>")
    assert page.tree.bind("<Delete>")


def test_borrowers_page_has_add_delete_key_bindings(root, app):
    from views.borrowers import BorrowersPage

    page = BorrowersPage(root, app)
    assert page.tree.bind("<plus>")
    assert page.tree.bind("<KP_Add>")
    assert page.tree.bind("<Delete>")
