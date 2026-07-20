# KenoLib — Sistem de Gestiune Bibliotecă

Aplicație desktop (Python + CustomTkinter + SQLite) pentru gestiunea unei
biblioteci: catalog de cărți, împrumuturi, rapoarte, import CSV masiv,
scanner de coduri de bare GM65 și clasificare automată a categoriilor
prin machine learning.

## Instalare

```bash
pip install -r requirements.txt
```

Necesită Python 3.9+.

## Rulare (din surse, cu Python instalat)

```bash
python main.py
```

La prima rulare se creează automat `library.db` (SQLite) cu schema și
categoriile implicite.

## Executabil standalone (.exe) — fără Python instalat

Pentru a rula aplicația pe orice calculator Windows fără să fie nevoie
de Python sau de librăriile din `requirements.txt`, se poate construi
un executabil de sine stătător cu PyInstaller:

```bash
build_exe.bat
```

(sau manual: `pip install -r requirements-build.txt` apoi
`python -m PyInstaller --noconfirm KenoLib.spec`)

Rezultatul apare în `dist\KenoLib\` — un folder ce conține
`KenoLib.exe` și dependințele sale (`_internal\`). **Pentru
distribuire, copiază întregul folder `dist\KenoLib`** (nu doar
fișierul `.exe`) pe calculatorul țintă și rulează `KenoLib.exe`
direct — nu necesită instalare. La prima pornire, `library.db` și
`ml_model.joblib` se creează automat lângă executabil, în același
folder, așa că folderul rămâne complet portabil (poate fi mutat pe un
stick USB sau alt calculator, păstrându-și datele).

Folderul este relativ mare (~190 MB) din cauza librăriilor
scikit-learn/scipy/numpy incluse pentru clasificarea ML — este normal.

Notă: acesta este un executabil **Windows** (folosește pyserial +
tkinter nativ); pentru macOS/Linux aplicația trebuie rulată din surse
cu Python.

## Structură modulară

| Fișier | Rol |
|---|---|
| `config.py` | Constante globale (căi, URL-uri API, praguri ML) |
| `database.py` | Model — acces SQLite, schema, CRUD |
| `ml_classifier.py` | Clasificator ML (TF-IDF + Regresie Logistică) pentru sugestii de categorie |
| `scanner_service.py` | Ascultare pe port serial (thread separat) pentru scannerul GM65 |
| `api_service.py` | Interogare Google Books / Open Library, după ISBN sau după titlu+autor |
| `gui_app.py` | Fereastra principală, sidebar, navigare |
| `views/dashboard.py` | Pagina Dashboard (statistici + activitate recentă) |
| `views/catalog.py` | Pagina Catalog Cărți (tabel, căutare, CRUD) |
| `views/loans.py` | Pagina Împrumuturi active (restanțe evidențiate roșu) |
| `views/reports.py` | Pagina Rapoarte (cărți/categorie, istoric tranzacții) |
| `views/inventory.py` | Pagina Inventar (listă completă, alfabetic sau pe categorii, export CSV) |
| `views/import_view.py` | Import CSV cu mapare coloane + clasificare ML |
| `views/dialogs.py` | Ferestre modale: adăugare/editare carte, împrumutător, împrumut |
| `main.py` | Punct de pornire |

## Scanner GM65

Scannerul GM65 (mod USB-COM, emulare tastatură/serial) este detectat ca
un port COM. Din bara laterală, selectează portul și apasă
„Conectează”. Codurile scanate în pagina **Catalog Cărți** (dialogul de
adăugare carte deschis sau nou) completează automat ISBN-ul și declanșează
căutarea online a datelor cărții.

## Căutare online (Google Books / Open Library)

Căutarea online (din formularul de carte sau la import) încearcă, în
ordine:
1. **După ISBN** (dacă e valid) — Google Books, apoi Open Library.
2. **După titlu + autor**, dacă ISBN-ul lipsește, e invalid sau nu a dat
   rezultate — util pentru cărțile vechi fără ISBN. Dacă una dintre surse
   găsește totuși un ISBN pentru acea carte, câmpul ISBN se completează
   automat.

Din cele două surse găsite se păstrează combinația cea mai completă —
titlu/autor/an din oricare are datele, iar descrierea este cea mai lungă
găsită (adesea Open Library nu are descriere deloc pentru anumite ediții;
în acel caz rămâne doar ce a găsit Google Books, sau invers).

## Clasificare ML

Modelul (TF-IDF pe n-grame de caractere + Regresie Logistică cu
`class_weight="balanced"`) se antrenează din pagina **Import Date**
(„Antrenează modelul ML”), pe baza cărților deja categorisite din bază.
N-gramele de caractere (nu de cuvinte) au fost alese pentru că
generalizează mai bine la formele flexionare ale limbii române
(„iubire”/„iubit”/„iubește” nu au niciun cuvânt comun, dar multe secvențe
de caractere comune) — validat prin cross-validare (~55% acuratețe brută,
față de ~49% cu n-grame de cuvinte). Pragul de încredere sub care o carte
e marcată „De Confirmat” se ajustează automat în funcție de numărul de
categorii din bibliotecă (config.py: `ML_CONFIDENCE_RATIO`,
`ML_MIN_CONFIDENCE`) — calibrat printr-o evaluare pe date separate de
antrenare (nu doar pe ochi), pentru un echilibru bun între cât de des
riscă o predicție și cât de des are dreptate când o face.

**De reținut**: cu un titlu singur, fără nicio descriere, orice
clasificator de text are foarte puțin semnal de lucru — de aceea multe
cărți (mai ales cele fără descriere găsită online) vor rămâne „De
Confirmat”, ceea ce e comportamentul de siguranță dorit, nu o eroare.
Cu cât categoria are mai multe cărți etichetate (din import-uri proprii,
re-antrenate periodic), cu atât predicțiile devin mai sigure.

**Modelul vine deja antrenat** — `ml_model.joblib` este inclus în proiect
(și copiat automat lângă `.exe` la fiecare rulare a `build_exe.bat`), deci
aplicația e pregătită din prima rulare să sugereze categorii pentru orice
import ulterior, fără niciun pas suplimentar.

### Îmbogățire online la import (opțional)

Pagina **Import Date** are o bifă „Îmbogățește cu date online” — dacă e
bifată, pentru fiecare carte fără descriere se încearcă mai întâi
completarea ei (după ISBN sau după titlu+autor) înainte de clasificarea
ML, exact pentru cazul unui export dintr-un soft vechi care are doar
titlu/autor/an/ISBN. O descriere mai bogată înseamnă o predicție ML mai
sigură. E dezactivată implicit (necesită internet și încetinește
importul); clasificarea ML funcționează integral offline și fără ea,
doar cu mai puțin semnal din text.

Dacă, după îmbogățire, modelul ML tot rămâne nesigur, se încearcă drept
ultimă soluție categoria generică oferită chiar de Google Books (ex.
„Biography” → Biografie, „Poetry” → Poezie) — folosită doar ca rezervă,
niciodată în locul unei predicții ML sigure. Același failsafe se aplică
și la adăugarea manuală a unei cărți (butonul „Caută online” din formular):
dacă modelul ML rămâne nesigur după căutare, categoria propusă de sursa
online (dacă a oferit una) e folosită în locul lui „De Confirmat”.

### Categorii

`Literatură română`, `Literatură străină`, `Poezie`, `Teatru`,
`Fantezie & SF`, `Thriller & Mister`, `Non-ficțiune`, `Știință`,
`Istorie`, `Biografie`, `Filozofie`, `Psihologie`, `Economie & Afaceri`,
`Copii`, `Tehnologie`, `Artă` (+ „De Confirmat” pentru cazurile
nesigure).

### Setul de date folosit la antrenare

Fișierul [`carti_exemplu_import.csv`](carti_exemplu_import.csv) conține
373 de cărți reale (majoritatea românești — aproape 50 doar la
Literatură română, plus autori români în Poezie, Teatru, Filozofie,
Istorie, Copii etc. — alături de clasici străini), distribuite pe toate
cele 16 categorii. Include și cărți străine cu descrieri în engleză (pe
lângă restul, descrise în română) — pentru ca modelul să recunoască și
textul în engleză pe care „Căutarea online”/îmbogățirea la import îl
aduce frecvent pentru cărți străine, nu doar vocabular românesc.

Acesta e setul folosit pentru a antrena modelul livrat cu aplicația; nu
a fost importat și în catalogul propriu-zis, ca să nu apară cărți
„fantomă” pe care nu le ai — catalogul pornește gol. Dacă vrei totuși
aceste cărți și în Catalog (ex. ca punct de plecare), le poți importa
oricând din pagina **Import Date**, la fel ca orice alt CSV.

Pentru a re-antrena modelul (de exemplu după ce adaugi propriile cărți):
pagina **Import Date** → „Selectează fișier CSV” → coloanele se mapează
automat (Titlu, Autor, An, Categorie, Descriere) → „Începe Import” →
„Antrenează modelul ML”.

## Câmpuri suplimentare ale cărții

Pe lângă titlu/autor/an/descriere/categorie, fiecare carte mai are:
**Editură** (auto-completată la „Caută online”, sau introdusă manual),
**Loc apariție**, **Preț** (introdus manual), **Nr. exemplare** (implicit
1) și **CZU**. Toate sunt disponibile atât în formularul de
adăugare/editare, cât și la import CSV (mapare de coloane) și în
tabelul din Catalog.

Bazele de date create cu o versiune mai veche a aplicației se
actualizează automat la prima pornire (coloanele noi se adaugă fără să
șteargă cărțile existente).

### CZU (Clasificarea Zecimală Universală)

Butonul „Sugerează” de lângă câmpul CZU oferă un cod de pornire pe baza
categoriei (ex. `821.135.1` pentru Literatură română, `004` pentru
Tehnologie — clasele principale UDC/CZU, stabile și bine documentate).
**Nu este o catalogare CZU completă** — sistemul CZU are subdiviziuni
mult mai fine (limbă, perioadă, sub-gen) pe care o mapare simplă
categorie→cod nu le poate acoperi; codul sugerat e un punct de plecare,
de verificat/rafinat de bibliotecar cu tabelele oficiale CZU. La import
CSV, dacă nu e mapată o coloană CZU sau celula e goală, se completează
automat aceeași sugestie.

## Inventar

Pagina **Inventar** generează lista completă a cărților, fie sortată
alfabetic după titlu, fie grupată pe categorie (și alfabetic în
interiorul fiecăreia). Afișează și un rezumat (număr de titluri, total
exemplare, valoare totală — calculată din preț × exemplare pentru
cărțile care au preț completat) și permite exportul listei ca fișier
CSV.
