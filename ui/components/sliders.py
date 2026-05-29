"""Componentes de sliders reutilizables."""

import customtkinter as ctk

def create_slider(parent, from_, to, command=None):
    return ctk.CTkSlider(
        parent,
        from_=from_,
        to=to,
        command=command,
        progress_color="#1F8A70",
        button_color="#1F8A70",
        button_hover_color="#176854",
    )
