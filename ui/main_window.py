"""Ventana principal rediseñada — GazeDash."""

import math
import threading
import time
from tkinter import messagebox

import cv2
import customtkinter as ctk
from PIL import Image, ImageTk

from core.gesture_engine.cooldown_manager import CooldownManager
from core.gesture_engine.gesture_arbiter import GestureArbiter
from core.gesture_engine.gesture_diagnostics_logger import GestureDiagnosticsLogger
from core.gesture_engine.gesture_mapper import map_gesture
from core.gesture_engine.hotkey_executor import HotkeyExecutor
from core.voice_control.voice_control import VoiceCommandController
from vision.camera.camera_stream import close_camera, open_camera, read_frame
from vision.face_tracking.face_detector import MediaPipeFaceDetector
from vision.gesture_detection.facial_gestures import FacialGestureDetector
from ui.calibration_screen import show_calibration
from ui.config_panel import open_config_panel
from ui.settings_store import (
    AVAILABLE_GESTURE_NAMES,
    GESTURE_THRESHOLD_KEYS,
    get_active_profile_name,
    get_effective_thresholds,
    get_profile_details,
    get_profile_mouse_settings,
    get_profile_voice_actions,
    get_profiles,
    get_voice_control_settings,
    load_config,
    save_config,
    set_profile_mouse_settings,
    set_voice_control_settings,
)
from core.input.mouse_controller import MouseController
from core.input.blink_click_controller import BlinkClickController

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

# ── Paleta de colores ─────────────────────────────────────────────────────────
BG         = "#0D1117"
SIDEBAR_BG = "#111827"
CARD       = "#161F2E"
CARD_IN    = "#0F172A"
GREEN      = "#10B981"
GREEN_DIM  = "#064E3B"
GREEN_TXT  = "#34D399"
TEXT       = "#E2E8F0"
TEXT2      = "#9CA3AF"
TEXT3      = "#4B5563"
NAV_ACT    = "#064E3B"
DANGER     = "#F87171"
WARN       = "#F59E0B"
BLUE       = "#6366F1"
PURPLE     = "#8B5CF6"

DEAD_ZONE = 25
MAX_SPEED  = 35
SMOOTHING  = 0.2


# ── Helpers de construcción ───────────────────────────────────────────────────

def _lbl(parent, text, size=13, bold=False, color=TEXT, **kw):
    weight = "bold" if bold else "normal"
    return ctk.CTkLabel(parent, text=text,
                        font=("Segoe UI", size, weight),
                        text_color=color, **kw)


def _card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16, **kw)


def _inner_card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=CARD_IN, corner_radius=12, **kw)


def _green_badge(parent, text, **kw):
    frame = ctk.CTkFrame(parent, fg_color=GREEN_DIM, corner_radius=10, **kw)
    ctk.CTkLabel(frame, text=text,
                 font=("Segoe UI", 13, "bold"),
                 text_color=GREEN_TXT).pack(padx=16, pady=6)
    return frame


def _section_title(parent, text):
    return ctk.CTkLabel(parent, text=text.upper(),
                        font=("Segoe UI", 10, "bold"),
                        text_color=TEXT3, anchor="w")


def _action_button(parent, text, cmd, col=None, fg=CARD, text_col=TEXT):
    btn = ctk.CTkButton(
        parent, text=text, command=cmd,
        fg_color=fg, hover_color=CARD_IN if fg == CARD else GREEN_TXT,
        text_color=text_col,
        border_color=TEXT3, border_width=1 if fg == CARD else 0,
        corner_radius=10, height=40,
        font=("Segoe UI", 12),
    )
    if col is not None:
        btn.grid(row=0, column=col, sticky="ew", padx=4)
    return btn


# ── Aplicación principal ──────────────────────────────────────────────────────

class GazeDashApp(ctk.CTk):
    _GESTURE_META_KEYS = {"has_face", "calibrating", "calibration_progress", "gesture_scores"}
    _NAV_ITEMS = [
        ("inicio",        "⌂",  "Inicio"),
        ("configuracion", "⚙",  "Configuración"),
        ("calibracion",   "◎",  "Calibración"),
        ("voz",           "♪",  "Voz"),
    ]

    def __init__(self):
        super().__init__()
        self.title("GazeDash — Control por gestos faciales")
        self.geometry("1020x660")
        self.minsize(880, 580)
        self.configure(fg_color=BG)

        # ── Estado backend ──
        self._config = load_config()
        self._preview_thread = None
        self._preview_stop_event = threading.Event()
        self._camera = None
        self._camera_detector = None
        self._preview_image = None
        self._mini_overlay = None
        self._mini_overlay_pending = False
        self._last_detected_gesture = "Sin gesto"
        self._last_detected_input  = "Sin deteccion"
        self._controller_active = True
        self._controller_paused = False
        self._last_nose_tip = None
        self._last_fps = 0
        self._last_confidence = 0.0

        self._gesture_detector    = FacialGestureDetector()
        self._gesture_arbiter     = GestureArbiter.from_config(self._config)
        self._gesture_diag_logger = GestureDiagnosticsLogger.from_config(self._config, component="ui")
        self._gesture_executor    = HotkeyExecutor()
        self._voice_controller    = VoiceCommandController(
            self._config, status_callback=self._set_voice_status
        )
        self._cooldown_manager    = CooldownManager(cooldown_seconds=0.5)
        self._mouse_controller    = None
        self._blink_click_controller = BlinkClickController()
        self._nose_center = None  # actualizado al recalibrar
        self._load_mouse_settings()
        # Inicializar centro desde la config guardada
        _ms = get_profile_mouse_settings(self._config, get_active_profile_name(self._config))
        if _ms.get("center"):
            self._nose_center = tuple(_ms["center"])

        # ── Layout ──
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Unmap>", self._on_window_unmap)
        self.bind("<Map>",   self._on_window_map)

        self._current_view = "inicio"
        self._nav_buttons  = {}
        self._views        = {}

        self._build_sidebar()
        self._build_all_views()
        self._switch_view("inicio")
        self._voice_controller.start()
        self.start_camera_preview()
        self.after(200, self.refresh_state)  # poblar módulos y chip de perfil

    # ── Backend: mouse ────────────────────────────────────────────────────────

    def _load_mouse_settings(self):
        profile_name   = get_active_profile_name(self._config)
        mouse_settings = get_profile_mouse_settings(self._config, profile_name)
        self._analog_mouse_enabled = bool(mouse_settings.get("enabled", True))
        self._mouse_controller = MouseController(
            mouse_settings.get("dead_zone", DEAD_ZONE),
            mouse_settings.get("max_speed",  MAX_SPEED),
            mouse_settings.get("smoothing",  SMOOTHING),
            center=mouse_settings.get("center"),
        )

    def _recalibrate_mouse(self):
        if self._last_nose_tip is None:
            messagebox.showwarning("GazeDash", "Todavía no se detectó la nariz.")
            return
        nose_x, nose_y = self._last_nose_tip
        if self._mouse_controller is None:
            self._load_mouse_settings()
        self._mouse_controller.recalibrate(nose_x, nose_y)
        self._nose_center = (nose_x, nose_y)  # guardar centro local
        profile_name   = get_active_profile_name(self._config)
        mouse_settings = get_profile_mouse_settings(self._config, profile_name)
        mouse_settings["center"] = [float(nose_x), float(nose_y)]
        updated = set_profile_mouse_settings(self._config, profile_name, mouse_settings)
        save_config(updated)
        self._config = updated
        self.refresh_state()

    def _capture_neutral_base(self):
        """Dispara la captura de expresión neutral en el FacialGestureDetector."""
        if self._gesture_detector is not None:
            self._gesture_detector.reset_calibration()
            messagebox.showinfo(
                "GazeDash",
                "Mantenés expresión neutral 3 segundos.\n"
                "El sistema capturará la base automáticamente.",
            )
        else:
            messagebox.showwarning("GazeDash", "El detector de gestos no está activo.")

    def _toggle_pause(self):
        self._controller_paused = not self._controller_paused
        if self._controller_paused:
            self._gesture_executor.release_all_holds()
        label = "▶  Reanudar" if self._controller_paused else "⏸  Pausar"
        if hasattr(self, "_btn_pause"):
            self._btn_pause.configure(text=label)

    # ── Backend: voz ──────────────────────────────────────────────────────────

    def _set_voice_status(self, message):
        """Callback del VoiceCommandController — actualiza el panel de voz en vivo (hilo-seguro)."""
        self.after(0, self._apply_voice_status, message)

    def _apply_voice_status(self, message: str):
        """Actualiza widgets de voz desde el hilo principal."""
        from core.voice_control.voice_control import VoiceControlState
        vc = self._voice_controller
        state = vc.state
        module = vc.active_module

        # ── Clasificar el mensaje ──────────────────────────────────────────────
        is_listening  = state == VoiceControlState.LISTENING_COMMAND
        is_module_act = state == VoiceControlState.MODULE_ACTIVE
        is_waiting    = state == VoiceControlState.WAITING_MODULE
        is_error      = state == VoiceControlState.ERROR
        is_disabled   = state == VoiceControlState.DISABLED
        is_low_conf   = "confianza baja" in message.lower() or "baja" in message.lower()
        is_executed   = "ejecutada" in message.lower()

        # ── Icono + color del estado ───────────────────────────────────────────
        if is_disabled:
            icon, icon_col, msg_col = "○", TEXT3, TEXT3
        elif is_error:
            icon, icon_col, msg_col = "⚠", WARN, WARN
        elif is_listening:
            icon, icon_col, msg_col = "🎙", GREEN_TXT, TEXT
        elif is_module_act:
            icon, icon_col, msg_col = "●", GREEN, TEXT
        elif is_waiting:
            icon, icon_col, msg_col = "◎", BLUE, TEXT2
        else:
            icon, icon_col, msg_col = "○", TEXT3, TEXT2

        # ── Mensaje corto (sin prefijo largo) ─────────────────────────────────
        short = message
        for prefix in ("Voz lista: ", "Módulo activo: ", "Acción ejecutada: ",
                       "Escuchando comando de ", "Confianza baja: "):
            if message.startswith(prefix):
                short = message[len(prefix):]
                break

        # ── Módulo activo ──────────────────────────────────────────────────────
        from core.voice_control.voice_control import MODULE_LABELS
        mod_label = MODULE_LABELS.get(module or "", "—") if module else "—"

        # ── Último comando ejecutado ───────────────────────────────────────────
        if is_executed:
            cmd_text  = short
            cmd_color = GREEN_TXT
        elif is_low_conf:
            cmd_text  = "⚠ baja confianza"
            cmd_color = WARN
        else:
            cmd_text  = short if is_module_act else "—"
            cmd_color = TEXT

        # ── Card de estado en la vista Inicio ─────────────────────────────────
        if hasattr(self, "_voice_state_icon"):
            self._voice_state_icon.configure(text=icon, text_color=icon_col)
            self._voice_state_lbl.configure(text=short[:28], text_color=msg_col)
            self._voice_module_lbl.configure(text=mod_label)
            self._voice_cmd_lbl.configure(text=cmd_text, text_color=cmd_color)

            # Advertencia confianza baja
            if is_low_conf:
                self._voice_warn_card.grid()
                # Auto-ocultar en 3 s
                self.after(3000, self._voice_warn_card.grid_remove)

            # Pulsar el card de estado cuando escucha
            card_bg = GREEN_DIM if is_listening else CARD
            self._voice_status_card.configure(fg_color=card_bg)

        # ── Mini overlay ──────────────────────────────────────────────────────
        if hasattr(self, "_mini_voice_state_lbl"):
            self._mini_voice_state_lbl.configure(text=f"{icon}  {short[:22]}", text_color=icon_col)
        if hasattr(self, "_mini_voice_mod_lbl"):
            self._mini_voice_mod_lbl.configure(text=mod_label)

    @staticmethod
    def _check_voice_deps() -> bool:
        import importlib.util
        return all(
            importlib.util.find_spec(m) is not None
            for m in ["librosa", "sounddevice", "pandas", "xgboost"]
        )

    # ── Backend: gestos ───────────────────────────────────────────────────────

    def _summarize_input(self, gestures):
        if not gestures or not gestures.get("has_face"):
            return "Sin rostro", "Sin gesto"
        if gestures.get("calibrating"):
            p = f"Calibrando {gestures.get('calibration_progress', 0.0):.0%}"
            return p, p
        for gesture_name, is_active in gestures.items():
            if gesture_name in self._GESTURE_META_KEYS or not is_active:
                continue
            action = map_gesture(gesture_name)
            if action and isinstance(action, dict):
                return action.get("label") or gesture_name, gesture_name
            return gesture_name, gesture_name
        return "Sin gesto", "Sin gesto"

    def _handle_gestures(self, gestures):
        if not gestures or not gestures.get("has_face"):
            self._gesture_executor.release_all_holds()
            return
        if gestures.get("calibrating") or self._controller_paused:
            self._gesture_executor.release_all_holds()
            return
        for gesture_name, is_active in gestures.items():
            if gesture_name in self._GESTURE_META_KEYS:
                continue
            action = map_gesture(gesture_name, self._config)
            if not action:
                continue
            if self._gesture_executor.is_hold_action(action):
                try:
                    self._gesture_executor.update_hold(gesture_name, action, bool(is_active))
                except RuntimeError:
                    pass
                continue
            if not is_active:
                continue
            cooldown_key = action.get("label") or gesture_name
            if not self._cooldown_manager.allow(cooldown_key):
                continue
            try:
                self._gesture_executor.execute(action)
            except RuntimeError:
                pass

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=186, corner_radius=0, fg_color=SIDEBAR_BG)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(3, weight=1)
        sb.grid_columnconfigure(0, weight=1)

        # Logo
        logo = ctk.CTkFrame(sb, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="ew", padx=16, pady=(22, 16))
        icon_f = ctk.CTkFrame(logo, fg_color=GREEN_DIM, corner_radius=10,
                               width=36, height=36)
        icon_f.pack(side="left")
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="👁", font=("Segoe UI", 16)).place(
            relx=0.5, rely=0.5, anchor="center"
        )
        _lbl(logo, "GazeDash", 17, bold=True).pack(side="left", padx=10)

        # Separador
        ctk.CTkFrame(sb, height=1, fg_color=TEXT3).grid(
            row=1, column=0, sticky="ew", padx=16, pady=(0, 10)
        )

        # Nav
        nav = ctk.CTkFrame(sb, fg_color="transparent")
        nav.grid(row=2, column=0, sticky="ew", padx=8)

        for key, icon, label in self._NAV_ITEMS:
            btn = ctk.CTkButton(
                nav,
                text=f"  {icon}  {label}",
                anchor="w",
                font=("Segoe UI", 13),
                fg_color="transparent",
                text_color=TEXT2,
                hover_color="#1F2937",
                corner_radius=10,
                height=44,
                command=lambda k=key: self._switch_view(k),
            )
            btn.pack(fill="x", pady=2)
            self._nav_buttons[key] = btn

        # Chip de perfil (abajo)
        chip = ctk.CTkFrame(sb, fg_color=CARD_IN, corner_radius=12)
        chip.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 18))
        _lbl(chip, "●", 11, color=GREEN).pack(side="left", padx=(12, 4), pady=12)
        self._profile_chip_label = _lbl(chip, "—", 12, bold=True)
        self._profile_chip_label.pack(side="left", pady=12)

    def _switch_view(self, view_name):
        for key, btn in self._nav_buttons.items():
            if key == view_name:
                btn.configure(fg_color=NAV_ACT, text_color=GREEN_TXT)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT2)
        for key, frame in self._views.items():
            if key == view_name:
                frame.grid()
            else:
                frame.grid_remove()
        self._current_view = view_name

    # ── Contenedor de vistas ──────────────────────────────────────────────────

    def _build_all_views(self):
        host = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        host.grid(row=0, column=1, sticky="nsew")
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)

        for key in ("inicio", "configuracion", "calibracion", "voz"):
            f = ctk.CTkFrame(host, fg_color=BG, corner_radius=0)
            f.grid(row=0, column=0, sticky="nsew")
            f.grid_columnconfigure(0, weight=1)
            f.grid_rowconfigure(0, weight=1)
            self._views[key] = f

        self._build_view_inicio(self._views["inicio"])
        self._build_view_configuracion(self._views["configuracion"])
        self._build_view_calibracion(self._views["calibracion"])
        self._build_view_voz(self._views["voz"])

    # ── VISTA: INICIO ─────────────────────────────────────────────────────────

    def _build_view_inicio(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, minsize=230)
        parent.grid_rowconfigure(0, weight=1)

        # ── Columna izquierda ─────────────────────────────────────────────────
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(18, 8), pady=18)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1)

        # Camera card
        cam_card = _card(left)
        cam_card.grid(row=0, column=0, sticky="nsew")
        cam_card.grid_columnconfigure(0, weight=1)
        cam_card.grid_rowconfigure(1, weight=1)

        cam_top = ctk.CTkFrame(cam_card, fg_color="transparent")
        cam_top.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        cam_top.grid_columnconfigure(0, weight=1)
        self._cam_status_label = _lbl(
            cam_top, "● Activo · 0 fps", 11, color=GREEN, anchor="e"
        )
        self._cam_status_label.grid(row=0, column=0, sticky="e")

        cam_surf = ctk.CTkFrame(cam_card, fg_color=BG, corner_radius=12)
        cam_surf.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        cam_surf.grid_rowconfigure(0, weight=1)
        cam_surf.grid_columnconfigure(0, weight=1)
        self.preview_label = ctk.CTkLabel(cam_surf, text="Iniciando cámara...", anchor="center")
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        # Badge de gesto sobre la cámara (debajo) — guardamos ref al label interno
        self._gesture_badge_frame = _green_badge(cam_card, "Sin gesto")
        self._gesture_badge_frame.grid(row=2, column=0, pady=(2, 12))
        self._gesture_badge_lbl = self._gesture_badge_frame.winfo_children()[0]

        # Botones de acción
        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        btn_row.grid_columnconfigure((0, 1, 2), weight=1)

        _action_button(btn_row, "↺  Recalibrar", self._recalibrate_mouse, col=0)
        self._btn_pause = ctk.CTkButton(
            btn_row, text="⏸  Pausar", command=self._toggle_pause,
            fg_color=CARD, hover_color=CARD_IN, text_color=TEXT,
            border_color=TEXT3, border_width=1,
            corner_radius=10, height=40, font=("Segoe UI", 12),
        )
        self._btn_pause.grid(row=0, column=1, sticky="ew", padx=4)
        _action_button(btn_row, "⊡  Foto base", self._capture_neutral_base, col=2)

        # Metric cards
        metric_row = ctk.CTkFrame(left, fg_color="transparent")
        metric_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        metric_row.grid_columnconfigure((0, 1, 2), weight=1)

        def _metric(col, title, val_attr, sub_attr, sub_text="—"):
            c = _card(metric_row)
            c.grid(row=0, column=col, sticky="ew", padx=4)
            _lbl(c, title, 10, color=TEXT2, anchor="w").pack(anchor="w", padx=14, pady=(12, 2))
            v = _lbl(c, "—", 20, bold=True, anchor="w")
            v.pack(anchor="w", padx=14)
            s = _lbl(c, sub_text, 10, color=GREEN_TXT, anchor="w")
            s.pack(anchor="w", padx=14, pady=(0, 12))
            setattr(self, val_attr, v)
            setattr(self, sub_attr, s)

        _metric(0, "Nariz (despl.)", "_mn_val", "_mn_sub", "posición relativa")
        _metric(1, "FPS cámara",     "_fps_val", "_fps_sub", "tiempo real")
        _metric(2, "Confianza",      "_conf_val", "_conf_sub", "detección facial")

        # ── Columna derecha ───────────────────────────────────────────────────
        right = ctk.CTkFrame(parent, fg_color=SIDEBAR_BG, width=230, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)
        right.grid_columnconfigure(0, weight=1)

        ri = ctk.CTkScrollableFrame(right, fg_color="transparent")
        ri.pack(fill="both", expand=True, padx=14, pady=16)
        ri.grid_columnconfigure(0, weight=1)

        # Gesto activo — guardamos ref al label interno para no recrearlo
        _section_title(ri, "Gesto activo").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self._active_gesture_badge = _green_badge(ri, "Sin gesto")
        self._active_gesture_badge.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self._active_gesture_badge_lbl = self._active_gesture_badge.winfo_children()[0]

        action_frame = ctk.CTkFrame(ri, fg_color=BLUE, corner_radius=10)
        action_frame.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        self._active_action_label = ctk.CTkLabel(
            action_frame, text="→  —",
            text_color="white", font=("Segoe UI", 12),
        )
        self._active_action_label.pack(padx=14, pady=6)

        # Diagnóstico de arbitraje
        diag_card = ctk.CTkFrame(ri, fg_color=CARD, corner_radius=12)
        diag_card.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        diag_card.grid_columnconfigure(0, weight=1)
        _lbl(diag_card, "Diagnóstico", 10, color=TEXT3).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 2)
        )
        self._gesture_diag_winner = _lbl(diag_card, "Ganador: —", 11, color=GREEN_TXT, anchor="w")
        self._gesture_diag_winner.grid(row=1, column=0, sticky="ew", padx=10)
        self._gesture_diag_raw = _lbl(diag_card, "Crudos: —", 10, color=TEXT2, anchor="w", wraplength=180)
        self._gesture_diag_raw.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 0))
        self._gesture_diag_rejected = _lbl(diag_card, "Descartados: —", 10, color=TEXT2, anchor="w", wraplength=180)
        self._gesture_diag_rejected.grid(row=3, column=0, sticky="ew", padx=10, pady=(2, 8))

        # Métricas faciales
        ctk.CTkFrame(ri, height=1, fg_color=TEXT3).grid(
            row=4, column=0, sticky="ew", pady=(0, 8)
        )
        _section_title(ri, "Métricas faciales").grid(row=5, column=0, sticky="w", pady=(0, 6))

        self._metric_rows = {}
        facial_metrics = [
            ("boca",      "mouth_open"),
            ("ojo izq.",  "eye_blink_left"),
            ("ojo der.",  "eye_blink_right"),
            ("ceja izq.", "brow_raise"),
            ("sonrisa",   "smile"),
        ]
        for i, (display, key) in enumerate(facial_metrics):
            row = ctk.CTkFrame(ri, fg_color="transparent")
            row.grid(row=6 + i, column=0, sticky="ew", pady=2)
            row.grid_columnconfigure(0, weight=1)
            _lbl(row, display, 12, color=TEXT2).grid(row=0, column=0, sticky="w")
            val = _lbl(row, "0.00", 12, bold=True, color=GREEN_TXT)
            val.grid(row=0, column=1, sticky="e")
            self._metric_rows[key] = val

        # Módulos
        ctk.CTkFrame(ri, height=1, fg_color=TEXT3).grid(
            row=11, column=0, sticky="ew", pady=(8, 8)
        )
        _section_title(ri, "Módulos").grid(row=12, column=0, sticky="w", pady=(0, 6))

        self._mod_rows = {}
        for i, (key, label) in enumerate([("gestos", "Gestos"),
                                           ("mouse",  "Mouse nariz"),
                                           ("voz",    "Voz")]):
            row = ctk.CTkFrame(ri, fg_color="transparent")
            row.grid(row=13 + i, column=0, sticky="ew", pady=2)
            row.grid_columnconfigure(0, weight=1)
            _lbl(row, label, 12, color=TEXT2).grid(row=0, column=0, sticky="w")
            dot = _lbl(row, "○ inactivo", 11, color=TEXT3)
            dot.grid(row=0, column=1, sticky="e")
            self._mod_rows[key] = dot

        # ── Voz en vivo ───────────────────────────────────────────────────────
        ctk.CTkFrame(ri, height=1, fg_color=TEXT3).grid(
            row=16, column=0, sticky="ew", pady=(8, 8)
        )
        _section_title(ri, "Voz en vivo").grid(row=17, column=0, sticky="w", pady=(0, 6))

        # Card de estado
        self._voice_status_card = ctk.CTkFrame(ri, fg_color=CARD, corner_radius=12)
        self._voice_status_card.grid(row=18, column=0, sticky="ew", pady=(0, 6))
        self._voice_status_card.grid_columnconfigure(0, weight=1)

        # Fila icono + estado
        vs_top = ctk.CTkFrame(self._voice_status_card, fg_color="transparent")
        vs_top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        vs_top.grid_columnconfigure(1, weight=1)
        self._voice_state_icon = _lbl(vs_top, "○", 13, bold=True, color=TEXT3)
        self._voice_state_icon.grid(row=0, column=0, padx=(0, 6))
        self._voice_state_lbl = _lbl(vs_top, "Voz desactivada", 11, color=TEXT2)
        self._voice_state_lbl.grid(row=0, column=1, sticky="w")

        # Módulo activo
        vm_row = ctk.CTkFrame(self._voice_status_card, fg_color="transparent")
        vm_row.grid(row=1, column=0, sticky="ew", padx=10, pady=2)
        vm_row.grid_columnconfigure(0, weight=1)
        _lbl(vm_row, "Módulo", 10, color=TEXT3).grid(row=0, column=0, sticky="w")
        self._voice_module_lbl = _lbl(vm_row, "—", 11, bold=True, color=GREEN_TXT)
        self._voice_module_lbl.grid(row=0, column=1, sticky="e")

        # Último comando
        vc_row = ctk.CTkFrame(self._voice_status_card, fg_color="transparent")
        vc_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 8))
        vc_row.grid_columnconfigure(0, weight=1)
        _lbl(vc_row, "Comando", 10, color=TEXT3).grid(row=0, column=0, sticky="w")
        self._voice_cmd_lbl = _lbl(vc_row, "—", 11, bold=True, color=TEXT)
        self._voice_cmd_lbl.grid(row=0, column=1, sticky="e")

        # Advertencia confianza baja
        self._voice_warn_card = ctk.CTkFrame(ri, fg_color="#2D1B00", corner_radius=10)
        self._voice_warn_card.grid(row=19, column=0, sticky="ew")
        self._voice_warn_card.grid_remove()  # oculto por defecto
        self._voice_warn_card.grid_columnconfigure(0, weight=1)
        _lbl(self._voice_warn_card, "⚠  Confianza baja — repetí el comando",
             10, color=WARN, wraplength=170).grid(padx=10, pady=6, sticky="w")

    # ── VISTA: CONFIGURACIÓN ──────────────────────────────────────────────────

    def _build_view_configuracion(self, parent):
        """Vista embebida de configuración con tabs: Gestos, Perfiles, Mouse."""
        from ui.settings_store import (
            AVAILABLE_GESTURE_NAMES, GESTURE_THRESHOLD_KEYS,
            clone_profile, rename_profile, get_profile_actions, get_profile_voice_actions,
            parse_hotkey_spec, remove_profile_gesture_action, remove_profile_voice_action,
            set_general_settings, set_profile_gesture_action, set_profile_mouse_settings,
            set_profile_thresholds, set_profile_voice_action,
        )
        from ui.components.sliders import create_slider

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, minsize=240)
        parent.grid_rowconfigure(0, weight=1)

        cfg_state = {"config": load_config()}

        # ── Izquierda: tabs + contenido ─────────────────────────────────────────
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(18, 8), pady=18)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        # Tab bar
        tab_bar = ctk.CTkFrame(left, fg_color=CARD, corner_radius=12)
        tab_bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._cfg_tab_btns = {}
        tab_names = [("gestos", "Gestos → Acciones"), ("perfiles", "Perfiles"), ("mouse", "Mouse")]

        for col, (key, label) in enumerate(tab_names):
            btn = ctk.CTkButton(
                tab_bar, text=label, font=("Segoe UI", 12),
                fg_color=GREEN if col == 0 else "transparent",
                text_color=BG if col == 0 else TEXT2,
                hover_color=CARD_IN, corner_radius=10, height=36,
                command=lambda k=key: self._cfg_switch_tab(k),
            )
            btn.grid(row=0, column=col, sticky="ew", padx=(6 if col == 0 else 2, 2 if col < 2 else 6), pady=6)
            tab_bar.grid_columnconfigure(col, weight=1)
            self._cfg_tab_btns[key] = btn

        # Tab content host
        self._cfg_tab_host = ctk.CTkFrame(left, fg_color="transparent")
        self._cfg_tab_host.grid(row=1, column=0, sticky="nsew")
        self._cfg_tab_host.grid_columnconfigure(0, weight=1)
        self._cfg_tab_host.grid_rowconfigure(0, weight=1)
        self._cfg_tab_frames = {}

        for key in ("gestos", "perfiles", "mouse"):
            f = ctk.CTkFrame(self._cfg_tab_host, fg_color="transparent")
            f.grid(row=0, column=0, sticky="nsew")
            f.grid_columnconfigure(0, weight=1)
            f.grid_rowconfigure(0, weight=1)
            self._cfg_tab_frames[key] = f

        # ── TAB GESTOS ──────────────────────────────────────────────────────────
        tab_g = self._cfg_tab_frames["gestos"]
        tab_g.grid_rowconfigure(0, weight=1)

        scroller_g = ctk.CTkScrollableFrame(tab_g, fg_color="transparent")
        scroller_g.grid(row=0, column=0, sticky="nsew")
        scroller_g.grid_columnconfigure(0, weight=1)

        # Header row
        hdr = ctk.CTkFrame(scroller_g, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        hdr.grid_columnconfigure(1, weight=1)
        for col, txt in enumerate(["GESTO", "ACCIÓN", "MODO", "UMBRAL", "ESTADO"]):
            _lbl(hdr, txt, 9, color=TEXT3).grid(row=0, column=col, sticky="w",
                padx=(0 if col == 0 else 8, 0))

        self._gesture_row_widgets = {}  # gesture_name -> (keys_entry, slider, switch_var, action_type, hold_var)

        def build_gesture_rows(profile_name):
            for w in scroller_g.winfo_children():
                if w != hdr:
                    w.destroy()
            self._gesture_row_widgets.clear()
            actions = get_profile_actions(cfg_state["config"], profile_name)
            thresholds = get_effective_thresholds(cfg_state["config"], profile_name)
            for i, gname in enumerate(AVAILABLE_GESTURE_NAMES):
                action = actions.get(gname, {})
                threshold = thresholds.get(gname, 0.5)
                action_type = action.get("type", "hotkey") if isinstance(action, dict) else "hotkey"
                row = ctk.CTkFrame(scroller_g, fg_color=CARD, corner_radius=12)
                row.grid(row=i + 1, column=0, sticky="ew", pady=(0, 6))
                row.grid_columnconfigure(2, weight=1)

                # Icon + name
                icon_f = ctk.CTkFrame(row, fg_color=BLUE, corner_radius=8, width=30, height=30)
                icon_f.grid(row=0, column=0, padx=(10, 6), pady=8, sticky="w")
                icon_f.grid_propagate(False)
                ctk.CTkLabel(icon_f, text="👁", font=("Segoe UI", 12)).place(relx=0.5, rely=0.5, anchor="center")
                _lbl(row, gname.replace("_", " "), 12).grid(row=0, column=1, sticky="w", padx=(0, 8))

                # Action badge (editable)
                keys_str = "+".join(action.get("keys", [])) if isinstance(action, dict) else ""
                action_entry = ctk.CTkEntry(row, width=80, placeholder_text="ctrl+tab",
                                            font=("Segoe UI", 11))
                action_entry.insert(0, keys_str)
                action_entry.grid(row=0, column=2, padx=4)

                # Action mode: tap once or hold while gesture remains active.
                hold_var = ctk.BooleanVar(value=action_type == "key_hold")
                hold_sw = ctk.CTkSwitch(
                    row,
                    text="mantener",
                    variable=hold_var,
                    button_color=GREEN,
                    progress_color=GREEN_DIM,
                    width=70,
                    font=("Segoe UI", 10),
                )
                hold_sw.grid(row=0, column=3, padx=4)
                if action_type in {"mouse_click", "mouse_double_click"}:
                    hold_sw.configure(state="disabled")

                # Threshold slider
                thr_var = ctk.StringVar(value=f"{threshold:.1f}")
                sl = ctk.CTkSlider(row, from_=0.0, to=1.0, width=80,
                                   button_color=GREEN, progress_color=GREEN, fg_color=CARD_IN)
                sl.set(threshold)
                sl.configure(command=lambda v, tv=thr_var: tv.set(f"{v:.1f}"))
                sl.grid(row=0, column=4, padx=4)
                ctk.CTkLabel(row, textvariable=thr_var, width=28,
                             font=("Segoe UI", 11), text_color=GREEN_TXT).grid(row=0, column=5, padx=(0, 4))

                # Enable toggle
                sw_var = ctk.BooleanVar(value=bool(action))
                sw = ctk.CTkSwitch(row, text="", variable=sw_var,
                                   button_color=GREEN, progress_color=GREEN_DIM, width=44)
                sw.grid(row=0, column=6, padx=(4, 10))

                self._gesture_row_widgets[gname] = (action_entry, sl, sw_var, action_type, hold_var)

            # Save row
            save_row = ctk.CTkFrame(scroller_g, fg_color="transparent")
            save_row.grid(row=len(AVAILABLE_GESTURE_NAMES) + 1, column=0, sticky="ew", pady=(10, 0))
            save_row.grid_columnconfigure((0, 1), weight=1)
            ctk.CTkButton(
                save_row, text="✓  Guardar gestos",
                fg_color=GREEN, text_color=BG, hover_color=GREEN_TXT,
                font=("Segoe UI", 12, "bold"), corner_radius=10, height=38,
                command=lambda: save_gestures(cfg_profile_sel.get()),
            ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
            ctk.CTkButton(
                save_row, text="↺  Recargar",
                fg_color=CARD, text_color=TEXT, border_width=1, border_color=TEXT3,
                hover_color=CARD_IN, corner_radius=10, height=38,
                command=lambda: build_gesture_rows(cfg_profile_sel.get()),
            ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        def save_gestures(profile_name):
            updated = cfg_state["config"]
            thr_payload = {}
            for gname, (entry, sl, sw_var, action_type, hold_var) in self._gesture_row_widgets.items():
                keys_raw = entry.get().strip()
                if sw_var.get() and action_type in {"mouse_click", "mouse_double_click"}:
                    updated = set_profile_gesture_action(
                        updated,
                        profile_name,
                        gname,
                        keys=[],
                        label=gname,
                        action_type=action_type,
                    )
                elif keys_raw and sw_var.get():
                    keys = parse_hotkey_spec(keys_raw)
                    if keys:
                        selected_action_type = "key_hold" if bool(hold_var.get()) else "hotkey"
                        updated = set_profile_gesture_action(
                            updated,
                            profile_name,
                            gname,
                            keys=keys,
                            label=gname,
                            action_type=selected_action_type,
                        )
                else:
                    updated = remove_profile_gesture_action(updated, profile_name, gname)
                thr_payload[gname] = float(sl.get())
            updated = set_profile_thresholds(updated, profile_name, thr_payload)
            save_config(updated)
            cfg_state["config"] = updated
            self._config = updated
            refresh_right_panel(profile_name)
            messagebox.showinfo("GazeDash", "Gestos guardados correctamente.")

        # ── TAB PERFILES ─────────────────────────────────────────────────────────
        tab_p = self._cfg_tab_frames["perfiles"]
        tab_p.grid_rowconfigure(0, weight=1)
        p_scroll = ctk.CTkScrollableFrame(tab_p, fg_color="transparent")
        p_scroll.grid(row=0, column=0, sticky="nsew")
        p_scroll.grid_columnconfigure(0, weight=1)

        _section_title(p_scroll, "Perfil activo").grid(row=0, column=0, sticky="w", pady=(0, 8))

        # Selector de perfil
        profile_sel_row = ctk.CTkFrame(p_scroll, fg_color="transparent")
        profile_sel_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        profile_sel_row.grid_columnconfigure(0, weight=1)

        cfg_profile_sel = ctk.CTkOptionMenu(
            profile_sel_row,
            values=list(get_profiles(cfg_state["config"]).keys()),
            font=("Segoe UI", 12), fg_color=CARD, button_color=GREEN,
            dropdown_fg_color=CARD,
        )
        cfg_profile_sel.set(get_active_profile_name(cfg_state["config"]))
        cfg_profile_sel.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            profile_sel_row, text="✏ Renombrar", width=90,
            fg_color=CARD, text_color=TEXT, hover_color=TEXT3,
            font=("Segoe UI", 11, "bold"), corner_radius=8,
            command=lambda: rename_current_profile(),
        ).grid(row=0, column=1)

        # Info del perfil
        self._cfg_profile_info = _lbl(p_scroll, "—", 12, color=TEXT2)
        self._cfg_profile_info.grid(row=2, column=0, sticky="w", pady=(0, 16))

        _section_title(p_scroll, "Crear nuevo perfil").grid(row=3, column=0, sticky="w", pady=(0, 6))
        new_row = ctk.CTkFrame(p_scroll, fg_color="transparent")
        new_row.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        new_row.grid_columnconfigure(0, weight=1)
        new_profile_entry = ctk.CTkEntry(new_row, placeholder_text="Nombre del nuevo perfil...")
        new_profile_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            new_row, text="+ Crear", width=80,
            fg_color=GREEN, text_color=BG, hover_color=GREEN_TXT,
            font=("Segoe UI", 11, "bold"), corner_radius=8,
            command=lambda: create_profile(),
        ).grid(row=0, column=1)

        _section_title(p_scroll, "Vista rápida de gestos").grid(
            row=5, column=0, sticky="w", pady=(12, 6)
        )
        self._cfg_actions_box = ctk.CTkTextbox(p_scroll, height=160, font=("Segoe UI", 11))
        self._cfg_actions_box.grid(row=6, column=0, sticky="ew")
        self._cfg_actions_box.configure(state="disabled")

        _section_title(p_scroll, "Comandos de voz").grid(row=7, column=0, sticky="w", pady=(12, 6))
        self._cfg_voice_box = ctk.CTkTextbox(p_scroll, height=120, font=("Segoe UI", 11))
        self._cfg_voice_box.grid(row=8, column=0, sticky="ew")
        self._cfg_voice_box.configure(state="disabled")

        def _set_textbox(box, text):
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", text)
            box.configure(state="disabled")

        def rename_current_profile():
            old_name = cfg_profile_sel.get()
            dialog = ctk.CTkInputDialog(text=f"Ingresa el nuevo nombre para el perfil '{old_name}':", title="Renombrar perfil")
            new_name = dialog.get_input()
            if not new_name: return
            new_name = new_name.strip()
            if not new_name or new_name == old_name: return
            if new_name in get_profiles(cfg_state["config"]):
                messagebox.showwarning("GazeDash", "Ya existe ese perfil."); return
            
            updated = rename_profile(cfg_state["config"], old_name, new_name)
            save_config(updated)
            cfg_state["config"] = updated
            self._config = updated
            if hasattr(self, "_hotkey_executor"):
                self._hotkey_executor.update_config(self._config)
            if hasattr(self, "_voice_controller"):
                self._voice_controller.update_config(self._config)
            if hasattr(self, "_mouse_driver"):
                self._mouse_driver.update_config(self._config)
            self.refresh_state()
            profiles = list(get_profiles(updated).keys())
            cfg_profile_sel.configure(values=profiles)
            cfg_profile_sel.set(new_name)
            refresh_right_panel(new_name)
            messagebox.showinfo("GazeDash", f"Perfil renombrado a: '{new_name}'.")

        def create_profile():
            name = new_profile_entry.get().strip()
            if not name:
                messagebox.showwarning("GazeDash", "Ingresá un nombre."); return
            if name in get_profiles(cfg_state["config"]):
                messagebox.showwarning("GazeDash", "Ya existe ese perfil."); return
            updated = clone_profile(cfg_state["config"], name, cfg_profile_sel.get())
            save_config(updated)
            cfg_state["config"] = updated
            self._config = updated
            profiles = list(get_profiles(updated).keys())
            cfg_profile_sel.configure(values=profiles)
            cfg_profile_sel.set(name)
            new_profile_entry.delete(0, "end")
            refresh_right_panel(name)
            messagebox.showinfo("GazeDash", f"Perfil '{name}' creado.")

        # ── TAB MOUSE ────────────────────────────────────────────────────────────
        tab_m = self._cfg_tab_frames["mouse"]
        tab_m.grid_rowconfigure(0, weight=1)
        m_scroll = ctk.CTkScrollableFrame(tab_m, fg_color="transparent")
        m_scroll.grid(row=0, column=0, sticky="nsew")
        m_scroll.grid_columnconfigure(0, weight=1)

        self._mouse_cfg_widgets = {}

        def build_mouse_tab(profile_name):
            for w in m_scroll.winfo_children():
                w.destroy()
            self._mouse_cfg_widgets.clear()
            ms = get_profile_mouse_settings(cfg_state["config"], profile_name)

            _section_title(m_scroll, "Estado").grid(row=0, column=0, sticky="w", pady=(0, 8))
            en_var = ctk.BooleanVar(value=bool(ms.get("enabled", True)))
            en_row = ctk.CTkFrame(m_scroll, fg_color=CARD, corner_radius=12)
            en_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
            en_row.grid_columnconfigure(0, weight=1)
            _lbl(en_row, "Activar mouse por nariz", 12).grid(row=0, column=0, sticky="w", padx=14, pady=10)

            def _toggle_mouse_now(profile=profile_name, var=en_var):
                """Aplica el cambio de mouse enabled inmediatamente sin necesitar guardar."""
                ms_now = get_profile_mouse_settings(cfg_state["config"], profile)
                ms_now["enabled"] = bool(var.get())
                updated = set_profile_mouse_settings(cfg_state["config"], profile, ms_now)
                save_config(updated)
                cfg_state["config"] = updated
                self._config = updated
                self._load_mouse_settings()
                self.refresh_state()

            ctk.CTkSwitch(en_row, text="", variable=en_var,
                          button_color=GREEN, progress_color=GREEN_DIM,
                          command=_toggle_mouse_now).grid(
                row=0, column=1, sticky="e", padx=14
            )
            self._mouse_cfg_widgets["enabled"] = en_var

            def _mouse_slider(row_idx, key, label, default, lo, hi):
                c = _card(m_scroll)
                c.grid(row=row_idx, column=0, sticky="ew", pady=(0, 8))
                c.grid_columnconfigure(0, weight=1)
                c_top = ctk.CTkFrame(c, fg_color="transparent")
                c_top.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
                c_top.grid_columnconfigure(0, weight=1)
                _lbl(c_top, label, 12, color=TEXT2).grid(row=0, column=0, sticky="w")
                vv = ctk.StringVar(value=f"{float(default):.2f}")
                ctk.CTkLabel(c_top, textvariable=vv, text_color=GREEN_TXT,
                             font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="e")
                sl2 = ctk.CTkSlider(c, from_=lo, to=hi, button_color=GREEN,
                                    progress_color=GREEN, fg_color=CARD_IN)
                sl2.set(float(default))
                sl2.configure(command=lambda v, vvr=vv: vvr.set(f"{v:.2f}"))
                sl2.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
                self._mouse_cfg_widgets[key] = sl2

            _mouse_slider(2, "dead_zone",  "Zona muerta",  ms.get("dead_zone",  25), 0, 150)
            _mouse_slider(3, "max_speed",  "Velocidad máx", ms.get("max_speed",  35), 1, 100)
            _mouse_slider(4, "smoothing",  "Suavizado",     ms.get("smoothing", 0.2), 0, 1)

            center_val = "Calibrado" if ms.get("center") else "No calibrado"
            info_c = _inner_card(m_scroll)
            info_c.grid(row=5, column=0, sticky="ew", pady=(0, 8))
            info_c.grid_columnconfigure(0, weight=1)
            _lbl(info_c, "Centro de referencia", 12, color=TEXT2).grid(
                row=0, column=0, sticky="w", padx=14, pady=8
            )
            _lbl(info_c, center_val, 12, color=GREEN_TXT, bold=True).grid(
                row=0, column=1, sticky="e", padx=14
            )

            save_mouse_btn = ctk.CTkFrame(m_scroll, fg_color="transparent")
            save_mouse_btn.grid(row=6, column=0, sticky="ew", pady=(10, 0))
            save_mouse_btn.grid_columnconfigure(0, weight=1)
            ctk.CTkButton(
                save_mouse_btn, text="✓  Guardar ajustes de mouse",
                fg_color=GREEN, text_color=BG, hover_color=GREEN_TXT,
                font=("Segoe UI", 12, "bold"), corner_radius=10, height=38,
                command=lambda: save_mouse(cfg_profile_sel.get()),
            ).grid(row=0, column=0, sticky="ew")

        def save_mouse(profile_name):
            ms_existing = get_profile_mouse_settings(cfg_state["config"], profile_name)
            ms_existing.update({
                "enabled":  bool(self._mouse_cfg_widgets["enabled"].get()),
                "dead_zone": float(self._mouse_cfg_widgets["dead_zone"].get()),
                "max_speed": float(self._mouse_cfg_widgets["max_speed"].get()),
                "smoothing": float(self._mouse_cfg_widgets["smoothing"].get()),
            })
            updated = set_profile_mouse_settings(cfg_state["config"], profile_name, ms_existing)
            save_config(updated)
            cfg_state["config"] = updated
            self._config = updated
            self._load_mouse_settings()
            messagebox.showinfo("GazeDash", "Ajustes de mouse guardados.")

        # ── Panel derecho ─────────────────────────────────────────────────────
        right = ctk.CTkFrame(parent, fg_color=SIDEBAR_BG, width=240, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)
        right.grid_columnconfigure(0, weight=1)

        ri = ctk.CTkScrollableFrame(right, fg_color="transparent")
        ri.pack(fill="both", expand=True, padx=14, pady=16)
        ri.grid_columnconfigure(0, weight=1)

        # Perfil activo (chip grande)
        _section_title(ri, "Perfil activo").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self._cfg_active_chip = ctk.CTkFrame(ri, fg_color=CARD, corner_radius=12)
        self._cfg_active_chip.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self._cfg_active_chip.grid_columnconfigure(0, weight=1)
        self._cfg_active_name_lbl = _lbl(self._cfg_active_chip, "—", 14, bold=True)
        self._cfg_active_name_lbl.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self._cfg_active_sub_lbl = _lbl(self._cfg_active_chip, "—", 11, color=TEXT2)
        self._cfg_active_sub_lbl.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))

        # Otros perfiles
        ctk.CTkFrame(ri, height=1, fg_color=TEXT3).grid(
            row=2, column=0, sticky="ew", pady=(8, 8)
        )
        _section_title(ri, "Otros perfiles").grid(row=3, column=0, sticky="w", pady=(0, 6))
        self._cfg_other_profiles_frame = ctk.CTkFrame(ri, fg_color="transparent")
        self._cfg_other_profiles_frame.grid(row=4, column=0, sticky="ew")
        self._cfg_other_profiles_frame.grid_columnconfigure(0, weight=1)

        # Mouse por nariz (resumen)
        ctk.CTkFrame(ri, height=1, fg_color=TEXT3).grid(
            row=5, column=0, sticky="ew", pady=(8, 8)
        )
        _section_title(ri, "Mouse por nariz").grid(row=6, column=0, sticky="w", pady=(0, 6))
        self._cfg_mouse_right = {}
        for r_idx, (label, key, fmt) in enumerate([
            ("Estado",    "enabled",   lambda v: "activo" if v else "inactivo"),
            ("Velocidad", "max_speed", lambda v: f"{v:.0f}×"),
            ("Zona muerta","dead_zone",lambda v: f"{v:.0f}"),
            ("Suavizado",  "smoothing", lambda v: f"{v:.2f}"),
        ]):
            row_f = ctk.CTkFrame(ri, fg_color="transparent")
            row_f.grid(row=7 + r_idx, column=0, sticky="ew", pady=2)
            row_f.grid_columnconfigure(0, weight=1)
            _lbl(row_f, label, 12, color=TEXT2).grid(row=0, column=0, sticky="w")
            vl = _lbl(row_f, "—", 11, color=GREEN_TXT, bold=True)
            vl.grid(row=0, column=1, sticky="e")
            self._cfg_mouse_right[key] = (vl, fmt)

        # Control de voz — toggle
        ctk.CTkFrame(ri, height=1, fg_color=TEXT3).grid(
            row=11, column=0, sticky="ew", pady=(8, 8)
        )
        _section_title(ri, "Control de voz").grid(row=12, column=0, sticky="w", pady=(0, 6))
        voice_card = ctk.CTkFrame(ri, fg_color=CARD, corner_radius=12)
        voice_card.grid(row=13, column=0, sticky="ew", pady=(0, 4))
        voice_card.grid_columnconfigure(0, weight=1)
        _lbl(voice_card, "Activar módulo de voz", 12).grid(
            row=0, column=0, sticky="w", padx=12, pady=10
        )
        self._cfg_voice_enabled_var = ctk.BooleanVar(
            value=bool(get_voice_control_settings(cfg_state["config"]).get("enabled", False))
        )

        def _toggle_voice_enabled():
            val = self._cfg_voice_enabled_var.get()
            updated = set_voice_control_settings(cfg_state["config"], enabled=val)
            save_config(updated)
            cfg_state["config"] = updated
            self._config = updated
            self._voice_controller.update_config(updated)
            self.refresh_state()

        ctk.CTkSwitch(
            voice_card, text="", variable=self._cfg_voice_enabled_var,
            button_color=GREEN, progress_color=GREEN_DIM,
            command=_toggle_voice_enabled,
        ).grid(row=0, column=1, sticky="e", padx=12)

        def refresh_right_panel(profile_name):
            """Actualiza el panel derecho cuando cambia el perfil."""
            profiles_dict = get_profiles(cfg_state["config"])
            _, profile = get_profile_details(cfg_state["config"], profile_name)
            actions = get_profile_actions(cfg_state["config"], profile_name)
            voice_actions = get_profile_voice_actions(cfg_state["config"], profile_name)
            ms = get_profile_mouse_settings(cfg_state["config"], profile_name)

            # Active chip
            disp = profile.get("display_name") or profile_name
            gesture_count = len([a for a in actions.values() if a])
            self._cfg_active_name_lbl.configure(text=disp)
            self._cfg_active_sub_lbl.configure(
                text=f"{gesture_count} gestos · {'mouse activo' if ms.get('enabled', True) else 'mouse inactivo'}"
            )

            # Other profiles list
            for w in self._cfg_other_profiles_frame.winfo_children():
                w.destroy()
            other = [p for p in profiles_dict if p != profile_name]
            for i, pname in enumerate(other[:4]):
                pf = ctk.CTkFrame(self._cfg_other_profiles_frame, fg_color=CARD, corner_radius=8)
                pf.grid(row=i, column=0, sticky="ew", pady=2)
                pf.grid_columnconfigure(0, weight=1)
                _lbl(pf, pname, 12).grid(row=0, column=0, sticky="w", padx=10, pady=7)
            if len(other) == 0:
                _lbl(self._cfg_other_profiles_frame, "Solo un perfil", 11, color=TEXT3
                     ).grid(row=0, column=0, sticky="w")

            # Mouse summary
            for key, (lbl_w, fmt_fn) in self._cfg_mouse_right.items():
                raw_val = ms.get(key, "—")
                try:
                    lbl_w.configure(text=fmt_fn(raw_val),
                                    text_color=GREEN_TXT if key == "enabled" and raw_val else
                                               (TEXT3 if key == "enabled" else GREEN_TXT))
                except Exception:
                    lbl_w.configure(text="—")

            # Sync voice toggle
            voice_enabled = bool(
                get_voice_control_settings(cfg_state["config"]).get("enabled", False)
            )
            self._cfg_voice_enabled_var.set(voice_enabled)

            # Textboxes
            lines_g = [f"{g}: {'+'.join(a.get('keys', [])) if isinstance(a, dict) else '—'}"
                       for g, a in actions.items()]
            _set_textbox(self._cfg_actions_box,
                         "\n".join(lines_g) if lines_g else "Sin gestos configurados.")
            lines_v = [f"{c}: {'+'.join(a.get('keys', [])) if isinstance(a, dict) else '—'}"
                       for c, a in voice_actions.items()]
            _set_textbox(self._cfg_voice_box,
                         "\n".join(lines_v) if lines_v else "Sin comandos de voz.")

            # Update gesture rows and mouse tab if built
            build_gesture_rows(profile_name)
            build_mouse_tab(profile_name)
            cfg_profile_sel.configure(values=list(profiles_dict.keys()))
            cfg_profile_sel.set(profile_name)

        def activate_profile(profile_name):
            cfg_state["config"]["active_profile"] = profile_name
            save_config(cfg_state["config"])
            self._config = cfg_state["config"]
            if hasattr(self, "_hotkey_executor"):
                self._hotkey_executor.update_config(self._config)
            if hasattr(self, "_voice_controller"):
                self._voice_controller.update_config(self._config)
            if hasattr(self, "_mouse_driver"):
                self._mouse_driver.update_config(self._config)
            self.refresh_state()
            refresh_right_panel(profile_name)

        # Wire profile selector
        cfg_profile_sel.configure(
            command=lambda v: activate_profile(v)
        )

        # Initial load
        initial_profile = get_active_profile_name(cfg_state["config"])
        build_gesture_rows(initial_profile)
        build_mouse_tab(initial_profile)
        refresh_right_panel(initial_profile)
        self._cfg_switch_tab("gestos")

    def _cfg_switch_tab(self, tab_name):
        """Muestra el tab activo y actualiza estilos de los botones."""
        for key, btn in self._cfg_tab_btns.items():
            if key == tab_name:
                btn.configure(fg_color=GREEN, text_color=BG)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT2)
        for key, frame in self._cfg_tab_frames.items():
            if key == tab_name:
                frame.grid()
            else:
                frame.grid_remove()


    # ── VISTA: CALIBRACIÓN ────────────────────────────────────────────────────

    def _build_view_calibracion(self, parent):
        """Vista embebida de calibración con sliders por gesto, selector de perfil y botones de acción."""
        from ui.settings_store import (
            get_effective_thresholds, get_active_profile_name,
            get_profile_details, set_profile_thresholds,
        )

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        cal_state = {"config": load_config()}

        # ── Layout principal: izquierda (sliders) + derecha (info panel) ──────
        main = ctk.CTkFrame(parent, fg_color="transparent")
        main.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, minsize=220)
        main.grid_rowconfigure(1, weight=1)

        # ── Banner instrucción ─────────────────────────────────────────────────
        banner = ctk.CTkFrame(main, fg_color=CARD, corner_radius=14)
        banner.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        banner.grid_columnconfigure(1, weight=1)

        icon_b = ctk.CTkFrame(banner, fg_color=GREEN_DIM, corner_radius=10, width=40, height=40)
        icon_b.grid(row=0, column=0, padx=(14, 10), pady=12)
        icon_b.grid_propagate(False)
        ctk.CTkLabel(icon_b, text="◎", font=("Segoe UI", 18), text_color=GREEN_TXT).place(
            relx=0.5, rely=0.5, anchor="center"
        )
        _lbl(banner, "Ajustá cada umbral hasta que el gesto quede estable. "
             "Guardá al terminar para aplicar al perfil activo.",
             12, color=TEXT2).grid(row=0, column=1, sticky="w", pady=12, padx=(0, 14))

        # ── Área izquierda: selector + grid de sliders ─────────────────────────
        left = ctk.CTkFrame(main, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        # Selector de perfil
        prof_row = ctk.CTkFrame(left, fg_color="transparent")
        prof_row.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        prof_row.grid_columnconfigure(1, weight=1)
        _section_title(prof_row, "Perfil").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self._cal_profile_sel = ctk.CTkOptionMenu(
            prof_row,
            values=list(get_profiles(cal_state["config"]).keys()),
            font=("Segoe UI", 12), fg_color=CARD, button_color=GREEN,
            dropdown_fg_color=CARD,
        )
        self._cal_profile_sel.set(get_active_profile_name(cal_state["config"]))
        self._cal_profile_sel.grid(row=0, column=1, sticky="ew")

        # Scroller de tarjetas de umbral (grid 2-col)
        scroller = ctk.CTkScrollableFrame(left, fg_color="transparent")
        scroller.grid(row=1, column=0, sticky="nsew")
        scroller.grid_columnconfigure(0, weight=1)
        scroller.grid_columnconfigure(1, weight=1)

        self._cal_slider_widgets = {}  # key -> CTkSlider

        def build_sliders(profile_name):
            for w in scroller.winfo_children():
                w.destroy()
            self._cal_slider_widgets.clear()
            thresholds = get_effective_thresholds(cal_state["config"], profile_name)

            for idx, key in enumerate(GESTURE_THRESHOLD_KEYS):
                val = float(thresholds.get(key, 0.5))
                col = idx % 2
                row = idx // 2
                card = _card(scroller)
                card.grid(row=row, column=col, sticky="ew",
                          padx=(0 if col == 0 else 4, 4 if col == 0 else 0), pady=(0, 8))
                card.grid_columnconfigure(0, weight=1)

                # Header: nombre + valor en vivo
                hdr = ctk.CTkFrame(card, fg_color="transparent")
                hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
                hdr.grid_columnconfigure(0, weight=1)
                _lbl(hdr, key.replace("_", " ").title(), 11, color=TEXT2).grid(
                    row=0, column=0, sticky="w"
                )
                val_var = ctk.StringVar(value=f"{val:.3f}")
                ctk.CTkLabel(hdr, textvariable=val_var, text_color=GREEN_TXT,
                             font=("Segoe UI", 11, "bold")).grid(row=0, column=1, sticky="e")

                sl = ctk.CTkSlider(
                    card, from_=0.0, to=1.0,
                    button_color=GREEN, progress_color=GREEN, fg_color=CARD_IN,
                )
                sl.set(val)
                sl.configure(command=lambda v, vv=val_var: vv.set(f"{v:.3f}"))
                sl.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
                self._cal_slider_widgets[key] = sl

            # Botón Auto-calibrar ocupa ancho completo al final
            auto_row = len(GESTURE_THRESHOLD_KEYS) // 2 + (1 if len(GESTURE_THRESHOLD_KEYS) % 2 else 0)
            auto_btn = ctk.CTkButton(
                scroller, text="⟳  Auto-calibrar (posición neutral)",
                fg_color=CARD, text_color=TEXT, border_width=1, border_color=TEXT3,
                hover_color=CARD_IN, corner_radius=10, height=38,
                command=self._capture_neutral_base,
            )
            auto_btn.grid(row=auto_row, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # Actualizar sliders al cambiar perfil
        self._cal_profile_sel.configure(
            command=lambda v: build_sliders(v)
        )

        # Carga inicial
        build_sliders(get_active_profile_name(cal_state["config"]))

        # ── Botones de acción ──────────────────────────────────────────────────
        footer = ctk.CTkFrame(left, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        footer.grid_columnconfigure((0, 1, 2), weight=1)

        def save_calibration():
            profile_name = self._cal_profile_sel.get()
            payload = {k: float(sl.get()) for k, sl in self._cal_slider_widgets.items()}
            updated = set_profile_thresholds(cal_state["config"], profile_name, payload)
            save_config(updated)
            cal_state["config"] = updated
            self._config = updated
            messagebox.showinfo("GazeDash", "Calibración guardada correctamente.")

        def restore_defaults():
            defaults = {k: 0.5 for k in GESTURE_THRESHOLD_KEYS}
            for k, sl in self._cal_slider_widgets.items():
                sl.set(defaults.get(k, 0.5))
            messagebox.showinfo("GazeDash", "Valores restaurados a 0.5. Guardá para aplicar.")

        ctk.CTkButton(
            footer, text="✓  Guardar",
            fg_color=GREEN, text_color=BG, hover_color=GREEN_TXT,
            font=("Segoe UI", 12, "bold"), corner_radius=10, height=40,
            command=save_calibration,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            footer, text="↺  Restaurar defaults",
            fg_color=CARD, text_color=TEXT, border_width=1, border_color=TEXT3,
            hover_color=CARD_IN, corner_radius=10, height=40,
            command=restore_defaults,
        ).grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkButton(
            footer, text="⊡  Foto base neutral",
            fg_color=CARD, text_color=TEXT, border_width=1, border_color=TEXT3,
            hover_color=CARD_IN, corner_radius=10, height=40,
            command=self._capture_neutral_base,
        ).grid(row=0, column=2, sticky="ew", padx=(4, 0))

        # ── Panel derecho: info + instrucciones ───────────────────────────────
        right = ctk.CTkFrame(main, fg_color=SIDEBAR_BG, width=220, corner_radius=0)
        right.grid(row=1, column=1, sticky="nsew")
        right.grid_propagate(False)
        right.grid_columnconfigure(0, weight=1)

        ri = ctk.CTkScrollableFrame(right, fg_color="transparent")
        ri.pack(fill="both", expand=True, padx=14, pady=16)
        ri.grid_columnconfigure(0, weight=1)

        _section_title(ri, "Instrucciones").pack(anchor="w", pady=(0, 10))

        hints = [
            ("1.", "Seleccioná el perfil a ajustar."),
            ("2.", "Mové cada slider hasta que el gesto quede estable."),
            ("3.", "Usá 'Foto base' para recapturar tu expresión neutral."),
            ("4.", "Guardá para aplicar los cambios."),
        ]
        for num, hint in hints:
            h_row = ctk.CTkFrame(ri, fg_color=CARD, corner_radius=10)
            h_row.pack(fill="x", pady=(0, 6))
            h_row.grid_columnconfigure(1, weight=1)
            _lbl(h_row, num, 11, bold=True, color=GREEN_TXT).grid(
                row=0, column=0, padx=(10, 6), pady=8, sticky="w"
            )
            _lbl(h_row, hint, 11, color=TEXT2).grid(
                row=0, column=1, padx=(0, 10), pady=8, sticky="w"
            )

        ctk.CTkFrame(ri, height=1, fg_color=TEXT3).pack(fill="x", pady=(8, 10))
        _section_title(ri, "Resumen").pack(anchor="w", pady=(0, 8))

        summary_card = _inner_card(ri)
        summary_card.pack(fill="x")
        summary_card.grid_columnconfigure(0, weight=1)

        for s_idx, (s_label, s_val) in enumerate([
            ("Gestos calibrables", str(len(GESTURE_THRESHOLD_KEYS))),
            ("Cámara",             str(cal_state["config"].get("camera_index", 0))),
        ]):
            sr = ctk.CTkFrame(summary_card, fg_color="transparent")
            sr.grid(row=s_idx, column=0, sticky="ew",
                    padx=12, pady=(10 if s_idx == 0 else 4, 10 if s_idx == 1 else 0))
            sr.grid_columnconfigure(0, weight=1)
            _lbl(sr, s_label, 11, color=TEXT2).grid(row=0, column=0, sticky="w")
            _lbl(sr, s_val, 11, bold=True, color=GREEN_TXT).grid(row=0, column=1, sticky="e")

    # ── VISTA: VOZ ────────────────────────────────────────────────────────────

    def _build_view_voz(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, minsize=230)
        parent.grid_rowconfigure(0, weight=1)

        # ── Izquierda ──────────────────────────────────────────────────────────
        left = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(18, 8), pady=18)
        left.grid_columnconfigure(0, weight=1)

        # Banner de estado
        deps_ok = self._check_voice_deps()
        banner_bg   = "#2D1B00" if not deps_ok else GREEN_DIM
        banner_icon = "⚠" if not deps_ok else "✓"
        banner_msg  = (
            "Módulo inactivo — instalá librosa, sounddevice, pandas, xgboost"
            if not deps_ok
            else "Módulo de voz listo. Habilitá desde Configuración → Control de voz."
        )
        banner = ctk.CTkFrame(left, fg_color=banner_bg, corner_radius=12)
        banner.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        ctk.CTkLabel(
            banner,
            text=f"{banner_icon}  {banner_msg}",
            font=("Segoe UI", 12),
            text_color=WARN if not deps_ok else GREEN_TXT,
            anchor="w", wraplength=440,
        ).pack(anchor="w", padx=16, pady=12)

        # Módulos de activación
        _section_title(left, "Módulos de activación").grid(
            row=1, column=0, sticky="w", pady=(0, 8)
        )
        mg = ctk.CTkFrame(left, fg_color="transparent")
        mg.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        mg.grid_columnconfigure((0, 1), weight=1)

        module_defs = [
            ("🌐", "Web",           BLUE,    0, 0),
            ("▶",  "Multimedia",    PURPLE,  0, 1),
            ("🧭", "Navegación",    "#065F46", 1, 0),
            ("♿", "Accesibilidad", "#1E1B4B", 1, 1),
        ]
        self._voice_module_count_labels = {}
        for icon, name, color, r, c in module_defs:
            mc = _card(mg)
            mc.grid(row=r, column=c, sticky="ew", padx=4, pady=4)
            mc.grid_columnconfigure(0, weight=1)
            icon_f = ctk.CTkFrame(mc, fg_color=color, corner_radius=8, width=36, height=36)
            icon_f.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
            icon_f.grid_propagate(False)
            ctk.CTkLabel(icon_f, text=icon, font=("Segoe UI", 14)).place(
                relx=0.5, rely=0.5, anchor="center"
            )
            _lbl(mc, name, 13, bold=True).grid(row=1, column=0, sticky="w", padx=12)
            cnt = _lbl(mc, "— comandos", 11, color=TEXT2)
            cnt.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 12))
            self._voice_module_count_labels[name.lower()] = cnt

        # Ajustes de audio
        ctk.CTkFrame(left, height=1, fg_color=TEXT3).grid(
            row=3, column=0, sticky="ew", pady=(4, 12)
        )
        _section_title(left, "Ajustes de audio").grid(row=4, column=0, sticky="w", pady=(0, 8))

        audio = ctk.CTkFrame(left, fg_color="transparent")
        audio.grid(row=5, column=0, sticky="ew")
        audio.grid_columnconfigure(1, weight=1)

        def _audio_slider(row_idx, label, attr_s, attr_l, default, max_v, fmt):
            _lbl(audio, label, 12, color=TEXT2).grid(
                row=row_idx, column=0, sticky="w", pady=6, padx=(0, 10)
            )
            sl = ctk.CTkSlider(audio, from_=0, to=max_v,
                               button_color=GREEN, progress_color=GREEN,
                               fg_color=CARD_IN)
            sl.set(default)
            sl.grid(row=row_idx, column=1, sticky="ew", padx=(0, 8))
            vl = _lbl(audio, fmt(default), 12, bold=True, color=GREEN_TXT, width=52, anchor="e")
            vl.grid(row=row_idx, column=2, sticky="e")
            sl.configure(command=lambda v, lbl=vl, f=fmt: lbl.configure(text=f(v)))
            setattr(self, attr_s, sl)
            setattr(self, attr_l, vl)

        _audio_slider(0, "Ganancia",  "_voz_gain_s", "_voz_gain_l",
                      1.0, 10.0, lambda v: f"{int(v * 10)}%")
        _audio_slider(1, "Cooldown",  "_voz_cool_s", "_voz_cool_l",
                      1.5, 10.0, lambda v: f"{v:.1f} s")

        # Diagnóstico
        ctk.CTkFrame(left, height=1, fg_color=TEXT3).grid(
            row=6, column=0, sticky="ew", pady=(12, 12)
        )
        _section_title(left, "Diagnóstico").grid(row=7, column=0, sticky="w", pady=(0, 8))
        diag_card = _inner_card(left)
        diag_card.grid(row=8, column=0, sticky="ew")
        diag_card.grid_columnconfigure(0, weight=1)

        self._diag_labels = {}
        for i, (dname, dkey) in enumerate([("Micrófono",    "mic"),
                                            ("Modelos",      "models"),
                                            ("Dependencias", "deps")]):
            dr = ctk.CTkFrame(diag_card, fg_color="transparent")
            dr.grid(row=i, column=0, sticky="ew",
                    padx=14, pady=(10 if i == 0 else 4, 10 if i == 2 else 0))
            dr.grid_columnconfigure(0, weight=1)
            _lbl(dr, dname, 12, color=TEXT2).grid(row=0, column=0, sticky="w")
            dl = _lbl(dr, "verificando...", 11, color=TEXT3)
            dl.grid(row=0, column=1, sticky="e")
            self._diag_labels[dkey] = dl

        # Botones
        vbr = ctk.CTkFrame(left, fg_color="transparent")
        vbr.grid(row=9, column=0, sticky="ew", pady=(16, 0))
        vbr.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            vbr, text="🎙  Probar micrófono",
            fg_color=CARD, hover_color=CARD_IN, text_color=TEXT,
            border_width=1, border_color=TEXT3, corner_radius=10, height=40,
            command=self._test_mic,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            vbr, text="💾  Guardar ajustes",
            fg_color=GREEN, hover_color=GREEN_TXT, text_color=BG,
            font=("Segoe UI", 12, "bold"), corner_radius=10, height=40,
            command=self._save_voice_settings,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # ── Derecha: mini overlay preview ───────────────────────────────────────
        right = ctk.CTkFrame(parent, fg_color=SIDEBAR_BG, width=230, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)
        right.grid_columnconfigure(0, weight=1)

        ri = ctk.CTkFrame(right, fg_color="transparent")
        ri.pack(fill="both", expand=True, padx=14, pady=16)
        ri.grid_columnconfigure(0, weight=1)

        _section_title(ri, "Mini overlay").pack(anchor="w", pady=(0, 10))

        mini_cam = _card(ri)
        mini_cam.pack(fill="x")
        self._voz_mini_preview = ctk.CTkLabel(mini_cam, text="Vista de cámara", height=120)
        self._voz_mini_preview.pack(fill="x", padx=10, pady=10)
        mini_gb = _green_badge(mini_cam, "Sin gesto")
        mini_gb.pack(pady=(0, 10))
        self._voz_mini_gesture = mini_gb.winfo_children()[0]

        mbr = ctk.CTkFrame(ri, fg_color="transparent")
        mbr.pack(fill="x", pady=(12, 0))
        mbr.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(mbr, text="↺", width=38,
                      fg_color=CARD, text_color=TEXT, hover_color=CARD_IN,
                      corner_radius=8, command=self._recalibrate_mouse,
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(mbr, text="Abrir",
                      fg_color=GREEN, text_color=BG, hover_color=GREEN_TXT,
                      font=("Segoe UI", 11, "bold"), corner_radius=8,
                      command=self.deiconify,
                      ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        _lbl(ri, "Ventana flotante al minimizar", 10, color=TEXT3).pack(pady=(10, 0))

        # Trigger diagnósticos
        self.after(600, self._run_voice_diagnostics)
        self.after(400, self._refresh_voice_module_counts)

    # ── Voz: helpers ──────────────────────────────────────────────────────────

    def _run_voice_diagnostics(self):
        deps_ok = self._check_voice_deps()
        d = self._diag_labels
        if "deps" in d:
            d["deps"].configure(
                text="✓ OK" if deps_ok else "⚠ faltan paquetes",
                text_color=GREEN_TXT if deps_ok else WARN,
            )
        if "mic" in d:
            try:
                import importlib.util
                if importlib.util.find_spec("sounddevice") is not None:
                    import sounddevice as sd
                    sd.query_devices()
                    d["mic"].configure(text="✓ detectado", text_color=GREEN_TXT)
                else:
                    d["mic"].configure(text="○ sin sounddevice", text_color=TEXT3)
            except Exception:
                d["mic"].configure(text="⚠ no detectado", text_color=DANGER)

        if "models" in d:
            from pathlib import Path
            voice_cfg   = self._config.get("voice_control", {}) if isinstance(self._config, dict) else {}
            model_paths = voice_cfg.get("model_paths", {}) if isinstance(voice_cfg, dict) else {}
            missing = [
                name for name, path in (model_paths or {}).items()
                if not Path(path).exists() and not (Path(".") / path).exists()
            ]
            if missing:
                d["models"].configure(text=f"⚠ {len(missing)} faltantes", text_color=WARN)
            else:
                d["models"].configure(
                    text=f"✓ {len(model_paths or {})} cargados", text_color=GREEN_TXT
                )

    def _refresh_voice_module_counts(self):
        profile_name  = get_active_profile_name(self._config)
        voice_actions = get_profile_voice_actions(self._config, profile_name) or {}
        prefix_map    = {
            "web":           "web",
            "multimedia":    "multimedia",
            "navegacion":    "navegación",
            "accesibilidad": "accesibilidad",
        }
        counts = {v: 0 for v in prefix_map.values()}
        for action_key in voice_actions:
            for prefix, mod in prefix_map.items():
                if str(action_key).lower().startswith(prefix):
                    counts[mod] = counts.get(mod, 0) + 1
                    break

        for mod_key, lbl in self._voice_module_count_labels.items():
            count = counts.get(mod_key, 0)
            lbl.configure(text=f"{count} comandos")

    def _test_mic(self):
        def _run():
            try:
                import sounddevice as sd
                import numpy as np
                self._diag_labels["mic"].configure(text="🎙 grabando...", text_color="#93C5FD")
                audio = sd.rec(int(2 * 16000), samplerate=16000, channels=1, dtype="float32")
                sd.wait()
                peak = float(np.max(np.abs(audio)))
                if peak < 0.01:
                    t, c = f"⚠ silencioso ({peak:.3f})", WARN
                else:
                    t, c = f"✓ OK  pico {peak:.3f}", GREEN_TXT
                self._diag_labels["mic"].configure(text=t, text_color=c)
            except ImportError:
                self._diag_labels["mic"].configure(text="⚠ sounddevice no instalado", text_color=WARN)
            except Exception as exc:
                self._diag_labels["mic"].configure(text=f"⚠ {exc}", text_color=DANGER)
        threading.Thread(target=_run, daemon=True).start()

    def _save_voice_settings(self):
        gain     = float(self._voz_gain_s.get())
        cooldown = float(self._voz_cool_s.get())
        updated  = set_voice_control_settings(self._config, gain=gain, cooldown_seconds=cooldown)
        save_config(updated)
        self._config = updated
        self._voice_controller.update_config(updated)
        messagebox.showinfo("GazeDash", "Ajustes de voz guardados.")

    # ── Refresh state ─────────────────────────────────────────────────────────

    def refresh_state(self, *_):
        self._gesture_executor.release_all_holds()
        self._config    = load_config()
        self._gesture_arbiter = GestureArbiter.from_config(self._config)
        self._restart_gesture_diagnostics_logger()
        self._voice_controller.update_config(self._config)
        profile_name    = get_active_profile_name(self._config)
        _, profile      = get_profile_details(self._config, profile_name)
        mouse_settings  = get_profile_mouse_settings(self._config, profile_name)
        voice_cfg       = get_voice_control_settings(self._config)
        self._load_mouse_settings()

        # Chip de perfil
        display = profile.get("display_name") or profile_name
        self._profile_chip_label.configure(text=display)

        # Módulos
        if hasattr(self, "_mod_rows"):
            voice_enabled = bool(voice_cfg.get("enabled", False))
            mouse_enabled = bool(mouse_settings.get("enabled", True))
            statuses = [
                ("gestos", not self._controller_paused),
                ("mouse",  mouse_enabled),
                ("voz",    voice_enabled),
            ]
            for key, active in statuses:
                dot = self._mod_rows.get(key)
                if dot:
                    dot.configure(
                        text="● activo" if active else "○ inactivo",
                        text_color=GREEN if active else TEXT3,
                    )

        # Voice sliders
        if hasattr(self, "_voz_gain_s"):
            self._voz_gain_s.set(float(voice_cfg.get("gain", 1.0)))
            self._voz_cool_s.set(float(voice_cfg.get("cooldown_seconds", 1.5)))

        # Voice module counts
        if hasattr(self, "_voice_module_count_labels"):
            self._refresh_voice_module_counts()

    def _restart_gesture_diagnostics_logger(self):
        if hasattr(self, "_gesture_diag_logger") and self._gesture_diag_logger is not None:
            self._gesture_diag_logger.close()
        self._gesture_diag_logger = GestureDiagnosticsLogger.from_config(self._config, component="ui")

    # ── Preview update ────────────────────────────────────────────────────────

    def _update_preview_widgets(self, photo, detected_gesture, face_data=None, mini_photo=None, gesture_debug=None):
        self._preview_image        = photo
        self._last_detected_gesture = detected_gesture

        # Preview label
        self.preview_label.configure(image=photo, text="")

        # Badge debajo de cámara — actualizar texto directo (sin recrear widget)
        gtext = detected_gesture or "Sin gesto"
        self._gesture_badge_lbl.configure(text=gtext)
        # Panel derecho — gesto activo
        self._active_gesture_badge_lbl.configure(text=gtext)

        # Acción activa
        action = map_gesture(detected_gesture) if detected_gesture and detected_gesture != "Sin gesto" else None
        if action and isinstance(action, dict):
            keys_text = " + ".join(action.get("keys") or [])
            action_text = keys_text or action.get("label") or action.get("type") or "—"
            self._active_action_label.configure(text=f"→  {action_text}")
        else:
            self._active_action_label.configure(text="→  —")

        self._apply_gesture_debug(gesture_debug)

        # Métricas faciales
        if face_data and isinstance(face_data, dict):
            for key, lbl in self._metric_rows.items():
                val = face_data.get(key, 0.0)
                lbl.configure(text=f"{float(val):.2f}")

        # Status de cámara
        self._cam_status_label.configure(text=f"● Activo · {self._last_fps} fps")

        # Metric cards de nariz, fps, confianza
        if self._last_nose_tip:
            nx, ny = self._last_nose_tip
            if self._nose_center:
                cx, cy = self._nose_center
                dx, dy = int(nx - cx), int(ny - cy)
                self._mn_val.configure(text=f"{dx:+d}, {dy:+d}")
                self._mn_sub.configure(text=f"↗ {self._direction(dx, dy)}")
            else:
                self._mn_val.configure(text="sin calibrar")
                self._mn_sub.configure(text="usá Recalibrar")
        self._fps_val.configure(text=str(self._last_fps))
        self._conf_val.configure(text=f"{int(self._last_confidence * 100)}%")

        # Mini overlay
        if self._mini_overlay is not None and self._mini_overlay.winfo_exists():
            _mp = mini_photo if mini_photo is not None else photo
            self._mini_preview_image = _mp   # mantener referencia
            if hasattr(self, "mini_preview_label"):
                self.mini_preview_label.configure(image=_mp, text="")
            if hasattr(self, "mini_gesture_label"):
                self.mini_gesture_label.configure(text=detected_gesture or "Sin gesto")

        # Vista voz — mini preview
        if hasattr(self, "_voz_mini_preview"):
            self._voz_mini_preview.configure(image=photo, text="")

    def _apply_gesture_debug(self, gesture_debug):
        if not isinstance(gesture_debug, dict) or not hasattr(self, "_gesture_diag_winner"):
            return

        active = gesture_debug.get("active") or []
        raw_active = gesture_debug.get("raw_active") or []
        groups = gesture_debug.get("groups") or {}

        rejected = []
        waiting = []
        score_lookup = {}
        for group_name, details in groups.items():
            if not isinstance(details, dict):
                continue
            scores = details.get("scores") or {}
            if isinstance(scores, dict):
                score_lookup.update(scores)
            rejected.extend(details.get("rejected") or [])
            candidate = details.get("candidate")
            active_winner = details.get("active")
            if candidate and candidate != active_winner:
                current = int(details.get("candidate_frames") or 0)
                required = int(details.get("required_activation_frames") or 0)
                confidence = self._gesture_debug_confidence(score_lookup.get(candidate))
                waiting.append(f"{candidate} {confidence} {current}/{required}".strip())

        winner_text = ", ".join(
            f"{gesture_name} {self._gesture_debug_confidence(score_lookup.get(gesture_name))}".strip()
            for gesture_name in active
        ) if active else "—"
        raw_text = ", ".join(raw_active) if raw_active else "—"
        rejected_text = ", ".join(dict.fromkeys(rejected)) if rejected else "—"

        if waiting and not active:
            winner_text = f"esperando {', '.join(waiting[:2])}"

        self._gesture_diag_winner.configure(text=f"Ganador: {winner_text[:42]}")
        self._gesture_diag_raw.configure(text=f"Crudos: {raw_text[:70]}")
        self._gesture_diag_rejected.configure(text=f"Descartados: {rejected_text[:64]}")

    @staticmethod
    def _gesture_debug_confidence(score_info):
        if not isinstance(score_info, dict):
            return ""
        try:
            return f"{float(score_info.get('confidence', 0.0)):.2f}"
        except (TypeError, ValueError):
            return ""

    @staticmethod
    def _direction(dx, dy):
        if abs(dx) < 5 and abs(dy) < 5:
            return "centro"
        angle = math.degrees(math.atan2(dy, dx))
        if -45 <= angle < 45:   return "este"
        if 45  <= angle < 135:  return "sur"
        if angle >= 135 or angle < -135: return "oeste"
        return "norte"

    def _draw_joystick_hud(self, frame):
        """Dibuja un HUD estilo joystick analógico sobre el frame BGR.

        Muestra:
        - Anillo exterior (rango máximo de movimiento)
        - Círculo de zona muerta (centro)
        - Línea del centro al punto actual de la nariz
        - Punto coloreado según intensidad (verde→amarillo→rojo)
        - Etiqueta de dirección
        """
        import numpy as np

        h, w = frame.shape[:2]
        # Posición del HUD: esquina inferior izquierda del video
        hud_cx = 68
        hud_cy = h - 68
        dead_r  = 18   # radio zona muerta (px en HUD)
        outer_r = 52   # radio del anillo exterior (rango máximo)

        # ── Overlay semitransparente ──────────────────────────────────────────
        overlay = frame.copy()

        # Anillo exterior (rango)  — colores en RGB
        cv2.circle(overlay, (hud_cx, hud_cy), outer_r, (40, 40, 40), -1)       # fondo oscuro
        cv2.circle(overlay, (hud_cx, hud_cy), outer_r, (80, 80, 80), 2)        # borde gris
        # Zona muerta
        cv2.circle(overlay, (hud_cx, hud_cy), dead_r, (16, 185, 129), -1)     # verde #10B981 relleno
        cv2.circle(overlay, (hud_cx, hud_cy), dead_r, (52, 211, 153), 2)      # borde verde claro

        # Cruces de referencia
        lc = (90, 90, 90)
        cv2.line(overlay, (hud_cx - outer_r, hud_cy), (hud_cx + outer_r, hud_cy), lc, 1)
        cv2.line(overlay, (hud_cx, hud_cy - outer_r), (hud_cx, hud_cy + outer_r), lc, 1)

        # Fusionar con alpha
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        # ── Posición de la nariz ──────────────────────────────────────────────
        nose = self._last_nose_tip
        center = self._nose_center

        if nose is None or center is None:
            # Sin calibrar — aviso
            cv2.putText(
                frame, "Recalibrar",
                (hud_cx - outer_r + 4, hud_cy + outer_r + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (245, 158, 11), 1, cv2.LINE_AA,
            )
            return

        nx_raw, ny_raw = nose
        cx_raw, cy_raw = center

        # Distancia real en px de cámara
        rdx = nx_raw - cx_raw
        rdy = ny_raw - cy_raw
        dist = math.hypot(rdx, rdy)

        # Escalar al HUD: max_speed en config → outer_r en HUD
        max_dist = float(getattr(self._mouse_controller, "max_speed", 35)) or 35
        scale = outer_r / max(max_dist, 1)
        hx = int(hud_cx + rdx * scale)
        hy = int(hud_cy + rdy * scale)

        # Clampear al círculo exterior
        ddx, ddy = hx - hud_cx, hy - hud_cy
        if math.hypot(ddx, ddy) > outer_r:
            ang = math.atan2(ddy, ddx)
            hx = hud_cx + int(math.cos(ang) * outer_r)
            hy = hud_cy + int(math.sin(ang) * outer_r)

        # ── Color según intensidad en RGB: verde → amarillo → rojo ────────────
        ratio = min(dist / max(max_dist, 1), 1.0)
        if ratio < 0.5:
            # verde puro → amarillo: R sube 0→220, G fijo en 210
            rc = int(ratio * 2 * 220)
            gc = 210
        else:
            # amarillo → rojo: R fijo en 220, G baja 210→0
            rc = 220
            gc = int((1.0 - (ratio - 0.5) * 2) * 210)
        dot_color = (rc, gc, 0)   # RGB — sin canal azul

        # Línea de dirección (desde centro hasta el punto)
        if math.hypot(ddx, ddy) > dead_r:
            cv2.line(frame, (hud_cx, hud_cy), (hx, hy), dot_color, 2, cv2.LINE_AA)

        # Punto de posición
        cv2.circle(frame, (hx, hy), 7, dot_color, -1, cv2.LINE_AA)
        cv2.circle(frame, (hx, hy), 7, (255, 255, 255), 1, cv2.LINE_AA)  # borde blanco

        # Punto central fijo
        cv2.circle(frame, (hud_cx, hud_cy), 3, (200, 200, 200), -1, cv2.LINE_AA)

        # ── Etiqueta de dirección ─────────────────────────────────────────────
        direction = self._direction(rdx, rdy)
        dir_icons = {
            "norte": "▲", "sur": "▼", "este": "▶", "oeste": "◀", "centro": "●"
        }
        label = dir_icons.get(direction, direction)
        cv2.putText(
            frame, label,
            (hud_cx - outer_r, hud_cy + outer_r + 14),
            cv2.FONT_HERSHEY_SIMPLEX, 0.42,
            (220, 220, 220), 1, cv2.LINE_AA,
        )

    # ── Camera loop ───────────────────────────────────────────────────────────

    def start_camera_preview(self):
        if self._preview_thread is not None and self._preview_thread.is_alive():
            return
        self._preview_stop_event.clear()
        camera_index     = int(self._config.get("camera_index", 0))
        face_cfg         = self._config.get("face_landmarks", {}) if isinstance(self._config, dict) else {}
        landmark_indices = face_cfg.get("indices", {}) if isinstance(face_cfg, dict) else {}
        landmark_offsets = face_cfg.get("offsets", {}) if isinstance(face_cfg, dict) else {}

        try:
            self._camera = open_camera(camera_index)
            self._camera_detector = MediaPipeFaceDetector(
                live_stream=False, draw_landmarks=True,
                landmark_overrides=landmark_indices,
                landmark_offsets=landmark_offsets,
            )
        except Exception as exc:
            self._cam_status_label.configure(text="⚠ Sin cámara", text_color=DANGER)
            return

        def worker():
            detector   = self._camera_detector
            frame_count = 0
            fps_timer   = time.time()

            while not self._preview_stop_event.is_set():
                frame = read_frame(self._camera)
                if frame is None:
                    continue

                frame_count += 1
                if (elapsed := time.time() - fps_timer) >= 1.0:
                    self._last_fps = int(frame_count / elapsed)
                    frame_count = 0
                    fps_timer = time.time()

                try:
                    face_data = detector.detect(frame)

                    if face_data is not None:
                        nose_tip = face_data.get("nose_tip")
                        if nose_tip is not None:
                            nx, ny = nose_tip
                            self._last_nose_tip = (nx, ny)  # siempre actualizar para Recalibrar
                            if self._analog_mouse_enabled:
                                self._mouse_controller.update(nx, ny)

                    if face_data is not None:
                        self._blink_click_controller.update(face_data)
                        self._last_confidence = max(
                            float(face_data.get("mouth_open", 0.0)),
                            float(face_data.get("smile", 0.0)),
                            0.85,
                        )

                    raw_gestures = self._gesture_detector.detect(face_data)
                    gestures = self._gesture_arbiter.filter(
                        raw_gestures,
                        action_resolver=lambda gesture_name: map_gesture(gesture_name, self._config),
                    )
                    gesture_debug = dict(self._gesture_arbiter.last_debug)
                    _, detected_gesture = self._summarize_input(gestures)
                    diag_logger = self._gesture_diag_logger
                    if diag_logger is not None:
                        diag_logger.record(
                            gesture_debug,
                            profile_name=get_active_profile_name(self._config),
                            detected_gesture=detected_gesture,
                        )

                    if self._controller_active and not self._controller_paused:
                        self._handle_gestures(gestures)
                        self._voice_controller.handle_gesture_input(gestures)
                    else:
                        self._gesture_executor.release_all_holds()

                except Exception:
                    self._gesture_executor.release_all_holds()
                    continue

                rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # HUD joystick sobre el frame principal
                try:
                    self._draw_joystick_hud(rgb)
                except Exception:
                    pass
                photo = ImageTk.PhotoImage(image=Image.fromarray(rgb))

                # Mini photo redimensionado (240×180) para el overlay
                # El HUD ya está dibujado en rgb — sólo redimensionar, no redibujar
                try:
                    mini_rgb = cv2.resize(rgb, (240, 180))
                    mini_photo = ImageTk.PhotoImage(image=Image.fromarray(mini_rgb))
                except Exception:
                    mini_photo = photo

                fd = dict(face_data) if face_data else {}

                self.after(
                    0,
                    lambda p=photo, mp=mini_photo, g=detected_gesture, f=fd, gd=gesture_debug:
                        self._update_preview_widgets(p, g, f, mp, gd),
                )

        self._preview_thread = threading.Thread(target=worker, daemon=True)
        self._preview_thread.start()

    def stop_camera_preview(self):
        self._gesture_executor.release_all_holds()
        if hasattr(self, "_gesture_diag_logger") and self._gesture_diag_logger is not None:
            self._gesture_diag_logger.close()
            self._gesture_diag_logger = None
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

    # ── Abrir ventanas de Config / Calibración ─────────────────────────────────

    def open_config(self):
        dialog = open_config_panel(self)
        self.wait_window(dialog)
        self.refresh_state()

    def open_calibration(self):
        dialog = show_calibration(self)
        self.wait_window(dialog)
        self.refresh_state()

    # ── Mini overlay (rediseñado + draggable) ─────────────────────────────────

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

        ov = ctk.CTkToplevel(self)
        ov.overrideredirect(True)
        ov.geometry("280x430+24+24")   # más alto para los toggles
        ov.attributes("-topmost", True)
        ov.configure(fg_color=SIDEBAR_BG)

        # Drag state
        ov._dx = 0
        ov._dy = 0

        def drag_start(e):
            ov._dx = e.x_root - ov.winfo_x()
            ov._dy = e.y_root - ov.winfo_y()

        def drag_move(e):
            ov.geometry(f"+{e.x_root - ov._dx}+{e.y_root - ov._dy}")

        def bind_drag(*widgets):
            for w in widgets:
                w.bind("<ButtonPress-1>", drag_start)
                w.bind("<B1-Motion>",     drag_move)

        # Container
        cont = ctk.CTkFrame(ov, fg_color=SIDEBAR_BG, corner_radius=18)
        cont.pack(fill="both", expand=True, padx=4, pady=4)
        cont.grid_columnconfigure(0, weight=1)
        cont.grid_rowconfigure(1, weight=1)

        # Header (draggable)
        hdr = ctk.CTkFrame(cont, fg_color=CARD, corner_radius=12)
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        hdr.grid_columnconfigure(1, weight=1)

        dots = ctk.CTkFrame(hdr, fg_color="transparent")
        dots.grid(row=0, column=0, sticky="w", padx=10, pady=9)
        for dot_color in (GREEN, WARN, DANGER):
            ctk.CTkFrame(dots, fg_color=dot_color, width=9, height=9,
                         corner_radius=5).pack(side="left", padx=2)

        ctk.CTkLabel(hdr, text="GazeDash",
                     font=("Segoe UI", 12, "bold"), text_color=TEXT).grid(
            row=0, column=1, pady=9,
        )
        bind_drag(hdr, dots)

        # Camera preview
        cam_f = ctk.CTkFrame(cont, fg_color=BG, corner_radius=12)
        cam_f.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        cam_f.grid_rowconfigure(0, weight=1)
        cam_f.grid_columnconfigure(0, weight=1)
        self.mini_preview_label = ctk.CTkLabel(cam_f, text="Esperando...", anchor="center")
        self.mini_preview_label.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        if self._preview_image is not None:
            self.mini_preview_label.configure(image=self._preview_image, text="")
        bind_drag(cam_f)

        # Gesture badge
        mini_gb = _green_badge(cont, self._last_detected_gesture or "Sin gesto")
        mini_gb.grid(row=2, column=0, pady=(2, 4))
        self.mini_gesture_label = mini_gb.winfo_children()[0]

        # ── Panel de voz en mini overlay ──────────────────────────────────────
        voice_card_ov = ctk.CTkFrame(cont, fg_color=CARD, corner_radius=10)
        voice_card_ov.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 4))
        voice_card_ov.grid_columnconfigure(0, weight=1)
        vc_top = ctk.CTkFrame(voice_card_ov, fg_color="transparent")
        vc_top.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        vc_top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(vc_top, text="🎙", font=("Segoe UI", 11)).grid(row=0, column=0, padx=(0, 5))
        from core.voice_control.voice_control import VoiceControlState
        init_state = self._voice_controller.state
        init_icon = "○" if init_state == VoiceControlState.DISABLED else "◎"
        self._mini_voice_state_lbl = ctk.CTkLabel(
            vc_top, text=f"{init_icon}  Voz desactivada",
            font=("Segoe UI", 10), text_color=TEXT3, anchor="w"
        )
        self._mini_voice_state_lbl.grid(row=0, column=1, sticky="w")
        vm_ov = ctk.CTkFrame(voice_card_ov, fg_color="transparent")
        vm_ov.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        vm_ov.grid_columnconfigure(0, weight=1)
        _lbl(vm_ov, "Módulo:", 10, color=TEXT3).grid(row=0, column=0, sticky="w")
        self._mini_voice_mod_lbl = _lbl(vm_ov, "—", 10, bold=True, color=GREEN_TXT)
        self._mini_voice_mod_lbl.grid(row=0, column=1, sticky="e")
        bind_drag(voice_card_ov, vc_top)

        # ── Fila de toggles: Mouse + Voz ────────────────────────────────────────
        tog_row = ctk.CTkFrame(cont, fg_color="transparent")
        tog_row.grid(row=4, column=0, sticky="ew", padx=8, pady=(2, 4))
        tog_row.grid_columnconfigure((0, 1), weight=1)

        # Toggle mouse — 1 fila: icono | texto | switch
        mc = ctk.CTkFrame(tog_row, fg_color=CARD, corner_radius=8)
        mc.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        mc.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            mc, text="◉", font=("Segoe UI", 20, "bold"), text_color=GREEN_TXT, width=28,
        ).grid(row=0, column=0, padx=(8, 2), pady=8)
        ctk.CTkLabel(
            mc, text="Mouse", font=("Segoe UI", 10), text_color=TEXT2, anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(0, 2), pady=8)

        _mini_mouse_var = ctk.BooleanVar(value=bool(self._analog_mouse_enabled))

        def _toggle_mini_mouse(var=_mini_mouse_var):
            pname = get_active_profile_name(self._config)
            ms_now = get_profile_mouse_settings(self._config, pname)
            ms_now["enabled"] = bool(var.get())
            updated = set_profile_mouse_settings(self._config, pname, ms_now)
            save_config(updated)
            self._config = updated
            self._load_mouse_settings()
            self.refresh_state()

        ctk.CTkSwitch(
            mc, text="", variable=_mini_mouse_var, width=36,
            button_color=GREEN, progress_color=GREEN_DIM,
            command=_toggle_mini_mouse,
        ).grid(row=0, column=2, padx=6, pady=8)

        # Toggle voz — 1 fila: icono | texto | switch
        vc2 = ctk.CTkFrame(tog_row, fg_color=CARD, corner_radius=8)
        vc2.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        vc2.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            vc2, text="♫", font=("Segoe UI", 20, "bold"), text_color=GREEN_TXT, width=28,
        ).grid(row=0, column=0, padx=(8, 2), pady=8)
        ctk.CTkLabel(
            vc2, text="Voz", font=("Segoe UI", 10), text_color=TEXT2, anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(0, 2), pady=8)

        _mini_voice_var = ctk.BooleanVar(
            value=bool(get_voice_control_settings(self._config).get("enabled", False))
        )

        def _toggle_mini_voice(var=_mini_voice_var):
            updated = set_voice_control_settings(self._config, enabled=bool(var.get()))
            save_config(updated)
            self._config = updated
            self._voice_controller.update_config(updated)
            self.refresh_state()

        ctk.CTkSwitch(
            vc2, text="", variable=_mini_voice_var, width=36,
            button_color=GREEN, progress_color=GREEN_DIM,
            command=_toggle_mini_voice,
        ).grid(row=0, column=2, padx=6, pady=8)

        # Buttons
        fbr = ctk.CTkFrame(cont, fg_color="transparent")
        fbr.grid(row=5, column=0, sticky="ew", padx=8, pady=(0, 8))
        fbr.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(fbr, text="↺", width=38,
                      fg_color=CARD, text_color=TEXT, hover_color=CARD_IN,
                      corner_radius=8, command=self._recalibrate_mouse,
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(fbr, text="Abrir",
                      fg_color=GREEN, text_color=BG, hover_color=GREEN_TXT,
                      font=("Segoe UI", 11, "bold"), corner_radius=8,
                      command=self.deiconify,
                      ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        bind_drag(ov, cont)
        self._mini_overlay = ov

    def _hide_mini_overlay(self):
        if self._mini_overlay is not None and self._mini_overlay.winfo_exists():
            self._mini_overlay.destroy()
        self._mini_overlay = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_close(self):
        self.stop_camera_preview()
        self.destroy()


def create_main_window():
    return GazeDashApp()
