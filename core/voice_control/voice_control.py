from __future__ import annotations

import threading
import time
import unicodedata
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import numpy as np

from core.gesture_engine.hotkey_executor import HotkeyExecutor
from .voice_model import VoiceCommandModel

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover
    sd = None


class VoiceControlState(str, Enum):
    DISABLED = "DISABLED"
    WAITING_MODULE = "WAITING_MODULE"
    MODULE_ACTIVE = "MODULE_ACTIVE"
    LISTENING_COMMAND = "LISTENING_COMMAND"
    CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
    ERROR = "ERROR"


MODULE_LABELS = {
    "accesibilidad": "Accesibilidad",
    "multimedia": "Multimedia",
    "navegacion": "Navegacion",
    "web": "Web",
}


def _normalize_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.replace(" ", "_")


class VoiceCommandController:
    """Controla la escucha por voz con activacion por palabra de modulo."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, status_callback: Optional[Callable[[str], None]] = None):
        self._config = config or {}
        self._status_callback = status_callback
        self._hotkey_executor = HotkeyExecutor()
        self._listening_lock = threading.Lock()
        self._listening = False
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._last_activation = 0.0
        self._last_command_label: Optional[str] = None
        self._last_command_at = 0.0
        self._pending_confirmation: Optional[tuple[str, Dict[str, Any]]] = None
        self.state = VoiceControlState.DISABLED
        self.active_module: Optional[str] = None
        self._activation_model: Optional[VoiceCommandModel] = None
        self._command_models: dict[str, VoiceCommandModel] = {}
        self._model_load_errors: dict[str, str] = {}
        self._load_settings_from_config()
        if self.enabled:
            self._build_models()

    def _load_settings_from_config(self):
        voice_config = self._config.get("voice_control", {}) if isinstance(self._config, dict) else {}
        self.enabled = bool(voice_config.get("enabled", False))
        self.activation_gesture = str(voice_config.get("activation_gesture", "")).strip() or None
        self.activation_word = str(voice_config.get("activation_word", "")).strip() or None
        self.listen_duration = float(voice_config.get("listen_duration", 2.0))
        self.cooldown_seconds = float(voice_config.get("cooldown_seconds", 1.5))
        self.gain = float(voice_config.get("gain", 1.0))
        self.min_confidence = float(voice_config.get("min_confidence", 0.65))
        self.repeat_guard_enabled = bool(voice_config.get("repeat_guard_enabled", True))
        self.dangerous_confirmation_enabled = bool(voice_config.get("dangerous_confirmation_enabled", True))
        self.command_action_map = voice_config.get("command_actions", {}) if isinstance(voice_config.get("command_actions", {}), dict) else {}
        self.sample_rate = int(voice_config.get("sample_rate", 16000))
        self.model_paths = voice_config.get("model_paths", {}) if isinstance(voice_config.get("model_paths", {}), dict) else {}
        configured_module = _normalize_label(voice_config.get("active_module"))
        self.active_module = configured_module if configured_module in MODULE_LABELS else None

    def _build_models(self):
        self._activation_model = None
        self._command_models = {}
        self._model_load_errors = {}

        for model_name, model_path in (self.model_paths or {}).items():
            normalized_name = _normalize_label(model_name)
            try:
                path = Path(model_path)
                if not path.is_absolute():
                    path = Path(".") / model_path
                model = VoiceCommandModel(path)
            except Exception as exc:
                self._model_load_errors[normalized_name] = f"{type(exc).__name__}: {exc}"
                continue

            if normalized_name == "activacion":
                self._activation_model = model
            elif normalized_name in MODULE_LABELS:
                self._command_models[normalized_name] = model

    def update_config(self, config: Dict[str, Any]):
        was_running = self._worker_thread is not None and self._worker_thread.is_alive()
        if was_running:
            self.stop()

        self._config = config or {}
        self._load_settings_from_config()
        if self.enabled:
            self._build_models()
        else:
            self._activation_model = None
            self._command_models = {}
            self._model_load_errors = {}

        if was_running or self.enabled:
            self.start()

    def start(self):
        if not self.enabled:
            self._set_state(VoiceControlState.DISABLED, "Voz desactivada")
            return

        if sd is None:
            self._set_state(VoiceControlState.ERROR, "Advertencia: falta sounddevice para usar el microfono")
            return

        if self._activation_model is None and not self._command_models:
            self._build_models()

        if self._activation_model is None:
            self._set_state(VoiceControlState.ERROR, "Advertencia: modelo de activacion no cargo")
            return

        if not self._command_models:
            self._set_state(VoiceControlState.ERROR, "Advertencia: no cargaron modelos de comandos")
            return

        self._stop_event.clear()
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return

        self._set_state(VoiceControlState.WAITING_MODULE, "Voz lista: esperando modulo")
        self._worker_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._worker_thread.start()

    def stop(self):
        self._stop_event.set()
        self._listening = False

    def handle_gesture_input(self, gestures: Dict[str, Any]):
        if not self.enabled or self._activation_model is None:
            return
        if self._listening or self._worker_thread is not None and self._worker_thread.is_alive():
            return
        if not isinstance(gestures, dict):
            return

        if self.activation_gesture and gestures.get(self.activation_gesture):
            self._trigger_listen("gesto")

    def _listen_loop(self):
        while not self._stop_event.is_set():
            self._listen_and_process("voz")
            if self._stop_event.wait(max(0.05, self.cooldown_seconds)):
                break

    def _trigger_listen(self, activation_reason: str):
        now = time.time()
        if now - self._last_activation < self.cooldown_seconds:
            self._set_status("Voz en cooldown. Esperando...")
            return

        if self._listening:
            return

        if sd is None:
            self._set_state(VoiceControlState.ERROR, "Advertencia: falta sounddevice para usar el microfono")
            return

        self._last_activation = now
        thread = threading.Thread(target=self._listen_and_process, args=(activation_reason,), daemon=True)
        thread.start()

    def _listen_and_process(self, activation_reason: str):
        with self._listening_lock:
            if self._stop_event.is_set():
                return

            self._listening = True
            self._announce_listening_state(activation_reason)
            audio = None
            try:
                audio = self._record_audio(self.listen_duration)
            except Exception as exc:
                self._set_state(VoiceControlState.ERROR, f"Error grabando audio: {exc}")
            finally:
                if audio is None:
                    self._listening = False
                    return

            try:
                self._process_audio(audio)
            except Exception as exc:
                self._set_state(VoiceControlState.ERROR, f"Error procesando audio: {exc}")
            finally:
                self._listening = False

    def _announce_listening_state(self, activation_reason: str):
        if self.active_module:
            module_label = MODULE_LABELS.get(self.active_module, self.active_module)
            self._set_state(VoiceControlState.LISTENING_COMMAND, f"Escuchando comando de {module_label}")
        else:
            self._set_state(VoiceControlState.WAITING_MODULE, f"Voz lista: esperando modulo ({activation_reason})")

    def _process_audio(self, audio: np.ndarray):
        if self.active_module is None:
            activation = self._predict_activation(audio)
            self._handle_module_prediction(activation)
            return

        command_prediction = self._predict_command(audio, self.active_module)
        activation_prediction = self._predict_activation(audio)

        module_key = self._module_key_from_prediction(activation_prediction.label)
        if module_key and activation_prediction.confidence >= self.min_confidence:
            if command_prediction.label is None or activation_prediction.confidence >= command_prediction.confidence + 0.10:
                self._activate_module(module_key, activation_prediction.confidence)
                return

        self._handle_command_prediction(command_prediction)

    def _predict_activation(self, audio: np.ndarray):
        if self._activation_model is None:
            raise RuntimeError("Modelo de activacion no disponible")
        return self._activation_model.predict_from_audio(audio, self.sample_rate, gain=self.gain)

    def _predict_command(self, audio: np.ndarray, module_key: str):
        model = self._command_models.get(module_key)
        if model is None:
            raise RuntimeError(f"Modelo de comandos no disponible para {module_key}")
        return model.predict_from_audio(audio, self.sample_rate, gain=self.gain)

    def _handle_module_prediction(self, prediction):
        module_key = self._module_key_from_prediction(prediction.label)
        if not module_key or prediction.confidence < self.min_confidence:
            self._set_state(VoiceControlState.WAITING_MODULE, "Confianza baja: repetí el modulo")
            return
        self._activate_module(module_key, prediction.confidence)

    def _activate_module(self, module_key: str, confidence: float):
        self.active_module = module_key
        self._pending_confirmation = None
        module_label = MODULE_LABELS.get(module_key, module_key)
        self._set_state(VoiceControlState.MODULE_ACTIVE, f"Modulo activo: {module_label} ({confidence:.2f})")

    def _handle_command_prediction(self, prediction):
        label = prediction.label
        confidence = float(prediction.confidence or 0.0)
        module_label = MODULE_LABELS.get(self.active_module or "", self.active_module or "")

        if not label or confidence < self.min_confidence:
            self._set_state(VoiceControlState.MODULE_ACTIVE, f"Confianza baja: repetí el comando de {module_label}")
            return

        action = self._resolve_action(label)
        if action is None:
            self._set_state(VoiceControlState.MODULE_ACTIVE, f"Ninguna accion configurada para comando: {label}")
            return

        if self._requires_confirmation(label, action):
            if self._pending_confirmation and self._pending_confirmation[0] == label:
                self._pending_confirmation = None
            else:
                self._pending_confirmation = (label, action)
                self._set_state(VoiceControlState.CONFIRM_REQUIRED, f"Confirmacion requerida: repetí {label}")
                return

        if self._should_skip_repeat(label):
            self._set_state(VoiceControlState.MODULE_ACTIVE, f"Comando repetido ignorado: {label}")
            return

        self._execute_command(label, action)
        self._last_command_label = label
        self._last_command_at = time.time()

    def _execute_command(self, label: str, action: Dict[str, Any]):
        try:
            executed = self._hotkey_executor.execute(action)
            if executed:
                self._set_state(VoiceControlState.MODULE_ACTIVE, f"Accion ejecutada: {label}")
            else:
                self._set_state(VoiceControlState.MODULE_ACTIVE, f"Accion no ejecutable para comando: {label}")
        except RuntimeError as exc:
            self._set_state(VoiceControlState.ERROR, f"Fallo al ejecutar accion de voz: {exc}")

    def _should_skip_repeat(self, label: str) -> bool:
        if not self.repeat_guard_enabled:
            return False
        return label == self._last_command_label and time.time() - self._last_command_at < self.cooldown_seconds

    def _requires_confirmation(self, label: str, action: Dict[str, Any]) -> bool:
        if not self.dangerous_confirmation_enabled:
            return False
        if bool(action.get("requires_confirmation", False)):
            return True
        return _normalize_label(label) in {"cerrar"}

    @staticmethod
    def _module_key_from_prediction(label: Any) -> Optional[str]:
        normalized = _normalize_label(label)
        if normalized in MODULE_LABELS:
            return normalized
        return None

    def _record_audio(self, duration: float) -> Optional[np.ndarray]:
        if sd is None:
            raise RuntimeError("sounddevice no esta instalado")

        if duration <= 0:
            duration = 2.0

        sd.default.samplerate = self.sample_rate
        sd.default.channels = 1
        self._set_status("Grabando audio...")
        recording = sd.rec(int(duration * self.sample_rate), samplerate=self.sample_rate, channels=1, dtype="float32")
        sd.wait()
        return recording.reshape(-1)

    def _resolve_action(self, command_label: str) -> Optional[Dict[str, Any]]:
        if not isinstance(command_label, str):
            return None

        voice_actions = {}
        active_profile = self._config.get("active_profile") or self._config.get("profile")
        profiles = self._config.get("profiles", {}) if isinstance(self._config.get("profiles", {}), dict) else {}
        profile = profiles.get(active_profile, {}) if isinstance(active_profile, str) and isinstance(profiles, dict) else {}
        if isinstance(profile, dict):
            voice_actions.update(profile.get("voice_actions", {}) or {})

        if command_label in voice_actions:
            return voice_actions.get(command_label)

        if command_label in self.command_action_map:
            return self.command_action_map.get(command_label)

        return None

    def _set_state(self, state: VoiceControlState, message: str):
        self.state = state
        self._set_status(message)

    def _set_status(self, message: str):
        if callable(self._status_callback):
            try:
                self._status_callback(message)
            except Exception:
                pass
