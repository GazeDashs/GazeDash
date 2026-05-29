"""Modelo simple de calibración (placeholder)."""


class CalibrationModel:
    def __init__(self):
        self.points = []

    def add_point(self, gaze, screen_point):
        self.points.append((gaze, screen_point))
