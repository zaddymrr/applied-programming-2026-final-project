from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
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
        controls.addWidget(self.channel_box)

        controls.addWidget(QLabel("Mode:"))
        self.mode_box = QComboBox()
        self.mode_box.addItems(["original", "rms", "filtered"])
        controls.addWidget(self.mode_box)

        controls.addStretch()
        layout.addLayout(controls)

        # --- matplotlib canvas -------------------------------------------
        self.figure = Figure(figsize=(9, 5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)
        layout.addWidget(self.canvas)

        self.channel_box.currentIndexChanged.connect(self.redraw)
        self.mode_box.currentTextChanged.connect(self.redraw)

        self.redraw()

    def redraw(self):
        """Redraw the currently selected channel and mode."""
        self.ax.clear()

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
