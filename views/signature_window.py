"""
Standalone "about" window.

This module is completely independent of the rest of the application:
it does not import, read, or modify the TCP model, the rolling buffer, the
signal processor, or the 32-channel pipeline in any way. It is a decorative
credit screen only, and removing this file would not change the behaviour of
the application.

The handle is rendered as a synthetic waveform by taking the vector outlines
of the text glyphs and drawing them as a line trace, in the style of a signal
plot. No measured data is involved.
"""

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

HANDLE = "@zaddymrr"


def _text_to_traces(text, size=1.0):
    """
    Convert ``text`` into a list of (x, y) arrays.

    Each array is one continuous stroke of the glyph outlines, so the letters
    are drawn as separate traces instead of being joined by stray lines.
    """
    font = FontProperties(family="DejaVu Sans", weight="bold")
    path = TextPath((0.0, 0.0), text, size=size, prop=font)

    traces = []
    current = []
    for (x, y), code in zip(path.vertices, path.codes):
        # code 1 == MOVETO, which starts a new stroke.
        if code == 1 and current:
            traces.append(np.asarray(current, dtype=float))
            current = []
        current.append((x, y))
    if current:
        traces.append(np.asarray(current, dtype=float))

    return traces


class SignatureWindow(QWidget):
    """Decorative credit window. Not part of the signal-processing pipeline."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("About")
        self.resize(760, 340)

        layout = QVBoxLayout(self)

        figure = Figure(figsize=(7.4, 2.8), facecolor="#1e1e2e")
        canvas = FigureCanvasQTAgg(figure)
        ax = figure.add_subplot(111)
        ax.set_facecolor("#1e1e2e")

        traces = _text_to_traces(HANDLE)

        # Colour the strokes across a gradient, mirroring the all-channel view.
        n = max(1, len(traces))
        for i, trace in enumerate(traces):
            shade = 0.45 + 0.5 * (i / n)
            ax.plot(
                trace[:, 0],
                trace[:, 1],
                color=(0.35, 0.55 * shade + 0.3, 0.98),
                linewidth=2.0,
                solid_capstyle="round",
            )

        all_points = np.concatenate(traces, axis=0)
        ax.set_xlim(all_points[:, 0].min() - 0.2, all_points[:, 0].max() + 0.2)
        ax.set_ylim(all_points[:, 1].min() - 0.5, all_points[:, 1].max() + 0.35)
        ax.set_aspect("equal")
        ax.axis("off")

        figure.tight_layout()
        layout.addWidget(canvas)

        caption = QLabel(
            "TCP EMG Viewer — built by Mohammad Zaid\n"
            "Decorative credit screen. Synthetic trace, not measured data."
        )
        caption.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(caption)
