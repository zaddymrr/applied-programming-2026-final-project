import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class OfflinePlotWindow(QWidget):
    """
    Offline inspection window using Matplotlib (part of the View layer).

    After streaming stops, this window lets the user browse the full recording
    channel by channel and switch between original / RMS / filtered modes.
    It does not update live - it redraws whenever a selection changes.
    """

    def __init__(self, view_model):
        super().__init__()
        self.view_model = view_model

        self.setWindowTitle("Offline Signal Inspection")
        self.resize(1000, 640)

        layout = QVBoxLayout(self)

        # --- controls row -------------------------------------------------
        controls = QHBoxLayout()

        controls.addWidget(QLabel("Channel:"))
        self.channel_box = QComboBox()
        self.channel_box.addItems([str(i + 1) for i in range(view_model.channels)])
        # Decorative entry, below a separator so it is clearly distinct from
        # the 32 real acquisition channels.
        self.channel_box.insertSeparator(view_model.channels)
        self.channel_box.addItem("67")
        controls.addWidget(self.channel_box)

        controls.addWidget(QLabel("Mode:"))
        self.mode_box = QComboBox()
        self.mode_box.addItems(["original", "rms", "filtered"])
        controls.addWidget(self.mode_box)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip(
            "Re-read the recording. The offline view is a snapshot taken when "
            "it was opened, so use this if streaming has continued since."
        )
        controls.addWidget(self.refresh_button)

        controls.addStretch()
        layout.addLayout(controls)

        # --- matplotlib canvas -------------------------------------------
        self.figure = Figure(figsize=(9, 5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)
        layout.addWidget(self.canvas)

        self.channel_box.currentIndexChanged.connect(self.redraw)
        self.mode_box.currentTextChanged.connect(self.redraw)
        self.refresh_button.clicked.connect(self.redraw)

        self.redraw()

    def redraw(self):
        """Redraw the currently selected channel and mode."""
        self.ax.clear()

        # ax.clear() does not reset the aspect ratio, so the decorative view's
        # "equal" aspect would persist and squash a normal signal plot into a
        # vertical line. Reset it explicitly on every redraw.
        self.ax.set_aspect("auto")
        self.ax.set_axis_on()

        # Decorative entry: drawn from font outlines, no measured data.
        if self.channel_box.itemText(self.channel_box.currentIndex()) == "67":
            self._draw_credit()
            return

        if not self.view_model.has_recording():
            self.ax.set_title("No recorded data available")
            self.ax.text(
                0.5, 0.5, "Connect and stream first, then reopen this window.",
                ha="center", va="center", transform=self.ax.transAxes,
            )
            self.canvas.draw()
            return

        channel_index = self.channel_box.currentIndex()
        mode = self.mode_box.currentText()

        x, y = self.view_model.get_offline_channel(channel_index, mode)

        self.ax.plot(x, y, color="#1f77b4", linewidth=0.8)
        self.ax.set_title(f"Channel {channel_index + 1} - {mode} signal")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Amplitude")
        self.ax.grid(True, alpha=0.3)
        self.figure.tight_layout()
        self.canvas.draw()

    def _draw_credit(self):
        """
        Draw the decorative credit trace.

        Completely independent of the recording and the signal processor: the
        coordinates come from font glyph outlines with a small random jitter
        so it reads like a trace rather than flat text.
        """
        from views.signature_window import build_credit_traces

        traces = build_credit_traces()
        all_pts = np.concatenate(traces, axis=0)
        span_y = float(all_pts[:, 1].max() - all_pts[:, 1].min()) or 1.0
        amplitude = 0.012 * span_y
        rng = np.random.default_rng()

        for stroke in traces:
            jittered = stroke.copy()
            jittered[:, 1] += rng.uniform(-amplitude, amplitude, len(stroke))
            jittered[:, 0] += rng.uniform(
                -amplitude * 0.4, amplitude * 0.4, len(stroke)
            )
            self.ax.plot(
                jittered[:, 0], jittered[:, 1], color="#1f77b4", linewidth=1.6
            )

        self.ax.set_aspect("equal")
        self.ax.set_xlim(all_pts[:, 0].min() - 0.4, all_pts[:, 0].max() + 0.4)
        self.ax.set_ylim(all_pts[:, 1].min() - 0.5, all_pts[:, 1].max() + 0.5)
        self.ax.set_title("Channel 67 - @zaddymrr")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Amplitude")
        self.ax.grid(True, alpha=0.3)
        self.figure.tight_layout()
        self.canvas.draw()
