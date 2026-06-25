"""Ejecucion de acciones de entrada resueltas por el mapper."""

from typing import Any, Dict, Iterable, Optional


class HotkeyExecutor:
    """Ejecuta acciones por medio de gestos mapeados a hotkeys usando pyautogui."""

    def __init__(self):
        self._pyautogui = None
        self._held_actions: dict[str, tuple[str, ...]] = {}

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
        action_type = action.get("type")
        if action_type in {"hotkey", "key_hold"}:
            return bool(action.get("keys"))
        if action_type in {"mouse_click", "mouse_double_click"}:
            return True
        return False

    def is_hold_action(self, action: Optional[Dict[str, Any]]) -> bool:
        return bool(isinstance(action, dict) and action.get("type") == "key_hold")

    def update_hold(self, action_id: str, action: Optional[Dict[str, Any]], active: bool) -> bool:
        """Mantiene una tecla/combinacion presionada mientras el gesto esta activo."""
        if not self.is_hold_action(action):
            return False

        keys = self._normalize_keys(action.get("keys") if isinstance(action, dict) else None)
        key_tuple = tuple(keys or ())
        if not key_tuple:
            return False

        pyautogui = self._get_pyautogui()
        is_held = action_id in self._held_actions

        if active and not is_held:
            for key in key_tuple:
                pyautogui.keyDown(key)
            self._held_actions[action_id] = key_tuple
            return True

        if not active and is_held:
            self.release_hold(action_id)
            return True

        return False

    def release_hold(self, action_id: str) -> bool:
        keys = self._held_actions.pop(action_id, None)
        if not keys:
            return False

        pyautogui = self._get_pyautogui()
        for key in reversed(keys):
            pyautogui.keyUp(key)
        return True

    def release_all_holds(self) -> bool:
        released = False
        for action_id in list(self._held_actions):
            released = self.release_hold(action_id) or released
        return released

    def execute(self, action: Optional[Dict[str, Any]]) -> bool:
        """Ejecuta una accion de entrada y devuelve True si se disparo."""
        if not self.can_execute(action):
            return False

        action_type = action.get("type")
        if action_type == "key_hold":
            return False

        pyautogui = self._get_pyautogui()

        if action_type == "mouse_click":
            pyautogui.click(button=str(action.get("button") or "left"))
            return True

        if action_type == "mouse_double_click":
            pyautogui.doubleClick(button=str(action.get("button") or "left"))
            return True

        keys = self._normalize_keys(action.get("keys") if isinstance(action, dict) else None)
        if not keys:
            return False

        key_list = tuple(keys)
        if len(key_list) == 1:
            pyautogui.press(key_list[0])
        else:
            pyautogui.hotkey(*key_list)
        return True
