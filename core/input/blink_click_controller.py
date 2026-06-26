import time
import pydirectinput


class BlinkClickController:

    def __init__(self):
        # Thresholds independientes por ojo porque cada cara es distinta
        self.threshold_left = 0.32   # ojo izquierdo da valores más bajos
        self.threshold_right = 0.38  # ojo derecho da valores más altos
        self.diff_ratio = 0.80       # el ojo abierto debe ser < 80% del cerrado
        self.min_hold_time = 0.08
        self.max_hold_time = 0.4
        self.cooldown = 0.5

        self.left_active = False
        self.right_active = False

        self.left_start = 0.0
        self.right_start = 0.0

        self.last_left_click = 0.0
        self.last_right_click = 0.0

        pydirectinput.FAILSAFE = False

    def update(self, face_data):

        left = face_data.get("eye_blink_left", 0.0)
        right = face_data.get("eye_blink_right", 0.0)

        now = time.time()

        # MediaPipe invierte izquierda/derecha (efecto espejo)
        # eye_blink_right → click izquierdo, eye_blink_left → click derecho
        left_closed  = right > self.threshold_right and left  < right * self.diff_ratio
        right_closed = left  > self.threshold_left  and right < left  * self.diff_ratio

        # Click izquierdo
        if left_closed:
            if not self.left_active:
                self.left_active = True
                self.left_start = now
            elif (
                now - self.left_start > self.max_hold_time
                and now - self.last_left_click > self.cooldown
            ):
                pydirectinput.click(button="left")
                self.last_left_click = now
                self.left_active = False
        elif self.left_active:
            duration = now - self.left_start
            if duration >= self.min_hold_time and now - self.last_left_click > self.cooldown:
                pydirectinput.click(button="left")
                self.last_left_click = now
            self.left_active = False

        # Click derecho
        if right_closed:
            if not self.right_active:
                self.right_active = True
                self.right_start = now
            elif (
                now - self.right_start > self.max_hold_time
                and now - self.last_right_click > self.cooldown
            ):
                pydirectinput.click(button="right")
                self.last_right_click = now
                self.right_active = False
        elif self.right_active:
            duration = now - self.right_start
            if duration >= self.min_hold_time and now - self.last_right_click > self.cooldown:
                pydirectinput.click(button="right")
                self.last_right_click = now
            self.right_active = False