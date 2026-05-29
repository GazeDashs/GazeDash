"""Gestor de cooldowns para evitar activaciones repetidas."""

import time


class CooldownManager:
    def __init__(self, cooldown_seconds=0.5):
        self.cooldown = cooldown_seconds
        self._last = {}

    def allow(self, key):
        now = time.time()
        last = self._last.get(key, 0)
        if now - last >= self.cooldown:
            self._last[key] = now
            return True
        return False
