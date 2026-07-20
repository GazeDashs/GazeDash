"""Wrapper centralizado para acciones de mouse (lazy import de pyautogui).

Centraliza el acceso a `pyautogui` para evitar imports dispersos
en módulos individuales y permite manejar errores de dependencia
de forma consistente.
"""

from typing import Optional


class MouseDriver:
    """Driver mínimo para mover y clics usando pydirectinput.

    Importa `pydirectinput` bajo demanda y lanza un RuntimeError claro
    si no está instalado.
    """

    def __init__(self) -> None:
        self._pydirectinput: Optional[object] = None

    def _get_pydirectinput(self):
        if self._pydirectinput is not None:
            return self._pydirectinput

        try:
            import pydirectinput
            # Optional: Disable fail-safe if it interferes with games
            pydirectinput.FAILSAFE = False
        except Exception as exc:
            raise RuntimeError(
                "pydirectinput no está disponible. Instala la dependencia para controlar el cursor."
            ) from exc

        self._pydirectinput = pydirectinput
        return self._pydirectinput

    def move_rel(self, dx: int, dy: int) -> None:
        py = self._get_pydirectinput()
        py.moveRel(dx, dy)

    def move_to(self, x: int, y: int) -> None:
        py = self._get_pydirectinput()
        py.moveTo(x, y)

    def position(self) -> tuple[int, int]:
        py = self._get_pydirectinput()
        return py.position()

    def size(self) -> tuple[int, int]:
        py = self._get_pydirectinput()
        return py.size()

    def click(self) -> None:
        py = self._get_pydirectinput()
        py.click()

    def right_click(self) -> None:
        py = self._get_pydirectinput()
        py.rightClick()
