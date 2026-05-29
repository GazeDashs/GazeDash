import sys
from pathlib import Path
import json
import cv2

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from vision.face_tracking.face_detector import MediaPipeFaceDetector

USER_SETTINGS = Path("config") / "user_settings.json"

DEFAULTS = {
    "cheek_puff": 0.5,
    "mouth_pucker": 0.5,
    "mouth_open": 0.08,
    "brow_raise": 2.4,
}

PARAM_KEYS = ["cheek_puff", "mouth_pucker", "mouth_open", "brow_raise"]

STEP = 0.01


def load_settings():
    if USER_SETTINGS.exists():
        try:
            with open(USER_SETTINGS, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if "gesture_thresholds" in data:
                    return data.get("gesture_thresholds", DEFAULTS)
                active_profile = data.get("active_profile") or data.get("profile")
                profiles = data.get("profiles", {})
                if active_profile and isinstance(profiles, dict):
                    profile = profiles.get(active_profile, {})
                    if isinstance(profile, dict):
                        return profile.get("gesture_thresholds", DEFAULTS)
                return DEFAULTS
        except Exception:
            return DEFAULTS.copy()
    return DEFAULTS.copy()


def save_settings(settings):
    USER_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    with open(USER_SETTINGS, "w", encoding="utf-8") as fh:
        json.dump({"gesture_thresholds": settings, "active_profile": "navegacion"}, fh, indent=2, ensure_ascii=False)


def main():
    settings = load_settings()
    sel = 0

    detector = MediaPipeFaceDetector(draw_landmarks=True)

    cap = cv2.VideoCapture(0)
    if not cap or not cap.isOpened():
        print("No camera available")
        return

    print("Calibración de gestos: teclas 1-4 seleccionar parámetro, +/- ajustar, s guardar, q salir")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        face_data = detector.detect(frame)

        blendshapes = face_data.get("blendshapes", {}) if face_data else {}

        # Map display values
        display = {
            "cheek_puff": blendshapes.get("cheekPuff", face_data.get("cheek_puff_score") if face_data else 0.0),
            "mouth_pucker": blendshapes.get("mouthPucker", face_data.get("mouth_pucker_score") if face_data else 0.0),
            "mouth_open": face_data.get("mouth_ratio", 0.0) if face_data else 0.0,
            "brow_raise": face_data.get("brow_ratio", 0.0) if face_data else 0.0,
        }

        # Draw info with activation status
        h, w = frame.shape[:2]
        y = 24
        for i, key in enumerate(PARAM_KEYS):
            sel_mark = ">" if i == sel else " "
            # determine activation based on current threshold
            val = display[key]
            th = settings[key]
            active = val >= th
            status_text = "ON" if active else "off"
            color = (0, 200, 0) if active else (0, 0, 200)

            # draw status circle
            cv2.circle(frame, (8, y - 6), 6, color, -1)

            cv2.putText(frame, f"{sel_mark} {i+1}. {key}: {val:.3f} (th={th:.3f}) [{status_text}]",
                        (24, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            y += 28

        cv2.imshow("Calibrate Gestures", frame)
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        elif k in (ord("1"), ord("2"), ord("3"), ord("4")):
            sel = int(chr(k)) - 1
        elif k in (ord("+"), ord("=")):
            key = PARAM_KEYS[sel]
            settings[key] = round(settings[key] + STEP, 4)
        elif k == ord("-"):
            key = PARAM_KEYS[sel]
            settings[key] = round(max(0.0, settings[key] - STEP), 4)
        elif k == ord("s"):
            save_settings(settings)
            print("Guardado:", settings)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
