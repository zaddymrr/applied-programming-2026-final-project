import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QVBoxLayout, QWidget
from vispy import scene


class VisPyPlotWidget(QWidget):
    """
    VisPy-based live plotting widget (part of the View layer).

    Two display modes are supported:

    - single channel: one signal line in a rolling 10 second window
    - all channels  : all 32 channels stacked vertically with an offset so
                      the whole array can be inspected at a glance

    The widget only draws what it is given. All data selection and processing
    happens in the ViewModel / Models.
    """

    def __init__(self, visible_duration_seconds=10.0, num_channels=32):
        super().__init__()

        self.visible_duration_seconds = visible_duration_seconds
        self.num_channels = num_channels
        self.y_scale = 1.0
        self.show_all = False
        self._last_y = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.canvas = scene.SceneCanvas(
            keys="interactive",
            show=False,
            bgcolor="#1e1e2e",
            size=(1000, 600),
        )

        grid = self.canvas.central_widget.add_grid(margin=10)

        self.y_axis = scene.AxisWidget(
            orientation="left", text_color="#cdd6f4", axis_color="#cdd6f4",
            tick_color="#cdd6f4",
        )
        self.x_axis = scene.AxisWidget(
            orientation="bottom", text_color="#cdd6f4", axis_color="#cdd6f4",
            tick_color="#cdd6f4",
        )
        self.y_axis.width_max = 60
        self.x_axis.height_max = 40

        grid.add_widget(self.y_axis, row=0, col=0)
        self.view = grid.add_view(row=0, col=1)
        self.view.camera = "panzoom"
        grid.add_widget(self.x_axis, row=1, col=1)
        self.x_axis.link_view(self.view)
        self.y_axis.link_view(self.view)

        # Single-channel line.
        self.line = scene.Line(
            pos=np.array([[0.0, 0.0], [1.0, 0.0]], dtype=float),
            color=(0.54, 0.71, 0.98, 1.0),
            parent=self.view.scene,
            width=2,
        )

        # One line per channel for the "all channels" view.
        self.channel_lines = []
        cmap = self._build_colors(self.num_channels)
        for i in range(self.num_channels):
            ln = scene.Line(
                pos=np.array([[0.0, 0.0], [1.0, 0.0]], dtype=float),
                color=cmap[i],
                parent=self.view.scene,
                width=1,
            )
            ln.visible = False
            self.channel_lines.append(ln)

        layout.addWidget(self.canvas.native)

        # ------------------------------------------------------------------
        # Decorative easter-egg layer.
        #
        # Entirely separate from the signal pipeline: it draws glyph outlines
        # generated from a font, never touches the TCP model or the 32-channel
        # buffers, and is driven by its own timer. Deleting this block and the
        # two methods at the end of the class would leave the application
        # behaviour unchanged.
        # ------------------------------------------------------------------
        self.easter_egg_active = False
        self._egg_base = None
        self._egg_lines = []
        for _ in range(40):
            ln = scene.Line(
                pos=np.array([[0.0, 0.0], [1.0, 0.0]], dtype=float),
                color=(0.42, 0.66, 0.98, 1.0),
                parent=self.view.scene,
                width=2,
            )
            ln.visible = False
            self._egg_lines.append(ln)

        self._egg_timer = QTimer(self)
        self._egg_timer.timeout.connect(self._animate_easter_egg)

    # ------------------------------------------------------------------
    def _build_colors(self, n):
        """Generate n distinct-ish colors cycling through hues."""
        colors = []
        for i in range(n):
            hue = (i / max(1, n)) * 1.0
            colors.append(self._hsv_to_rgba(hue, 0.55, 0.95))
        return colors

    @staticmethod
    def _hsv_to_rgba(h, s, v):
        i = int(h * 6.0)
        f = h * 6.0 - i
        p = v * (1.0 - s)
        q = v * (1.0 - f * s)
        t = v * (1.0 - (1.0 - f) * s)
        i = i % 6
        r, g, b = [
            (v, t, p), (q, v, p), (p, v, t),
            (p, q, v), (t, p, v), (v, p, q),
        ][i]
        return (r, g, b, 1.0)

    # ------------------------------------------------------------------
    def set_y_scale(self, y_scale):
        self.y_scale = float(y_scale)
        self._update_camera()

    def set_show_all(self, show_all):
        """Switch between single-channel and all-channels rendering."""
        self.show_all = bool(show_all)

        # While the decorative trace is showing it owns the canvas: record the
        # requested mode but do not un-hide the signal lines, otherwise both
        # layers would be drawn on top of each other.
        if self.easter_egg_active:
            return

        self.line.visible = not self.show_all
        for ln in self.channel_lines:
            ln.visible = self.show_all
        self._update_camera()

    # ------------------------------------------------------------------
    def update_plot(self, x, y):
        """Update the single-channel line (called when show_all is False)."""
        if self.show_all or self.easter_egg_active:
            return
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if x.size < 2 or y.size < 2:
            return

        self._last_y = y

        pos = np.column_stack((x, y))
        self.line.set_data(pos=pos)

        # The y range is driven by the user's Y-scale setting, not by the data
        # min/max. Auto-ranging looks reasonable until a single transient
        # (electrode pop, saturation) arrives - then the whole real signal gets
        # squashed into a flat line while the axis stretches to fit the spike.
        self.view.camera.set_range(
            x=(float(x.min()), float(x.max())),
            y=(-self.y_scale, self.y_scale),
            margin=0.02,
        )

    def suggest_y_scale(self):
        """
        Return a robust y-scale for the current channel.

        Uses a high percentile rather than the maximum so that isolated
        artefacts do not dictate the scale. Returns None if there is no data.
        """
        if self._last_y is None or self._last_y.size < 2:
            return None
        scale = float(np.percentile(np.abs(self._last_y), 99.0))
        if not np.isfinite(scale) or scale <= 0:
            return None
        return scale * 1.2  # small headroom above the percentile

    def update_plot_all(self, matrix):
        """
        Update all channels at once (called when show_all is True).

        ``matrix`` is shaped channels x samples. Each channel is drawn with a
        vertical offset so the lines don't overlap.
        """
        if not self.show_all or self.easter_egg_active:
            return
        matrix = np.asarray(matrix, dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] < 2:
            return

        n_channels, n_samples = matrix.shape
        x = np.arange(n_samples) / 2000.0  # sampling_rate = 2000

        # Normalize each channel to a comparable amplitude, then offset.
        offsets = np.arange(n_channels)
        spread = np.max(np.abs(matrix)) + 1e-9
        norm = matrix / (2.5 * spread)

        for i in range(n_channels):
            y = norm[i] + offsets[i]
            pos = np.column_stack((x, y))
            self.channel_lines[i].set_data(pos=pos)

        self.view.camera.set_range(
            x=(float(x.min()), float(x.max())),
            y=(-1.0, float(n_channels)),
            margin=0.02,
        )

    def _update_camera(self):
        if self.show_all:
            self.view.camera.set_range(
                x=(0.0, self.visible_duration_seconds),
                y=(-1.0, float(self.num_channels)),
                margin=0.02,
            )
        else:
            self.view.camera.set_range(
                x=(0.0, self.visible_duration_seconds),
                y=(-self.y_scale, self.y_scale),
                margin=0.02,
            )

    # ----------------------------------------------------------------------
    # Decorative easter egg (not part of the signal pipeline)
    # ----------------------------------------------------------------------
    def set_easter_egg(self, active):
        """
        Show or hide the decorative credit trace.

        While active, the normal signal line is hidden and an independent
        timer animates the glyph outlines so they behave like a live trace.
        No measured data is involved.
        """
        from views.signature_window import build_credit_traces

        self.easter_egg_active = bool(active)

        if self.easter_egg_active:
            self._egg_base = build_credit_traces()
            self.line.visible = False
            for ln in self.channel_lines:
                ln.visible = False
            for i, ln in enumerate(self._egg_lines):
                ln.visible = i < len(self._egg_base)
            self._animate_easter_egg()
            self._egg_timer.start(40)  # ~25 fps is plenty for this
        else:
            self._egg_timer.stop()
            self._egg_base = None
            for ln in self._egg_lines:
                ln.visible = False
            self.line.visible = not self.show_all
            for ln in self.channel_lines:
                ln.visible = self.show_all
            # Restore a sensible axis range. Without this the camera keeps the
            # range left behind by the decorative view, which is visible if no
            # data arrives to redraw it.
            self._update_camera()

    def _animate_easter_egg(self):
        """Redraw the credit trace with a small random jitter each frame."""
        if not self.easter_egg_active or not self._egg_base:
            return

        all_pts = np.concatenate(self._egg_base, axis=0)
        span_y = float(all_pts[:, 1].max() - all_pts[:, 1].min()) or 1.0
        amplitude = 0.012 * span_y

        for i, stroke in enumerate(self._egg_base):
            jittered = stroke.copy()
            jittered[:, 1] += np.random.uniform(
                -amplitude, amplitude, size=stroke.shape[0]
            )
            jittered[:, 0] += np.random.uniform(
                -amplitude * 0.4, amplitude * 0.4, size=stroke.shape[0]
            )
            self._egg_lines[i].set_data(pos=jittered)

        pad_x = 0.05 * (all_pts[:, 0].max() - all_pts[:, 0].min() + 1e-9)
        pad_y = 0.35 * span_y
        self.view.camera.set_range(
            x=(float(all_pts[:, 0].min()) - pad_x, float(all_pts[:, 0].max()) + pad_x),
            y=(float(all_pts[:, 1].min()) - pad_y, float(all_pts[:, 1].max()) + pad_y),
            margin=0.02,
        )
