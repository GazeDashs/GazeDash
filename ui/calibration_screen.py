"""Pantalla de calibracion con CustomTkinter."""

from tkinter import messagebox

import customtkinter as ctk

from ui.components.buttons import create_button
from ui.components.sliders import create_slider
from ui.settings_store import (
    GESTURE_THRESHOLD_KEYS,
    get_active_profile_name,
    get_effective_thresholds,
    get_profile_details,
    load_config,
    save_config,
    set_profile_thresholds,
)


CALIBRATION_HINTS = [
    "1. Selecciona el perfil que quieres ajustar.",
    "2. Cambia los controles hasta que el gesto quede estable.",
    "3. Guarda para aplicar los cambios a la configuracion activa.",
]


def _build_threshold_card(parent, key, value):
    card = ctk.CTkFrame(parent, fg_color="#17202A", corner_radius=14)
    card.grid_columnconfigure(0, weight=1)

    header = ctk.CTkFrame(card, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
    header.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(header, text=key.replace("_", " ").title(), anchor="w").grid(row=0, column=0, sticky="w")
    value_var = ctk.StringVar(value=f"{float(value):.3f}")
    ctk.CTkLabel(header, textvariable=value_var, width=72, anchor="e").grid(row=0, column=1, sticky="e")

    slider = create_slider(card, 0.0, 1.0, command=lambda current: value_var.set(f"{float(current):.3f}"))
    slider.grid(row=1, column=0, sticky="ew", padx=14, pady=(6, 14))
    slider.set(float(value))
    return card, slider


def show_calibration(master=None, config_manager=None):
    config = load_config() if config_manager is None else config_manager.load_merged()
    active_profile = get_active_profile_name(config)
    profile_key, profile = get_profile_details(config, active_profile)
    thresholds = get_effective_thresholds(config, profile_key)

    window = ctk.CTkToplevel(master) if master is not None else ctk.CTk()
    window.title("GazeDash - Calibracion")
    window.geometry("1120x780")
    window.minsize(980, 680)

    if master is not None:
        window.transient(master)
        window.grab_set()

    root = ctk.CTkFrame(window, fg_color="#0B1220")
    root.pack(fill="both", expand=True)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(1, weight=1)

    left = ctk.CTkFrame(root, fg_color="#111827", corner_radius=0, width=300)
    left.grid(row=0, column=0, rowspan=2, sticky="nsew")
    left.grid_propagate(False)

    ctk.CTkLabel(left, text="Calibracion", font=("Segoe UI", 28, "bold")).pack(anchor="w", padx=24, pady=(28, 10))
    left_hint = ctk.CTkLabel(left, text=profile.get("description") or "Ajusta umbrales para que el perfil responda mejor a tu rostro.", wraplength=240, justify="left")
    left_hint.pack(anchor="w", padx=24, pady=(0, 20))

    profile_var = ctk.StringVar(value=active_profile)
    ctk.CTkLabel(left, text="Perfil", anchor="w").pack(anchor="w", padx=24, pady=(0, 6))
    profile_selector = ctk.CTkOptionMenu(left, values=list((config.get("profiles", {}) or {}).keys()) or [active_profile], variable=profile_var)
    profile_selector.pack(fill="x", padx=24, pady=(0, 18))

    hint_box = ctk.CTkFrame(left, fg_color="#0F172A", corner_radius=16)
    hint_box.pack(fill="x", padx=24, pady=(0, 18))
    for index, hint in enumerate(CALIBRATION_HINTS):
        ctk.CTkLabel(hint_box, text=hint, wraplength=238, justify="left", anchor="w").pack(anchor="w", padx=14, pady=(14 if index == 0 else 8, 0))

    summary_box = ctk.CTkFrame(left, fg_color="#0F172A", corner_radius=16)
    summary_box.pack(fill="x", padx=24, pady=(0, 18))
    summary_label_profile = ctk.CTkLabel(summary_box, text=f"Perfil activo: {active_profile}", anchor="w")
    summary_label_profile.pack(anchor="w", padx=14, pady=(12, 4))
    summary_label_camera = ctk.CTkLabel(summary_box, text=f"Camara: {config.get('camera_index', 0)}", anchor="w")
    summary_label_camera.pack(anchor="w", padx=14, pady=4)
    summary_label_count = ctk.CTkLabel(summary_box, text=f"Gestos calibrables: {len(GESTURE_THRESHOLD_KEYS)}", anchor="w")
    summary_label_count.pack(anchor="w", padx=14, pady=(4, 12))

    right = ctk.CTkFrame(root, fg_color="#0B1220")
    right.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=24, pady=24)
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(1, weight=1)

    header = ctk.CTkFrame(right, fg_color="#111827", corner_radius=18)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(header, text="Calibracion manual de gestos", font=("Segoe UI", 22, "bold")).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 4))
    ctk.CTkLabel(header, text="Ajusta el umbral de respuesta para cada gesto y guarda el perfil activo.", anchor="w").grid(row=1, column=0, sticky="w", padx=20, pady=(0, 18))

    scroller = ctk.CTkScrollableFrame(right, fg_color="#0B1220", corner_radius=0)
    scroller.grid(row=1, column=0, sticky="nsew", pady=(18, 16))
    scroller.grid_columnconfigure(0, weight=1)

    threshold_widgets = {}
    for index, key in enumerate(GESTURE_THRESHOLD_KEYS):
        card, slider = _build_threshold_card(scroller, key, thresholds.get(key, 0.5))
        card.grid(row=index, column=0, sticky="ew", pady=(0, 12))
        threshold_widgets[key] = slider

    footer = ctk.CTkFrame(right, fg_color="#111827", corner_radius=18)
    footer.grid(row=2, column=0, sticky="ew")
    footer.grid_columnconfigure(0, weight=1)

    def reload_profile(*_):
        selected_profile = profile_selector.get()
        selected_thresholds = get_effective_thresholds(config, selected_profile)
        _, selected_profile_data = get_profile_details(config, selected_profile)
        summary_label_profile.configure(text=f"Perfil activo: {selected_profile}")
        summary_label_camera.configure(text=f"Camara: {config.get('camera_index', 0)}")
        summary_label_count.configure(text=f"Gestos calibrables: {len(GESTURE_THRESHOLD_KEYS)}")
        left_hint.configure(text=selected_profile_data.get("description") or "Ajusta umbrales para que el perfil responda mejor a tu rostro.")
        for key, slider in threshold_widgets.items():
            slider.set(float(selected_thresholds.get(key, thresholds.get(key, 0.5))))

    profile_selector.configure(command=reload_profile)

    def save_changes():
        selected_profile = profile_selector.get()
        thresholds_payload = {key: float(slider.get()) for key, slider in threshold_widgets.items()}
        updated = set_profile_thresholds(config, selected_profile, thresholds_payload)
        save_config(updated)
        messagebox.showinfo("GazeDash", "Calibracion guardada correctamente.")
        window.destroy()

    create_button(footer, "Guardar calibracion", save_changes).grid(row=0, column=0, sticky="w", padx=18, pady=18)
    create_button(footer, "Cerrar", window.destroy).grid(row=0, column=1, sticky="e", padx=18, pady=18)

    if master is None:
        window.mainloop()

    return window
