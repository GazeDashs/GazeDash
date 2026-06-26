"""Extraccion de features compatible con los modelos de voz entrenados (V3 Final).

El formato replica exactamente create_feature_names_v3_final y extract_features_v3_final
del notebook de entrenamiento:
- Audio a 22050 Hz
- 3 segmentos temporales con MFCC(20) + deltas + features espectrales
- 2 features globales
- Vector tabular de 275 features
"""

from __future__ import annotations

import numpy as np

TARGET_SR = 22050
TARGET_LENGTH = 22050  # 1 segundo a 22050 Hz
TARGET_DUR = 1.0
N_SEGMENTS = 3


def create_feature_names_v3_final(n_segments: int = N_SEGMENTS, n_mfcc: int = 20) -> list[str]:
    """Genera los 275 nombres de features en el orden exacto del notebook."""
    names: list[str] = []

    for s in range(n_segments):
        part = f"seg{s + 1}"

        for i in range(1, n_mfcc + 1):
            names.append(f"mfcc_{i}_mean_{part}")
        for i in range(1, n_mfcc + 1):
            names.append(f"mfcc_{i}_std_{part}")
        for i in range(1, n_mfcc + 1):
            names.append(f"delta_mfcc_{i}_{part}")
        for i in range(1, n_mfcc + 1):
            names.append(f"delta2_mfcc_{i}_{part}")

        names.extend([
            f"centroid_mean_{part}", f"centroid_std_{part}",
            f"rolloff_mean_{part}", f"rolloff_std_{part}",
            f"bandwidth_{part}",
            f"flatness_{part}",
            f"rms_mean_{part}", f"rms_std_{part}", f"rms_max_{part}",
            f"zcr_mean_{part}", f"zcr_std_{part}",
        ])

    names.extend(["global_flatness", "global_mfcc_mean"])
    return names


FEATURE_COLUMNS_V3_FINAL = create_feature_names_v3_final()
# Alias para compatibilidad con cualquier import existente
FEATURE_COLUMNS_V3 = FEATURE_COLUMNS_V3_FINAL


def _require_librosa():
    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError(
            "librosa no esta instalado. Instala las dependencias de voz para procesar audio."
        ) from exc
    return librosa


def preprocess_audio_array(audio: np.ndarray, sample_rate: int, gain: float = 1.0) -> np.ndarray:
    """Normaliza, resamplea, recorta silencios y ajusta el audio a 1 segundo a 22050 Hz."""
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
        audio = audio[start: start + TARGET_LENGTH]

    if len(audio) < TARGET_LENGTH:
        pad_total = TARGET_LENGTH - len(audio)
        pad_before = pad_total // 2
        pad_after = pad_total - pad_before
        audio = np.pad(audio, (pad_before, pad_after), mode="constant")

    return np.asarray(audio[:TARGET_LENGTH], dtype=np.float32)


def extract_features_v3(audio: np.ndarray, sample_rate: int = TARGET_SR) -> np.ndarray:
    """
    Extrae el vector de 275 features usado por los modelos nuevos (XGBoost + SMOTE).

    Replica exactamente extract_features_v3_final del notebook:
    - 3 segmentos: MFCC(20) mean+std, delta mean, delta2 mean,
      centroid, rolloff, bandwidth, flatness, rms, zcr
    - 2 features globales: global_flatness, global_mfcc_mean
    """
    librosa = _require_librosa()

    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    if int(sample_rate) != TARGET_SR:
        audio = librosa.resample(audio, orig_sr=int(sample_rate), target_sr=TARGET_SR)
        sample_rate = TARGET_SR

    features: list[float] = []
    total_len = len(audio)
    segment_length = total_len // N_SEGMENTS

    if segment_length < 1600:
        segment_length = max(1600, total_len // 2)

    for i in range(N_SEGMENTS):
        start = i * segment_length
        end = min((i + 1) * segment_length, total_len)
        segment = audio[start:end]

        if len(segment) < 1024:
            segment = np.pad(segment, (0, 1024 - len(segment)))

        n_fft = min(len(segment), 1024)
        hop_length = max(1, n_fft // 4)

        # MFCC + deltas
        mfcc = librosa.feature.mfcc(
            y=segment, sr=sample_rate, n_mfcc=20, n_fft=n_fft, hop_length=hop_length
        )
        delta = librosa.feature.delta(mfcc)
        delta2 = librosa.feature.delta(mfcc, order=2)

        features.extend(np.mean(mfcc, axis=1))       # mfcc_i_mean_segN  (20)
        features.extend(np.std(mfcc, axis=1))        # mfcc_i_std_segN   (20)
        features.extend(np.mean(delta, axis=1))      # delta_mfcc_i_segN (20)
        features.extend(np.mean(delta2, axis=1))     # delta2_mfcc_i_segN(20)

        # Espectrales
        centroid = librosa.feature.spectral_centroid(
            y=segment, sr=sample_rate, n_fft=n_fft, hop_length=hop_length
        )
        features.append(float(np.mean(centroid)))    # centroid_mean_segN
        features.append(float(np.std(centroid)))     # centroid_std_segN

        rolloff = librosa.feature.spectral_rolloff(
            y=segment, sr=sample_rate, n_fft=n_fft, hop_length=hop_length
        )
        features.append(float(np.mean(rolloff)))     # rolloff_mean_segN
        features.append(float(np.std(rolloff)))      # rolloff_std_segN

        bandwidth = librosa.feature.spectral_bandwidth(
            y=segment, sr=sample_rate, n_fft=n_fft, hop_length=hop_length
        )
        features.append(float(np.mean(bandwidth)))   # bandwidth_segN

        flatness = librosa.feature.spectral_flatness(
            y=segment, n_fft=n_fft, hop_length=hop_length
        )
        features.append(float(np.mean(flatness)))    # flatness_segN

        # Energía
        rms = librosa.feature.rms(y=segment, hop_length=hop_length)
        features.append(float(np.mean(rms)))         # rms_mean_segN
        features.append(float(np.std(rms)))          # rms_std_segN
        features.append(float(np.max(rms)))          # rms_max_segN

        zcr = librosa.feature.zero_crossing_rate(y=segment, hop_length=hop_length)
        features.append(float(np.mean(zcr)))         # zcr_mean_segN
        features.append(float(np.std(zcr)))          # zcr_std_segN

    # Features globales
    global_mfcc = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=13)
    features.append(float(np.mean(librosa.feature.spectral_flatness(y=audio))))  # global_flatness
    features.append(float(np.mean(global_mfcc)))                                  # global_mfcc_mean

    result = np.asarray(features, dtype=np.float32)
    if len(result) != len(FEATURE_COLUMNS_V3_FINAL):
        raise RuntimeError(
            f"Vector de features incompatible: {len(result)} generado, "
            f"{len(FEATURE_COLUMNS_V3_FINAL)} esperado."
        )
    return result
