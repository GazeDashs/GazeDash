"""Controlador principal de la aplicación (placeholder)."""

import cv2
from pathlib import Path

from config.config_manager import ConfigManager

from vision.camera.camera_stream import close_camera, open_camera, read_frame
from vision.face_tracking.face_detector import MediaPipeFaceDetector
from vision.gesture_detection.facial_gestures import FacialGestureDetector
from core.gesture_engine.cooldown_manager import CooldownManager
from core.gesture_engine.gesture_mapper import map_gesture
from core.gesture_engine.hotkey_executor import HotkeyExecutor
from core.voice_control.voice_control import VoiceCommandController

class AppController:
    _GESTURE_META_KEYS = {"has_face", "calibrating", "calibration_progress"}

    def __init__(self):
        self.cap = None
        self.config_manager = ConfigManager(Path("config") / "user_settings.json")
        self.config = self.config_manager.load_merged()

        face_landmarks_cfg = {}
        if isinstance(self.config, dict):
            face_landmarks_cfg = self.config.get("face_landmarks", {}) or {}

        self.face_detector = MediaPipeFaceDetector(
            live_stream=True,
            draw_landmarks=False,
            landmark_overrides=face_landmarks_cfg.get("indices", {}),
            landmark_offsets=face_landmarks_cfg.get("offsets", {}),
        )
        self.gesture_detector = FacialGestureDetector()
        self.gesture_executor = HotkeyExecutor()
        self.voice_controller = VoiceCommandController(self.config, status_callback=lambda message: print(f"Voz: {message}"))
        self.voice_controller.start()
        self.cooldown_manager = CooldownManager(cooldown_seconds=0.5) 
        # interactive landmark adjustment state
        self._last_face_landmarks = None
        self._last_frame_size = (0, 0)
        self._dragging = False
        self._drag_name = None
        self._drag_start = (0, 0)
        self._drag_orig_offset = (0, 0)
        self._drag_offset_live = (0, 0)  # current offset during drag
        # all editable landmarks
        self._editable_landmarks = [
            "left_brow_inner", "left_brow_mid", "left_brow_outer",
            "right_brow_inner", "right_brow_mid", "right_brow_outer",
            "left_eye_top", "left_eye_bottom",
            "right_eye_top", "right_eye_bottom",
            "mouth_top", "mouth_bottom", "mouth_left", "mouth_right",
        ]
        self._selected_landmark_idx = 0  # for cycling with keys

        # prepare window and mouse callback
        cv2.namedWindow("GazeDash - Camara")
        cv2.setMouseCallback("GazeDash - Camara", self._on_mouse)

    def run(self):
        self.cap = open_camera(0)
        # ensure the neutral baseline is collected before entering main loop
        self._ensure_neutral_calibrated()

        try:
            while True:
                frame = read_frame(self.cap)

                if frame is None:
                    continue

                # Feed frame to the detector (schedules async processing in LIVE_STREAM).
                # `_detect_face` will enqueue the frame; the callback updates `_latest_result`.
                # Enqueue frame for async processing and read latest result safely
                try:
                    self.face_detector.enqueue_frame(frame)
                    raw_face_result = self.face_detector.get_latest_result()
                    face_data = self.face_detector.get_latest_result(frame)
                except Exception:
                    # fallback to synchronous detect if async not available
                    raw_face_result = self.face_detector._detect_face(frame)
                    face_data = self.face_detector.get_latest_result(frame)
                # keep last landmarks for interactive adjustments
                face_landmarks_list = getattr(raw_face_result, "face_landmarks", None)
                if face_landmarks_list:
                    self._last_face_landmarks = face_landmarks_list[0]
                    self._last_frame_size = frame.shape[:2]
                gestures = self.gesture_detector.detect(face_data)
                self._handle_gestures(gestures)
                self.voice_controller.handle_gesture_input(gestures)
                if raw_face_result is not None:
                    self.draw_face_mesh(frame, raw_face_result)
                if face_data is not None:
                    self._draw_face_metrics(frame, face_data, gestures)
                self._draw_landmarks_overlay(frame)
                self._draw_shortcuts(frame)

                cv2.imshow("GazeDash - Camara", frame)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key == ord("g"):
                    # start interactive gesture calibration flow
                    self.run_gesture_calibration_flow()
                if key == ord("r"):
                    # rerun the full gesture calibration sequence
                    self.run_initial_full_calibration()
                # landmark selection: +/- to cycle through available points
                if key in (ord("+"), ord("=")) or key == 82:  # + or UP arrow
                    self._selected_landmark_idx = (self._selected_landmark_idx + 1) % len(self._editable_landmarks)
                if key in (ord("-"), ord("_")) or key == 84:  # - or DOWN arrow
                    self._selected_landmark_idx = (self._selected_landmark_idx - 1) % len(self._editable_landmarks)
        finally:
            self.gesture_executor.release_all_holds()
            close_camera(self.cap)
            self.face_detector.close()
            self.voice_controller.stop()
            cv2.destroyAllWindows()

    def draw_face_mesh(self, frame, face_result):
        if frame is None or face_result is None:
            return

        face_landmarks = getattr(face_result, "face_landmarks", None)
        if not face_landmarks:
            return

        height, width = frame.shape[:2]
        self.face_detector._draw_face_mesh(frame, face_landmarks[0], height, width)

    def _draw_face_metrics(self, frame, face_data, gestures):
        status_state = "CALIBRANDO" if gestures.get("calibrating") else "LISTO"
        progress = gestures.get("calibration_progress", 1.0)
        pucker_state = "ON" if gestures["mouth_pucker"] else "off"
        pucker_threshold = self.gesture_detector._scaled_threshold(
            "mouth_pucker", self.gesture_detector.thresholds.mouth_pucker
        )
        pucker_neutral = self.gesture_detector._neutral_value("mouth_pucker_score")
        pucker_effective_threshold = max(pucker_neutral + 0.25, pucker_threshold)
        pucker_counter = self.gesture_detector._gesture_counters.get("mouth_pucker", 0)
        debug_blendshapes = " ".join(
            f"{name}:{score:.3f}"
            for name, score in face_data.get("debug_blendshapes", {}).items()
        )
        lines = [
            f"estado={status_state} progreso={progress:.0%}",
            (
                f"yaw={face_data['yaw']:.2f} "
                f"brow L/R={face_data['left_brow_ratio']:.2f}/"
                f"{face_data['right_brow_ratio']:.2f} "
                f"mouth={face_data['mouth_ratio']:.2f}"
            ),
            f"mouthPucker={face_data['mouth_pucker_score']:.4f} thr={pucker_threshold:.3f} eff={pucker_effective_threshold:.3f} cnt={pucker_counter} {pucker_state}",
            f"debug: {debug_blendshapes}",
        ]

        for index, line in enumerate(lines):
            cv2.putText(
                frame,
                line,
                (12, 28 + index * 26),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (80, 220, 120),
                2,
                cv2.LINE_AA,
            )
    def _handle_gestures(self, gestures):
        if not gestures or not gestures.get("has_face"):
            self.gesture_executor.release_all_holds()
            return

        if gestures.get("calibrating"):
            self.gesture_executor.release_all_holds()
            return

        for gesture_name, is_active in gestures.items():
            if gesture_name in self._GESTURE_META_KEYS:
                continue

            action = map_gesture(gesture_name, self.config)
            if not action:
                if is_active:
                    print(f"Gesto activo sin mapeo: {gesture_name}")
                continue

            if self.gesture_executor.is_hold_action(action):
                try:
                    self.gesture_executor.update_hold(gesture_name, action, bool(is_active))
                except RuntimeError as exc:
                    print(f"No se pudo mantener la accion para {gesture_name}: {exc}")
                continue

            if not is_active:
                continue

            # usa label o nombre de gesto como clave de cooldown
            cooldown_key = action.get("label") or gesture_name
            if not self.cooldown_manager.allow(cooldown_key):
                print(f"Gesto activo en cooldown: {gesture_name} -> {cooldown_key}")
                continue

            print(f"Gesto activo: {gesture_name} -> {action.get('label') or action}")

            try:
                executed = self.gesture_executor.execute(action)
                if executed:
                    print(f"Accion ejecutada: {action.get('label') or action}")
                else:
                    print(f"Accion no ejecutable para {gesture_name}: {action}")
            except RuntimeError as exc:
                # pyautogui no instalado u otro fallo de ejecución
                print(f"No se pudo ejecutar la accion para {gesture_name}: {exc}")

    def run_gesture_calibration_flow(self):
        """Interactive flow: choose a gesture, wait for neutral calibration,
        prompt the user to perform the gesture, collect samples, compute a
        recommended threshold and save it to user config.
        """
        SUPPORTED = [
            "mouth_pucker",
            "mouth_open",
            "mouth_o",
            "smile",
            "smile_left",
            "smile_right",
            "brow_raise",
            "brow_frown",
            "eye_blink",
            "eye_wide",
            "nose_sneer",
        ]

        # ensure camera is open
        if self.cap is None:
            self.cap = open_camera(0)

        # display selection overlay until a valid key is pressed
        selected = None
        prompt_lines = [f"Calibracion de gesto: pulsa numero para elegir"] + [f"{i+1}. {g}" for i, g in enumerate(SUPPORTED)]
        while selected is None:
            frame = read_frame(self.cap)
            if frame is None:
                continue
            h = 20
            for L in prompt_lines:
                cv2.putText(frame, L, (12, h), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 180, 80), 2)
                h += 28
            cv2.putText(frame, "Pulsa tecla 'q' para cancelar", (12, h + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 80, 80), 1)
            cv2.imshow("GazeDash - Calibracion gesto", frame)
            k = cv2.waitKey(1) & 0xFF
            if k in (ord("q"), 27):
                break
            if ord("1") <= k <= ord(str(min(9, len(SUPPORTED)))):
                idx = k - ord("1")
                if idx < len(SUPPORTED):
                    selected = SUPPORTED[idx]

        if not selected:
            return

        # Ensure neutral calibration is ready
        while not self.gesture_detector.is_calibrated():
            frame = read_frame(self.cap)
            if frame is None:
                continue
            cv2.putText(frame, "Esperando calibracion neutral... mantente quieto", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 50), 2)
            cv2.imshow("GazeDash - Calibracion gesto", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                return

        # countdown
        for sec in (3, 2, 1):
            frame = read_frame(self.cap)
            if frame is None:
                continue
            cv2.putText(frame, f"Comenzando en {sec}... realiza: {selected}", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 200, 120), 2)
            cv2.imshow("GazeDash - Calibracion gesto", frame)
            cv2.waitKey(1000)

        # collect samples for a short duration
        duration = 2.0
        end_at = cv2.getTickCount() + int(duration * cv2.getTickFrequency())
        samples = []
        while cv2.getTickCount() < end_at:
            frame = read_frame(self.cap)
            if frame is None:
                continue
            try:
                raw = self.face_detector.get_latest_result(frame)
                face_data = raw if isinstance(raw, dict) else self.face_detector.get_latest_result(frame)
            except Exception:
                face_data = self.face_detector._detect_face(frame)

            if face_data is None:
                cv2.putText(frame, "No se detecta rostro, acércate", (12, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 80, 80), 2)
                cv2.imshow("GazeDash - Calibracion gesto", frame)
                cv2.waitKey(1)
                continue

            metrics = self.gesture_detector._normalize_face_data(face_data)
            samples.append(metrics)

            cv2.putText(frame, f"Recolectando muestras para {selected}... {len(samples)}", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 200, 120), 2)
            cv2.imshow("GazeDash - Calibracion gesto", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                return

        # compute recommended threshold and save
        try:
            recommended = self.gesture_detector.calibrate_gesture_from_samples(selected, samples)
            self.gesture_detector.save_gesture_threshold_to_user_config(selected, recommended)
            self._refresh_gesture_thresholds()
        except Exception as exc:
            recommended = None
            print(f"Error calibrando gesto {selected}: {exc}")

        # show result
        show_msg = f"Umbral guardado: {selected} = {recommended:.4f}" if recommended is not None else "Fallo al guardar umbral"
        for i in range(30):
            frame = read_frame(self.cap)
            if frame is None:
                continue
            cv2.putText(frame, show_msg, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (120, 220, 200), 2)
            cv2.imshow("GazeDash - Calibracion gesto", frame)
            cv2.waitKey(30)

        # close calibration window
        cv2.destroyWindow("GazeDash - Calibracion gesto")

    def _draw_landmarks_overlay(self, frame):
        """Show landmark name and offset during drag."""
        if not self._dragging or self._drag_name is None:
            return
        
        if frame is None:
            return
        
        height, width = frame.shape[:2]
        dx, dy = self._drag_offset_live
        overlay_text = f"{self._drag_name}: dx={dx} dy={dy}"
        
        cv2.putText(
            frame,
            overlay_text,
            (12, height - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (50, 255, 50),
            2,
            cv2.LINE_AA,
        )

    def _draw_shortcuts(self, frame):
        if frame is None:
            return

        height, width = frame.shape[:2]
        help_lines = [
            "q/ESC: salir", "g: calibrar gesto", "r: recalibrar todo",
            "+/-: cambiar punto", "drag: ajustar offset"
        ]
        x = 12
        y = max(22, height - 72)

        for line in help_lines:
            cv2.putText(
                frame,
                line,
                (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (200, 200, 200),
                1,
                cv2.LINE_AA,
            )
            y += 16
        
        # show currently selected landmark (if not dragging)
        if not self._dragging and len(self._editable_landmarks) > 0:
            selected_name = self._editable_landmarks[self._selected_landmark_idx % len(self._editable_landmarks)]
            sel_text = f"Selec: {selected_name}"
            cv2.putText(
                frame,
                sel_text,
                (x, y + 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (100, 255, 100),
                2,
                cv2.LINE_AA,
            )

    def _on_mouse(self, event, x, y, flags, param):
        """Mouse callback: click near a landmark to drag and save offset.

        - Press left button on/near a drawn landmark to start dragging.
        - Move mouse to change offset (pixels). Release to save to config.
        """
        # only operate if we have a recent face_landmarks
        if self._last_face_landmarks is None:
            return

        height, width = self._last_frame_size

        if event == cv2.EVENT_LBUTTONDOWN:
            # find nearest editable landmark
            best = None
            best_dist = 9999
            for name in self._editable_landmarks:
                try:
                    px, py = self.face_detector.get_resolved_landmark_pixel(self._last_face_landmarks, name, height, width)
                except Exception:
                    continue
                d = (px - x) ** 2 + (py - y) ** 2
                if d < best_dist:
                    best_dist = d
                    best = (name, px, py)

            # threshold ~ 20 px
            if best and best_dist <= 20 * 20:
                name, px, py = best
                self._dragging = True
                self._drag_name = name
                self._drag_start = (x, y)
                # read original offset from user config (prefer user file)
                user_cfg = self.config_manager.load() or {}
                fl = user_cfg.get("face_landmarks", {})
                offsets = fl.get("offsets", {}) if isinstance(fl, dict) else {}
                orig = offsets.get(name, [0, 0])
                if isinstance(orig, dict):
                    ox, oy = orig.get("dx", 0), orig.get("dy", 0)
                elif isinstance(orig, (list, tuple)) and len(orig) >= 2:
                    ox, oy = orig[0], orig[1]
                else:
                    ox, oy = 0, 0
                try:
                    ox, oy = int(ox), int(oy)
                except Exception:
                    ox, oy = 0, 0
                self._drag_orig_offset = (ox, oy)

        elif event == cv2.EVENT_MOUSEMOVE and self._dragging and self._drag_name:
            dx = x - self._drag_start[0]
            dy = y - self._drag_start[1]
            new_off = (self._drag_orig_offset[0] + dx, self._drag_orig_offset[1] + dy)
            self._drag_offset_live = new_off
            # update live detector offsets
            if not hasattr(self.face_detector, "landmark_offsets"):
                self.face_detector.landmark_offsets = {}
            self.face_detector.landmark_offsets[self._drag_name] = new_off

        elif event == cv2.EVENT_LBUTTONUP and self._dragging and self._drag_name:
            dx = x - self._drag_start[0]
            dy = y - self._drag_start[1]
            new_off = (self._drag_orig_offset[0] + dx, self._drag_orig_offset[1] + dy)
            # persist to user_settings.json
            user_cfg = self.config_manager.load() or {}
            if not isinstance(user_cfg, dict):
                user_cfg = {}
            fl = user_cfg.get("face_landmarks") or {}
            offsets = fl.get("offsets") or {}
            offsets[self._drag_name] = [int(new_off[0]), int(new_off[1])]
            fl["offsets"] = offsets
            user_cfg["face_landmarks"] = fl
            try:
                self.config_manager.save(user_cfg)
                # update in-memory merged config too
                self.config = self.config_manager.load_merged()
            except Exception as exc:
                print(f"No se pudo guardar offset: {exc}")

            # ensure detector has the final offset
            self.face_detector.landmark_offsets[self._drag_name] = (int(new_off[0]), int(new_off[1]))
            # clear drag state
            self._dragging = False
            self._drag_name = None
            self._drag_start = (0, 0)
            self._drag_orig_offset = (0, 0)
            self._drag_offset_live = (0, 0)

    def run_initial_full_calibration(self):
        """Run an initial calibration sequence for all supported gestures.

        For each gesture: prompt, countdown, collect samples, compute recommended
        threshold and save it. Finally mark `initial_gesture_calibrated` in user config.
        """
        SUPPORTED = [
            "mouth_pucker",
            "mouth_open",
            "mouth_o",
            "smile",
            "smile_left",
            "smile_right",
            "brow_raise",
            "brow_frown",
            "eye_blink",
            "eye_wide",
            "nose_sneer",
        ]

        results = {}
        for gesture in SUPPORTED:
            # short instructions
            start_time = cv2.getTickCount()
            for i in range(30):
                frame = read_frame(self.cap)
                if frame is None:
                    continue
                cv2.putText(frame, f"Proxima calibracion: {gesture}", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (220, 200, 80), 2)
                cv2.putText(frame, "Prepárate y mantén la pose cuando indique", (12, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 180, 80), 1)
                cv2.imshow("GazeDash - Calibracion inicial", frame)
                cv2.waitKey(30)

            # countdown
            for sec in (3, 2, 1):
                frame = read_frame(self.cap)
                if frame is None:
                    continue
                cv2.putText(frame, f"Comienza en {sec}... realiza: {gesture}", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 200, 120), 2)
                cv2.imshow("GazeDash - Calibracion inicial", frame)
                cv2.waitKey(1000)

            # collect samples
            duration = 2.0
            end_at = cv2.getTickCount() + int(duration * cv2.getTickFrequency())
            samples = []
            while cv2.getTickCount() < end_at:
                frame = read_frame(self.cap)
                if frame is None:
                    continue
                try:
                    raw = self.face_detector.get_latest_result(frame)
                    face_data = raw if isinstance(raw, dict) else self.face_detector.get_latest_result(frame)
                except Exception:
                    face_data = self.face_detector._detect_face(frame)

                if face_data is None:
                    cv2.putText(frame, "No se detecta rostro, acércate", (12, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 80, 80), 2)
                    cv2.imshow("GazeDash - Calibracion inicial", frame)
                    cv2.waitKey(1)
                    continue

                metrics = self.gesture_detector._normalize_face_data(face_data)
                samples.append(metrics)

                cv2.putText(frame, f"Recolectando {gesture}... {len(samples)}", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 200, 120), 2)
                cv2.imshow("GazeDash - Calibracion inicial", frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    cv2.destroyWindow("GazeDash - Calibracion inicial")
                    return

            # compute and save
            try:
                recommended = self.gesture_detector.calibrate_gesture_from_samples(gesture, samples)

                # Validate the recommended threshold against a short set of neutral samples.
                # If the threshold causes activations on neutral frames, increase it iteratively.
                for attempt in range(5):
                    neutral_bad = False
                    # collect a few neutral checks
                    checks = 12
                    checked = 0
                    for _ in range(checks * 3):
                        frame = read_frame(self.cap)
                        if frame is None:
                            continue
                        try:
                            raw = self.face_detector.get_latest_result(frame)
                            face_data = raw if isinstance(raw, dict) else self.face_detector.get_latest_result(frame)
                        except Exception:
                            face_data = self.face_detector._detect_face(frame)

                        if face_data is None:
                            continue

                        metrics = self.gesture_detector._normalize_face_data(face_data)
                        checked += 1

                        # simple check: replicate the detector's raw_gesture logic for this gesture
                        triggered = False
                        if gesture == "brow_raise":
                            bs_delta = metrics.get("brow_inner_up", 0.0) - self.gesture_detector._neutral_value("brow_inner_up")
                            br_delta = metrics.get("brow_ratio", 0.0) - self.gesture_detector._neutral_value("brow_ratio")
                            if (
                                metrics.get("brow_inner_up", 0.0)
                                >= self.gesture_detector._neutral_value("brow_inner_up")
                                + self.gesture_detector._scaled_threshold("brow_raise", recommended)
                                or metrics.get("brow_ratio", 0.0) >= self.gesture_detector._neutral_value("brow_ratio") + self.gesture_detector.GEOMETRY_DELTAS["brow_raise"]
                            ):
                                triggered = True
                        else:
                            # generic: test primary fields from calibrator mapping
                            fields_map = {
                                "mouth_pucker": ["mouth_pucker_score"],
                                "mouth_open": ["jaw_open_score", "mouth_ratio"],
                                "mouth_o": ["mouth_funnel_score", "jaw_open_score"],
                                "smile": ["smile_left", "smile_right", "mouth_ratio"],
                                "smile_left": ["smile_left"],
                                "smile_right": ["smile_right"],
                                "brow_frown": ["brow_down_left", "brow_down_right"],
                                "eye_blink": ["eye_blink_left", "eye_blink_right"],
                                "eye_wide": ["eye_wide_left", "eye_wide_right"],
                                "nose_sneer": ["nose_sneer_left", "nose_sneer_right"],
                            }
                            fields = fields_map.get(gesture, [])
                            for f in fields:
                                if metrics.get(f, 0.0) >= self.gesture_detector._neutral_value(f) + self.gesture_detector._scaled_threshold(gesture, recommended):
                                    triggered = True
                                    break

                        if triggered:
                            neutral_bad = True
                            break
                        if checked >= checks:
                            break

                    if not neutral_bad:
                        break
                    # otherwise increase recommended threshold
                    recommended = float(recommended) * 1.5

                self.gesture_detector.save_gesture_threshold_to_user_config(gesture, recommended)
                results[gesture] = recommended
            except Exception as exc:
                results[gesture] = None
                print(f"Error calibrando {gesture}: {exc}")

        # mark initial calibration done in user settings
        cfg_path = Path("config") / "user_settings.json"
        manager = ConfigManager(cfg_path)
        current = manager.load()
        if not isinstance(current, dict):
            current = {}
        current["initial_gesture_calibrated"] = True
        manager.save(current)
        self._refresh_gesture_thresholds()

        # show summary
        for _ in range(60):
            frame = read_frame(self.cap)
            if frame is None:
                continue
            y = 30
            cv2.putText(frame, "Calibracion inicial completada - umbrales: ", (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 220, 200), 2)
            y += 28
            for g, v in results.items():
                cv2.putText(frame, f"{g}: {v if v is not None else 'ERR'}", (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 200, 120), 1)
                y += 22
            cv2.imshow("GazeDash - Calibracion inicial", frame)
            cv2.waitKey(50)

        cv2.destroyWindow("GazeDash - Calibracion inicial")

    def _ensure_neutral_calibrated(self):
        """Block until the `gesture_detector` has a neutral baseline.

        This displays a simple overlay asking the user to hold a neutral
        expression while samples are collected.
        """
        if self.cap is None:
            self.cap = open_camera(0)

        # keep reading frames and feed detector until calibrated
        while not self.gesture_detector.is_calibrated():
            frame = read_frame(self.cap)
            if frame is None:
                continue

            # prefer fast synchronous detection to feed metrics
            try:
                face_data = self.face_detector._detect_face(frame)
            except Exception:
                face_data = None

            # let the gesture detector collect neutral samples
            _ = self.gesture_detector.detect(face_data)

            prog = self.gesture_detector.calibration_progress()
            cv2.putText(frame, "Calibracion neutral: mantente quieto", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 50), 2)
            cv2.putText(frame, f"Progreso: {int(prog*100)}%", (12, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 50), 2)
            cv2.imshow("GazeDash - Camara", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break

        # small confirmation flash
        for i in range(10):
            frame = read_frame(self.cap)
            if frame is None:
                continue
            cv2.putText(frame, "Calibracion neutral completada", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 200, 120), 2)
            cv2.imshow("GazeDash - Camara", frame)
            cv2.waitKey(40)

        # If initial full calibration not yet done, run it now (collect thresholds for all gestures)
        cfg_path = Path("config") / "user_settings.json"
        manager = ConfigManager(cfg_path)
        current = manager.load()
        initial_done = False
        if isinstance(current, dict):
            initial_done = bool(current.get("initial_gesture_calibrated", False))
            # sanity-check stored thresholds: ensure all gestures present and values within reasonable range
            thresholds = current.get("gesture_thresholds", {}) if isinstance(current.get("gesture_thresholds", {}), dict) else {}
            required_gestures = [
                "mouth_pucker",
                "mouth_open",
                "mouth_o",
                "smile",
                "brow_raise",
                "brow_frown",
                "eye_blink",
                "eye_wide",
                "nose_sneer",
            ]
            sane = True
            for g in required_gestures:
                v = thresholds.get(g)
                if v is None:
                    sane = False
                    break
                try:
                    fv = float(v)
                except Exception:
                    sane = False
                    break
                # basic bounds: between 0.005 and 0.8 (brow geometry handled separately)
                if not (0.005 <= fv <= 0.8):
                    sane = False
                    break

            if not sane:
                initial_done = False

        if not initial_done:
            try:
                self.run_initial_full_calibration()
            except Exception:
                # don't block startup on calibration issues
                pass

    def _refresh_gesture_thresholds(self):
        self.gesture_detector.thresholds = self.gesture_detector._load_thresholds_from_config()

