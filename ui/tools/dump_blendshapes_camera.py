import sys
from pathlib import Path
import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision as mp_vision
from mediapipe import tasks as mp_tasks

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

MODEL_PATH = "assets/models/face_landmarker.task"


def main():
    opts = mp_vision.FaceLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=mp_vision.RunningMode.IMAGE,
        num_faces=1,
    )
    landmarker = mp_vision.FaceLandmarker.create_from_options(opts)

    cap = cv2.VideoCapture(0)
    if not cap or not cap.isOpened():
        print('No camera available; cannot list blendshapes.')
        return
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        print('Camera opened but failed to read a frame.')
        return

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    res = landmarker.detect(mp_img)
    if res and getattr(res, 'face_blendshapes', None):
        for c in res.face_blendshapes[0]:
            print(c.category_name, c.score)
    else:
        print('No blendshapes in result')


if __name__ == '__main__':
    main()
