# api_service.py
"""
Integrare cu API-uri externe pentru auto-completarea datelor unei cărți:
Google Books API (sursă principală) și Open Library API (rezervă). Cele
două surse sunt independente — dacă una nu răspunde sau nu are date,
se încearcă cealaltă, iar dacă amândouă au răspuns, se păstrează
combinația cea mai completă (ex. descrierea cea mai lungă găsită).

Două moduri de căutare:
- după ISBN (cel mai precis, folosit când scanerul GM65 sau utilizatorul
  introduce un cod valid);
- după titlu + autor (rezervă pentru cărțile fără ISBN sau al căror ISBN
  nu se găsește în nicio bază de date — frecvent la cărți vechi sau la
  ediții românești mai puțin cunoscute).

Funcțiile din acest modul sunt sincrone (blocante) și folosesc
`requests`. Apelantul (GUI / import CSV) este responsabil să le ruleze
într-un thread separat pentru a nu bloca interfața grafică.
"""

import re

import requests

from config import (
    GOOGLE_BOOKS_API,
    GOOGLE_BOOKS_SEARCH_API,
    OPEN_LIBRARY_API,
    OPEN_LIBRARY_SEARCH_API,
    API_TIMEOUT,
)
from utils import is_valid_isbn, normalize_isbn

# Mapare aproximativă a categoriilor/subiectelor generice (Google Books
# "categories" sau Open Library "subject"/"subjects") -> taxonomia proprie
# a aplicației. Folosită doar ca ultimă soluție (failsafe), atunci când
# clasificatorul ML nu are suficientă încredere.
#
# Ordinea contează: cuvintele-cheie compuse/specifice sunt verificate
# înaintea celor generice de un singur cuvânt care le-ar putea "conține"
# (ex. "computer science" înainte de "science" generic — altfel un subiect
# Open Library precum "Computer science" s-ar mapa greșit la Știință în loc
# de Tehnologie). Potrivirea se face pe cuvinte întregi (word-boundary),
# nu substring simplu — altfel "art" s-ar potrivi și în "heart"/"start".
CATEGORY_KEYWORD_MAP = {
    "romanian fiction": "Literatură română",
    "romanian literature": "Literatură română",
    "romanian authors": "Literatură română",
    "romanian poetry": "Poezie",
    "romanian drama": "Teatru",
    "juvenile fiction": "Copii",
    "juvenile nonfiction": "Copii",
    "science fiction": "Fantezie & SF",
    "computer science": "Tehnologie",
    "computer program": "Tehnologie",
    "performing arts": "Teatru",
    "fine arts": "Artă",
    "visual arts": "Artă",
    "children": "Copii",
    "poetry": "Poezie",
    "plays": "Teatru",
    "fantasy": "Fantezie & SF",
    "mystery": "Thriller & Mister",
    "thriller": "Thriller & Mister",
    "detective": "Thriller & Mister",
    "autobiography": "Biografie",
    "biography": "Biografie",
    "history": "Istorie",
    "philosophy": "Filozofie",
    "psychology": "Psihologie",
    "business": "Economie & Afaceri",
    "economics": "Economie & Afaceri",
    "technology": "Tehnologie",
    "computers": "Tehnologie",
    "programming": "Tehnologie",
    "software": "Tehnologie",
    "art": "Artă",
    "science": "Știință",
}


def _extract_year(date_str):
    match = re.search(r"(\d{4})", date_str or "")
    return int(match.group(1)) if match else None


def _extract_isbn(volume_info):
    """Extrage ISBN-13 (preferat) sau ISBN-10 din industryIdentifiers Google Books."""
    identifiers = volume_info.get("industryIdentifiers", [])
    for wanted in ("ISBN_13", "ISBN_10"):
        for ident in identifiers:
            if ident.get("type") == wanted:
                return ident.get("identifier", "")
    return ""


def map_category_hint(labels):
    """
    Încearcă să mapeze etichete generice (categorii Google Books sau
    subiecte Open Library) la o categorie proprie a aplicației.

    Verifică fiecare cuvânt-cheie din CATEGORY_KEYWORD_MAP (în ordinea lui
    de prioritate) pe rând, contra TUTUROR etichetelor primite, nu invers —
    altfel un cuvânt-cheie nesigur/greșit dintr-o etichetă întâmplător
    listată prima (ex. eticheta eronată "Biography" pusă de un contribuitor
    Open Library pentru un roman) ar câștiga în fața unui cuvânt-cheie mult
    mai specific și de încredere (ex. "Romanian Authors"), doar pentru că
    apărea primul în listă.

    Potrivirea respectă convenția LCSH "Subiect, subdiviziune": un
    cuvânt-cheie e ignorat dacă apare DUPĂ o virgulă în etichetă, pentru
    că acolo joacă rol de calificativ, nu de subiect principal (ex.
    "Science, history" înseamnă "istoria științei", nu genul „Istorie" —
    fără regula asta, o carte de fizică ar fi primit greșit sugestia
    „Istorie" doar pentru că eticheta ei conținea, undeva, cuvântul
    "history").
    """
    if not labels:
        return None
    primary_parts = [label.lower().split(",", 1)[0] for label in labels]
    for keyword, mapped in CATEGORY_KEYWORD_MAP.items():
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if any(re.search(pattern, part) for part in primary_parts):
            return mapped
    return None


def _extract_names(items):
    """
    Normalizează un câmp care apare fie ca listă de string-uri
    (search.json, works.json), fie ca listă de dict-uri cu cheia "name"
    (endpoint-ul ISBN /api/books) — folosit atât pentru "subjects", cât
    și pentru "publishers"/"publish_places".
    """
    names = []
    for item in items or []:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            names.append(item["name"])
    return names


def _parse_google_item(info):
    if not info.get("title"):
        return None
    return {
        "title": info.get("title", ""),
        "author": ", ".join(info.get("authors", [])),
        "pub_year": _extract_year(info.get("publishedDate", "")),
        "desc": info.get("description", "") or "",
        "isbn": _extract_isbn(info),
        "publisher": info.get("publisher", "") or "",
        "pub_place": "",  # Google Books nu oferă locul apariției
        "category_hint": map_category_hint(info.get("categories")),
        "source": "Google Books",
    }


# ----------------------------------------------------------------------
# Căutare după ISBN
# ----------------------------------------------------------------------
def fetch_google_books_by_isbn(isbn):
    """Interoghează Google Books API după ISBN. Returnează dict sau None."""
    try:
        resp = requests.get(GOOGLE_BOOKS_API.format(isbn=isbn), timeout=API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items")
        if not items:
            return None
        return _parse_google_item(items[0].get("volumeInfo", {}))
    except (requests.RequestException, ValueError):
        return None


def fetch_open_library_by_isbn(isbn):
    """Interoghează Open Library API după ISBN (rezervă). Returnează dict sau None."""
    try:
        resp = requests.get(OPEN_LIBRARY_API.format(isbn=isbn), timeout=API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        key = f"ISBN:{isbn}"
        if key not in data:
            return None
        info = data[key]
        if not info.get("title"):
            return None
        authors = ", ".join(a.get("name", "") for a in info.get("authors", []))
        notes = info.get("notes")
        desc = notes if isinstance(notes, str) else (info.get("subtitle", "") or "")
        excerpts = info.get("excerpts") or []
        if not desc and excerpts:
            desc = excerpts[0].get("text", "") or ""
        subjects = _extract_names(info.get("subjects"))
        publishers = _extract_names(info.get("publishers"))
        pub_places = _extract_names(info.get("publish_places"))
        return {
            "title": info.get("title", ""),
            "author": authors,
            "pub_year": _extract_year(info.get("publish_date", "")),
            "desc": desc,
            "isbn": isbn,
            "publisher": publishers[0] if publishers else "",
            "pub_place": pub_places[0] if pub_places else "",
            "category_hint": map_category_hint(subjects),
            "source": "Open Library",
        }
    except (requests.RequestException, ValueError):
        return None


# ----------------------------------------------------------------------
# Căutare după titlu + autor (pentru cărți fără ISBN sau ISBN negăsit)
# ----------------------------------------------------------------------
def _google_books_search(query):
    try:
        resp = requests.get(
            GOOGLE_BOOKS_SEARCH_API, params={"q": query}, timeout=API_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items")
        if not items:
            return None
        return _parse_google_item(items[0].get("volumeInfo", {}))
    except (requests.RequestException, ValueError):
        return None


def fetch_google_books_by_title_author(title, author=None):
    """
    Căutare generală Google Books după titlu (+ autor opțional). Încearcă
    întâi o interogare "strictă" (intitle:/inauthor:), apoi, dacă nu dă
    rezultate, o interogare simplă (fără calificatori de câmp) — utilă
    pentru ediții mai puțin cunoscute (ex. traduceri românești) unde
    metadatele din Google Books nu se potrivesc exact pe câmpuri.
    """
    if not title:
        return None
    strict_query = f"intitle:{title}"
    if author:
        strict_query += f"+inauthor:{author}"
    result = _google_books_search(strict_query)
    if result:
        return result

    loose_query = f"{title} {author}".strip() if author else title
    return _google_books_search(loose_query)


def _fetch_open_library_work_details(work_key):
    """
    Aduce detalii suplimentare ale unei "opere" Open Library (endpoint
    /works/{id}.json): descrierea completă (mult mai bogată decât
    `first_sentence` din rezultatul de căutare — adesea un paragraf întreg,
    nu doar o propoziție) și lista de subiecte (folosită ca sugestie de
    categorie). Returnează (desc, subjects); ("", []) dacă nu există sau
    cererea eșuează.
    """
    if not work_key:
        return "", []
    try:
        resp = requests.get(f"https://openlibrary.org{work_key}.json", timeout=API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        description = data.get("description")
        if isinstance(description, dict):
            desc = description.get("value", "") or ""
        elif isinstance(description, str):
            desc = description
        else:
            desc = ""
        return desc, (data.get("subjects") or [])
    except (requests.RequestException, ValueError):
        return "", []


def fetch_open_library_by_title_author(title, author=None):
    """Căutare generală Open Library după titlu (+ autor opțional)."""
    if not title:
        return None
    params = {
        "title": title,
        "limit": 1,
        # Open Library omite isbn/first_sentence/subject/publisher/key din
        # răspuns dacă nu sunt cerute explicit prin "fields" — fără asta,
        # ISBN-ul nu se putea descoperi, "key" e necesar pentru descrierea
        # completă, "subject" pentru sugestia de categorie (failsafe), iar
        # "publisher"/"publish_place" pentru editură/locul apariției.
        "fields": "title,author_name,first_publish_year,isbn,first_sentence,"
                  "subject,publisher,publish_place,key",
    }
    if author:
        params["author"] = author
    try:
        resp = requests.get(OPEN_LIBRARY_SEARCH_API, params=params, timeout=API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        docs = data.get("docs")
        if not docs:
            return None
        doc = docs[0]
        if not doc.get("title"):
            return None
        first_sentence = doc.get("first_sentence")
        if isinstance(first_sentence, list):
            desc = first_sentence[0] if first_sentence else ""
        elif isinstance(first_sentence, str):
            desc = first_sentence
        else:
            desc = ""

        # first_sentence e adesea o singură propoziție — încearcă
        # descrierea completă a operei, care e de regulă mult mai lungă,
        # plus subiectele operei (mai multe/mai specifice decât "subject"
        # din search.json), pentru o sugestie de categorie mai bună.
        richer_desc, work_subjects = _fetch_open_library_work_details(doc.get("key"))
        if richer_desc and len(richer_desc) > len(desc):
            desc = richer_desc

        subjects = (doc.get("subject") or []) + work_subjects
        isbns = doc.get("isbn") or []
        return {
            "title": doc.get("title", ""),
            "author": ", ".join(doc.get("author_name", []) or []),
            "pub_year": doc.get("first_publish_year"),
            "desc": desc,
            "isbn": isbns[0] if isbns else "",
            # "publisher"/"publish_place" din search.json sunt agregate pe
            # TOATE edițiile mondiale ale operei (o carte populară poate
            # avea 100+ intrări) — alegerea primului element ar fi
            # esențial arbitrară și adesea nepotrivită cu titlul/descrierea
            # returnate (ex. o editură rusă lângă un titlu englezesc).
            # Lăsate goale aici; sunt corecte doar din căutarea după ISBN,
            # care se referă la o singură ediție concretă.
            "publisher": "",
            "pub_place": "",
            "category_hint": map_category_hint(subjects),
            "source": "Open Library",
        }
    except (requests.RequestException, ValueError):
        return None


# ----------------------------------------------------------------------
# Combinare rezultate din mai multe surse
# ----------------------------------------------------------------------
def _merge_best(*results):
    """
    Combină rezultatele găsite (unele pot fi None) într-un singur dict,
    păstrând descrierea cea mai lungă găsită.

    Câmpurile "invariante la ediție" (titlu, autor, an, ISBN, categorie
    sugerată) se pot completa dintr-o altă sursă dacă cea aleasă nu le
    are — sunt aceleași fapte despre carte, indiferent de ediție. Editura
    și locul apariției NU se completează din altă sursă decât cea aleasă
    (cu descrierea cea mai lungă): diferă real de la o ediție la alta, iar
    amestecarea lor ar produce o combinație incoerentă (ex. o editură
    rusă alături de un titlu englezesc, dintr-o ediție complet diferită).
    """
    valid = [r for r in results if r]
    if not valid:
        return None
    best = max(valid, key=lambda r: len(r.get("desc") or ""))
    merged = dict(best)
    for r in valid:
        for key in ("title", "author", "pub_year", "isbn", "category_hint"):
            if not merged.get(key) and r.get(key):
                merged[key] = r[key]
    return merged


# ----------------------------------------------------------------------
# Puncte de intrare folosite de restul aplicației
# ----------------------------------------------------------------------
def fetch_book_by_isbn(isbn):
    """
    Caută o carte după ISBN în ambele surse și le combină.
    Returnează dict (title/author/pub_year/desc/isbn/category_hint/source)
    sau None dacă ISBN-ul nu e valid sau nicio sursă nu are date.
    """
    isbn = normalize_isbn(isbn)
    if not is_valid_isbn(isbn):
        return None
    return _merge_best(fetch_google_books_by_isbn(isbn), fetch_open_library_by_isbn(isbn))


def fetch_book_by_title_author(title, author=None):
    """Caută o carte după titlu + autor în ambele surse și le combină."""
    if not title:
        return None
    return _merge_best(
        fetch_google_books_by_title_author(title, author),
        fetch_open_library_by_title_author(title, author),
    )


def fetch_book_metadata(isbn=None, title=None, author=None):
    """
    Punct de intrare unificat: dacă sunt disponibile ambele — ISBN valid
    ȘI titlu — încearcă AMÂNDOUĂ căutările și le combină, nu se oprește
    la prima cu rezultat. Un rezultat găsit după ISBN e adesea "subțire"
    (fără descriere, fără categorie sugerată) pentru ediții mai puțin
    documentate — o căutare după titlu poate găsi o ediție (eventual în
    altă limbă) cu date mult mai complete, iar combinarea ambelor dă cea
    mai bogată descriere și cea mai bună sugestie de categorie posibilă.
    Dacă e disponibil doar unul dintre cele două, se folosește doar
    acela (fără cereri irosite). Util atât pentru căutarea manuală din
    formularul de carte, cât și pentru îmbogățirea automată la import CSV.
    """
    isbn = normalize_isbn(isbn) if isbn else ""
    isbn_valid = bool(isbn) and is_valid_isbn(isbn)

    results = []
    if isbn_valid:
        results.append(fetch_book_by_isbn(isbn))
    if title:
        results.append(fetch_book_by_title_author(title, author))

    return _merge_best(*results)
