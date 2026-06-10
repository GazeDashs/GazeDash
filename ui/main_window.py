"""Ventana principal de la UI con CustomTkinter."""

import threading

from tkinter import messagebox

import cv2
import customtkinter as ctk
from PIL import Image, ImageTk

from core.gesture_engine.cooldown_manager import CooldownManager
from core.gesture_engine.gesture_mapper import map_gesture
from core.gesture_engine.hotkey_executor import HotkeyExecutor
from core.voice_control.voice_control import VoiceCommandController
from vision.camera.camera_stream import close_camera, open_camera, read_frame
from vision.face_tracking.face_detector import MediaPipeFaceDetector
from vision.gesture_detection.facial_gestures import FacialGestureDetector
from ui.calibration_screen import show_calibration
from ui.config_panel import open_config_panel
from ui.components.buttons import create_button
from ui.settings_store import (
    get_active_profile_name,
    get_effective_thresholds,
    get_profile_details,
    get_profile_mouse_settings,
    load_config,
    save_config,
    set_profile_mouse_settings,
)

from core.input.mouse_controller import MouseController
from core.input.blink_click_controller import BlinkClickController

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")



DEAD_ZONE = 25
MAX_SPEED = 35
SMOOTHING = 0.2

THRESHOLD = 0.010
HOLD_TIME = 0.3
CLICK_COOLDOWN = 1.0

OVERLAY_WIDTH = 220
OVERLAY_HEIGHT = 220

class GazeDashApp(ctk.CTk):
    _GESTURE_META_KEYS = {"has_face", "calibrating", "calibration_progress"}

    def __init__(self):
        super().__init__()
        self.title("GazeDash")
        self.geometry("1240x780")
        self.minsize(1080, 680)
        self.configure(fg_color="#0B1220")

        self._config = load_config()
        self._preview_thread = None
        self._preview_stop_event = threading.Event()
        self._camera = None
        self._camera_detector = None
        self._preview_image = None
        self._mini_overlay = None
        self._mini_overlay_image = None
        self._mini_overlay_pending = False
        self._last_detected_gesture = "Sin gesto"
        self._last_detected_input = "Sin deteccion"
        self._controller_active = True
        self._last_nose_tip = None
        self._gesture_detector = FacialGestureDetector()
        self._gesture_executor = HotkeyExecutor()
        self._voice_controller = VoiceCommandController(self._config, status_callback=self._set_voice_status)
        self._cooldown_manager = CooldownManager(cooldown_seconds=0.5)
        self._mouse_controller = None
        self._blink_click_controller = BlinkClickController()
        self._load_mouse_settings()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Unmap>", self._on_window_unmap)
        self.bind("<Map>", self._on_window_map)

        self._build_sidebar()
        self._build_main_content()
        self.refresh_state()
        self.controller_status.configure(text="Controlador: activo en la vista principal")
        self._voice_controller.start()
        self.start_camera_preview()

    def _load_mouse_settings(self):
        profile_name = get_active_profile_name(self._config)
        mouse_settings = get_profile_mouse_settings(self._config, profile_name)
        self._analog_mouse_enabled = bool(mouse_settings.get("enabled", True))
        self._mouse_controller = MouseController(
            mouse_settings.get("dead_zone", DEAD_ZONE),
            mouse_settings.get("max_speed", MAX_SPEED),
            mouse_settings.get("smoothing", SMOOTHING),
            center=mouse_settings.get("center"),
        )

    def _recalibrate_mouse(self):
        if self._last_nose_tip is None:
            messagebox.showwarning("GazeDash", "No se ha detectado una posición de nariz válida todavía.")
            return

        nose_x, nose_y = self._last_nose_tip
        if self._mouse_controller is None:
            self._load_mouse_settings()
        self._mouse_controller.recalibrate(nose_x, nose_y)

        profile_name = get_active_profile_name(self._config)
        mouse_settings = get_profile_mouse_settings(self._config, profile_name)
        mouse_settings["center"] = [float(nose_x), float(nose_y)]
        updated = set_profile_mouse_settings(self._config, profile_name, mouse_settings)
        save_config(updated)
        self._config = updated
        self.refresh_state()

    def _set_voice_status(self, message):
        if hasattr(self, "voice_status_label"):
            try:
                self.voice_status_label.configure(text=f"Voz: {message}")
            except Exception:
                pass

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color="#111827")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(self.sidebar, text="GazeDash", font=("Segoe UI", 28, "bold")).pack(anchor="w", padx=24, pady=(28, 6))
        ctk.CTkLabel(self.sidebar, text="Interfaz principal para configurar el control por gestos faciales.", wraplength=220, justify="left").pack(anchor="w", padx=24, pady=(0, 18))

        self.profile_chip = ctk.CTkLabel(self.sidebar, text="Perfil: -", anchor="w")
        self.profile_chip.pack(fill="x", padx=24, pady=(0, 10))
        self.camera_chip = ctk.CTkLabel(self.sidebar, text="Camara: -", anchor="w")
        self.camera_chip.pack(fill="x", padx=24, pady=(0, 18))

        create_button(self.sidebar, "Configuracion", self.open_config).pack(fill="x", padx=24, pady=(0, 12))
        create_button(self.sidebar, "Calibracion", self.open_calibration).pack(fill="x", padx=24, pady=(0, 12))
        create_button(self.sidebar, "Recalibrar mouse", self._recalibrate_mouse).pack(fill="x", padx=24, pady=(0, 12))
        create_button(self.sidebar, "Iniciar controlador", self.start_controller).pack(fill="x", padx=24, pady=(0, 12))
        create_button(self.sidebar, "Refrescar", self.refresh_state).pack(fill="x", padx=24, pady=(0, 24))

        self.status_card = ctk.CTkFrame(self.sidebar, fg_color="#0F172A", corner_radius=16)
        self.status_card.pack(fill="x", padx=24, pady=(0, 18))
        self.status_card.grid_columnconfigure(0, weight=1)
        self.status_line1 = ctk.CTkLabel(self.status_card, text="Estado: listo", anchor="w")
        self.status_line1.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 4))
        self.status_line2 = ctk.CTkLabel(self.status_card, text="Configuracion cargada desde el perfil activo.", wraplength=220, justify="left", anchor="w")
        self.status_line2.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))

    def _build_main_content(self):
        self.main = ctk.CTkScrollableFrame(self, fg_color="#0B1220", corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew", padx=24, pady=24)
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(2, weight=1)

        hero = ctk.CTkFrame(self.main, fg_color="#111827", corner_radius=20)
        hero.grid(row=0, column=0, sticky="ew")
        hero.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hero, text="Control accesible con mirada y gestos", font=("Segoe UI", 24, "bold")).grid(row=0, column=0, sticky="w", padx=22, pady=(22, 8))
        ctk.CTkLabel(hero, text="Esta pantalla reemplaza los placeholders anteriores y centraliza la navegación hacia configuracion y calibracion.", wraplength=820, justify="left").grid(row=1, column=0, sticky="w", padx=22, pady=(0, 18))

        preview = ctk.CTkFrame(self.main, fg_color="#111827", corner_radius=20)
        preview.grid(row=1, column=0, sticky="nsew", pady=(18, 0))
        preview.grid_columnconfigure(0, weight=1)
        preview.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(preview, text="Vista previa de cámara con malla", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 8))
        self.preview_status = ctk.CTkLabel(preview, text="Cámara detenida", anchor="w")
        self.preview_status.grid(row=0, column=0, sticky="e", padx=22, pady=(18, 8))
        self.preview_gesture = ctk.CTkLabel(preview, text="Gesto: Sin gesto", anchor="w")
        self.preview_gesture.grid(row=0, column=0, sticky="e", padx=180, pady=(18, 8))

        preview_surface = ctk.CTkFrame(preview, fg_color="#0F172A", corner_radius=16)
        preview_surface.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        preview_surface.grid_rowconfigure(0, weight=1)
        preview_surface.grid_columnconfigure(0, weight=1)

        self.preview_label = ctk.CTkLabel(preview_surface, text="Iniciando cámara...", anchor="center")
        self.preview_label.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        grid = ctk.CTkFrame(self.main, fg_color="#0B1220")
        grid.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_columnconfigure(2, weight=1)

        self.profile_card = self._make_metric_card(grid, 0, "Perfil activo", "-")
        self.threshold_card = self._make_metric_card(grid, 1, "Umbrales", "-")
        self.cooldown_card = self._make_metric_card(grid, 2, "Cooldown", "-")

        actions = ctk.CTkFrame(self.main, fg_color="#111827", corner_radius=20)
        actions.grid(row=3, column=0, sticky="nsew", pady=(18, 0))
        actions.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(actions, text="Acciones rapidas", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w", padx=22, pady=(20, 8))
        ctk.CTkLabel(actions, text="Usa estos accesos para abrir las pantallas nuevas o iniciar el controlador de cámara.", anchor="w").grid(row=1, column=0, sticky="w", padx=22, pady=(0, 16))

        action_row = ctk.CTkFrame(actions, fg_color="transparent")
        action_row.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        action_row.grid_columnconfigure(0, weight=1)
        action_row.grid_columnconfigure(1, weight=1)
        action_row.grid_columnconfigure(2, weight=1)
        create_button(action_row, "Abrir configuracion", self.open_config).grid(row=0, column=0, sticky="ew", padx=4)
        create_button(action_row, "Abrir calibracion", self.open_calibration).grid(row=0, column=1, sticky="ew", padx=4)
        create_button(action_row, "Recargar datos", self.refresh_state).grid(row=0, column=2, sticky="ew", padx=4)

        self.controller_status = ctk.CTkLabel(actions, text="Controlador: detenido", anchor="w")
        self.controller_status.grid(row=3, column=0, sticky="w", padx=22, pady=(0, 8))
        self.voice_status_label = ctk.CTkLabel(actions, text="Voz: detenido", anchor="w")
        self.voice_status_label.grid(row=4, column=0, sticky="w", padx=22, pady=(0, 18))

    def _make_metric_card(self, parent, column, title, value):
        card = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=18)
        card.grid(row=0, column=column, sticky="nsew", padx=8)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, anchor="w").grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 6))
        value_label = ctk.CTkLabel(card, text=value, font=("Segoe UI", 22, "bold"), anchor="w")
        value_label.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 16))
        return value_label

    def refresh_state(self, *_):
        self._config = load_config()
        self._voice_controller.update_config(self._config)
        profile_name = get_active_profile_name(self._config)
        _, profile = get_profile_details(self._config, profile_name)
        thresholds = get_effective_thresholds(self._config, profile_name)
        mouse_settings = get_profile_mouse_settings(self._config, profile_name)

        self._load_mouse_settings()
        self.profile_chip.configure(text=f"Perfil: {profile_name}")
        self.camera_chip.configure(text=f"Camara: {self._config.get('camera_index', 0)}")
        self.status_line1.configure(text=f"Estado: {profile.get('display_name') or profile_name}")
        self.status_line2.configure(text=(profile.get("description") or "Configuracion lista para abrir las pantallas de ajuste.") +
                                     f" | Mouse: {'activado' if mouse_settings.get('enabled', True) else 'desactivado'}")
        self.profile_card.configure(text=profile.get("display_name") or profile_name)
        self.threshold_card.configure(text=str(len(thresholds)))
        self.cooldown_card.configure(text=f"{float(self._config.get('gesture_cooldown', 0.5)):.2f}s")

    def open_config(self):
        dialog = open_config_panel(self)
        self.wait_window(dialog)
        self.refresh_state()

    def open_calibration(self):
        dialog = show_calibration(self)
        self.wait_window(dialog)
        self.refresh_state()

    def start_controller(self):
        if self._controller_active:
            messagebox.showinfo("GazeDash", "El controlador ya está activo dentro de la vista principal.")
            return

        self._controller_active = True
        self.controller_status.configure(text="Controlador: activo en la vista principal")

    def _summarize_input(self, gestures):
        if not gestures or not gestures.get("has_face"):
            return "Sin rostro", "Sin gesto"

        if gestures.get("calibrating"):
            progress = f"Calibrando {gestures.get('calibration_progress', 0.0):.0%}"
            return progress, progress

        for gesture_name, is_active in gestures.items():
            if gesture_name in self._GESTURE_META_KEYS or not is_active:
                continue

            action = map_gesture(gesture_name)
            if action and isinstance(action, dict):
                return action.get("label") or gesture_name, gesture_name

            return gesture_name, gesture_name

        return "Sin gesto", "Sin gesto"

    def _update_preview_widgets(self, photo, detected_input, detected_gesture):
        self._preview_image = photo
        self._last_detected_input = detected_input
        self._last_detected_gesture = detected_gesture
        self.preview_label.configure(image=photo, text="")
        self.preview_status.configure(text=f"Input: {detected_input}")
        self.preview_gesture.configure(text=f"Gesto: {detected_gesture}")

        if self._mini_overlay is not None and self._mini_overlay.winfo_exists():
            self._mini_overlay_image = photo
            if hasattr(self, "mini_preview_label"):
                self.mini_preview_label.configure(image=photo, text="")
            if hasattr(self, "mini_status_label"):
                self.mini_status_label.configure(text=f"Input: {detected_input}")
            if hasattr(self, "mini_gesture_label"):
                self.mini_gesture_label.configure(text=f"Gesto: {detected_gesture}")

    def _on_window_unmap(self, _event=None):
        if _event is not None and getattr(_event, "widget", None) is not self:
            return

        if self.state() != "iconic" or self._mini_overlay_pending:
            return

        self._mini_overlay_pending = True
        self.after(120, self._show_mini_overlay)

    def _on_window_map(self, _event=None):
        self._mini_overlay_pending = False
        if self.state() != "iconic":
            self._hide_mini_overlay()

    def _show_mini_overlay(self):
        self._mini_overlay_pending = False
        if self.state() != "iconic":
            return
        if self._mini_overlay is not None and self._mini_overlay.winfo_exists():
            self._mini_overlay.lift()
            self._mini_overlay.attributes("-topmost", True)
            return

        overlay = ctk.CTkToplevel(self)
        overlay.title("GazeDash Mini")
        overlay.geometry("320x280+20+20")
        overlay.resizable(False, False)
        overlay.attributes("-topmost", True)
        try:
            overlay.wm_attributes("-disabled", True)
        except Exception:
            pass
        overlay.protocol("WM_DELETE_WINDOW", self._hide_mini_overlay)
        overlay.bind("<Unmap>", lambda _event: None)
        overlay.configure(fg_color="#0B1220")

        container = ctk.CTkFrame(overlay, fg_color="#111827", corner_radius=16)
        container.pack(fill="both", expand=True, padx=8, pady=8)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(container, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="GazeDash mini", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
        self.mini_status_label = ctk.CTkLabel(header, text=f"Input: {self._last_detected_input}", anchor="e")
        self.mini_status_label.grid(row=0, column=1, sticky="e")

        self.mini_preview_label = ctk.CTkLabel(container, text="Esperando video...", anchor="center")
        self.mini_preview_label.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        ctk.CTkLabel(footer, text="Minimiza para esta vista flotante.", anchor="w").pack(anchor="w")
        self.mini_gesture_label = ctk.CTkLabel(footer, text=f"Gesto: {self._last_detected_gesture}", anchor="w")
        self.mini_gesture_label.pack(anchor="w")

        if self._preview_image is not None:
            self.mini_preview_label.configure(image=self._preview_image, text="")
        self.mini_gesture_label.configure(text=f"Gesto: {self._last_detected_gesture}")

        self._mini_overlay = overlay

    def _hide_mini_overlay(self):
        if self._mini_overlay is not None and self._mini_overlay.winfo_exists():
            self._mini_overlay.destroy()
        self._mini_overlay = None
        self._mini_overlay_image = None

    def _handle_gestures(self, gestures):
        if not gestures or not gestures.get("has_face"):
            return

        if gestures.get("calibrating"):
            return

        for gesture_name, is_active in gestures.items():
            if gesture_name in self._GESTURE_META_KEYS or not is_active:
                continue

            action = map_gesture(gesture_name)
            if not action:
                continue

            cooldown_key = action.get("label") or gesture_name
            if not self._cooldown_manager.allow(cooldown_key):
                continue

            try:
                self._gesture_executor.execute(action)
            except RuntimeError:
                pass

    def start_camera_preview(self):
        if self._preview_thread is not None and self._preview_thread.is_alive():
            return

        self._preview_stop_event.clear()
        camera_index = int(self._config.get("camera_index", 0))
        face_landmarks_cfg = self._config.get("face_landmarks", {}) if isinstance(self._config, dict) else {}
        landmark_indices = face_landmarks_cfg.get("indices", {}) if isinstance(face_landmarks_cfg, dict) else {}
        landmark_offsets = face_landmarks_cfg.get("offsets", {}) if isinstance(face_landmarks_cfg, dict) else {}

        try:
            self._camera = open_camera(camera_index)
            self._camera_detector = MediaPipeFaceDetector(
                live_stream=False,
                draw_landmarks=True,
                landmark_overrides=landmark_indices,
                landmark_offsets=landmark_offsets,
            )
        except Exception as exc:
            self.preview_status.configure(text=f"Cámara no disponible: {exc}")
            self.preview_label.configure(text="No se pudo iniciar la cámara.")
            return

        def worker():
            detector = self._camera_detector
            if detector is None:
                return

            while not self._preview_stop_event.is_set():
                frame = read_frame(self._camera)
                if frame is None:
                    continue

                try:
                    face_data = detector.detect(frame)
                    #Hay que pasar esto al modulo de mouse cuando se termine de provar
                    if self._analog_mouse_enabled and face_data is not None:
                        nose_tip = face_data.get("nose_tip")
                        if nose_tip is not None:
                            nose_x, nose_y = nose_tip
                            self._last_nose_tip = (nose_x, nose_y)
                            self._mouse_controller.update(nose_x, nose_y)
                    ####
                    # Clicks por guiño

                    if face_data is not None:
                        left = face_data.get("eye_blink_left", 0.0)
                        right = face_data.get("eye_blink_right", 0.0)
                        print(f"BLINK  L={left:.3f}  R={right:.3f}")
                        self._blink_click_controller.update(face_data)

                    gestures = self._gesture_detector.detect(face_data)
                    detected_input, detected_gesture = self._summarize_input(gestures)
                    if self._controller_active:
                        self._handle_gestures(gestures)
                        self._voice_controller.handle_gesture_input(gestures)
                    else:
                        self._last_detected_input = detected_input
                        self._last_detected_gesture = detected_gesture
                except Exception as exc:
                    self.after(0, lambda message=str(exc): self.preview_status.configure(text=f"Error en detector: {message}"))
                    continue

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(rgb_frame)
                photo = ImageTk.PhotoImage(image=image)

                def update_image(pil_photo=photo, input_text=detected_input, gesture_text=detected_gesture):
                    self._update_preview_widgets(pil_photo, input_text, gesture_text)
                    if self._controller_active:
                        self.controller_status.configure(text="Controlador: activo en la vista principal")

                self.after(0, update_image)

            self.after(0, lambda: self.preview_status.configure(text="Cámara detenida"))

        self._preview_thread = threading.Thread(target=worker, daemon=True)
        self._preview_thread.start()

    def stop_camera_preview(self):
        self._preview_stop_event.set()
        if self._camera is not None:
            close_camera(self._camera)
            self._camera = None
        if self._camera_detector is not None:
            try:
                self._camera_detector.close()
            except Exception:
                pass
            self._camera_detector = None
        self._voice_controller.stop()

    def _on_close(self):
        self.stop_camera_preview()
        self.destroy()


def create_main_window():
    return GazeDashApp()
