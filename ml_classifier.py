# ml_classifier.py
"""
Clasificare automată a cărților pe categorii, folosind scikit-learn.

Pipeline: TfidfVectorizer (transformă textul titlu+descriere în vectori
numerici) -> LogisticRegression (clasificator multi-clasă).

Modelul este antrenat pe cărțile deja categorisite manual din baza de
date. Odată antrenat, este persistat pe disc cu joblib astfel încât să
nu fie nevoie de re-antrenare la fiecare pornire a aplicației.

Dacă încrederea predicției (probabilitatea maximă) este sub pragul
calculat (vezi `config.ML_CONFIDENCE_RATIO`/`ML_MIN_CONFIDENCE`), cartea
este marcată drept "De Confirmat" pentru a fi verificată manual de
bibliotecar.
"""

import os
import threading

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from config import (
    ML_MODEL_PATH,
    ML_CONFIDENCE_RATIO,
    ML_MIN_CONFIDENCE,
    ML_MIN_SAMPLES,
    ML_MIN_CLASSES,
    UNCONFIRMED_CATEGORY,
)


class BookClassifier:
    """Încapsulează antrenarea, persistarea și predicția modelului ML."""

    def __init__(self, model_path=ML_MODEL_PATH):
        self.model_path = model_path
        self.pipeline = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def load(self):
        """Încarcă un model antrenat anterior de pe disc, dacă există."""
        if os.path.exists(self.model_path):
            try:
                self.pipeline = joblib.load(self.model_path)
                return True
            except Exception:
                self.pipeline = None
        return False

    def is_trained(self):
        return self.pipeline is not None

    # ------------------------------------------------------------------
    def train(self, samples):
        """
        Antrenează modelul pe o listă de tupluri (text, categorie).
        Returnează (success: bool, message: str).
        """
        texts = [s[0] for s in samples]
        labels = [s[1] for s in samples]
        distinct_classes = set(labels)

        if len(samples) < ML_MIN_SAMPLES or len(distinct_classes) < ML_MIN_CLASSES:
            return False, (
                f"Date insuficiente pentru antrenare "
                f"(necesare minim {ML_MIN_SAMPLES} cărți categorisite în cel puțin "
                f"{ML_MIN_CLASSES} categorii distincte)."
            )

        # class_weight="balanced" contrabalansează categoriile cu mai multe
        # cărți (ex. Literatură română, mai numeroasă intenționat) — altfel
        # modelul tinde să prezică mereu clasa majoritară când nu e sigur.
        #
        # N-grame de caractere (nu de cuvinte): validat prin cross-validare
        # pe setul de antrenare (5-fold), analyzer="char_wb" a dat consecvent
        # ~55-63% acuratețe (crește odată cu mai multe cărți etichetate)
        # față de ~49% cu n-grame de cuvinte. Motivul e morfologia bogată a
        # limbii române — "iubire"/"iubit"/"iubește" nu au niciun token
        # comun la nivel de cuvânt, dar au multe secvențe de caractere
        # comune, deci modelul generalizează mai bine la forme flexionare
        # neîntâlnite exact în antrenare.
        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(max_features=8000, ngram_range=(3, 5), analyzer="char_wb", min_df=1)),
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ])
        pipeline.fit(texts, labels)

        with self._lock:
            self.pipeline = pipeline
            joblib.dump(pipeline, self.model_path)

        return True, f"Model antrenat cu succes pe {len(samples)} cărți / {len(distinct_classes)} categorii."

    def train_from_db(self, db):
        samples = db.get_training_dataset()
        return self.train(samples)

    # ------------------------------------------------------------------
    def predict(self, text):
        """
        Returnează (categorie_sugerată, încredere) pentru un text (titlu + descriere).
        Dacă modelul nu e antrenat sau încrederea e prea mică, categoria
        sugerată devine UNCONFIRMED_CATEGORY.
        """
        if not self.is_trained() or not text or not text.strip():
            return UNCONFIRMED_CATEGORY, 0.0

        with self._lock:
            pipeline = self.pipeline

        probabilities = pipeline.predict_proba([text])[0]
        classes = pipeline.classes_
        best_idx = probabilities.argmax()
        confidence = float(probabilities[best_idx])
        predicted_label = classes[best_idx]

        # Pragul scade proporțional cu numărul de categorii: cu mai multe
        # categorii, masa de probabilitate se împarte, deci un top-scor
        # "de încredere" este în mod natural mai mic (vezi config.py).
        threshold = max(ML_MIN_CONFIDENCE, ML_CONFIDENCE_RATIO / len(classes))

        if confidence < threshold:
            return UNCONFIRMED_CATEGORY, confidence
        return predicted_label, confidence
