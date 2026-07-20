# views/widgets.py
"""Widget-uri reutilizabile cu polish vizual peste cele de bază din
CustomTkinter (în prezent: scroll animat pentru liste lungi)."""

import sys

import customtkinter as ctk


class SmoothScrollableFrame(ctk.CTkScrollableFrame):
    """CTkScrollableFrame cu scroll animat (ease-out) la rotița mouse-ului.

    CustomTkinter scrolează instant, cu un salt fix per notch de rotiță;
    aici distanța se consumă treptat -- o fracțiune din rest la fiecare
    cadru -- dând o senzație de decelerare lină în loc de salt brusc.
    Scrollbar-ul și scroll-ul orizontal (Shift+rotiță) rămân neschimbate.
    """

    _DECAY = 0.32
    _INTERVAL_MS = 12
    _MAX_BACKLOG = 400  # limitează acumularea la scroll foarte rapid/continuu

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._smooth_remaining = 0.0
        self._smooth_anim_id = None

    def _mouse_wheel_all(self, event):
        if self._shift_pressed:
            super()._mouse_wheel_all(event)
            return
        if not self._check_if_valid_scroll(event.widget):
            return
        if self._parent_canvas.yview() == (0.0, 1.0):
            return

        if sys.platform.startswith("win"):
            units = -event.delta / 6
        elif sys.platform == "darwin":
            units = -event.delta
        else:
            units = -1 if event.num == 4 else 1

        self._smooth_remaining = max(
            -self._MAX_BACKLOG, min(self._MAX_BACKLOG, self._smooth_remaining + units)
        )
        if self._smooth_anim_id is None:
            self._smooth_step()

    def _smooth_step(self):
        remaining = self._smooth_remaining
        if abs(remaining) < 0.5:
            self._smooth_remaining = 0.0
            self._smooth_anim_id = None
            return

        move = remaining * self._DECAY
        if abs(move) < 1:
            move = 1 if remaining > 0 else -1
        move = int(move)

        self._parent_canvas.yview_scroll(move, "units")
        self._smooth_remaining -= move
        self._smooth_anim_id = self.after(self._INTERVAL_MS, self._smooth_step)
