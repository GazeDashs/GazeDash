"""Filtros reutilizables para señales."""


def moving_average(values, n=3):
    if not values:
        return []
    res = []
    for i in range(len(values)):
        window = values[max(0, i - n + 1): i + 1]
        res.append(sum(window) / len(window))
    return res
