import importlib.util
import os
import sys


from core.input.mouse_controller import MouseController

from vision.camera.camera_stream import close_camera, open_camera, read_frame
from vision.face_tracking.face_detector import MediaPipeFaceDetector
from ui.overlay import Overlay

DEAD_ZONE = 25
MAX_SPEED = 35
SMOOTHING = 0.2

THRESHOLD = 0.010
HOLD_TIME = 0.5
CLICK_COOLDOWN = 1.0

OVERLAY_WIDTH = 220
OVERLAY_HEIGHT = 220


class App:

    def __init__(self):
        self.cap = open_camera(0, width=640, height=480)
        self.face_detector = MediaPipeFaceDetector(draw_landmarks=False, live_stream=True)
        self.mouse = MouseController(
            DEAD_ZONE,
            MAX_SPEED,
            SMOOTHING,
        )
        
        self.overlay = Overlay(
            OVERLAY_WIDTH,
            OVERLAY_HEIGHT,
            DEAD_ZONE,
        )

        self.overlay.root.protocol("WM_DELETE_WINDOW", self._shutdown)
        self.update()
        self.overlay.root.mainloop()

    def _shutdown(self):
        if self.cap is not None:
            close_camera(self.cap)
            self.cap = None

        if self.face_detector is not None:
            self.face_detector.close()
            self.face_detector = None

        self.overlay.root.destroy()

    def update(self):
        frame = read_frame(self.cap)

        if frame is not None:
            face_data = self.face_detector.detect(frame)

            if face_data is not None:
                nose_tip = face_data.get("nose_tip")
                if nose_tip is not None:
                    nose_x, nose_y = nose_tip
                    dx, dy = self.mouse.update(nose_x, nose_y)
                    self.overlay.draw(int(dx * 1.5), int(dy * 1.5))
                else:
                    self.overlay.draw(0, 0)
            else:
                self.overlay.draw(0, 0)
        else:
            self.overlay.draw(0, 0)

        self.overlay.root.after(16, self.update)


if __name__ == "__main__":
    App()
