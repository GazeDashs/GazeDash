"""Captura de cámara y manejo de stream (placeholder)."""

import cv2


def open_camera(index=0, width=640, height=480):
    """Abre la cámara con OpenCV y devuelte el stream."""
    cap = cv2.VideoCapture(index)

    if not cap.isOpened():
        raise RuntimeError(
            f"No se puedo abrir la cámara {index}."
            "Verifica que esté conectada o prueba con otro índice."
        )

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    return cap

def read_frame(cap, flip=True):
    ok, frame = cap.read()

    if not ok or frame is None:
        return None

    if flip:
        frame = cv2.flip(frame, 1)

    return frame

def close_camera(cap):
    if cap is not None:
        cap.release()
