"""Acceso compartido a la configuracion usada por la UI."""

from copy import deepcopy
from pathlib import Path

from config.config_manager import ConfigManager


PROJECT_ROOT = Path(__file__).resolve().parents[1]
USER_SETTINGS_PATH = PROJECT_ROOT / "config" / "user_settings.json"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default_config.json"

GESTURE_THRESHOLD_KEYS = [
    "mouth_pucker",
    "mouth_open",
    "mouth_funnel",
    "smile",
    "smile_left",
    "smile_right",
    "brow_raise",
    "brow_frown",
    "eye_blink",
    "eye_wide",
    "nose_sneer",
    "mouth_conflict_margin",
]

AVAILABLE_GESTURE_NAMES = [
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
]


def load_config():
    manager = ConfigManager(USER_SETTINGS_PATH, DEFAULT_CONFIG_PATH)
    return manager.load_merged()


def save_config(config):
    manager = ConfigManager(USER_SETTINGS_PATH, DEFAULT_CONFIG_PATH)
    manager.save(config)


def get_profiles(config):
    profiles = config.get("profiles", {}) if isinstance(config, dict) else {}
    return profiles if isinstance(profiles, dict) else {}


def get_active_profile_name(config):
    if not isinstance(config, dict):
        return "navegacion"
    return config.get("active_profile") or config.get("profile") or "navegacion"


def get_profile_details(config, profile_name=None):
    profiles = get_profiles(config)
    profile_key = profile_name or get_active_profile_name(config)
    profile = profiles.get(profile_key, {}) if isinstance(profiles, dict) else {}
    if not isinstance(profile, dict):
        profile = {}
    return profile_key, profile


def get_effective_thresholds(config, profile_name=None):
    _, profile = get_profile_details(config, profile_name)
    thresholds = dict(config.get("gesture_thresholds", {}) or {})
    if isinstance(profile, dict):
        thresholds.update(profile.get("gesture_thresholds", {}) or {})
    return thresholds


def set_profile_thresholds(config, profile_name, thresholds):
    updated = deepcopy(config) if isinstance(config, dict) else {}
    profiles = updated.setdefault("profiles", {})
    profile = profiles.setdefault(profile_name, {})
    profile["gesture_thresholds"] = dict(thresholds)
    updated["gesture_thresholds"] = dict(thresholds)
    updated["active_profile"] = profile_name
    return updated

def clone_profile(config, new_profile_name, source_profile_name=None):
    updated = deepcopy(config) if isinstance(config, dict) else {}
    profiles = updated.setdefault("profiles", {})
    source_key = source_profile_name or get_active_profile_name(updated)
    source_profile = profiles.get(source_key, {}) if isinstance(profiles, dict) else {}
    cloned_profile = deepcopy(source_profile) if isinstance(source_profile, dict) else {}
    cloned_profile.setdefault("gesture_thresholds", {})
    cloned_profile.setdefault("gesture_actions", {})
    cloned_profile.setdefault("mouse_settings", {})
    if not cloned_profile.get("display_name"):
        cloned_profile["display_name"] = new_profile_name.replace("_", " ").title()
    profiles[new_profile_name] = cloned_profile
    updated["active_profile"] = new_profile_name
    return updated


def get_profile_mouse_settings(config, profile_name=None):
    _, profile = get_profile_details(config, profile_name)
    defaults = {
        "enabled": True,
        "dead_zone": 25.0,
        "max_speed": 35.0,
        "smoothing": 0.2,
        "center": None,
    }
    if not isinstance(profile, dict):
        return defaults
    profile_settings = profile.get("mouse_settings", {}) if isinstance(profile.get("mouse_settings", {}), dict) else {}
    merged = dict(defaults)
    merged.update(profile_settings)
    return merged


def set_profile_mouse_settings(config, profile_name, mouse_settings):
    updated = deepcopy(config) if isinstance(config, dict) else {}
    profiles = updated.setdefault("profiles", {})
    profile = profiles.setdefault(profile_name, {})
    profile["mouse_settings"] = {
        "enabled": bool(mouse_settings.get("enabled", True)),
        "dead_zone": float(mouse_settings.get("dead_zone", 25.0)),
        "max_speed": float(mouse_settings.get("max_speed", 35.0)),
        "smoothing": float(mouse_settings.get("smoothing", 0.2)),
        "center": list(mouse_settings.get("center")) if mouse_settings.get("center") is not None else None,
    }
    updated["active_profile"] = profile_name
    return updated


def get_profile_actions(config, profile_name=None):
    _, profile = get_profile_details(config, profile_name)
    actions = profile.get("gesture_actions", {}) if isinstance(profile, dict) else {}
    return actions if isinstance(actions, dict) else {}


def get_profile_voice_actions(config, profile_name=None):
    _, profile = get_profile_details(config, profile_name)
    actions = profile.get("voice_actions", {}) if isinstance(profile, dict) else {}
    return actions if isinstance(actions, dict) else {}


def set_profile_voice_action(config, profile_name, command_label, *, keys=None, label=None, action_type="hotkey"):
    updated = deepcopy(config) if isinstance(config, dict) else {}
    profiles = updated.setdefault("profiles", {})
    profile = profiles.setdefault(profile_name, {})
    voice_actions = profile.setdefault("voice_actions", {})

    command_key = str(command_label or "").strip()
    if not command_key:
        return updated

    key_list = list(keys or [])
    if not key_list:
        voice_actions.pop(command_key, None)
        return updated

    voice_actions[command_key] = {
        "type": action_type,
        "keys": key_list,
        "label": label.strip() if isinstance(label, str) and label.strip() else command_key,
    }

    updated["active_profile"] = profile_name
    return updated


def remove_profile_voice_action(config, profile_name, command_label):
    updated = deepcopy(config) if isinstance(config, dict) else {}
    profiles = updated.setdefault("profiles", {})
    profile = profiles.setdefault(profile_name, {})
    voice_actions = profile.setdefault("voice_actions", {})
    command_key = str(command_label or "").strip()
    if command_key:
        voice_actions.pop(command_key, None)
    updated["active_profile"] = profile_name
    return updated


def get_voice_control_settings(config):
    voice_control = config.get("voice_control", {}) if isinstance(config, dict) else {}
    return voice_control if isinstance(voice_control, dict) else {}


def set_voice_control_settings(config, **kwargs):
    updated = deepcopy(config) if isinstance(config, dict) else {}
    voice_control = dict(updated.get("voice_control", {}) or {})
    for key, value in kwargs.items():
        voice_control[key] = value
    updated["voice_control"] = voice_control
    return updated


def parse_hotkey_spec(text):
    if text is None:
        return []

    normalized = str(text).replace("+", ",")
    keys = [part.strip() for part in normalized.split(",")]
    return [key for key in keys if key]


def set_profile_gesture_action(config, profile_name, gesture_name, *, keys=None, label=None, action_type="hotkey"):
    updated = deepcopy(config) if isinstance(config, dict) else {}
    profiles = updated.setdefault("profiles", {})
    profile = profiles.setdefault(profile_name, {})
    gesture_actions = profile.setdefault("gesture_actions", {})

    gesture_key = str(gesture_name or "").strip()
    if not gesture_key:
        return updated

    key_list = list(keys or [])
    if not key_list and action_type not in {"mouse_click", "mouse_double_click"}:
        gesture_actions.pop(gesture_key, None)
        return updated

    action_payload = {
        "type": action_type,
        "label": label.strip() if isinstance(label, str) and label.strip() else gesture_key,
    }
    if action_type in {"mouse_click", "mouse_double_click"}:
        action_payload["button"] = "left"
    else:
        action_payload["keys"] = key_list

    gesture_actions[gesture_key] = action_payload

    updated["active_profile"] = profile_name
    return updated


def remove_profile_gesture_action(config, profile_name, gesture_name):
    updated = deepcopy(config) if isinstance(config, dict) else {}
    profiles = updated.setdefault("profiles", {})
    profile = profiles.setdefault(profile_name, {})
    gesture_actions = profile.setdefault("gesture_actions", {})
    gesture_key = str(gesture_name or "").strip()
    if gesture_key:
        gesture_actions.pop(gesture_key, None)
    updated["active_profile"] = profile_name
    return updated


def set_general_settings(config, *, active_profile=None, camera_index=None, smoothing_alpha=None, gesture_cooldown=None):
    updated = deepcopy(config) if isinstance(config, dict) else {}
    if active_profile is not None:
        updated["active_profile"] = active_profile
    if camera_index is not None:
        updated["camera_index"] = int(camera_index)
    if smoothing_alpha is not None:
        updated["smoothing_alpha"] = float(smoothing_alpha)
    if gesture_cooldown is not None:
        updated["gesture_cooldown"] = float(gesture_cooldown)
    return updated
