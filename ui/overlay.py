import tkinter as tk


class Overlay:

    def __init__(
        self,
        width,
        height,
        dead_zone
    ):

        self.width = width
        self.height = height

        self.dead_zone = dead_zone

        self.root = tk.Tk()

        self.root.attributes(
            "-topmost",
            True
        )

        self.root.overrideredirect(True)

        self.root.config(bg="black")

        self.root.wm_attributes(
            "-transparentcolor",
            "black"
        )

        self.root.geometry(
            f"{width}x{height}+40+40"
        )

        self.canvas = tk.Canvas(
            self.root,
            width=width,
            height=height,
            bg="black",
            highlightthickness=0
        )

        self.canvas.pack()

        self.cx = width // 2
        self.cy = height // 2

    def draw(self, dx, dy):

        self.canvas.delete("all")

        x = self.cx + dx
        y = self.cy + dy

        self.canvas.create_oval(
            self.cx - self.dead_zone,
            self.cy - self.dead_zone,
            self.cx + self.dead_zone,
            self.cy + self.dead_zone,
            outline="#00FF66",
            width=2
        )

        self.canvas.create_line(
            self.cx,
            self.cy,
            x,
            y,
            fill="#0099FF",
            width=3
        )

        self.canvas.create_oval(
            x - 7,
            y - 7,
            x + 7,
            y + 7,
            fill="#FF3333",
            outline=""
        )