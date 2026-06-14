"""Extraccion de features compatible con los modelos de voz entrenados.

El formato replica el notebook `Copia_de_Modulo_de_Habla_Mejorado.ipynb`:
audio mono a 16 kHz, 1 segundo de duracion y vector tabular de 236 features.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np


TARGET_SR = 16000
TARGET_LENGTH = 16000
TARGET_DUR = 1.0


def create_feature_names_v3(n_mels: int = 128) -> list[str]:
    names = []
    for i in range(1, 27):
        names.append(f"mfcc_{i}_mean")
    for i in range(1, 27):
        names.append(f"mfcc_{i}_std")
    for i in range(1, 27):
        names.append(f"delta_mfcc_{i}_mean")
    for i in range(1, 13):
        names.append(f"chroma_{i}")
    for i in range(1, n_mels + 1):
        names.append(f"mel_{i}")
    names.extend(["zcr_mean", "zcr_std"])
    for i in range(1, 8):
        names.append(f"contrast_{i}")
    names.extend(
        [
            "centroid_mean",
            "centroid_std",
            "rolloff_mean",
            "rolloff_std",
            "flatness_mean",
            "bandwidth_mean",
            "rms_mean",
            "rms_std",
            "rms_max",
        ]
    )
    return names


FEATURE_COLUMNS_V3 = create_feature_names_v3(n_mels=128)


def _require_librosa():
    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError(
            "librosa no esta instalado. Instala las dependencias de voz para procesar audio."
        ) from exc
    return librosa


def preprocess_audio_array(audio: np.ndarray, sample_rate: int, gain: float = 1.0) -> np.ndarray:
    """Normaliza, resamplea, recorta silencios y ajusta el audio a 1 segundo."""
    librosa = _require_librosa()

    if audio is None:
        raise ValueError("Audio vacio para procesar voz.")

    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    if gain and gain != 1.0:
        audio = audio * float(gain)

    if int(sample_rate) != TARGET_SR:
        audio = librosa.resample(audio, orig_sr=int(sample_rate), target_sr=TARGET_SR)

    audio, _ = librosa.effects.trim(audio, top_db=25)

    if audio.size == 0:
        audio = np.zeros(TARGET_LENGTH, dtype=np.float32)

    max_amp = float(np.max(np.abs(audio))) if audio.size else 0.0
    if max_amp > 0:
        audio = audio / max_amp

    if len(audio) > TARGET_LENGTH:
        start = max(0, (len(audio) - TARGET_LENGTH) // 2)
        audio = audio[start : start + TARGET_LENGTH]

    if len(audio) < TARGET_LENGTH:
        pad_total = TARGET_LENGTH - len(audio)
        pad_before = pad_total // 2
        pad_after = pad_total - pad_before
        audio = np.pad(audio, (pad_before, pad_after), mode="constant")

    return np.asarray(audio[:TARGET_LENGTH], dtype=np.float32)


def extract_features_v3(audio: np.ndarray, sample_rate: int = TARGET_SR) -> np.ndarray:
    """Devuelve el vector de 236 features usado por los modelos `*_pipeline.pkl`."""
    librosa = _require_librosa()

    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    if int(sample_rate) != TARGET_SR:
        audio = librosa.resample(audio, orig_sr=int(sample_rate), target_sr=TARGET_SR)
        sample_rate = TARGET_SR

    features: list[float] = []
    n_samples = len(audio)
    n_fft = min(n_samples, 1024)
    hop_length = max(1, n_fft // 4)

    mfccs = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=26, n_fft=n_fft, hop_length=hop_length)
    features.extend(np.mean(mfccs, axis=1))
    features.extend(np.std(mfccs, axis=1))

    delta_mfcc = librosa.feature.delta(mfccs)
    features.extend(np.mean(delta_mfcc, axis=1))

    chroma = librosa.feature.chroma_stft(y=audio, sr=sample_rate, n_fft=n_fft, hop_length=hop_length)
    features.extend(np.mean(chroma, axis=1))

    n_mels = min(128, n_fft // 2 + 1)
    mel = librosa.feature.melspectrogram(
        y=audio,
        sr=sample_rate,
        n_fft=n_fft,
        hop_length=hop_length,
        n_mels=n_mels,
    )
    mel_db = librosa.power_to_db(mel)
    mel_features = np.mean(mel_db, axis=1)
    features.extend(_pad_to_length(mel_features, 128))

    zcr = librosa.feature.zero_crossing_rate(audio, hop_length=hop_length)
    features.append(float(np.mean(zcr)))
    features.append(float(np.std(zcr)))

    try:
        contrast = librosa.feature.spectral_contrast(y=audio, sr=sample_rate, n_fft=n_fft, hop_length=hop_length)
        features.extend(np.mean(contrast, axis=1))
    except Exception:
        features.extend([0.0] * 7)

    centroid = librosa.feature.spectral_centroid(y=audio, sr=sample_rate, n_fft=n_fft, hop_length=hop_length)
    features.append(float(np.mean(centroid)))
    features.append(float(np.std(centroid)))

    rolloff = librosa.feature.spectral_rolloff(y=audio, sr=sample_rate, n_fft=n_fft, hop_length=hop_length)
    features.append(float(np.mean(rolloff)))
    features.append(float(np.std(rolloff)))

    flatness = librosa.feature.spectral_flatness(y=audio, n_fft=n_fft, hop_length=hop_length)
    features.append(float(np.mean(flatness)))

    bandwidth = librosa.feature.spectral_bandwidth(y=audio, sr=sample_rate, n_fft=n_fft, hop_length=hop_length)
    features.append(float(np.mean(bandwidth)))

    rms = librosa.feature.rms(y=audio, hop_length=hop_length)
    features.append(float(np.mean(rms)))
    features.append(float(np.std(rms)))
    features.append(float(np.max(rms)))

    result = np.asarray(features, dtype=np.float32)
    if len(result) != len(FEATURE_COLUMNS_V3):
        raise RuntimeError(
            f"Vector de features incompatible: {len(result)} generado, {len(FEATURE_COLUMNS_V3)} esperado."
        )
    return result


def _pad_to_length(values: Iterable[float], expected_length: int) -> list[float]:
    padded = list(values)
    if len(padded) < expected_length:
        padded.extend([0.0] * (expected_length - len(padded)))
    return padded[:expected_length]
