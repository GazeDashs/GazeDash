"""Mapeo de coordenadas de mirada a posición de cursor."""


def map_gaze_to_cursor(gaze_point, screen_size):
    """Placeholder: convierte `gaze_point` a coordenadas de pantalla.

    Args:
        gaze_point: (x, y) normalizado
        screen_size: (width, height)

    Returns:
        (x, y) en píxeles
    """
    w, h = screen_size
    return int(gaze_point[0] * w), int(gaze_point[1] * h)
