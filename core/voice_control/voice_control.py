import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import numpy as np

from core.gesture_engine.hotkey_executor import HotkeyExecutor
from .voice_model import VoiceCommandClassifier
  
try:
    import sounddevice as sd
except ImportError:  # pragma: no cover
    sd = None

try:
    from python_speech_features import logfbank, mfcc
except ImportError:  # pragma: no cover
    logfbank = None
    mfcc = None


class VoiceFeatureExtractor:
    @staticmethod
    def extract_features(audio: np.ndarray, sample_rate: int) -> np.ndarray:
        if audio is None or sample_rate is None:
            raise ValueError("Audio o tasa de muestreo no validos para extraer features")

        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)

        if mfcc is None or logfbank is None:
            raise RuntimeError(
                "python_speech_features no esta instalado. Instala la dependencia para extraer caracteristicas de voz."
            )

        mfcc_features = mfcc(audio, samplerate=sample_rate, numcep=13, nfft=2048)
        logfbank_features = logfbank(audio, samplerate=sample_rate, nfilt=26, nfft=2048)

        features = []
        for matrix in (mfcc_features, logfbank_features):
            features.extend(matrix.mean(axis=0).tolist())
            features.extend(matrix.std(axis=0).tolist())
            features.extend(np.percentile(matrix, [10, 50, 90], axis=0).flatten().tolist())

        zero_crossings = np.mean(np.abs(np.diff(np.sign(audio)))) / 2.0
        energy = float(np.mean(audio.astype(np.float32) ** 2))
        features.extend([zero_crossings, energy])

        return np.asarray(features, dtype=np.float32)


class VoiceCommandController:
    """Controla el flujo de activacion y clasificacion de comandos de voz."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, status_callback: Optional[Callable[[str], None]] = None):
        self._config = config or {}
        self._status_callback = status_callback
        self._hotkey_executor = HotkeyExecutor()
        self._listening_lock = threading.Lock()
        self._listening = False
        self._stop_event = threading.Event()
        self._last_activation = 0.0
        self._classifier = self._build_classifier()
        self._load_settings_from_config()

    def _load_settings_from_config(self):
        voice_config = self._config.get("voice_control", {}) if isinstance(self._config, dict) else {}
        self.enabled = bool(voice_config.get("enabled", False))
        self.activation_gesture = str(voice_config.get("activation_gesture", "")).strip() or None
        self.activation_word = str(voice_config.get("activation_word", "")).strip() or None
        self.listen_duration = float(voice_config.get("listen_duration", 10.0))
        self.cooldown_seconds = float(voice_config.get("cooldown_seconds", 5.0))
        self.gain = float(voice_config.get("gain", 1.0))
        self.command_action_map = voice_config.get("command_actions", {}) if isinstance(voice_config.get("command_actions", {}), dict) else {}
        self.sample_rate = int(voice_config.get("sample_rate", 16000))
        self.model_paths = voice_config.get("model_paths", {}) if isinstance(voice_config.get("model_paths", {}), dict) else {}

    def _build_classifier(self) -> Optional[VoiceCommandClassifier]:
        voice_config = self._config.get("voice_control", {}) if isinstance(self._config, dict) else {}
        model_paths = voice_config.get("model_paths", {}) if isinstance(voice_config.get("model_paths", {}), dict) else {}
        classifier = VoiceCommandClassifier(model_paths)
        return classifier if classifier.has_models() else None

    def update_config(self, config: Dict[str, Any]):
        self._config = config or {}
        self._load_settings_from_config()
        self._classifier = self._build_classifier()

    def start(self):
        if not self.enabled:
            return
        if self._classifier is None:
            self._set_status("Control de voz deshabilitado: no se encontraron modelos validos.")
            return
        self._set_status("Control de voz listo. Esperando activador.")

    def stop(self):
        self._stop_event.set()

    def handle_gesture_input(self, gestures: Dict[str, Any]):
        if not self.enabled or self._classifier is None:
            return
        if self._listening:
            return
        if not isinstance(gestures, dict):
            return

        if self.activation_gesture and gestures.get(self.activation_gesture):
            self._trigger_listen("gesto")

    def _trigger_listen(self, activation_reason: str):
        now = time.time()
        if now - self._last_activation < self.cooldown_seconds:
            self._set_status("Voz en cooldown. Esperando...")
            return

        if self._listening:
            return

        if sd is None:
            self._set_status("No se puede grabar audio: sounddevice no esta instalado.")
            return

        self._last_activation = now
        thread = threading.Thread(target=self._listen_and_process, args=(activation_reason,), daemon=True)
        thread.start()

    def _listen_and_process(self, activation_reason: str):
        with self._listening_lock:
            self._listening = True
            self._set_status(f"Escuchando comando por voz ({activation_reason})... {self.listen_duration}s")
            audio = None
            try:
                audio = self._record_audio(self.listen_duration)
            except Exception as exc:
                self._set_status(f"Error grabando audio: {exc}")
            if audio is None:
                self._listening = False
                return

            if self.gain and self.gain != 1.0:
                audio = self._apply_gain(audio, self.gain)

            try:
                features = VoiceFeatureExtractor.extract_features(audio, self.sample_rate)
                label, confidence, source = self._classifier.predict(features)
            except Exception as exc:
                self._set_status(f"Error procesando audio: {exc}")
                self._listening = False
                return

            if not label:
                self._set_status("No se reconocio ningun comando de voz.")
                self._listening = False
                return

            self._set_status(f"Comando detectado: {label} ({confidence:.2f})")
            action = self._resolve_action(label)
            if action is None:
                self._set_status(f"Ninguna accion configurada para comando: {label}")
                self._listening = False
                return

            try:
                executed = self._hotkey_executor.execute(action)
                if executed:
                    self._set_status(f"Accion ejecutada para comando: {label}")
                else:
                    self._set_status(f"Accion no ejecutable para comando: {label}")
            except RuntimeError as exc:
                self._set_status(f"Fallo al ejecutar accion de voz: {exc}")
            finally:
                self._listening = False

    def _record_audio(self, duration: float) -> Optional[np.ndarray]:
        if sd is None:
            raise RuntimeError("sounddevice no esta instalado")

        if duration <= 0:
            duration = 10.0

        sd.default.samplerate = self.sample_rate
        sd.default.channels = 1
        self._set_status("Grabando audio...")
        recording = sd.rec(int(duration * self.sample_rate), samplerate=self.sample_rate, channels=1, dtype="float32")
        sd.wait()
        return recording.reshape(-1)

    @staticmethod
    def _apply_gain(audio: np.ndarray, gain: float) -> np.ndarray:
        if audio is None:
            return audio
        try:
            amplified = audio.astype(np.float32) * float(gain)
        except Exception:
            return audio
        return np.clip(amplified, -1.0, 1.0)

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

    def _set_status(self, message: str):
        if callable(self._status_callback):
            try:
                self._status_callback(message)
            except Exception:
                pass
