import math

from typing import Optional

from core.cursor_control.smoothing import simple_exponential_smoothing
from core.input.mouse_driver import MouseDriver


class MouseController:
    """Controlador de tipo 'joystick' basado en la posición del rostro.

    Recibe coordenadas de referencia (píxeles) y mueve el cursor relativo.
    """

    def __init__(self, dead_zone: float, max_speed: float, smoothing: float, center: Optional[tuple[float, float]] = None):
        self.dead_zone = float(dead_zone)
        self.max_speed = float(max_speed)
        self.smoothing = float(smoothing)

        self.center_x: Optional[float] = None
        self.center_y: Optional[float] = None
        if center is not None and isinstance(center, (list, tuple)) and len(center) == 2:
            self.center_x, self.center_y = float(center[0]), float(center[1])

        self.smooth_dx: Optional[float] = None
        self.smooth_dy: Optional[float] = None

        self._mouse = MouseDriver()

    def recalibrate(self, x: float, y: float):
        self.center_x = x
        self.center_y = y
        self.smooth_dx = 0.0
        self.smooth_dy = 0.0

    def reset_center(self):
        self.center_x = None
        self.center_y = None
        self.smooth_dx = None
        self.smooth_dy = None

    def update(self, x: float, y: float):
        if self.center_x is None or self.center_y is None:
            self.center_x = x
            self.center_y = y

        dx = x - self.center_x
        dy = y - self.center_y

        distance = math.hypot(dx, dy)

        move_x = 0.0
        move_y = 0.0

        if distance > self.dead_zone:
            norm_x = dx / distance
            norm_y = dy / distance
            intensity = min(max((distance - self.dead_zone) / 150.0, 0.0), 1.0)
            speed = intensity * self.max_speed
            move_x = norm_x * speed
            move_y = norm_y * speed

        self.smooth_dx = simple_exponential_smoothing(self.smooth_dx, move_x, alpha=self.smoothing)
        self.smooth_dy = simple_exponential_smoothing(self.smooth_dy, move_y, alpha=self.smoothing)

        self._mouse.move_rel(int(round(self.smooth_dx)), int(round(self.smooth_dy)))

        return dx, dy
