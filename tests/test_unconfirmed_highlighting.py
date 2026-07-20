"""
Teste pentru evidențierea vizuală a cărților "De Confirmat" (categorie
nesigură) în Catalog și Inventar -- oglindește modelul deja existent
pentru împrumuturile restante (rând roșu în Împrumuturi active): un
tag ttk.Treeview distinct aplicat doar cărților a căror categorie e
exact UNCONFIRMED_CATEGORY, nu celor cu o categorie reală.
"""

import customtkinter as ctk
import pytest

from config import UNCONFIRMED_CATEGORY
from database import Database
from ml_classifier import BookClassifier
from views.catalog import CatalogPage
from views.inventory import InventoryPage


class FakeApp:
    def __init__(self, db_path):
        self.db = Database(db_path=str(db_path))
        self.classifier = BookClassifier()
        self.classifier.load()
        self.pages = {}

    def show_page(self, key):
        pass


@pytest.fixture(scope="module")
def root():
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def app(tmp_path):
    return FakeApp(tmp_path / "test.db")


def _add_book(app, title, category_name):
    cat_id = app.db.get_or_create_category(category_name)
    return app.db.add_book(None, title, None, None, "", cat_id)


# ------------------------------------------------------------------
# Catalog
# ------------------------------------------------------------------
def test_catalog_tags_unconfirmed_book(root, app):
    unconfirmed_id = _add_book(app, "Carte Nesigura", UNCONFIRMED_CATEGORY)
    confirmed_id = _add_book(app, "Carte Sigura", "Fantezie & SF")

    page = CatalogPage(root, app)
    page.refresh()

    assert "unconfirmed" in page.tree.item(str(unconfirmed_id))["tags"]
    # Rândul confirmat poate avea alte tag-uri (ex. "oddrow" pentru zebra
    # striping), dar niciodată "unconfirmed".
    assert "unconfirmed" not in page.tree.item(str(confirmed_id))["tags"]


def test_catalog_tag_style_is_configured(root, app):
    page = CatalogPage(root, app)
    style = page.tree.tag_configure("unconfirmed")
    assert style["background"]
    assert style["foreground"]


# ------------------------------------------------------------------
# Inventar
# ------------------------------------------------------------------
def test_inventory_tags_unconfirmed_book(root, app):
    unconfirmed_id = _add_book(app, "Carte Nesigura", UNCONFIRMED_CATEGORY)
    confirmed_id = _add_book(app, "Carte Sigura", "Fantezie & SF")

    page = InventoryPage(root, app)
    page.refresh()

    assert "unconfirmed" in page.tree.item(str(unconfirmed_id))["tags"]
    # Rândul confirmat poate avea alte tag-uri (ex. "oddrow" pentru zebra
    # striping), dar niciodată "unconfirmed".
    assert "unconfirmed" not in page.tree.item(str(confirmed_id))["tags"]


def test_inventory_tag_style_is_configured(root, app):
    page = InventoryPage(root, app)
    style = page.tree.tag_configure("unconfirmed")
    assert style["background"]
    assert style["foreground"]
