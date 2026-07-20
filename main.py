# main.py
"""
Punct de pornire al aplicației. Rulează:
    python main.py

La prima rulare, baza de date SQLite (library.db) și schema tabelelor
sunt create automat de modulul `database.py`, iar categoriile implicite
sunt inserate. Restul aplicației este construit modular:
    - config.py            configurări globale
    - database.py           strat de acces la date (Model)
    - ml_classifier.py       clasificare automată a cărților (ML)
    - scanner_service.py     ascultare scanner GM65 pe port serial
    - api_service.py         integrare Google Books / Open Library
    - gui_app.py + views/    interfața grafică (View/Controller)
"""

from gui_app import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
