from PySide6.QtCore import QObject, QTimer, Signal

from models.signal_processor import SignalProcessor
from models.tcp_client_model import TcpClientModel


class MainViewModel(QObject):
    """
    ViewModel for the final project.

    The ViewModel is the middle layer of the MVVM structure. It owns the
    application state and mediates between the View (GUI) and the Models
    (TCP client + signal processor). The View never touches the TCP model
    directly - it only reacts to the signals emitted here.

    Signals emitted to the View:
    - plot_updated(x, y)          : new single-channel live data
    - plot_all_updated(matrix)    : new all-channels live data (channels x samples)
    - status_updated(text)        : human-readable connection/status text
    - signal_time_updated(seconds): total received signal time
    - connection_changed(bool)    : True when connected, False when not
    """

    plot_updated = Signal(object, object)
    plot_all_updated = Signal(object)
    status_updated = Signal(str)
    signal_time_updated = Signal(float)
    connection_changed = Signal(bool)

    def __init__(self):
        super().__init__()

        self.sampling_rate = 2000
        self.channels = 32

        self.model = TcpClientModel(
            host="localhost",
            port=12345,
            sampling_rate=self.sampling_rate,
            channels=self.channels,
            samples_per_packet=18,
            window_seconds=10,
        )
        self.processor = SignalProcessor(sampling_rate=self.sampling_rate)

        # Application state.
        self.is_plotting = False
        self.selected_channel = 0
        self.mode = "original"        # original | rms | filtered
        self.show_all_channels = False

        # The all-channel view is refreshed every Nth timer tick (see
        # update_plot). With a 10 ms timer, 10 gives ~10 refreshes per second.
        self.all_channels_decimation = 10
        self._all_tick = 0

        # Qt timer drives the periodic polling of the TCP model.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_plot)

    # ------------------------------------------------------------------
    # Connection control
    # ------------------------------------------------------------------
    def start_plotting(self, port=None):
        """Connect to the server and begin streaming. Safe to call twice."""
        if self.is_plotting:
            return

        try:
            self.model.connect(port=port)
        except (OSError, ValueError) as error:
            self.status_updated.emit(f"Could not connect to server: {error}")
            return

        self.is_plotting = True
        self.connection_changed.emit(True)
        self.status_updated.emit(f"Connected to TCP server on port {self.model.port}.")
        self.timer.start(10)

    def stop_plotting(self):
        """Stop streaming and disconnect, keeping the recording for offline use."""
        if not self.is_plotting:
            return

        self.timer.stop()
        self.model.disconnect()

        self.is_plotting = False
        self.connection_changed.emit(False)

        if self.model.has_recording():
            self.status_updated.emit(
                "Disconnected. Recorded data available for offline inspection."
            )
        else:
            self.status_updated.emit("Disconnected from TCP server.")

    # ------------------------------------------------------------------
    # User selections (called by the View)
    # ------------------------------------------------------------------
    def set_channel(self, channel_index):
        """Change which channel the single-channel live view shows."""
        self.selected_channel = int(channel_index) % self.channels

    def set_mode(self, mode):
        """Change the processing mode: original / rms / filtered."""
        if mode in SignalProcessor.MODES:
            self.mode = mode

    def set_show_all_channels(self, show_all):
        """Toggle between single-channel and all-channels live view."""
        self.show_all_channels = bool(show_all)

    # ------------------------------------------------------------------
    # Periodic update (driven by the timer)
    # ------------------------------------------------------------------
    def update_plot(self):
        """Poll the TCP model, process the data, and emit it to the View."""
        self.model.receive_data()

        # If the model disconnected itself (server closed / lost), reflect it.
        if not self.model.is_connected and self.is_plotting:
            self.stop_plotting()
            self.status_updated.emit("Connection lost.")
            return

        if not self.model.has_data():
            return

        buffer = self.model.get_live_buffer()  # channels x samples

        if self.show_all_channels:
            # Processing 32 channels of a 10 s window is expensive (tens of ms
            # in rms/filtered mode). Running that at the full 100 Hz timer rate
            # would saturate the CPU and freeze the GUI, so the all-channel
            # overview is refreshed at a lower rate. A stacked 32-channel
            # overview does not need 100 fps to be readable.
            self._all_tick = (self._all_tick + 1) % self.all_channels_decimation
            if self._all_tick != 0:
                return
            processed = self.processor.process(buffer, self.mode)
            self.plot_all_updated.emit(processed)
        else:
            channel = buffer[self.selected_channel, :]
            processed = self.processor.process(channel, self.mode)
            n = processed.shape[0]
            x = self._time_axis(n)
            self.plot_updated.emit(x, processed)

        self.signal_time_updated.emit(self.model.get_signal_time_seconds())

    def _time_axis(self, n_samples):
        import numpy as np

        return np.arange(n_samples) / self.sampling_rate

    # ------------------------------------------------------------------
    # Offline inspection support
    # ------------------------------------------------------------------
    def has_recording(self):
        """True if there is recorded data to inspect offline."""
        return self.model.has_recording()

    def get_offline_channel(self, channel_index, mode):
        """
        Return (x, y) for one channel of the full recording, processed with
        the given mode. Used by the offline Matplotlib window.
        """
        import numpy as np

        recording = self.model.get_full_recording()
        channel_index = int(channel_index) % self.channels
        channel = recording[channel_index, :]
        processed = self.processor.process(channel, mode)
        x = np.arange(processed.shape[0]) / self.sampling_rate
        return x, processed
