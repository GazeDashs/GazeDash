"""Mapeo de gestos detectados a acciones del sistema."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from config.config_manager import ConfigManager


DEFAULT_GESTURE_MAP = {
    "blink": {"type": "action", "name": "click"}
}


def normalize_gesture_name(gesture_name: str) -> str:
    gesture_key = gesture_name.strip().lower().replace("-", "_").replace(" ", "_")
    if gesture_key == "mouthpucker":
        return "mouth_pucker"
    return gesture_key


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    if config_path is None:
        config_path = Path("config") / "user_settings.json"

    default_path = Path("config") / "default_config.json"
    legacy_default_path = Path("config") / "default_Config.json"

    config_source = default_path if default_path.exists() else legacy_default_path
    if config_source.exists():
        return ConfigManager(config_path, config_source).load_merged()

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    return {}


def get_active_profile(config: Dict[str, Any]) -> Dict[str, Any]:
    active_profile = config.get("active_profile", "navegacion")
    profiles = config.get("profiles", {})
    if not isinstance(profiles, dict):
        return {}

    profile = profiles.get(active_profile, {})
    return profile if isinstance(profile, dict) else {}


def map_gesture(gesture_name: str, config: Optional[Dict[str, Any]] = None):
    gesture_key = normalize_gesture_name(gesture_name)

    if config is None:
        config = load_config()

    profile = get_active_profile(config)
    gesture_actions = profile.get("gesture_actions", {})
    if not isinstance(gesture_actions, dict):
        gesture_actions = {}

    action = gesture_actions.get(gesture_key)
    if action is not None:
        return action

    return DEFAULT_GESTURE_MAP.get(gesture_key)
