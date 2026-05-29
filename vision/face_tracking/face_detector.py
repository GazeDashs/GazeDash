"""Deteccion facial con MediaPipe Face Landmarker."""

from pathlib import Path
from typing import Optional
import threading

import cv2
import numpy as np


class FaceLandmarks:
    """Indices principales del modelo Face Landmarker."""

    NOSE_TIP = 4
    LEFT_CHEEK = 234
    RIGHT_CHEEK = 454
    LEFT_BROW_MID = 296
    RIGHT_BROW_MID = 66
    LEFT_EYE_TOP = 386
    RIGHT_EYE_TOP = 159
    LEFT_EYE_BOTTOM = 374
    RIGHT_EYE_BOTTOM = 145
    MOUTH_TOP = 13
    MOUTH_BOTTOM = 14
    MOUTH_LEFT = 78
    MOUTH_RIGHT = 308
    LEFT_BROW_INNER = 70
    RIGHT_BROW_INNER = 300
    LEFT_BROW_OUTER = 107
    RIGHT_BROW_OUTER = 336


DEFAULT_LANDMARK_OFFSETS = {
    "left_brow_inner": (0, 0),
    "left_brow_mid": (0, 0),
    "left_brow_outer": (0, 0),
    "right_brow_inner": (0, 0),
    "right_brow_mid": (0, 0),
    "right_brow_outer": (0, 0),
}



DEBUG_BLENDSHAPES = (
    "mouthPucker",
    "mouthFunnel",
    "jawOpen",
    "mouthSmileLeft",
    "mouthSmileRight",
    "browInnerUp",
    "browDownLeft",
    "browDownRight",
    "eyeBlinkLeft",
    "eyeBlinkRight",
    "eyeSquintLeft",
    "eyeSquintRight",
    "eyeWideLeft",
    "eyeWideRight",
    "noseSneerLeft",
    "noseSneerRight",
)

MESH_COLOR = (80, 220, 120)
MESH_POINT_COLOR = (30, 180, 255)


class MediaPipeFaceDetector:
    """Extrae landmarks y metricas faciales desde frames BGR de OpenCV."""

    DEFAULT_MODEL_PATH = (
        Path(__file__).resolve().parents[2]
        / "assets"
        / "models"
        / "face_landmarker.task"
    )

    def __init__(
        self,
        model_path: Optional[Path] = None,
        fps: int = 30,
        detection_confidence: float = 0.7,
        tracking_confidence: float = 0.7,
        draw_landmarks: bool = True,
        live_stream: bool = False,
        landmark_overrides: Optional[dict] = None,
        landmark_offsets: Optional[dict] = None,
    ):
        self.model_path = Path(model_path or self.DEFAULT_MODEL_PATH)
        self.frame_interval_ms = max(1, int(1000 / max(fps, 1)))
        self.draw_landmarks = draw_landmarks
        self._timestamp_ms = 0
        self.landmark_overrides = landmark_overrides or {}
        self.landmark_offsets = {**DEFAULT_LANDMARK_OFFSETS, **(landmark_offsets or {})}

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"No se encontro el modelo de MediaPipe en {self.model_path}."
            )

        try:
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipe no esta instalado. Ejecuta: pip install -r requirements.txt"
            ) from exc

        self.mp = mp
        self._live_stream = live_stream
        # Choose running mode: VIDEO by default, LIVE_STREAM only if requested.
        running_mode = (
            mp.tasks.vision.RunningMode.LIVE_STREAM if live_stream else mp.tasks.vision.RunningMode.VIDEO
        )

        options_kwargs = dict(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=running_mode,
            num_faces=1,
            output_face_blendshapes=True,
            min_face_detection_confidence=detection_confidence,
            min_face_presence_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )

        # Only pass a result_callback when using LIVE_STREAM (required by the Tasks API)
        if live_stream:
            final_kwargs = {**options_kwargs, "result_callback": self._on_result}
        else:
            final_kwargs = options_kwargs

        options = mp.tasks.vision.FaceLandmarkerOptions(**final_kwargs)

        self.face_landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        self._latest_result = None
        self._latest_timestamp = 0
        self._lock = threading.Lock()

    def _on_result(self, result, output_image, timestamp_ms):
        # guardar el resultado para que detect() lo pueda leer
        with self._lock:
            self._latest_result = result
            self._latest_timestamp = timestamp_ms

    def enqueue_frame(self, frame: np.ndarray):
        """API pública: encola un fotograma para procesamiento asíncrono en modo LIVE_STREAM.

        Esto llamará al flujo interno (asíncrono si está disponible). No bloquea
        y el resultado estará disponible mediante `get_latest_result()` o el callback.
        """
        return self._detect_face(frame)

    def get_latest_result(self, frame: Optional[np.ndarray] = None):
        """Devuelve el resultado más reciente.

        Si se proporciona `frame`, transforma el objeto `FaceLandmarkerResult`
        en el mismo dict que devuelve `detect()` (con métricas escaladas por el
        tamaño del frame). Si no se proporciona frame, devuelve el objeto
        crudo (útil solo para inspección).
        """

        with self._lock:
            result = self._latest_result

        if result is None:
            return None

        # Si ya es un dict (por ejemplo, resultado de detect()), devolverlo.
        if isinstance(result, dict):
            return result

        # Si no se proporcionó frame no podemos convertir coordenadas normalizadas
        # a píxeles, así que devolvemos el objeto crudo.
        if frame is None:
            return result

        return self._build_face_data(result, frame)

    def detect(self, frame: np.ndarray) -> Optional[dict]:
        """Devuelve metricas faciales o None si no se detecta una cara."""
        result = self._detect_face(frame)
        if result is None:
            return None

        return self._build_face_data(result, frame)

    def _build_face_data(self, result, frame: np.ndarray) -> dict:
        face_landmarks = result.face_landmarks[0]
        blendshapes = self._extract_blendshapes(result)
        h, w = frame.shape[:2]

        def resolve_index(name: str, default_index: int) -> int:
            value = self.landmark_overrides.get(name, default_index)
            try:
                return int(value)
            except (TypeError, ValueError):
                return default_index

        def resolve_offset(name: str) -> tuple[int, int]:
            value = self.landmark_offsets.get(name, (0, 0))
            if isinstance(value, dict):
                dx = value.get("dx", 0)
                dy = value.get("dy", 0)
            elif isinstance(value, (list, tuple)) and len(value) >= 2:
                dx, dy = value[0], value[1]
            else:
                dx, dy = 0, 0

            try:
                return int(dx), int(dy)
            except (TypeError, ValueError):
                return 0, 0

        def point(index: int, landmark_name: Optional[str] = None) -> np.ndarray:
            landmark = face_landmarks[index]
            dx, dy = resolve_offset(landmark_name) if landmark_name else (0, 0)
            return np.array([landmark.x * w + dx, landmark.y * h + dy, landmark.z * w])

        left_cheek = point(FaceLandmarks.LEFT_CHEEK)
        right_cheek = point(FaceLandmarks.RIGHT_CHEEK)
        nose_tip = point(FaceLandmarks.NOSE_TIP)

        face_center = (left_cheek + right_cheek) / 2
        face_width = np.linalg.norm(right_cheek - left_cheek)
        yaw = (nose_tip[0] - face_center[0]) / (face_width / 2 + 1e-6)

        left_brow_ratio = self._calculate_brow_ratio(
            point,
            resolve_index("left_brow_mid", FaceLandmarks.LEFT_BROW_MID),
            FaceLandmarks.LEFT_EYE_TOP,
            FaceLandmarks.LEFT_EYE_BOTTOM,
            landmark_name="left_brow_mid",
        )
        right_brow_ratio = self._calculate_brow_ratio(
            point,
            resolve_index("right_brow_mid", FaceLandmarks.RIGHT_BROW_MID),
            FaceLandmarks.RIGHT_EYE_TOP,
            FaceLandmarks.RIGHT_EYE_BOTTOM,
            landmark_name="right_brow_mid",
        )
        brow_ratio = (left_brow_ratio + right_brow_ratio) / 2

        mouth_top = point(FaceLandmarks.MOUTH_TOP)
        mouth_bottom = point(FaceLandmarks.MOUTH_BOTTOM)
        mouth_left = point(FaceLandmarks.MOUTH_LEFT)
        mouth_right = point(FaceLandmarks.MOUTH_RIGHT)
        mouth_open = np.linalg.norm(mouth_top - mouth_bottom)
        mouth_width = np.linalg.norm(mouth_right - mouth_left) + 1e-6
        mouth_ratio = mouth_open / mouth_width

        debug_blendshapes = self._select_blendshapes(blendshapes)

        nose_tip = point(FaceLandmarks.NOSE_TIP)
        face_center = (left_cheek + right_cheek) / 2

        if self.draw_landmarks:
            self._draw_face_mesh(frame, face_landmarks, h, w)

        return {
            "yaw": float(yaw),
            "brow_ratio": float(brow_ratio),
            "left_brow_ratio": float(left_brow_ratio),
            "right_brow_ratio": float(right_brow_ratio),
            "mouth_ratio": float(mouth_ratio),
            "nose_tip": (int(nose_tip[0]), int(nose_tip[1])),
            "face_center": (int(face_center[0]), int(face_center[1])),
            "cheek_puff_score": float(blendshapes.get("cheekPuff", 0.0)),
            "mouth_pucker_score": float(blendshapes.get("mouthPucker", 0.0)),
            "jaw_open_score": float(blendshapes.get("jawOpen", 0.0)),
            "mouth_funnel_score": float(blendshapes.get("mouthFunnel", 0.0)),
            "smile_left": float(blendshapes.get("mouthSmileLeft", 0.0)),
            "smile_right": float(blendshapes.get("mouthSmileRight", 0.0)),
            "brow_inner_up": float(blendshapes.get("browInnerUp", 0.0)),
            "brow_down_left": float(blendshapes.get("browDownLeft", 0.0)),
            "brow_down_right": float(blendshapes.get("browDownRight", 0.0)),
            "eye_blink_left": float(blendshapes.get("eyeBlinkLeft", 0.0)),
            "eye_blink_right": float(blendshapes.get("eyeBlinkRight", 0.0)),
            "eye_squint_left": float(blendshapes.get("eyeSquintLeft", 0.0)),
            "eye_squint_right": float(blendshapes.get("eyeSquintRight", 0.0)),
            "eye_wide_left": float(blendshapes.get("eyeWideLeft", 0.0)),
            "eye_wide_right": float(blendshapes.get("eyeWideRight", 0.0)),
            "nose_sneer_left": float(blendshapes.get("noseSneerLeft", 0.0)),
            "nose_sneer_right": float(blendshapes.get("noseSneerRight", 0.0)),
            "blendshapes": blendshapes,
            "debug_blendshapes": debug_blendshapes,
            "confidence": 1.0,
        }

    def _calculate_brow_ratio(self, point, brow_index, eye_top_index, eye_bottom_index, landmark_name: Optional[str] = None):
        brow_mid = point(brow_index, landmark_name)
        eye_top = point(eye_top_index)
        eye_bottom = point(eye_bottom_index)
        eye_height = np.linalg.norm(eye_top - eye_bottom) + 1e-6
        return np.linalg.norm(brow_mid - eye_top) / eye_height

    def _detect_face(self, frame: np.ndarray):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)

        self._timestamp_ms += self.frame_interval_ms

        # llamada asíncrona solo si el detector fue inicializado en LIVE_STREAM
        if self._live_stream and hasattr(self.face_landmarker, "detect_async"):
            self.face_landmarker.detect_async(mp_image, self._timestamp_ms)
        else:
            # fallback: mantener detect_for_video para compatibilidad
            result = self.face_landmarker.detect_for_video(mp_image, self._timestamp_ms)
            self._latest_result = result

        # devolver el último resultado disponible (puede ser None la primera vez)
        return self._latest_result

    def _extract_blendshapes(self, result) -> dict:
        if not result.face_blendshapes:
            return {}

        return {
            category.category_name: category.score
            for category in result.face_blendshapes[0]
        }

    def _select_blendshapes(self, blendshapes: dict) -> dict:
        return {name: float(blendshapes.get(name, 0.0)) for name in DEBUG_BLENDSHAPES}

    def _draw_face_mesh(self, frame, face_landmarks, height: int, width: int):
        points = self._landmarks_to_points(face_landmarks, height, width)

        if len(points) < 3:
            return

        overlay = frame.copy()
        self._draw_delaunay_mesh(overlay, points, height, width)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        self._draw_key_landmarks(frame, face_landmarks, height, width)

    def _landmarks_to_points(self, face_landmarks, height: int, width: int) -> list:
        points = []
        for landmark in face_landmarks:
            x = min(max(int(landmark.x * width), 0), width - 1)
            y = min(max(int(landmark.y * height), 0), height - 1)
            points.append((x, y))
        return points

    def _draw_delaunay_mesh(self, frame, points: list, height: int, width: int):
        subdiv = cv2.Subdiv2D((0, 0, width, height))

        for point in points:
            try:
                subdiv.insert(point)
            except cv2.error:
                continue

        for triangle in subdiv.getTriangleList():
            pt1 = (int(triangle[0]), int(triangle[1]))
            pt2 = (int(triangle[2]), int(triangle[3]))
            pt3 = (int(triangle[4]), int(triangle[5]))

            if not all(self._is_inside_frame(pt, height, width) for pt in (pt1, pt2, pt3)):
                continue

            cv2.line(frame, pt1, pt2, MESH_COLOR, 1, cv2.LINE_AA)
            cv2.line(frame, pt2, pt3, MESH_COLOR, 1, cv2.LINE_AA)
            cv2.line(frame, pt3, pt1, MESH_COLOR, 1, cv2.LINE_AA)

    def _is_inside_frame(self, point, height: int, width: int) -> bool:
        x, y = point
        return 0 <= x < width and 0 <= y < height

    def _draw_key_landmarks(self, frame, face_landmarks, height: int, width: int):
        def resolve_index(name: str, default_index: int) -> int:
            value = self.landmark_overrides.get(name, default_index)
            try:
                return int(value)
            except (TypeError, ValueError):
                return default_index

        def resolve_offset(name: str) -> tuple[int, int]:
            value = self.landmark_offsets.get(name, (0, 0))
            if isinstance(value, dict):
                dx = value.get("dx", 0)
                dy = value.get("dy", 0)
            elif isinstance(value, (list, tuple)) and len(value) >= 2:
                dx, dy = value[0], value[1]
            else:
                dx, dy = 0, 0

            try:
                return int(dx), int(dy)
            except (TypeError, ValueError):
                return 0, 0

        key_points = [
            ("nose_tip", FaceLandmarks.NOSE_TIP),
            ("left_cheek", FaceLandmarks.LEFT_CHEEK),
            ("right_cheek", FaceLandmarks.RIGHT_CHEEK),
            ("left_brow_inner", FaceLandmarks.LEFT_BROW_INNER),
            ("left_brow_mid", FaceLandmarks.LEFT_BROW_MID),
            ("left_brow_outer", FaceLandmarks.LEFT_BROW_OUTER),
            ("left_eye_top", FaceLandmarks.LEFT_EYE_TOP),
            ("left_eye_bottom", FaceLandmarks.LEFT_EYE_BOTTOM),
            ("right_brow_inner", FaceLandmarks.RIGHT_BROW_INNER),
            ("right_brow_mid", FaceLandmarks.RIGHT_BROW_MID),
            ("right_brow_outer", FaceLandmarks.RIGHT_BROW_OUTER),
            ("right_eye_top", FaceLandmarks.RIGHT_EYE_TOP),
            ("right_eye_bottom", FaceLandmarks.RIGHT_EYE_BOTTOM),
            ("mouth_top", FaceLandmarks.MOUTH_TOP),
            ("mouth_bottom", FaceLandmarks.MOUTH_BOTTOM),
            ("mouth_left", FaceLandmarks.MOUTH_LEFT),
            ("mouth_right", FaceLandmarks.MOUTH_RIGHT),
            ("eye_blink_left", FaceLandmarks.LEFT_EYE_TOP),
            ("eye_blink_right", FaceLandmarks.RIGHT_EYE_TOP),
        ]

        for name, default_index in key_points:
            index = resolve_index(name, default_index)
            landmark = face_landmarks[index]
            dx, dy = resolve_offset(name)
            center = (int(landmark.x * width) + dx, int(landmark.y * height) + dy)
            cv2.circle(frame, center, 3, MESH_POINT_COLOR, -1)

    def get_resolved_landmark_pixel(self, face_landmarks, name: str, height: int, width: int):
        """Devuelve (x,y) del landmark `name` aplicando overrides y offsets.

        `face_landmarks` debe ser el objeto result.face_landmarks[0].
        """
        # mapping of default names to indices (kept in sync with key_points)
        defaults = {
            "nose_tip": FaceLandmarks.NOSE_TIP,
            "left_cheek": FaceLandmarks.LEFT_CHEEK,
            "right_cheek": FaceLandmarks.RIGHT_CHEEK,
            "left_brow_inner": FaceLandmarks.LEFT_BROW_INNER,
            "left_brow_mid": FaceLandmarks.LEFT_BROW_MID,
            "left_brow_outer": FaceLandmarks.LEFT_BROW_OUTER,
            "left_eye_top": FaceLandmarks.LEFT_EYE_TOP,
            "left_eye_bottom": FaceLandmarks.LEFT_EYE_BOTTOM,
            "right_brow_inner": FaceLandmarks.RIGHT_BROW_INNER,
            "right_brow_mid": FaceLandmarks.RIGHT_BROW_MID,
            "right_brow_outer": FaceLandmarks.RIGHT_BROW_OUTER,
            "right_eye_top": FaceLandmarks.RIGHT_EYE_TOP,
            "right_eye_bottom": FaceLandmarks.RIGHT_EYE_BOTTOM,
            "mouth_top": FaceLandmarks.MOUTH_TOP,
            "mouth_bottom": FaceLandmarks.MOUTH_BOTTOM,
            "mouth_left": FaceLandmarks.MOUTH_LEFT,
            "mouth_right": FaceLandmarks.MOUTH_RIGHT,
            "eye_blink_left": FaceLandmarks.LEFT_EYE_TOP,
            "eye_blink_right": FaceLandmarks.RIGHT_EYE_TOP,
        }

        default_idx = defaults.get(name)
        if default_idx is None:
            raise KeyError(f"Unknown landmark name: {name}")

        idx = int(self.landmark_overrides.get(name, default_idx))
        lm = face_landmarks[idx]
        off = self.landmark_offsets.get(name, (0, 0))
        if isinstance(off, dict):
            dx, dy = off.get("dx", 0), off.get("dy", 0)
        elif isinstance(off, (list, tuple)) and len(off) >= 2:
            dx, dy = off[0], off[1]
        else:
            dx, dy = 0, 0

        try:
            dx, dy = int(dx), int(dy)
        except Exception:
            dx, dy = 0, 0

        x = int(lm.x * width) + dx
        y = int(lm.y * height) + dy
        return x, y

    def close(self):
        if hasattr(self, "face_landmarker") and self.face_landmarker:
            self.face_landmarker.close()

def detect_faces(frame: np.ndarray) -> Optional[dict]:
    """Funcion simple de compatibilidad para detectar una cara en un frame."""
    detector = MediaPipeFaceDetector()
    try:
        return detector.detect(frame)
    finally:
        detector.close()
