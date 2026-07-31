from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from views.offline_plot_window import OfflinePlotWindow
from views.vispy_plot_widget import VisPyPlotWidget


DARK_STYLE = """
QWidget { background-color: #1e1e2e; color: #cdd6f4; font-size: 13px; }
QPushButton {
    background-color: #313244; border: 1px solid #45475a;
    border-radius: 6px; padding: 6px 12px;
}
QPushButton:hover { background-color: #45475a; }
QPushButton:pressed { background-color: #585b70; }
QPushButton:disabled { color: #6c7086; border-color: #313244; }
QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #313244; border: 1px solid #45475a;
    border-radius: 6px; padding: 4px 8px;
}
QLabel#status { color: #a6e3a1; font-weight: bold; }
QLabel#title { font-size: 16px; font-weight: bold; }
"""


class MainWindow(QMainWindow):
    """
    Main application window (View layer).

    Owns every visible control and wires user actions and ViewModel signals
    together. It never receives TCP data directly - it only forwards user
    intent to the ViewModel and displays whatever the ViewModel emits.
    """

    def __init__(self, view_model):
        super().__init__()
        self.view_model = view_model
        self.offline_window = None
        self.about_window = None

        self.setWindowTitle("TCP EMG Viewer - Final Project")
        self.resize(1300, 820)
        self.setStyleSheet(DARK_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # --- top bar: connection controls --------------------------------
        top_bar = QHBoxLayout()

        top_bar.addWidget(QLabel("Port:"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(12345)
        top_bar.addWidget(self.port_input)

        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)
        top_bar.addWidget(self.connect_button)
        top_bar.addWidget(self.disconnect_button)

        top_bar.addSpacing(20)
        self.status_label = QLabel("Not connected.")
        self.status_label.setObjectName("status")
        top_bar.addWidget(self.status_label)

        top_bar.addStretch()
        self.time_label = QLabel("Signal time: 0.00 s")
        self.time_label.setObjectName("title")
        top_bar.addWidget(self.time_label)

        root.addLayout(top_bar)

        # --- control row: channel, mode, plot-all, offline ---------------
        control_row = QHBoxLayout()

        control_row.addWidget(QLabel("Channel:"))
        self.channel_box = QComboBox()
        self.channel_box.addItems(
            [str(i + 1) for i in range(view_model.channels)]
        )
        # Decorative entry, kept below a separator so it is clearly distinct
        # from the 32 real acquisition channels.
        self.channel_box.insertSeparator(view_model.channels)
        self.channel_box.addItem("67")
        control_row.addWidget(self.channel_box)

        control_row.addWidget(QLabel("Mode:"))
        self.mode_box = QComboBox()
        self.mode_box.addItems(["original", "rms", "filtered"])
        control_row.addWidget(self.mode_box)

        control_row.addWidget(QLabel("Y scale:"))
        self.y_scale_input = QDoubleSpinBox()
        self.y_scale_input.setRange(0.0001, 100000.0)
        self.y_scale_input.setDecimals(4)
        self.y_scale_input.setValue(500.0)
        self.y_scale_input.setSingleStep(50.0)
        control_row.addWidget(self.y_scale_input)

        self.autofit_button = QPushButton("Auto-fit Y")
        control_row.addWidget(self.autofit_button)

        self.plot_all_button = QPushButton("Plot All Channels")
        self.plot_all_button.setCheckable(True)
        control_row.addWidget(self.plot_all_button)

        self.offline_button = QPushButton("Open Offline Plot")
        control_row.addWidget(self.offline_button)

        self.about_button = QPushButton("About")
        control_row.addWidget(self.about_button)

        control_row.addStretch()
        root.addLayout(control_row)

        # --- plot widget --------------------------------------------------
        self.plot_widget = VisPyPlotWidget(
            visible_duration_seconds=10.0,
            num_channels=view_model.channels,
        )
        self.plot_widget.set_y_scale(self.y_scale_input.value())
        root.addWidget(self.plot_widget, stretch=1)

        # --- wire user actions to the ViewModel --------------------------
        self.connect_button.clicked.connect(self._on_connect)
        self.disconnect_button.clicked.connect(self._on_disconnect)
        self.channel_box.currentIndexChanged.connect(self._on_channel_changed)
        self.mode_box.currentTextChanged.connect(self.view_model.set_mode)
        self.y_scale_input.valueChanged.connect(self.plot_widget.set_y_scale)
        self.autofit_button.clicked.connect(self._on_autofit)
        self.plot_all_button.toggled.connect(self._on_plot_all_toggled)
        self.offline_button.clicked.connect(self._open_offline)
        self.about_button.clicked.connect(self._open_about)

        # --- wire ViewModel signals to the View --------------------------
        self.view_model.plot_updated.connect(self.plot_widget.update_plot)
        self.view_model.plot_all_updated.connect(self.plot_widget.update_plot_all)
        self.view_model.status_updated.connect(self.status_label.setText)
        self.view_model.signal_time_updated.connect(self._on_time)
        self.view_model.connection_changed.connect(self._on_connection_changed)

    # ------------------------------------------------------------------
    def _on_connect(self):
        port = self.port_input.value()
        self.view_model.start_plotting(port=port)

    def _on_disconnect(self):
        self.view_model.stop_plotting()

    def _on_connection_changed(self, connected):
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.port_input.setEnabled(not connected)

    def _on_plot_all_toggled(self, checked):
        # The decorative trace owns the canvas while it is showing; ignore the
        # toggle rather than recording a mode that would be restored later.
        if self.plot_widget.easter_egg_active:
            if checked:
                self.plot_all_button.setChecked(False)
            return

        self.view_model.set_show_all_channels(checked)
        self.plot_widget.set_show_all(checked)
        self.plot_all_button.setText(
            "Show Single Channel" if checked else "Plot All Channels"
        )
        self.channel_box.setEnabled(not checked)
        self.y_scale_input.setEnabled(not checked)

    def _on_channel_changed(self, index):
        """
        Handle channel selection.

        Indices 0-31 are the real acquisition channels and are forwarded to
        the ViewModel. The decorative "67" entry is handled purely in the
        View and never reaches the ViewModel or the data pipeline.
        """
        if self.channel_box.itemText(index) == "67":
            # Leave the all-channel view first, so the two layers can never
            # be drawn on top of each other.
            if self.plot_all_button.isChecked():
                self.plot_all_button.setChecked(False)
            self.plot_all_button.setEnabled(False)
            self.y_scale_input.setEnabled(False)
            self.plot_widget.set_easter_egg(True)
            self.status_label.setText("@zaddymrr on instagram")
            return

        self.plot_widget.set_easter_egg(False)
        self.plot_all_button.setEnabled(True)
        self.y_scale_input.setEnabled(True)
        self.view_model.set_channel(index)

    def _on_autofit(self):
        """Set the Y scale to a robust fit of the current channel's data."""
        suggested = self.plot_widget.suggest_y_scale()
        if suggested is None:
            self.status_label.setText("No data to fit yet.")
            return
        self.y_scale_input.setValue(suggested)
        self.status_label.setText(f"Y scale set to {suggested:.4g}.")

    def _on_time(self, seconds):
        self.time_label.setText(f"Signal time: {seconds:.2f} s")

    def _open_about(self):
        """
        Open the decorative credit window.

        Imported lazily and kept entirely separate from the data pipeline.
        """
        from views.signature_window import SignatureWindow

        self.about_window = SignatureWindow()
        self.about_window.show()

    def _open_offline(self):
        """Open the Matplotlib offline inspection window."""
        if not self.view_model.has_recording():
            self.status_label.setText("No recorded data yet - stream first.")
            return
        self.offline_window = OfflinePlotWindow(self.view_model)
        self.offline_window.show()
