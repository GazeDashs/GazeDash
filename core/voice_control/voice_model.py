from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pickle
from typing import Any, Dict, Optional, Tuple

import numpy as np

from .audio_features import FEATURE_COLUMNS_V3, TARGET_SR, extract_features_v3, preprocess_audio_array

try:
    import joblib
except ImportError:  # pragma: no cover
    joblib = None


@dataclass(frozen=True)
class VoicePrediction:
    label: Optional[str]
    confidence: float
    source: Optional[str] = None
    probabilities: Optional[list[tuple[str, float]]] = None


class VoiceModelLoadError(RuntimeError):
    pass


class VoiceCommandModel:
    """Carga y ejecuta un modelo de comandos de voz.

    Soporta el formato nuevo exportado desde el notebook:
    {"model", "scaler", "features", "label_encoder", ...}
    y conserva un fallback para estimadores sklearn directos.
    """

    def __init__(self, model_path: Path):
        self.model_path = Path(model_path)
        self.pipeline = self._load_model(self.model_path)
        self.name = self.model_path.stem
        self._validate_pipeline()

    @staticmethod
    def _load_model(path: Path) -> Any:
        if not path.exists():
            raise FileNotFoundError(f"Modelo de voz no encontrado: {path}")

        errors = []
        if joblib is not None and hasattr(joblib, "load"):
            try:
                return joblib.load(path)
            except Exception as exc:
                errors.append(f"joblib: {type(exc).__name__}: {exc}")
        elif joblib is not None:
            errors.append("joblib importado pero no expone joblib.load")

        try:
            with open(path, "rb") as fh:
                return pickle.load(fh)
        except Exception as exc:
            errors.append(f"pickle: {type(exc).__name__}: {exc}")

        details = "; ".join(errors) if errors else "sin detalle"
        raise VoiceModelLoadError(f"No se pudo cargar {path}: {details}")

    def _validate_pipeline(self):
        if not isinstance(self.pipeline, dict):
            return

        required = {"model", "scaler", "features", "label_encoder"}
        missing = sorted(required - set(self.pipeline.keys()))
        if missing:
            raise VoiceModelLoadError(f"Modelo {self.model_path} incompleto. Faltan claves: {', '.join(missing)}")

    def predict_from_audio(
        self,
        audio: np.ndarray,
        sample_rate: int = TARGET_SR,
        gain: float = 1.0,
    ) -> VoicePrediction:
        processed = preprocess_audio_array(audio, sample_rate, gain=gain)
        features = extract_features_v3(processed, TARGET_SR)
        return self.predict(features)

    def predict(self, features: np.ndarray) -> VoicePrediction:
        if features is None:
            return VoicePrediction(None, 0.0, self.name)

        if isinstance(self.pipeline, dict):
            return self._predict_pipeline_dict(features)

        label, confidence, probabilities = self._predict_estimator(self.pipeline, features)
        return VoicePrediction(label, confidence, self.name, probabilities)

    def _predict_pipeline_dict(self, features: np.ndarray) -> VoicePrediction:
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError(
                "pandas no esta instalado. Instala las dependencias de voz para usar los modelos entrenados."
            ) from exc

        features_array = np.asarray(features, dtype=np.float32).reshape(1, -1)
        features_df = pd.DataFrame(features_array, columns=FEATURE_COLUMNS_V3)

        selected_features = list(self.pipeline["features"])
        missing = [name for name in selected_features if name not in features_df.columns]
        if missing:
            raise RuntimeError(f"Features requeridas no generadas para {self.name}: {', '.join(missing[:5])}")

        X_selected = features_df[selected_features]
        X_scaled = self.pipeline["scaler"].transform(X_selected)
        model = self.pipeline["model"]
        label_encoder = self.pipeline["label_encoder"]

        prediction_raw = model.predict(X_scaled)
        prediction_value = prediction_raw[0] if hasattr(prediction_raw, "__getitem__") else prediction_raw

        try:
            label = label_encoder.inverse_transform([int(prediction_value)])[0]
        except Exception:
            label = prediction_value

        probabilities = None
        confidence = 1.0
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X_scaled)
            if proba is not None and len(proba) > 0:
                class_names = list(getattr(label_encoder, "classes_", []))
                proba_row = list(proba[0])
                probabilities = [
                    (str(class_names[i]) if i < len(class_names) else str(i), float(value))
                    for i, value in enumerate(proba_row)
                ]
                probabilities.sort(key=lambda item: item[1], reverse=True)
                if probabilities:
                    confidence = float(probabilities[0][1])

        return VoicePrediction(str(label), float(confidence), self.name, probabilities)

    def _predict_estimator(self, model: Any, features: np.ndarray) -> Tuple[Optional[str], float, Optional[list[tuple[str, float]]]]:
        X = np.asarray(features, dtype=np.float32).reshape(1, -1)

        if hasattr(model, "predict_proba"):
            try:
                proba = model.predict_proba(X)
                if proba is not None and len(proba) > 0:
                    best_idx = int(np.argmax(proba[0]))
                    if hasattr(model, "classes_"):
                        label = model.classes_[best_idx]
                    else:
                        prediction = model.predict(X)
                        label = prediction[0] if hasattr(prediction, "__getitem__") else prediction
                    probabilities = None
                    if hasattr(model, "classes_"):
                        probabilities = [
                            (str(model.classes_[i]), float(value))
                            for i, value in enumerate(proba[0])
                        ]
                        probabilities.sort(key=lambda item: item[1], reverse=True)
                    return str(label), float(proba[0][best_idx]), probabilities
            except Exception:
                pass

        try:
            prediction = model.predict(X)
            label = prediction[0] if hasattr(prediction, "__getitem__") else prediction
            return str(label), 1.0, None
        except Exception:
            return None, 0.0, None


class VoiceCommandClassifier:
    """Agrupa varios modelos de comandos y selecciona la mejor prediccion."""

    def __init__(self, model_paths: Dict[str, str]):
        self.models: list[tuple[str, VoiceCommandModel]] = []
        self.load_errors: dict[str, str] = {}

        for model_name, model_path in (model_paths or {}).items():
            try:
                path = Path(model_path)
                if not path.is_absolute():
                    path = Path(".") / model_path
                model = VoiceCommandModel(path)
                self.models.append((str(model_name), model))
            except Exception as exc:
                self.load_errors[str(model_name)] = f"{type(exc).__name__}: {exc}"

    def has_models(self) -> bool:
        return len(self.models) > 0

    def get_load_errors(self) -> dict[str, str]:
        return dict(self.load_errors)

    def predict_from_audio(
        self,
        audio: np.ndarray,
        sample_rate: int = TARGET_SR,
        gain: float = 1.0,
    ) -> VoicePrediction:
        best = VoicePrediction(None, 0.0, None)
        for model_name, model in self.models:
            prediction = model.predict_from_audio(audio, sample_rate=sample_rate, gain=gain)
            if prediction.label is not None and prediction.confidence >= best.confidence:
                best = VoicePrediction(
                    prediction.label,
                    prediction.confidence,
                    model_name,
                    prediction.probabilities,
                )
        return best

    def predict(self, features: np.ndarray) -> Tuple[Optional[str], float, Optional[str]]:
        prediction = self.predict_detailed(features)
        return prediction.label, prediction.confidence, prediction.source

    def predict_detailed(self, features: np.ndarray) -> VoicePrediction:
        best = VoicePrediction(None, 0.0, None)
        for model_name, model in self.models:
            prediction = model.predict(features)
            if prediction.label is not None and prediction.confidence >= best.confidence:
                best = VoicePrediction(
                    prediction.label,
                    prediction.confidence,
                    model_name,
                    prediction.probabilities,
                )
        return best
