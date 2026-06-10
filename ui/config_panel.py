"""Panel de configuracion con CustomTkinter."""

from tkinter import messagebox

import customtkinter as ctk

from ui.components.buttons import create_button
from ui.components.sliders import create_slider
from ui.settings_store import (
    AVAILABLE_GESTURE_NAMES,
    GESTURE_THRESHOLD_KEYS,
    clone_profile,
    get_active_profile_name,
    get_effective_thresholds,
    get_profile_actions,
    get_profile_details,
    get_profile_mouse_settings,
    get_profile_voice_actions,
    get_profiles,
    get_voice_control_settings,
    load_config,
    parse_hotkey_spec,
    remove_profile_gesture_action,
    remove_profile_voice_action,
    save_config,
    set_general_settings,
    set_profile_gesture_action,
    set_profile_mouse_settings,
    set_profile_thresholds,
    set_profile_voice_action,
    set_voice_control_settings,
)


SECTION_HINT = "Crea perfiles nuevos y enlaza un gesto a un input concreto desde esta pantalla."


def _section_card(parent, title, subtitle=None):
    card = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=18)
    card.grid_columnconfigure(0, weight=1)

    title_row = ctk.CTkFrame(card, fg_color="transparent")
    title_row.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 0))
    title_row.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(title_row, text=title, font=("Segoe UI", 20, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
    if subtitle:
        ctk.CTkLabel(title_row, text=subtitle, anchor="w").grid(row=1, column=0, sticky="w", pady=(2, 0))

    body = ctk.CTkFrame(card, fg_color="transparent")
    body.grid(row=1, column=0, sticky="nsew", padx=18, pady=18)
    body.grid_columnconfigure(0, weight=1)
    return card, body


def _make_slider_row(parent, key, value, minimum=0.0, maximum=1.0):
    row = ctk.CTkFrame(parent, fg_color="#17202A", corner_radius=14)
    row.grid_columnconfigure(0, weight=1)

    header = ctk.CTkFrame(row, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
    header.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(header, text=key.replace("_", " ").title(), anchor="w").grid(row=0, column=0, sticky="w")
    value_var = ctk.StringVar(value=f"{float(value):.3f}")
    ctk.CTkLabel(header, textvariable=value_var, width=70, anchor="e").grid(row=0, column=1, sticky="e")

    slider = create_slider(row, minimum, maximum, command=lambda current: value_var.set(f"{float(current):.3f}"))
    slider.grid(row=1, column=0, sticky="ew", padx=14, pady=(8, 14))
    slider.set(float(value))
    return row, slider


def _format_action(action):
    if not isinstance(action, dict):
        return "Sin acción configurada"

    keys = action.get("keys") or []
    label = action.get("label") or "Sin etiqueta"
    action_type = action.get("type") or "hotkey"
    key_text = " + ".join(keys) if isinstance(keys, list) and keys else "-"
    return f"{label} | {action_type} | {key_text}"


def _render_profile_actions(actions):
    lines = []
    seen = set()
    for gesture_name in AVAILABLE_GESTURE_NAMES:
        action = actions.get(gesture_name)
        if action is None:
            continue
        lines.append(f"{gesture_name}: {_format_action(action)}")
        seen.add(gesture_name)

    for gesture_name, action in actions.items():
        if gesture_name in seen:
            continue
        lines.append(f"{gesture_name}: {_format_action(action)}")

    return "\n".join(lines) if lines else "Sin acciones configuradas para este perfil."


def _render_voice_actions(actions):
    if not isinstance(actions, dict):
        return "Sin acciones de voz configuradas para este perfil."
    lines = [f"{command}: {_format_action(action)}" for command, action in actions.items()]
    return "\n".join(lines) if lines else "Sin acciones de voz configuradas para este perfil."


def _make_text_entry_row(parent, label_text, value=""):
    row = ctk.CTkFrame(parent, fg_color="#17202A", corner_radius=14)
    row.grid_columnconfigure(0, weight=1)

    label = ctk.CTkLabel(row, text=label_text, anchor="w")
    label.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))

    entry = ctk.CTkEntry(row)
    entry.grid(row=1, column=0, sticky="ew", padx=14, pady=(8, 14))
    entry.delete(0, "end")
    entry.insert(0, str(value or ""))
    return row, entry


def open_config_panel(master=None, config_manager=None):
    state = {"config": load_config() if config_manager is None else config_manager.load_merged()}

    window = ctk.CTkToplevel(master) if master is not None else ctk.CTk()
    window.title("GazeDash - Configuracion")
    window.geometry("1280x820")
    window.minsize(1120, 760)
    window.grid_columnconfigure(0, weight=1)
    window.grid_rowconfigure(0, weight=1)

    if master is not None:
        window.transient(master)
        window.grab_set()

    root = ctk.CTkFrame(window, fg_color="#0D1117")
    root.grid(row=0, column=0, sticky="nsew")
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(1, weight=1)

    header = ctk.CTkFrame(root, fg_color="#111827", corner_radius=20)
    header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 16))
    header.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(header, text="Configuracion", font=("Segoe UI", 28, "bold")).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 6))
    ctk.CTkLabel(header, text=SECTION_HINT, anchor="w").grid(row=1, column=0, sticky="w", padx=22, pady=(0, 18))

    content = ctk.CTkScrollableFrame(root, fg_color="#0D1117", corner_radius=0)
    content.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
    content.grid_columnconfigure(0, weight=1)
    content.grid_columnconfigure(1, weight=1)
    content.grid_rowconfigure(0, weight=1)

    left_panel = ctk.CTkFrame(content, fg_color="transparent")
    left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
    left_panel.grid_columnconfigure(0, weight=1)

    right_panel = ctk.CTkFrame(content, fg_color="transparent")
    right_panel.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
    right_panel.grid_columnconfigure(0, weight=1)
    right_panel.grid_rowconfigure(1, weight=1)

    # Left column: profile management and gesture binding
    profile_card, profile_body = _section_card(left_panel, "Perfiles")
    profile_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))

    profile_names = list(get_profiles(state["config"]).keys()) or [get_active_profile_name(state["config"])]
    profile_selector = ctk.CTkOptionMenu(profile_body, values=profile_names)
    profile_selector.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    profile_selector.set(get_active_profile_name(state["config"]))

    profile_info = ctk.CTkLabel(profile_body, text="", justify="left", anchor="w", wraplength=430)
    profile_info.grid(row=1, column=0, sticky="ew", pady=(0, 12))

    new_profile_row = ctk.CTkFrame(profile_body, fg_color="transparent")
    new_profile_row.grid(row=2, column=0, sticky="ew", pady=(0, 10))
    new_profile_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(new_profile_row, text="Nuevo perfil", anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 12))
    new_profile_entry = ctk.CTkEntry(new_profile_row, placeholder_text="Ej: edicion")
    new_profile_entry.grid(row=0, column=1, sticky="ew")

    binding_card, binding_body = _section_card(left_panel, "Gesto a input")
    binding_card.grid(row=1, column=0, sticky="ew", pady=(0, 16))

    gesture_selector = ctk.CTkOptionMenu(binding_body, values=AVAILABLE_GESTURE_NAMES)
    gesture_selector.grid(row=0, column=0, sticky="ew", pady=(0, 10))

    gesture_keys_entry = ctk.CTkEntry(binding_body, placeholder_text="Ej: ctrl+v, enter")
    gesture_keys_entry.grid(row=1, column=0, sticky="ew", pady=(0, 10))

    gesture_label_entry = ctk.CTkEntry(binding_body, placeholder_text="Etiqueta visible")
    gesture_label_entry.grid(row=2, column=0, sticky="ew", pady=(0, 12))

    binding_buttons = ctk.CTkFrame(binding_body, fg_color="transparent")
    binding_buttons.grid(row=3, column=0, sticky="ew")
    binding_buttons.grid_columnconfigure((0, 1, 2), weight=1)

    voice_binding_card, voice_binding_body = _section_card(left_panel, "Comandos de voz", "Enlaza una etiqueta de comando a un hotkey")
    voice_binding_card.grid(row=2, column=0, sticky="ew", pady=(0, 16))

    voice_command_entry = ctk.CTkEntry(voice_binding_body, placeholder_text="Comando de voz (etiqueta)")
    voice_command_entry.grid(row=0, column=0, sticky="ew", pady=(0, 10))

    voice_keys_entry = ctk.CTkEntry(voice_binding_body, placeholder_text="Ej: ctrl+w, alt+f4")
    voice_keys_entry.grid(row=1, column=0, sticky="ew", pady=(0, 10))

    voice_label_entry = ctk.CTkEntry(voice_binding_body, placeholder_text="Etiqueta visible")
    voice_label_entry.grid(row=2, column=0, sticky="ew", pady=(0, 12))

    voice_buttons = ctk.CTkFrame(voice_binding_body, fg_color="transparent")
    voice_buttons.grid(row=3, column=0, sticky="ew")
    voice_buttons.grid_columnconfigure((0, 1, 2), weight=1)

    actions_card, actions_body = _section_card(left_panel, "Acciones del perfil", "Vista rápida de los gestos ya enlazados")
    actions_card.grid(row=3, column=0, sticky="nsew")
    actions_body.grid_rowconfigure(0, weight=1)
    profile_actions_box = ctk.CTkTextbox(actions_body, height=160)
    profile_actions_box.grid(row=0, column=0, sticky="nsew")
    profile_actions_box.configure(state="disabled")

    voice_actions_card, voice_actions_body = _section_card(left_panel, "Acciones de voz", "Vista rápida de comandos de voz configurados")
    voice_actions_card.grid(row=4, column=0, sticky="nsew")
    voice_actions_body.grid_rowconfigure(0, weight=1)
    voice_actions_box = ctk.CTkTextbox(voice_actions_body, height=160)
    voice_actions_box.grid(row=0, column=0, sticky="nsew")
    voice_actions_box.configure(state="disabled")

    # Right column: thresholds
    thresholds_card, thresholds_body = _section_card(right_panel, "Umbrales", "Ajusta la sensibilidad del perfil activo")
    thresholds_card.grid(row=0, column=0, sticky="nsew")
    thresholds_body.grid_columnconfigure(0, weight=1)
    thresholds_body.grid_rowconfigure(0, weight=1)

    thresholds_scroll = ctk.CTkScrollableFrame(thresholds_body, fg_color="#111827", corner_radius=14)
    thresholds_scroll.grid(row=0, column=0, sticky="nsew")
    thresholds_scroll.grid_columnconfigure(0, weight=1)

    voice_card, voice_body = _section_card(right_panel, "Control de voz", "Ajusta activación, descanso y ganancia para el micrófono")
    voice_card.grid(row=1, column=0, sticky="ew", pady=(16, 0))
    voice_body.grid_columnconfigure(0, weight=1)

    voice_enabled_row, voice_enabled_switch, voice_enabled_var = _make_boolean_row(voice_body, "activar voz", False)
    voice_enabled_row.grid(row=0, column=0, sticky="ew", pady=(0, 12))

    activation_gesture_row, activation_gesture_entry = _make_text_entry_row(voice_body, "Gesto de activación", "mouth_pucker")
    activation_gesture_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))

    activation_word_row, activation_word_entry = _make_text_entry_row(voice_body, "Palabra activación", "activar")
    activation_word_row.grid(row=2, column=0, sticky="ew", pady=(0, 12))

    listen_duration_row, listen_duration_slider = _make_slider_row(voice_body, "duración escucha", 10.0, 1.0, 20.0)
    listen_duration_row.grid(row=3, column=0, sticky="ew", pady=(0, 12))

    cooldown_row, cooldown_slider = _make_slider_row(voice_body, "cooldown", 5.0, 0.0, 15.0)
    cooldown_row.grid(row=4, column=0, sticky="ew", pady=(0, 12))

    gain_row, gain_slider = _make_slider_row(voice_body, "ganancia", 1.0, 1.0, 10.0)
    gain_row.grid(row=5, column=0, sticky="ew", pady=(0, 12))

    mouse_card, mouse_body = _section_card(right_panel, "Mouse analógico", "Ajusta la zona muerta, la velocidad y la calibración por perfil")
    mouse_card.grid(row=2, column=0, sticky="ew", pady=(16, 0))
    mouse_body.grid_columnconfigure(0, weight=1)

    mouse_scroll = ctk.CTkScrollableFrame(mouse_body, fg_color="#111827", corner_radius=14)
    mouse_scroll.grid(row=0, column=0, sticky="nsew")
    mouse_scroll.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(mouse_body, text="Usa el botón de recalibración en la ventana principal para guardar tu punto neutro actual.", wraplength=420, justify="left", text_color="#D1D5DB").grid(row=1, column=0, sticky="ew", padx=18, pady=(10, 12))

    summary_card, summary_body = _section_card(right_panel, "Resumen", "Información del perfil y guardado")
    summary_card.grid(row=3, column=0, sticky="ew", pady=(16, 0))

    summary_labels = [
        ctk.CTkLabel(summary_body, text="", anchor="w"),
        ctk.CTkLabel(summary_body, text="", anchor="w"),
        ctk.CTkLabel(summary_body, text="", anchor="w"),
        ctk.CTkLabel(summary_body, text="", anchor="w"),
        ctk.CTkLabel(summary_body, text="", anchor="w"),
    ]
    for index, widget in enumerate(summary_labels):
        widget.grid(row=index, column=0, sticky="ew", pady=(0 if index == 0 else 6, 0))

    footer = ctk.CTkFrame(root, fg_color="#111827", corner_radius=20)
    footer.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 24))
    footer.grid_columnconfigure(0, weight=1)
    footer.grid_columnconfigure(1, weight=1)

    form_state = {
        "threshold_widgets": {},
        "mouse_widgets": {},
        "profile_names": profile_names,
    }

    def current_config():
        return state["config"]

    def current_profile_name():
        return profile_selector.get() or get_active_profile_name(current_config())

    def current_gesture_name():
        return gesture_selector.get() or AVAILABLE_GESTURE_NAMES[0]

    def set_textbox_value(textbox, text):
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")

    def _make_boolean_row(parent, key, value):
        row = ctk.CTkFrame(parent, fg_color="#17202A", corner_radius=14)
        row.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(row, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text=key.replace("_", " ").title(), anchor="w").grid(row=0, column=0, sticky="w")
        var = ctk.BooleanVar(value=bool(value))
        switch = ctk.CTkSwitch(row, text="", variable=var)
        switch.grid(row=0, column=1, sticky="e", padx=(0, 14))
        return row, switch, var

    def build_threshold_widgets(profile_name):
        for child in thresholds_scroll.winfo_children():
            child.destroy()

        form_state["threshold_widgets"] = {}
        thresholds = get_effective_thresholds(current_config(), profile_name)
        for index, key in enumerate(GESTURE_THRESHOLD_KEYS):
            slider_frame, slider = _make_slider_row(thresholds_scroll, key, thresholds.get(key, 0.5))
            slider_frame.grid(row=index, column=0, sticky="ew", pady=(0, 12))
            form_state["threshold_widgets"][key] = slider

    def build_mouse_widgets(profile_name):
        for child in mouse_scroll.winfo_children():
            child.destroy()

        form_state["mouse_widgets"] = {}
        mouse_settings = get_profile_mouse_settings(current_config(), profile_name)

        row, switch, enabled_var = _make_boolean_row(mouse_scroll, "activar mouse", mouse_settings.get("enabled", True))
        row.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        form_state["mouse_widgets"]["enabled"] = enabled_var

        row, dead_zone_slider = _make_slider_row(mouse_scroll, "zona_muerta", mouse_settings.get("dead_zone", 25.0), 0.0, 150.0)
        row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        form_state["mouse_widgets"]["dead_zone"] = dead_zone_slider

        row, speed_slider = _make_slider_row(mouse_scroll, "velocidad_maxima", mouse_settings.get("max_speed", 35.0), 1.0, 100.0)
        row.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        form_state["mouse_widgets"]["max_speed"] = speed_slider

        row, smoothing_slider = _make_slider_row(mouse_scroll, "suavizado", mouse_settings.get("smoothing", 0.2), 0.0, 1.0)
        row.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        form_state["mouse_widgets"]["smoothing"] = smoothing_slider

        center_status = "Sí" if mouse_settings.get("center") else "No"
        status_label = ctk.CTkLabel(mouse_scroll, text=f"Centro calibrado: {center_status}", anchor="w")
        status_label.grid(row=4, column=0, sticky="ew", padx=18, pady=(4, 0))
        form_state["mouse_widgets"]["center_status"] = status_label

    def refresh_voice_settings(profile_name=None):
        voice_config = get_voice_control_settings(current_config())
        voice_enabled_var.set(bool(voice_config.get("enabled", False)))
        activation_gesture_entry.delete(0, "end")
        activation_gesture_entry.insert(0, voice_config.get("activation_gesture", "mouth_pucker"))
        activation_word_entry.delete(0, "end")
        activation_word_entry.insert(0, voice_config.get("activation_word", "activar"))
        listen_duration_slider.set(float(voice_config.get("listen_duration", 10.0)))
        cooldown_slider.set(float(voice_config.get("cooldown_seconds", 5.0)))
        gain_slider.set(float(voice_config.get("gain", 1.0)))

        voice_actions = get_profile_voice_actions(current_config(), profile_name or current_profile_name())
        set_textbox_value(voice_actions_box, _render_voice_actions(voice_actions))

    def refresh_profile_summary(selected_profile=None):
        active_name = selected_profile or current_profile_name()
        profile_key, profile = get_profile_details(current_config(), active_name)
        actions = get_profile_actions(current_config(), profile_key)
        mouse_settings = get_profile_mouse_settings(current_config(), active_name)

        profile_info.configure(text=profile.get("description") or "Sin descripcion disponible para este perfil.")
        summary_labels[0].configure(text=f"Perfiles: {len(get_profiles(current_config()))}")
        summary_labels[1].configure(text=f"Camara: {current_config().get('camera_index', 0)}")
        summary_labels[2].configure(text=f"Zona muerta: {float(mouse_settings.get('dead_zone', 25.0)):.1f}")
        summary_labels[3].configure(text=f"Velocidad: {float(mouse_settings.get('max_speed', 35.0)):.1f}")
        summary_labels[4].configure(text=f"Centro calibrado: {'Sí' if mouse_settings.get('center') else 'No'}")
        set_textbox_value(profile_actions_box, _render_profile_actions(actions))

    def load_binding(profile_name=None, gesture_name=None):
        active_name = profile_name or current_profile_name()
        selected_gesture = gesture_name or current_gesture_name()
        actions = get_profile_actions(current_config(), active_name)
        action = actions.get(selected_gesture, {}) if isinstance(actions, dict) else {}

        gesture_selector.set(selected_gesture)
        gesture_keys_entry.delete(0, "end")
        gesture_keys_entry.insert(0, "+".join(action.get("keys", [])) if isinstance(action, dict) and action.get("keys") else "")
        gesture_label_entry.delete(0, "end")
        gesture_label_entry.insert(0, action.get("label") or selected_gesture)

    def refresh_all(profile_name=None):
        selected_profile = profile_name or current_profile_name()
        profile_selector.set(selected_profile)
        build_threshold_widgets(selected_profile)
        build_mouse_widgets(selected_profile)
        refresh_profile_summary(selected_profile)
        load_binding(selected_profile, gesture_selector.get())
        refresh_voice_settings(selected_profile)

    def create_profile():
        new_name = new_profile_entry.get().strip()
        if not new_name:
            messagebox.showwarning("GazeDash", "Escribi un nombre para el nuevo perfil.")
            return
        if new_name in get_profiles(current_config()):
            messagebox.showwarning("GazeDash", "Ya existe un perfil con ese nombre.")
            return

        updated = clone_profile(current_config(), new_name, current_profile_name())
        state["config"] = updated
        save_config(updated)

        profile_names = list(get_profiles(updated).keys())
        form_state["profile_names"] = profile_names
        profile_selector.configure(values=profile_names)
        profile_selector.set(new_name)
        new_profile_entry.delete(0, "end")
        refresh_all(new_name)
        messagebox.showinfo("GazeDash", f"Perfil creado: {new_name}")

    def save_binding():
        selected_profile = current_profile_name()
        selected_gesture = current_gesture_name()
        keys = parse_hotkey_spec(gesture_keys_entry.get())
        label = gesture_label_entry.get().strip()

        if not keys:
            messagebox.showwarning("GazeDash", "Escribi al menos una tecla o combinacion para el gesto.")
            return

        updated = set_profile_gesture_action(current_config(), selected_profile, selected_gesture, keys=keys, label=label)
        state["config"] = updated
        save_config(updated)
        refresh_all(selected_profile)
        messagebox.showinfo("GazeDash", f"Gesto guardado: {selected_gesture}")

    def delete_binding():
        selected_profile = current_profile_name()
        selected_gesture = current_gesture_name()
        updated = remove_profile_gesture_action(current_config(), selected_profile, selected_gesture)
        state["config"] = updated
        save_config(updated)
        refresh_all(selected_profile)
        load_binding(selected_profile, selected_gesture)
        messagebox.showinfo("GazeDash", f"Gesto eliminado: {selected_gesture}")

    def save_voice_binding():
        selected_profile = current_profile_name()
        command_label = voice_command_entry.get().strip()
        keys = parse_hotkey_spec(voice_keys_entry.get())
        label = voice_label_entry.get().strip()

        if not command_label or not keys:
            messagebox.showwarning("GazeDash", "Escribi un comando de voz y al menos una tecla para guardarlo.")
            return

        updated = set_profile_voice_action(current_config(), selected_profile, command_label, keys=keys, label=label)
        state["config"] = updated
        save_config(updated)
        refresh_all(selected_profile)
        messagebox.showinfo("GazeDash", f"Acción de voz guardada: {command_label}")

    def delete_voice_binding():
        selected_profile = current_profile_name()
        command_label = voice_command_entry.get().strip()
        if not command_label:
            messagebox.showwarning("GazeDash", "Escribi el comando de voz que queres eliminar.")
            return

        updated = remove_profile_voice_action(current_config(), selected_profile, command_label)
        state["config"] = updated
        save_config(updated)
        refresh_all(selected_profile)
        messagebox.showinfo("GazeDash", f"Acción de voz eliminada: {command_label}")

    def save_all():
        selected_profile = current_profile_name()
        thresholds_payload = {key: float(slider.get()) for key, slider in form_state["threshold_widgets"].items()}
        updated = set_general_settings(
            current_config(),
            active_profile=selected_profile,
            camera_index=current_config().get("camera_index", 0),
            smoothing_alpha=current_config().get("smoothing_alpha", 0.5),
            gesture_cooldown=current_config().get("gesture_cooldown", 0.5),
        )
        updated = set_profile_thresholds(updated, selected_profile, thresholds_payload)

        mouse_settings_payload = get_profile_mouse_settings(current_config(), selected_profile)
        mouse_settings_payload.update({
            "enabled": bool(form_state["mouse_widgets"]["enabled"].get()),
            "dead_zone": float(form_state["mouse_widgets"]["dead_zone"].get()),
            "max_speed": float(form_state["mouse_widgets"]["max_speed"].get()),
            "smoothing": float(form_state["mouse_widgets"]["smoothing"].get()),
        })
        updated = set_profile_mouse_settings(updated, selected_profile, mouse_settings_payload)

        updated = set_voice_control_settings(
            updated,
            enabled=bool(voice_enabled_var.get()),
            activation_gesture=activation_gesture_entry.get().strip(),
            activation_word=activation_word_entry.get().strip(),
            listen_duration=float(listen_duration_slider.get()),
            cooldown_seconds=float(cooldown_slider.get()),
            gain=float(gain_slider.get()),
        )

        keys = parse_hotkey_spec(gesture_keys_entry.get())
        if keys:
            updated = set_profile_gesture_action(
                updated,
                selected_profile,
                current_gesture_name(),
                keys=keys,
                label=gesture_label_entry.get().strip(),
            )

        voice_command = voice_command_entry.get().strip()
        voice_keys = parse_hotkey_spec(voice_keys_entry.get())
        voice_label = voice_label_entry.get().strip()
        if voice_command and voice_keys:
            updated = set_profile_voice_action(
                updated,
                selected_profile,
                voice_command,
                keys=voice_keys,
                label=voice_label,
            )

        state["config"] = updated
        save_config(updated)
        refresh_all(selected_profile)
        messagebox.showinfo("GazeDash", "Configuracion guardada correctamente.")

    create_button(new_profile_row, "Crear perfil", create_profile).grid(row=0, column=2, sticky="e", padx=(12, 0))
    create_button(binding_buttons, "Guardar gesto", save_binding).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    create_button(binding_buttons, "Eliminar gesto", delete_binding).grid(row=0, column=1, sticky="ew", padx=6)
    create_button(binding_buttons, "Recargar", lambda: refresh_all(current_profile_name())).grid(row=0, column=2, sticky="ew", padx=(6, 0))
    create_button(voice_buttons, "Guardar voz", save_voice_binding).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    create_button(voice_buttons, "Eliminar voz", delete_voice_binding).grid(row=0, column=1, sticky="ew", padx=6)
    create_button(voice_buttons, "Recargar", lambda: refresh_all(current_profile_name())).grid(row=0, column=2, sticky="ew", padx=(6, 0))
    create_button(footer, "Guardar todo", save_all).grid(row=0, column=0, sticky="ew", padx=(18, 8), pady=18)
    create_button(footer, "Cerrar", window.destroy).grid(row=0, column=1, sticky="ew", padx=(8, 18), pady=18)

    profile_selector.configure(command=lambda _value=None: refresh_all(profile_selector.get()))
    gesture_selector.configure(command=lambda _value=None: load_binding(profile_selector.get(), gesture_selector.get()))

    refresh_all(get_active_profile_name(state["config"]))

    if master is None:
        window.mainloop()

    return window