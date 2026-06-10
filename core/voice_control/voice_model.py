from pathlib import Path
import pickle
from typing import Any, Dict, Optional, Tuple

import numpy as np

try:
    import joblib
except ImportError:  # pragma: no cover
    joblib = None


class VoiceCommandModel:
    """Carga y ejecuta un modelo de clasificación para comandos de voz."""

    def __init__(self, model_path: Path):
        self.model_path = Path(model_path)
        self.model = self._load_model(self.model_path)
        self.name = self.model_path.stem

    @staticmethod
    def _load_model(path: Path) -> Any:
        if not path.exists():
            raise FileNotFoundError(f"Modelo de voz no encontrado: {path}")

        if joblib is not None:
            try:
                return joblib.load(path)
            except Exception:
                pass

        with open(path, "rb") as fh:
            return pickle.load(fh)

    def predict(self, features: np.ndarray) -> Tuple[Optional[str], float]:
        if features is None:
            return None, 0.0

        X = np.asarray(features, dtype=np.float32).reshape(1, -1)

        if hasattr(self.model, "predict_proba"):
            try:
                proba = self.model.predict_proba(X)
                if proba is not None and len(proba) > 0:
                    best_idx = int(np.argmax(proba[0]))
                    label = None
                    if hasattr(self.model, "classes_"):
                        label = self.model.classes_[best_idx]
                    else:
                        prediction = self.model.predict(X)
                        label = prediction[0] if hasattr(prediction, "__getitem__") else prediction
                    return str(label), float(proba[0][best_idx])
            except Exception:
                pass

        try:
            prediction = self.model.predict(X)
            if hasattr(prediction, "__getitem__"):
                label = prediction[0]
            else:
                label = prediction
            return str(label), 1.0
        except Exception:
            return None, 0.0


class VoiceCommandClassifier:
    """Agrupa varios modelos de comandos y selecciona la mejor predicción."""

    def __init__(self, model_paths: Dict[str, str]):
        self.models = []
        for model_name, model_path in (model_paths or {}).items():
            try:
                path = Path(model_path)
                if not path.is_absolute():
                    path = Path(".") / model_path
                model = VoiceCommandModel(path)
                self.models.append((str(model_name), model))
            except Exception:
                continue

    def has_models(self) -> bool:
        return len(self.models) > 0

    def predict(self, features: np.ndarray) -> Tuple[Optional[str], float, Optional[str]]:
        best_label = None
        best_score = 0.0
        best_source = None

        for model_name, model in self.models:
            label, score = model.predict(features)
            if label is None:
                continue
            if score >= best_score:
                best_score = score
                best_label = label
                best_source = model_name

        return best_label, best_score, best_source
