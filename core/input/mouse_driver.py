"""Wrapper centralizado para acciones de mouse (lazy import de pyautogui).

Centraliza el acceso a `pyautogui` para evitar imports dispersos
en módulos individuales y permite manejar errores de dependencia
de forma consistente.
"""

from typing import Optional


class MouseDriver:
    """Driver mínimo para mover y clics usando pyautogui.

    Importa `pyautogui` bajo demanda y lanza un RuntimeError claro
    si no está instalado.
    """

    def __init__(self) -> None:
        self._pyautogui: Optional[object] = None

    def _get_pyautogui(self):
        if self._pyautogui is not None:
            return self._pyautogui

        try:
            import pyautogui
        except Exception as exc:
            raise RuntimeError(
                "pyautogui no está disponible. Instala la dependencia para controlar el cursor."
            ) from exc

        self._pyautogui = pyautogui
        return self._pyautogui

    def move_rel(self, dx: int, dy: int) -> None:
        py = self._get_pyautogui()
        py.moveRel(dx, dy)

    def move_to(self, x: int, y: int) -> None:
        py = self._get_pyautogui()
        py.moveTo(x, y)

    def position(self) -> tuple[int, int]:
        py = self._get_pyautogui()
        return py.position()

    def size(self) -> tuple[int, int]:
        py = self._get_pyautogui()
        return py.size()

    def click(self) -> None:
        py = self._get_pyautogui()
        py.click()

    def right_click(self) -> None:
        py = self._get_pyautogui()
        py.rightClick()
