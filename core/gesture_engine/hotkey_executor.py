"""Ejecucion de acciones de hotkey resueltas por el mapper."""

from typing import Any, Dict, Iterable, Optional


class HotkeyExecutor:
    """Ejecuta acciones por medio de gestos mapeados a hotkeys usando pyautogui."""

    def __init__(self):
        self._pyautogui = None

    def _get_pyautogui(self):
        if self._pyautogui is not None:
            return self._pyautogui

        try:
            import pyautogui
        except ImportError as exc:
            raise RuntimeError(
                "pyautogui no esta instalado. Instala la dependencia para poder enviar hotkeys."
            ) from exc

        self._pyautogui = pyautogui
        return pyautogui

    @staticmethod
    def _normalize_keys(keys: Any) -> Optional[Iterable[str]]:
        if keys is None:
            return None
        if isinstance(keys, str):
            normalized = keys.replace("+", ",")
            parsed = [part.strip() for part in normalized.split(",")]
            return [key for key in parsed if key]
        if isinstance(keys, (list, tuple)):
            return [str(key) for key in keys if str(key).strip()]
        return None

    def can_execute(self, action: Optional[Dict[str, Any]]) -> bool:
        if not action or not isinstance(action, dict):
            return False
        return action.get("type") == "hotkey" and bool(action.get("keys"))

    def execute(self, action: Optional[Dict[str, Any]]) -> bool:
        """Ejecuta una accion de hotkey y devuelve True si se disparo."""
        if not self.can_execute(action):
            return False

        keys = self._normalize_keys(action.get("keys") if isinstance(action, dict) else None)
        if not keys:
            return False

        pyautogui = self._get_pyautogui()
        if len(tuple(keys)) == 1:
            pyautogui.press(next(iter(keys)))
        else:
            pyautogui.hotkey(*keys)
        return True