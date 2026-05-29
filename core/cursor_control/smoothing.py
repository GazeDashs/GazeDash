"""Filtros y suavizado para movimientos del cursor."""


def simple_exponential_smoothing(prev, current, alpha=0.5):
    if prev is None:
        return current
    return prev * (1 - alpha) + current * alpha
