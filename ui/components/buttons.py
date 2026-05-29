"""Componentes de botones reutilizables."""

import customtkinter as ctk

def create_button(parent, text, command):
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        height=38,
        corner_radius=12,
        fg_color="#1F8A70",
        hover_color="#176854",
        text_color="#F6F8FB",
    )
