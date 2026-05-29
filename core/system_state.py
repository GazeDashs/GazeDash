"""Estado global del sistema (activo, pausado, etc.)."""


class SystemState:
    ACTIVE = "active"
    PAUSED = "paused"

    def __init__(self):
        self.state = SystemState.ACTIVE

    def pause(self):
        self.state = SystemState.PAUSED

    def resume(self):
        self.state = SystemState.ACTIVE
