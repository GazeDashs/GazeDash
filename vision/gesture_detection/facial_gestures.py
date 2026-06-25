"""Detección de gestos faciales con calibración neutral adaptativa.

Incluye debouncing por frames y umbrales mínimos absolutos para evitar
falsos positivos en gestos como `brow_raise`.
"""

from dataclasses import dataclass
from pathlib import Path
import time
from statistics import median
from typing import Dict, List, Optional

from config.config_manager import ConfigManager


NEUTRAL_METRIC_FIELDS = (
    "mouth_pucker_score",
    "jaw_open_score",
    "mouth_funnel_score",
    "mouth_ratio",
    "brow_ratio",
    "smile_left",
    "smile_right",
    "brow_inner_up",
    "brow_down_left",
    "brow_down_right",
    "eye_blink_left",
    "eye_blink_right",
    "eye_squint_left",
    "eye_squint_right",
    "eye_wide_left",
    "eye_wide_right",
    "nose_sneer_left",
    "nose_sneer_right",
)

GESTURE_NAMES = (
    "mouth_pucker",
    "mouth_open",
    "mouth_o",
    "smile",
    "smile_left",
    "smile_right",
    "brow_raise",
    "brow_frown",
    "eye_blink",
    "eye_wide",
    "nose_sneer",
)


@dataclass(frozen=True)
class FacialGestureThresholds:
    mouth_pucker: float = 0.5
    mouth_open: float = 0.6
    mouth_funnel: float = 0.5
    brow_raise: float = 0.5
    brow_frown: float = 0.4
    eye_blink: float = 0.7
    eye_wide: float = 0.6
    nose_sneer: float = 0.4
    smile: float = 0.5
    smile_left: float = 0.5
    smile_right: float = 0.5
    mouth_conflict_margin: float = 0.05


class FacialGestureDetector:
    """Convierte métricas faciales en gestos discretos usando una base neutral."""

    DEFAULT_CALIBRATION_SECONDS = 5.0
    DEFAULT_ADAPTATION_ALPHA = 0.01
    GESTURE_SCALES = {
        "mouth_pucker": 1.0,
        "mouth_open": 0.5,
        "mouth_o": 0.6,
        "smile": 0.65,
        "smile_left": 0.65,
        "smile_right": 0.65,
        "brow_raise": 0.6,
        "brow_frown": 0.75,
        "eye_blink": 0.85,
        "eye_wide": 0.65,
        "nose_sneer": 0.65,
    }
    GEOMETRY_DELTAS = {
        "mouth_open": 0.05,
        "mouth_o": 0.04,
        "brow_raise": 0.12,
        "smile": 0.05,
    }
    # Require a gesture to be observed for N consecutive frames before reporting
    GESTURE_DEBOUNCE_FRAMES = {
        "mouth_pucker": 1,
        "mouth_open": 2,
        "mouth_o": 2,
        "smile_left": 2,
        "smile_right": 2,
        "smile": 2,
        "brow_raise": 3,
        "brow_frown": 2,
        "eye_blink": 3,
        "eye_wide": 3,
        "nose_sneer": 2,
    }
    # Minimum absolute delta above baseline required (prevents tiny baseline noise)
    MIN_ABSOLUTE_DELTAS = {
        "brow_raise": 0.04,
        "mouth_pucker": 0.18,
        "eye_blink": 0.08,
    }

    def __init__(
        self,
        thresholds: Optional[FacialGestureThresholds] = None,
        calibration_seconds: float = DEFAULT_CALIBRATION_SECONDS,
        adaptation_alpha: float = DEFAULT_ADAPTATION_ALPHA,
    ):
        if thresholds is not None:
            self.thresholds = thresholds
        else:
            self.thresholds = self._load_thresholds_from_config()

        self.calibration_seconds = max(0.1, float(calibration_seconds))
        self.adaptation_alpha = max(0.0, min(float(adaptation_alpha), 1.0))
        self._neutral_samples: List[Dict[str, float]] = []
        self._neutral_baseline: Dict[str, float] = self._empty_metric_map()
        self._calibrated = False
        self._calibration_started_at: Optional[float] = None
        self._gesture_counters: Dict[str, int] = {g: 0 for g in self.GESTURE_DEBOUNCE_FRAMES}

    def _load_thresholds_from_config(self) -> FacialGestureThresholds:
        config_path = Path("config") / "user_settings.json"
        manager = ConfigManager(config_path)

        try:
            config = manager.load_merged()
        except Exception:
            return FacialGestureThresholds()

        profile_name = config.get("active_profile") or config.get("profile") or "navegacion"
        profiles = config.get("profiles", {}) if isinstance(config, dict) else {}
        profile = profiles.get(profile_name, {}) if isinstance(profiles, dict) else {}

        gesture_thresholds = dict(config.get("gesture_thresholds", {}) or {})
        if isinstance(profile, dict):
            gesture_thresholds.update(profile.get("gesture_thresholds", {}))

        return FacialGestureThresholds(
            mouth_pucker=float(gesture_thresholds.get("mouth_pucker", FacialGestureThresholds.mouth_pucker)),
            mouth_open=float(gesture_thresholds.get("mouth_open", FacialGestureThresholds.mouth_open)),
            mouth_funnel=float(gesture_thresholds.get("mouth_funnel", FacialGestureThresholds.mouth_funnel)),
            brow_raise=float(gesture_thresholds.get("brow_raise", FacialGestureThresholds.brow_raise)),
            brow_frown=float(gesture_thresholds.get("brow_frown", FacialGestureThresholds.brow_frown)),
            eye_blink=float(gesture_thresholds.get("eye_blink", FacialGestureThresholds.eye_blink)),
            eye_wide=float(gesture_thresholds.get("eye_wide", FacialGestureThresholds.eye_wide)),
            nose_sneer=float(gesture_thresholds.get("nose_sneer", FacialGestureThresholds.nose_sneer)),
            smile=float(gesture_thresholds.get("smile", FacialGestureThresholds.smile)),
            smile_left=float(gesture_thresholds.get("smile_left", FacialGestureThresholds.smile_left)),
            smile_right=float(gesture_thresholds.get("smile_right", FacialGestureThresholds.smile_right)),
            mouth_conflict_margin=float(
                gesture_thresholds.get("mouth_conflict_margin", FacialGestureThresholds.mouth_conflict_margin)
            ),
        )

    def reset_calibration(self):
        self._neutral_samples = []
        self._neutral_baseline = self._empty_metric_map()
        self._calibrated = False
        self._calibration_started_at = None
        for k in self._gesture_counters:
            self._gesture_counters[k] = 0

    def is_calibrated(self) -> bool:
        return self._calibrated

    def _empty_metric_map(self) -> Dict[str, float]:
        return {k: 0.0 for k in NEUTRAL_METRIC_FIELDS}

    def _normalize_face_data(self, face_data: dict) -> Dict[str, float]:
        """Normaliza la entrada `face_data` (blendshapes o métricas directas) a un mapa plano."""
        if not isinstance(face_data, dict):
            return self._empty_metric_map()

        blendshapes = face_data.get("blendshapes", {}) if isinstance(face_data, dict) else {}
        if not isinstance(blendshapes, dict):
            blendshapes = {}

        return {
            "mouth_pucker_score": float(face_data.get("mouth_pucker_score", blendshapes.get("mouthPucker", 0.0))),
            "jaw_open_score": float(face_data.get("jaw_open_score", blendshapes.get("jawOpen", 0.0))),
            "mouth_funnel_score": float(face_data.get("mouth_funnel_score", blendshapes.get("mouthFunnel", 0.0))),
            "mouth_ratio": float(face_data.get("mouth_ratio", 0.0)),
            "brow_ratio": float(face_data.get("brow_ratio", 0.0)),
            "smile_left": float(face_data.get("smile_left", blendshapes.get("mouthSmileLeft", 0.0))),
            "smile_right": float(face_data.get("smile_right", blendshapes.get("mouthSmileRight", 0.0))),
            "brow_inner_up": float(face_data.get("brow_inner_up", blendshapes.get("browInnerUp", 0.0))),
            "brow_down_left": float(face_data.get("brow_down_left", blendshapes.get("browDownLeft", 0.0))),
            "brow_down_right": float(face_data.get("brow_down_right", blendshapes.get("browDownRight", 0.0))),
            "eye_blink_left": float(face_data.get("eye_blink_left", blendshapes.get("eyeBlinkLeft", 0.0))),
            "eye_blink_right": float(face_data.get("eye_blink_right", blendshapes.get("eyeBlinkRight", 0.0))),
            "eye_squint_left": float(face_data.get("eye_squint_left", blendshapes.get("eyeSquintLeft", 0.0))),
            "eye_squint_right": float(face_data.get("eye_squint_right", blendshapes.get("eyeSquintRight", 0.0))),
            "eye_wide_left": float(face_data.get("eye_wide_left", blendshapes.get("eyeWideLeft", 0.0))),
            "eye_wide_right": float(face_data.get("eye_wide_right", blendshapes.get("eyeWideRight", 0.0))),
            "nose_sneer_left": float(face_data.get("nose_sneer_left", blendshapes.get("noseSneerLeft", 0.0))),
            "nose_sneer_right": float(face_data.get("nose_sneer_right", blendshapes.get("noseSneerRight", 0.0))),
        }

    def _collect_neutral_sample(self, metrics: Dict[str, float]):
        self._neutral_samples.append(metrics)
        if self._calibration_started_at is None:
            self._calibration_started_at = time.monotonic()

        elapsed = time.monotonic() - self._calibration_started_at
        if elapsed >= self.calibration_seconds:
            self._neutral_baseline = {
                field: float(median(sample[field] for sample in self._neutral_samples))
                for field in NEUTRAL_METRIC_FIELDS
            }
            self._calibrated = True

    def _neutral_value(self, field: str) -> float:
        return float(self._neutral_baseline.get(field, 0.0))

    def _adapt_neutral_baseline(self, metrics: Dict[str, float]):
        if not self._calibrated or self.adaptation_alpha <= 0:
            return

        alpha = self.adaptation_alpha
        for field in NEUTRAL_METRIC_FIELDS:
            current = float(metrics.get(field, 0.0))
            baseline = float(self._neutral_baseline.get(field, 0.0))
            self._neutral_baseline[field] = baseline * (1.0 - alpha) + current * alpha

    def _scaled_threshold(self, gesture_name: str, base_threshold: float) -> float:
        scale = self.GESTURE_SCALES.get(gesture_name, 1.0)
        return float(base_threshold) * float(scale)

    @staticmethod
    def _confidence_from_margin(score: float, threshold: float) -> float:
        threshold = max(float(threshold), 0.001)
        normalized = float(score) / threshold
        return max(0.0, min(1.0, normalized))

    @staticmethod
    def _ratio(delta: float, threshold: float) -> float:
        threshold = max(float(threshold), 0.001)
        return max(0.0, float(delta) / threshold)

    def _score_payload(self, score: float, threshold: float, active_raw: bool, *, detail: str = "") -> Dict[str, float | bool | str]:
        score = float(score)
        threshold = float(threshold)
        return {
            "score": score,
            "threshold": threshold,
            "margin": score - threshold,
            "confidence": self._confidence_from_margin(score, threshold),
            "active_raw": bool(active_raw),
            "detail": detail,
        }

    def _empty_gesture_scores(self) -> Dict[str, Dict[str, float | bool | str]]:
        return {gesture_name: self._score_payload(0.0, 1.0, False) for gesture_name in GESTURE_NAMES}

    def _base_result(self, *, has_face: bool, calibrating: bool, calibration_progress: float):
        result = {
            "has_face": has_face,
            "calibrating": calibrating,
            "calibration_progress": calibration_progress,
            "gesture_scores": self._empty_gesture_scores(),
        }
        for gesture_name in GESTURE_NAMES:
            result[gesture_name] = False
        return result

    def calibration_progress(self) -> float:
        if self._calibrated:
            return 1.0
        if self._calibration_started_at is None:
            return 0.0
        elapsed = time.monotonic() - self._calibration_started_at
        return max(0.0, min(1.0, elapsed / float(self.calibration_seconds)))

    def detect(self, face_data: Optional[dict]) -> dict:
        if face_data is None:
            self.reset_calibration()
            return self._base_result(
                has_face=False,
                calibrating=not self._calibrated,
                calibration_progress=self.calibration_progress(),
            )

        metrics = self._normalize_face_data(face_data)

        if not self._calibrated:
            self._collect_neutral_sample(metrics)
            if self._calibrated:
                return self._base_result(has_face=True, calibrating=False, calibration_progress=1.0)

            return self._base_result(
                has_face=True,
                calibrating=True,
                calibration_progress=self.calibration_progress(),
            )

        gesture_scores = self._empty_gesture_scores()

        mouth_open_threshold = self._scaled_threshold("mouth_open", self.thresholds.mouth_open)
        mouth_open_funnel_limit = self._scaled_threshold(
            "mouth_open", self.thresholds.mouth_funnel - self.thresholds.mouth_conflict_margin
        )
        mouth_open_jaw_delta = metrics.get("jaw_open_score", 0.0) - self._neutral_value("jaw_open_score")
        mouth_open_ratio_delta = metrics.get("mouth_ratio", 0.0) - self._neutral_value("mouth_ratio")
        mouth_open_funnel_delta = metrics.get("mouth_funnel_score", 0.0) - self._neutral_value("mouth_funnel_score")
        mouth_open_blend_score = self._ratio(mouth_open_jaw_delta, mouth_open_threshold)
        mouth_open_geometry_score = self._ratio(mouth_open_ratio_delta, self.GEOMETRY_DELTAS["mouth_open"])
        mouth_open_score = max(mouth_open_blend_score, mouth_open_geometry_score)
        mouth_open = (
            (mouth_open_blend_score >= 1.0 and mouth_open_funnel_delta < mouth_open_funnel_limit)
            or mouth_open_geometry_score >= 1.0
        )

        mouth_o_funnel_threshold = self._scaled_threshold("mouth_o", self.thresholds.mouth_funnel)
        mouth_o_jaw_threshold = self._scaled_threshold(
            "mouth_o", self.thresholds.mouth_open - self.thresholds.mouth_conflict_margin
        )
        mouth_o_funnel_delta = metrics.get("mouth_funnel_score", 0.0) - self._neutral_value("mouth_funnel_score")
        mouth_o_jaw_delta = metrics.get("jaw_open_score", 0.0) - self._neutral_value("jaw_open_score")
        mouth_o_funnel_score = self._ratio(mouth_o_funnel_delta, mouth_o_funnel_threshold)
        mouth_o_jaw_score = self._ratio(mouth_o_jaw_delta, mouth_o_jaw_threshold)
        mouth_o_score = min(mouth_o_funnel_score, mouth_o_jaw_score)
        mouth_o = mouth_o_score >= 1.0

        left_eye_blink_delta = metrics.get("eye_blink_left", 0.0) - self._neutral_value("eye_blink_left")
        right_eye_blink_delta = metrics.get("eye_blink_right", 0.0) - self._neutral_value("eye_blink_right")
        blink_threshold = self._scaled_threshold("eye_blink", self.thresholds.eye_blink)
        blink_min_delta = float(self.MIN_ABSOLUTE_DELTAS["eye_blink"])
        other_eye_max_delta = max(0.02, blink_threshold * 0.5)

        left_eye_blink_active = (
            left_eye_blink_delta >= blink_threshold
            and left_eye_blink_delta >= blink_min_delta
            and right_eye_blink_delta <= other_eye_max_delta
        )
        right_eye_blink_active = (
            right_eye_blink_delta >= blink_threshold
            and right_eye_blink_delta >= blink_min_delta
            and left_eye_blink_delta <= other_eye_max_delta
        )
        # Blink only counts as a one-eye wink; simultaneous closure is ignored.
        eye_blink_active = left_eye_blink_active or right_eye_blink_active

        eye_blink_score = max(
            self._ratio(left_eye_blink_delta, blink_threshold),
            self._ratio(right_eye_blink_delta, blink_threshold),
        )

        mouth_pucker_threshold = max(
            self._neutral_value("mouth_pucker_score") + 0.25,
            self._scaled_threshold("mouth_pucker", self.thresholds.mouth_pucker),
        )
        mouth_pucker_score_value = metrics.get("mouth_pucker_score", 0.0)
        mouth_pucker_score = self._ratio(mouth_pucker_score_value, mouth_pucker_threshold)
        mouth_pucker_support = (
            metrics.get("mouth_ratio", 1.0) <= self._neutral_value("mouth_ratio") - 0.005
            or metrics.get("mouth_funnel_score", 0.0) >= self._neutral_value("mouth_funnel_score") + 0.05
        )

        smile_left_delta = metrics.get("smile_left", 0.0) - self._neutral_value("smile_left")
        smile_right_delta = metrics.get("smile_right", 0.0) - self._neutral_value("smile_right")
        smile_left_threshold = self._scaled_threshold("smile_left", self.thresholds.smile_left)
        smile_right_threshold = self._scaled_threshold("smile_right", self.thresholds.smile_right)
        smile_left_score = self._ratio(smile_left_delta, smile_left_threshold)
        smile_right_score = self._ratio(smile_right_delta, smile_right_threshold)
        smile_score = min(smile_left_score, smile_right_score)

        brow_raise_threshold = self._scaled_threshold("brow_raise", self.thresholds.brow_raise)
        brow_raise_inner_delta = metrics.get("brow_inner_up", 0.0) - self._neutral_value("brow_inner_up")
        brow_raise_ratio_delta = metrics.get("brow_ratio", 0.0) - self._neutral_value("brow_ratio")
        brow_raise_score = max(
            self._ratio(brow_raise_inner_delta, brow_raise_threshold),
            self._ratio(brow_raise_ratio_delta, self.GEOMETRY_DELTAS["brow_raise"]),
        )

        brow_frown_threshold = self._scaled_threshold("brow_frown", self.thresholds.brow_frown)
        brow_frown_left_delta = metrics.get("brow_down_left", 0.0) - self._neutral_value("brow_down_left")
        brow_frown_right_delta = metrics.get("brow_down_right", 0.0) - self._neutral_value("brow_down_right")
        brow_frown_score = max(
            self._ratio(brow_frown_left_delta, brow_frown_threshold),
            self._ratio(brow_frown_right_delta, brow_frown_threshold),
        )

        eye_wide_threshold = self._scaled_threshold("eye_wide", self.thresholds.eye_wide)
        eye_wide_left_delta = metrics.get("eye_wide_left", 0.0) - self._neutral_value("eye_wide_left")
        eye_wide_right_delta = metrics.get("eye_wide_right", 0.0) - self._neutral_value("eye_wide_right")
        eye_wide_score = max(
            self._ratio(eye_wide_left_delta, eye_wide_threshold),
            self._ratio(eye_wide_right_delta, eye_wide_threshold),
        )

        nose_sneer_threshold = self._scaled_threshold("nose_sneer", self.thresholds.nose_sneer)
        nose_sneer_left_delta = metrics.get("nose_sneer_left", 0.0) - self._neutral_value("nose_sneer_left")
        nose_sneer_right_delta = metrics.get("nose_sneer_right", 0.0) - self._neutral_value("nose_sneer_right")
        nose_sneer_score = max(
            self._ratio(nose_sneer_left_delta, nose_sneer_threshold),
            self._ratio(nose_sneer_right_delta, nose_sneer_threshold),
        )

        raw_gestures = {
            # mouth_pucker requires both a high blendshape _and_ a supporting geometry change
            "mouth_pucker": mouth_pucker_score >= 1.0 and mouth_pucker_support,
            "mouth_open": mouth_open,
            "mouth_o": mouth_o,
            "smile_left": smile_left_score >= 1.0,
            "smile_right": smile_right_score >= 1.0,
            # brow_raise must come from eyebrow motion, not from eyelid closure.
            # If blink/squint is active, ignore brow_raise to avoid false positives.
            "brow_raise": not eye_blink_active and brow_raise_score >= 1.0,
            "brow_frown": brow_frown_score >= 1.0,
            "eye_blink": eye_blink_active,
            "eye_wide": eye_wide_score >= 1.0,
            "nose_sneer": nose_sneer_score >= 1.0,
        }

        gesture_scores.update(
            {
                "mouth_pucker": self._score_payload(
                    mouth_pucker_score,
                    1.0,
                    raw_gestures["mouth_pucker"],
                    detail="mouthPucker + geometry",
                ),
                "mouth_open": self._score_payload(mouth_open_score, 1.0, raw_gestures["mouth_open"], detail="jawOpen|mouthRatio"),
                "mouth_o": self._score_payload(mouth_o_score, 1.0, raw_gestures["mouth_o"], detail="mouthFunnel+jawOpen"),
                "smile_left": self._score_payload(smile_left_score, 1.0, raw_gestures["smile_left"], detail="mouthSmileLeft"),
                "smile_right": self._score_payload(smile_right_score, 1.0, raw_gestures["smile_right"], detail="mouthSmileRight"),
                "smile": self._score_payload(smile_score, 1.0, False, detail="left+right smile"),
                "brow_raise": self._score_payload(brow_raise_score, 1.0, raw_gestures["brow_raise"], detail="browInnerUp|browRatio"),
                "brow_frown": self._score_payload(brow_frown_score, 1.0, raw_gestures["brow_frown"], detail="browDown"),
                "eye_blink": self._score_payload(eye_blink_score, 1.0, raw_gestures["eye_blink"], detail="one-eye blink"),
                "eye_wide": self._score_payload(eye_wide_score, 1.0, raw_gestures["eye_wide"], detail="eyeWide"),
                "nose_sneer": self._score_payload(nose_sneer_score, 1.0, raw_gestures["nose_sneer"], detail="noseSneer"),
            }
        )

        # Apply minimum absolute deltas where configured
        for name, min_delta in self.MIN_ABSOLUTE_DELTAS.items():
            if raw_gestures.get(name):
                if name == "brow_raise":
                    delta = max(
                        metrics.get("brow_inner_up", 0.0) - self._neutral_value("brow_inner_up"),
                        metrics.get("brow_ratio", 0.0) - self._neutral_value("brow_ratio"),
                    )
                elif name == "mouth_pucker":
                    delta = metrics.get("mouth_pucker_score", 0.0) - self._neutral_value("mouth_pucker_score")
                elif name == "eye_blink":
                    delta = max(left_eye_blink_delta, right_eye_blink_delta)
                else:
                    delta = metrics.get(f"{name}_score", 0.0) - self._neutral_value(f"{name}_score")

                if delta < float(min_delta):
                    raw_gestures[name] = False

        for name, is_active in raw_gestures.items():
            if name in gesture_scores:
                gesture_scores[name]["active_raw"] = bool(is_active)

        # Debounce: require N consecutive frames
        gestures = {"has_face": True, "calibrating": False, "calibration_progress": 1.0}
        for name, val in raw_gestures.items():
            # increment when True, decrement when False (prevents instant reset/flicker)
            cur = self._gesture_counters.get(name, 0)
            if val:
                cur = cur + 1
            else:
                cur = max(0, cur - 1)
            self._gesture_counters[name] = cur

            required = self.GESTURE_DEBOUNCE_FRAMES.get(name, 1)
            gestures[name] = cur >= required

        # Treat the bilateral smile as the conjunction of the two confirmed side smiles.
        # This lets `smile` fire even when left/right reach threshold on adjacent frames.
        gestures["smile"] = bool(gestures.get("smile_left")) and bool(gestures.get("smile_right"))
        gesture_scores["smile"]["active_raw"] = bool(raw_gestures.get("smile_left")) and bool(raw_gestures.get("smile_right"))
        gesture_scores["smile"]["confidence"] = min(
            float(gesture_scores["smile_left"]["confidence"]),
            float(gesture_scores["smile_right"]["confidence"]),
        )
        gesture_scores["smile"]["margin"] = min(
            float(gesture_scores["smile_left"]["margin"]),
            float(gesture_scores["smile_right"]["margin"]),
        )
        gestures["gesture_scores"] = gesture_scores

        if not any(
            value
            for key, value in gestures.items()
            if key not in {"has_face", "calibrating", "calibration_progress", "gesture_scores"}
        ):
            self._adapt_neutral_baseline(metrics)

        return gestures

    def calibrate_gesture_from_samples(self, gesture_name: str, samples: List[Dict[str, float]]) -> float:
        """Given a list of normalized metric samples where the user performed `gesture_name`,
        compute a recommended base threshold value to store in configuration.

        Returns a float threshold (same units expected by `FacialGestureThresholds`).
        """
        if not samples:
            raise ValueError("No samples provided for calibration")

        # map gestures to metric fields that best represent them
        gesture_fields = {
            # brow_raise should be calibrated from eyebrow elevation only.
            "brow_raise": ["brow_inner_up"],
            "mouth_pucker": ["mouth_pucker_score"],
            "mouth_open": ["jaw_open_score", "mouth_ratio"],
            "mouth_o": ["mouth_funnel_score", "jaw_open_score"],
            "smile": ["smile_left", "smile_right", "mouth_ratio"],
            "smile_left": ["smile_left"],
            "smile_right": ["smile_right"],
            "brow_frown": ["brow_down_left", "brow_down_right"],
            "eye_blink": ["eye_blink_left", "eye_blink_right"],
            "eye_wide": ["eye_wide_left", "eye_wide_right"],
            "nose_sneer": ["nose_sneer_left", "nose_sneer_right"],
        }

        fields = gesture_fields.get(gesture_name, [])
        if not fields:
            # fallback: use any numeric field's delta
            fields = list(NEUTRAL_METRIC_FIELDS)

        # compute median delta per field relative to neutral baseline
        deltas = []
        for f in fields:
            vals = [s.get(f, 0.0) - self._neutral_value(f) for s in samples]
            # focus on positive deltas
            pos = [v for v in vals if v > 0]
            if not pos:
                continue
            deltas.append(median(pos))

        if not deltas:
            # nothing rose above baseline; return a conservative small threshold
            return float(getattr(FacialGestureThresholds, gesture_name, 0.2))

        # use the largest representative delta as gesture magnitude
        gesture_magnitude = max(deltas)

        # derive a recommended base threshold: fraction of observed magnitude
        # tuned to be slightly below observed peak so real gesture triggers but small noise doesn't
        recommended = max(0.01, float(gesture_magnitude) * 0.6)

        return float(recommended)

    def save_gesture_threshold_to_user_config(self, gesture_name: str, threshold_value: float):
        """Persist a computed gesture threshold to `config/user_settings.json` under `gesture_thresholds`.

        This will create or update the user's file only; defaults remain intact.
        """
        cfg_path = Path("config") / "user_settings.json"
        manager = ConfigManager(cfg_path)
        current = manager.load()
        if not isinstance(current, dict):
            current = {}

        gt = current.get("gesture_thresholds", {}) if isinstance(current.get("gesture_thresholds", {}), dict) else {}
        gt[gesture_name] = float(threshold_value)
        current["gesture_thresholds"] = gt
        manager.save(current)
