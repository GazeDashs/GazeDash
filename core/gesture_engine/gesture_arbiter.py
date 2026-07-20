"""Arbitraje de gestos para reducir activaciones confundidas.

El detector facial devuelve gestos booleanos independientes. Esta capa resuelve
conflictos entre gestos parecidos antes de ejecutar acciones del sistema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional


META_KEYS = {"has_face", "calibrating", "calibration_progress", "gesture_scores"}


DEFAULT_CONFLICT_GROUPS = {
    "mouth": ("mouth_pucker", "mouth_o", "mouth_open"),
    "smile": ("smile", "smile_right", "smile_left"),
    "eyes": ("eye_wide", "eye_blink"),
    "brows": ("brow_raise", "brow_frown"),
}


DEFAULT_PRIORITIES = {
    "mouth_pucker": 30,
    "mouth_o": 20,
    "mouth_open": 10,
    "smile": 30,
    "smile_right": 20,
    "smile_left": 20,
    "eye_wide": 20,
    "eye_blink": 10,
    "brow_raise": 20,
    "brow_frown": 20,
    "nose_sneer": 10,
}


@dataclass
class GestureArbiter:
    """Selecciona gestos confiables a partir de gestos crudos.

    - Permite como maximo un gesto activo por grupo conflictivo.
    - Prefiere gestos que tengan accion configurada.
    - Exige estabilidad por algunos frames cuando un ganador cambia.
    """

    activation_frames: int = 2
    hold_activation_frames: int = 1
    release_frames: int = 2
    hold_release_frames: int = 1
    mode: str = "realtime"
    realtime_confidence: float = 0.85
    realtime_margin: float = 0.15
    realtime_action_types: tuple[str, ...] = ("hotkey", "key_hold")
    enabled: bool = True
    conflict_groups: Dict[str, tuple[str, ...]] = field(default_factory=lambda: dict(DEFAULT_CONFLICT_GROUPS))
    priorities: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_PRIORITIES))
    activation_frames_by_gesture: Dict[str, int] = field(default_factory=dict)
    release_frames_by_gesture: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        self.activation_frames = max(1, int(self.activation_frames))
        self.hold_activation_frames = max(1, int(self.hold_activation_frames))
        self.release_frames = max(1, int(self.release_frames))
        self.hold_release_frames = max(1, int(self.hold_release_frames))
        self.mode = str(self.mode or "balanced").strip().lower()
        self.realtime_confidence = max(0.0, min(float(self.realtime_confidence), 1.0))
        self.realtime_margin = float(self.realtime_margin)
        self.realtime_action_types = tuple(str(action_type) for action_type in self.realtime_action_types)
        self.activation_frames_by_gesture = self._normalize_frame_overrides(self.activation_frames_by_gesture)
        self.release_frames_by_gesture = self._normalize_frame_overrides(self.release_frames_by_gesture)
        self._candidates: dict[str, Optional[str]] = {}
        self._candidate_counts: dict[str, int] = {}
        self._release_counts: dict[str, int] = {}
        self._active_by_group: dict[str, Optional[str]] = {}
        self._current_realtime_candidates: set[str] = set()
        self._gesture_to_group = {
            gesture_name: group_name
            for group_name, gestures in self.conflict_groups.items()
            for gesture_name in gestures
        }
        self.last_debug: Dict[str, Any] = self._empty_debug(reason="init")

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]]):
        settings = config.get("gesture_arbitration", {}) if isinstance(config, dict) else {}
        if not isinstance(settings, dict):
            settings = {}

        return cls(
            enabled=bool(settings.get("enabled", True)),
            activation_frames=int(settings.get("activation_frames", 2)),
            hold_activation_frames=int(settings.get("hold_activation_frames", 1)),
            release_frames=int(settings.get("release_frames", 2)),
            hold_release_frames=int(settings.get("hold_release_frames", 1)),
            mode=str(settings.get("mode", "realtime")),
            realtime_confidence=float(settings.get("realtime_confidence", 0.85)),
            realtime_margin=float(settings.get("realtime_margin", 0.15)),
            realtime_action_types=cls._read_str_tuple(
                settings.get("realtime_action_types", ("hotkey", "key_hold"))
            ),
            priorities=cls._merge_int_mapping(DEFAULT_PRIORITIES, settings.get("priorities")),
            activation_frames_by_gesture=cls._read_int_mapping(settings.get("activation_frames_by_gesture")),
            release_frames_by_gesture=cls._read_int_mapping(settings.get("release_frames_by_gesture")),
        )

    @staticmethod
    def _read_str_tuple(value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        if not isinstance(value, (list, tuple)):
            return ()
        return tuple(str(item) for item in value if str(item).strip())

    @staticmethod
    def _read_int_mapping(value: Any) -> Dict[str, int]:
        if not isinstance(value, dict):
            return {}

        parsed = {}
        for key, raw_value in value.items():
            try:
                parsed[str(key)] = int(raw_value)
            except (TypeError, ValueError):
                continue
        return parsed

    @classmethod
    def _merge_int_mapping(cls, base: Dict[str, int], override: Any) -> Dict[str, int]:
        merged = dict(base)
        merged.update(cls._read_int_mapping(override))
        return merged

    @staticmethod
    def _normalize_frame_overrides(value: Dict[str, int]) -> Dict[str, int]:
        return {str(key): max(1, int(raw_value)) for key, raw_value in value.items()}

    def reset(self):
        self._candidates.clear()
        self._candidate_counts.clear()
        self._release_counts.clear()
        self._active_by_group.clear()
        self._current_realtime_candidates.clear()
        self.last_debug = self._empty_debug(reason="reset")

    def filter(
        self,
        gestures: Optional[Dict[str, Any]],
        *,
        action_resolver: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(gestures, dict):
            self.reset()
            self.last_debug = self._empty_debug(reason="invalid_input")
            return {}

        if not self.enabled:
            active_names = self._active_gesture_names(gestures)
            self.last_debug = {
                **self._empty_debug(reason="disabled"),
                "raw_active": active_names,
                "active": active_names,
            }
            return dict(gestures)

        filtered = {key: False for key in gestures}
        for key in META_KEYS:
            if key in gestures:
                filtered[key] = gestures[key]

        if not gestures.get("has_face") or gestures.get("calibrating"):
            self.reset()
            self.last_debug = {
                **self._empty_debug(reason="no_face" if not gestures.get("has_face") else "calibrating"),
                "meta": {key: gestures.get(key) for key in META_KEYS if key in gestures},
            }
            return filtered

        gesture_scores = gestures.get("gesture_scores", {}) if isinstance(gestures.get("gesture_scores"), dict) else {}
        active_names = self._active_gesture_names(gestures)
        realtime_names = self._realtime_candidates(gestures, action_resolver, gesture_scores)
        self._current_realtime_candidates = set(realtime_names)
        active_names = list(dict.fromkeys(active_names + realtime_names))

        grouped: dict[str, list[str]] = {group_name: [] for group_name in self.conflict_groups}
        ungrouped = []
        for gesture_name in active_names:
            group_name = self._gesture_to_group.get(gesture_name)
            if group_name:
                grouped.setdefault(group_name, []).append(gesture_name)
            else:
                ungrouped.append(gesture_name)

        debug_groups = {}
        for group_name, candidates in grouped.items():
            winner = self._choose_winner(candidates, action_resolver, gesture_scores)
            active_winner = self._stable_winner(group_name, winner, action_resolver)
            if active_winner:
                filtered[active_winner] = True
            debug_groups[group_name] = self._group_debug(
                group_name,
                candidates,
                winner,
                active_winner,
                action_resolver,
                gesture_scores,
            )

        for gesture_name in ungrouped:
            filtered[gesture_name] = True

        filtered_active = self._active_gesture_names(filtered)
        self.last_debug = {
            "reason": "ok",
            "meta": {key: gestures.get(key) for key in META_KEYS if key in gestures},
            "raw_active": active_names,
            "realtime_active": realtime_names,
            "active": filtered_active,
            "groups": debug_groups,
            "ungrouped": ungrouped,
        }
        return filtered

    def _realtime_candidates(
        self,
        gestures: Dict[str, Any],
        action_resolver: Optional[Callable[[str], Optional[Dict[str, Any]]]],
        gesture_scores: Dict[str, Any],
    ) -> list[str]:
        if self.mode != "realtime" or action_resolver is None:
            return []

        candidates = []
        for gesture_name, score_info in gesture_scores.items():
            if gesture_name in META_KEYS or gestures.get(gesture_name):
                continue
            if not self._passes_realtime_score(score_info):
                continue
            action = action_resolver(gesture_name)
            if not isinstance(action, dict):
                continue
            if action.get("type") not in self.realtime_action_types:
                continue
            candidates.append(gesture_name)
        return candidates

    def _passes_realtime_score(self, score_info: Any) -> bool:
        if not isinstance(score_info, dict):
            return False
        if not bool(score_info.get("active_raw")):
            return False
        confidence, margin = self._score_rank_values(score_info)
        return confidence >= self.realtime_confidence and margin >= self.realtime_margin

    @staticmethod
    def _empty_debug(reason: str) -> Dict[str, Any]:
        return {
            "reason": reason,
            "meta": {},
            "raw_active": [],
            "realtime_active": [],
            "active": [],
            "groups": {},
            "ungrouped": [],
        }

    @staticmethod
    def _active_gesture_names(gestures: Dict[str, Any]) -> list[str]:
        return [
            gesture_name
            for gesture_name, is_active in gestures.items()
            if gesture_name not in META_KEYS and bool(is_active)
        ]

    def _group_debug(
        self,
        group_name: str,
        candidates: list[str],
        winner: Optional[str],
        active_winner: Optional[str],
        action_resolver: Optional[Callable[[str], Optional[Dict[str, Any]]]],
        gesture_scores: Dict[str, Any],
    ) -> Dict[str, Any]:
        rejected = [gesture_name for gesture_name in candidates if gesture_name != active_winner]
        return {
            "candidates": list(candidates),
            "candidate": winner,
            "active": active_winner,
            "rejected": rejected,
            "scores": {
                gesture_name: self._compact_score(gesture_scores.get(gesture_name))
                for gesture_name in candidates
            },
            "candidate_frames": self._candidate_counts.get(group_name, 0),
            "release_frames": self._release_counts.get(group_name, 0),
            "required_activation_frames": self._required_frames(winner, action_resolver) if winner else 0,
            "required_release_frames": self._required_release_frames(active_winner, action_resolver)
            if active_winner
            else 0,
        }

    def _choose_winner(
        self,
        candidates: Iterable[str],
        action_resolver: Optional[Callable[[str], Optional[Dict[str, Any]]]],
        gesture_scores: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        candidate_list = list(candidates)
        if not candidate_list:
            return None

        def rank(gesture_name: str):
            action = action_resolver(gesture_name) if action_resolver else None
            mapped_bonus = 10000 if action else 0
            score_info = (gesture_scores or {}).get(gesture_name)
            confidence, margin = self._score_rank_values(score_info)
            confidence_bonus = int(confidence * 1000)
            margin_bonus = int(max(-1.0, min(3.0, margin)) * 100)
            return (
                mapped_bonus,
                confidence_bonus,
                margin_bonus,
                int(self.priorities.get(gesture_name, 0)),
                gesture_name,
            )

        return max(candidate_list, key=rank)

    @staticmethod
    def _score_rank_values(score_info: Any) -> tuple[float, float]:
        if not isinstance(score_info, dict):
            return 0.0, 0.0
        try:
            confidence = float(score_info.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            margin = float(score_info.get("margin", 0.0))
        except (TypeError, ValueError):
            margin = 0.0
        return confidence, margin

    @classmethod
    def _compact_score(cls, score_info: Any) -> Dict[str, Any]:
        if not isinstance(score_info, dict):
            return {"confidence": 0.0, "margin": 0.0, "score": 0.0}
        confidence, margin = cls._score_rank_values(score_info)
        try:
            score = float(score_info.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        return {
            "score": round(score, 3),
            "confidence": round(confidence, 3),
            "margin": round(margin, 3),
            "detail": score_info.get("detail", ""),
        }

    def _stable_winner(
        self,
        group_name: str,
        winner: Optional[str],
        action_resolver: Optional[Callable[[str], Optional[Dict[str, Any]]]],
    ) -> Optional[str]:
        if winner is None:
            self._candidates.pop(group_name, None)
            self._candidate_counts[group_name] = 0
            active_winner = self._active_by_group.get(group_name)
            if not active_winner:
                self._release_counts[group_name] = 0
                return None

            self._release_counts[group_name] = self._release_counts.get(group_name, 0) + 1
            required_release_frames = self._required_release_frames(active_winner, action_resolver)
            if self._release_counts[group_name] >= required_release_frames:
                self._active_by_group[group_name] = None
                self._release_counts[group_name] = 0
                return None

            return active_winner

        if self._active_by_group.get(group_name) == winner:
            self._release_counts[group_name] = 0
            return winner

        if self._candidates.get(group_name) == winner:
            self._candidate_counts[group_name] = self._candidate_counts.get(group_name, 0) + 1
        else:
            self._candidates[group_name] = winner
            self._candidate_counts[group_name] = 1

        required_frames = self._required_frames(winner, action_resolver)
        if self._candidate_counts[group_name] >= required_frames:
            self._active_by_group[group_name] = winner
            self._release_counts[group_name] = 0
            return winner

        return self._active_by_group.get(group_name)

    def _required_frames(
        self,
        gesture_name: str,
        action_resolver: Optional[Callable[[str], Optional[Dict[str, Any]]]],
    ) -> int:
        if gesture_name in self._current_realtime_candidates:
            return 1

        if gesture_name in self.activation_frames_by_gesture:
            return self.activation_frames_by_gesture[gesture_name]

        action = action_resolver(gesture_name) if action_resolver else None
        if isinstance(action, dict) and action.get("type") == "key_hold":
            return self.hold_activation_frames
        return self.activation_frames

    def _required_release_frames(
        self,
        gesture_name: str,
        action_resolver: Optional[Callable[[str], Optional[Dict[str, Any]]]],
    ) -> int:
        if gesture_name in self.release_frames_by_gesture:
            return self.release_frames_by_gesture[gesture_name]

        action = action_resolver(gesture_name) if action_resolver else None
        if isinstance(action, dict) and action.get("type") == "key_hold":
            return self.hold_release_frames
        return self.release_frames
