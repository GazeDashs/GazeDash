"""Punto de entrada de la aplicación."""

if __package__ is None or __package__ == "":
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ui.main_window import create_main_window


def main():
    window = create_main_window()
    window.mainloop()


if __name__ == "__main__":
    main()
