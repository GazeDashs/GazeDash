"""Gestor de configuración persistente."""

import json
from pathlib import Path


class ConfigManager:
    def __init__(self, path, default_path=None):
        self.path = Path(path)
        self.default_path = Path(default_path) if default_path is not None else self.path.with_name("default_config.json")

    @staticmethod
    def _read_json(path):
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @classmethod
    def _deep_merge(cls, base, override):
        if not isinstance(base, dict) or not isinstance(override, dict):
            return override

        merged = dict(base)
        for key, value in override.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = cls._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def load_defaults(self):
        return self._read_json(self.default_path)

    def load(self):
        return self._read_json(self.path)

    def load_merged(self):
        return self._deep_merge(self.load_defaults(), self.load())

    def get_profile(self, profile_name=None):
        config = self.load_merged()
        profiles = config.get("profiles", {}) if isinstance(config, dict) else {}

        selected_profile = profile_name or config.get("active_profile") or config.get("profile") or "navegacion"
        profile = profiles.get(selected_profile, {}) if isinstance(profiles, dict) else {}

        return selected_profile, profile

    def save(self, cfg):
        self.path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
