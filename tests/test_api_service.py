"""
Teste pentru logica pură din api_service.py (fără apeluri de rețea):
map_category_hint() și _merge_best(). Acoperă regresiile descoperite în
timpul dezvoltării (ambiguitate LCSH "Subiect, subdiviziune", amestecarea
editurii/locului apariției între surse diferite).
"""

from api_service import map_category_hint, _merge_best


# ------------------------------------------------------------------
# map_category_hint
# ------------------------------------------------------------------
def test_lcsh_comma_qualifier_excluded():
    # Regresie: "Science, history" înseamnă "istoria științei", nu genul
    # Istorie -- fără regula virgulei, o carte de fizică (ex. "A Brief
    # History of Time") primea greșit sugestia "Istorie".
    assert map_category_hint(["Science, history"]) == "Știință"


def test_bare_drama_tag_not_treated_as_theatre():
    # Regresie: eticheta generică "Drama" (folosită pentru orice roman cu
    # conflict dramatic, nu doar piese de teatru) nu mai e în
    # CATEGORY_KEYWORD_MAP -- nu trebuie să mapeze la "Teatru".
    assert map_category_hint(["Drama"]) is None


def test_plays_keyword_still_maps_to_theatre():
    assert map_category_hint(["Plays"]) == "Teatru"


def test_specific_keyword_wins_over_generic_substring():
    # "computer science" trebuie să mapeze la Tehnologie, nu la Știință,
    # deși conține cuvântul "science".
    assert map_category_hint(["Computer science"]) == "Tehnologie"


def test_word_boundary_not_substring_match():
    # "art" nu trebuie să se potrivească în interiorul altor cuvinte.
    assert map_category_hint(["Heart disease"]) is None


def test_no_match_returns_none():
    assert map_category_hint(["Some completely unrelated tag"]) is None


def test_empty_or_none_labels_returns_none():
    assert map_category_hint([]) is None
    assert map_category_hint(None) is None


# ------------------------------------------------------------------
# _merge_best
# ------------------------------------------------------------------
def test_merge_best_picks_longest_description():
    a = {"title": "A", "desc": "short", "publisher": "Pub A"}
    b = {"title": "A", "desc": "a much longer description here", "publisher": "Pub B"}
    merged = _merge_best(a, b)
    assert merged["desc"] == b["desc"]


def test_merge_best_does_not_cross_backfill_publisher_or_place():
    # Regresie: editura/locul apariției nu trebuie preluate dintr-o altă
    # sursă decât cea aleasă pentru descriere -- altfel se amestecă date
    # din ediții diferite (ex. o editură rusă lângă un titlu englezesc).
    a = {"title": "A", "desc": "", "publisher": "Editura Veche", "pub_place": "Iasi"}
    b = {"title": "A", "desc": "long rich description chosen as best", "publisher": "", "pub_place": ""}
    merged = _merge_best(a, b)
    assert merged["desc"] == "long rich description chosen as best"
    assert merged.get("publisher", "") == ""
    assert merged.get("pub_place", "") == ""


def test_merge_best_cross_backfills_edition_invariant_fields():
    a = {"title": "", "author": "Frank Herbert", "desc": "long description chosen as best here"}
    b = {"title": "Dune", "author": "", "desc": ""}
    merged = _merge_best(a, b)
    assert merged["title"] == "Dune"
    assert merged["author"] == "Frank Herbert"


def test_merge_best_all_none_returns_none():
    assert _merge_best(None, None) is None


def test_merge_best_skips_none_results():
    a = {"title": "A", "desc": "desc"}
    merged = _merge_best(None, a, None)
    assert merged["title"] == "A"
