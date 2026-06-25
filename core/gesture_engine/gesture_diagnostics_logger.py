"""Registro liviano de diagnosticos de gestos en formato JSONL."""

from __future__ import annotations

import json
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class GestureDiagnosticsLogger:
    """Escribe diagnosticos de gestos sin bloquear el loop de camara."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        log_dir: str | Path = "logs/gesture_diagnostics",
        min_interval_seconds: float = 0.25,
        only_log_changes: bool = True,
        max_queue_size: int = 512,
        component: str = "app",
    ):
        self.enabled = bool(enabled)
        self.log_dir = Path(log_dir)
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self.only_log_changes = bool(only_log_changes)
        self.component = str(component or "app")
        self._queue: queue.Queue[Optional[Dict[str, Any]]] = queue.Queue(maxsize=max(1, int(max_queue_size)))
        self._worker: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._file = None
        self._path: Optional[Path] = None
        self._last_signature: Optional[tuple[Any, ...]] = None
        self._last_emit_at = 0.0
        self._dropped = 0

        if self.enabled:
            try:
                self._start()
            except OSError:
                self.enabled = False
                self._file = None
                self._path = None

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]], *, component: str = "app"):
        settings = config.get("gesture_diagnostics", {}) if isinstance(config, dict) else {}
        if not isinstance(settings, dict):
            settings = {}

        return cls(
            enabled=bool(settings.get("enabled", True)),
            log_dir=settings.get("log_dir", "logs/gesture_diagnostics"),
            min_interval_seconds=float(settings.get("min_interval_seconds", 0.25)),
            only_log_changes=bool(settings.get("only_log_changes", True)),
            component=component,
        )

    @property
    def path(self) -> Optional[Path]:
        return self._path

    @property
    def dropped_events(self) -> int:
        return self._dropped

    def record(
        self,
        debug: Optional[Dict[str, Any]],
        *,
        profile_name: Optional[str] = None,
        detected_gesture: Optional[str] = None,
    ) -> bool:
        if not self.enabled or not isinstance(debug, dict):
            return False

        signature = self._signature(debug)
        now = time.monotonic()
        changed = signature != self._last_signature
        due = now - self._last_emit_at >= self.min_interval_seconds

        raw_active = debug.get("raw_active") or []
        active = debug.get("active") or []
        should_log_idle = debug.get("reason") not in {"ok", "disabled"}
        if self.only_log_changes and not changed and not due:
            return False
        if not (raw_active or active or changed or should_log_idle):
            return False

        event = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "component": self.component,
            "profile": profile_name,
            "detected_gesture": detected_gesture,
            "debug": debug,
        }

        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self._dropped += 1
            return False

        self._last_signature = signature
        self._last_emit_at = now
        return True

    def close(self):
        if not self.enabled:
            return

        self.enabled = False
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=1.0)
        if self._file is not None:
            try:
                self._file.flush()
                self._file.close()
            finally:
                self._file = None

    def _start(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = self.log_dir / f"gesture_diagnostics_{self.component}_{stamp}.jsonl"
        self._file = self._path.open("a", encoding="utf-8")
        self._worker = threading.Thread(target=self._write_loop, daemon=True)
        self._worker.start()

    def _write_loop(self):
        while not self._stop_event.is_set():
            item = self._queue.get()
            if item is None:
                break
            self._write_event(item)

        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                self._write_event(item)

    def _write_event(self, event: Dict[str, Any]):
        if self._file is None:
            return
        self._file.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        self._file.flush()

    @staticmethod
    def _signature(debug: Dict[str, Any]) -> tuple[Any, ...]:
        groups = debug.get("groups") or {}
        group_signature = []
        for group_name in sorted(groups):
            details = groups.get(group_name) or {}
            if not isinstance(details, dict):
                continue
            group_signature.append(
                (
                    group_name,
                    tuple(details.get("candidates") or []),
                    details.get("candidate"),
                    details.get("active"),
                    tuple(details.get("rejected") or []),
                )
            )

        return (
            debug.get("reason"),
            tuple(debug.get("raw_active") or []),
            tuple(debug.get("active") or []),
            tuple(group_signature),
            tuple(debug.get("ungrouped") or []),
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
