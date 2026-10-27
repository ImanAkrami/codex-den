"""Brief, optional visual feedback that never gates input or operations."""

from textual.screen import ModalScreen


class DialogScreen(ModalScreen):
    def _on_mount(self):
        if self.app.motion_enabled:
            dialog = self.query_one(".dialog")
            dialog.styles.opacity = 0.85
            dialog.styles.animate("opacity", 1.0, duration=0.14, easing="out_cubic")
