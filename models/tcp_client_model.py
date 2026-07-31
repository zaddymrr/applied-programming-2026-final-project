import socket

import numpy as np


class TcpClientModel:
    """
    TCP client model for receiving streamed EMG data.

    This is the data/backend layer of the MVVM structure. It knows nothing
    about the GUI. Its only responsibilities are:

    - open / close the TCP connection
    - receive raw bytes and reconstruct fixed-size packets
    - keep a rolling window for the live plot
    - keep the full recording for offline inspection

    Server data format (identical to Exercise 5):
    - 32 channels
    - 18 samples per packet
    - float64 values
    - raw bytes produced with ``ndarray.tobytes()``

    One packet therefore contains::

        32 * 18 * 8 = 4608 bytes
    """

    def __init__(
        self,
        host="localhost",
        port=12345,
        sampling_rate=2000,
        channels=32,
        samples_per_packet=18,
        window_seconds=10,
    ):
        self.host = host
        self.port = port
        self.sampling_rate = sampling_rate
        self.channels = channels
        self.samples_per_packet = samples_per_packet
        self.window_seconds = window_seconds

        # Must match the dtype the server used before calling .tobytes().
        self.dtype = np.float64

        self.socket = None
        self.is_connected = False

        # One packet = channels * samples_per_packet values.
        self.packet_size = self.channels * self.samples_per_packet
        self.packet_size_bytes = self.packet_size * np.dtype(self.dtype).itemsize

        # Number of samples kept for the live rolling view.
        self.window_size = int(self.sampling_rate * self.window_seconds)

        # byte_buffer: incomplete bytes waiting to form a full packet.
        # data_buffer: the newest window_size samples, for the live plot.
        # full_recording: every sample received, for offline inspection.
        self.byte_buffer = bytearray()
        self.data_buffer = np.empty((self.channels, 0), dtype=self.dtype)
        self.full_recording = np.empty((self.channels, 0), dtype=self.dtype)

        self.total_samples_received = 0

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------
    def connect(self, port=None):
        """
        Connect to the TCP server.

        If ``port`` is given it overrides the stored port, so the GUI can let
        the user type a port. A non-blocking socket is used so the Qt timer
        can poll for data without ever freezing the interface.
        """
        if self.is_connected:
            return

        if port is not None:
            self.port = int(port)

        # Reset buffers so a fresh connection starts from a clean state.
        self.byte_buffer = bytearray()
        self.data_buffer = np.empty((self.channels, 0), dtype=self.dtype)
        self.full_recording = np.empty((self.channels, 0), dtype=self.dtype)
        self.total_samples_received = 0

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.connect((self.host, self.port))
        except OSError:
            # Do not leave a half-open socket behind on a failed attempt.
            self.socket.close()
            self.socket = None
            raise
        self.socket.setblocking(False)
        self.is_connected = True

    def disconnect(self):
        """Close the TCP connection but keep the recorded data for offline use."""
        self.is_connected = False
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------
    def receive_data(self):
        """
        Read all currently available bytes from the socket.

        TCP is a byte stream, so a single ``recv`` does not necessarily map to
        one packet. Bytes are appended to ``byte_buffer`` and complete packets
        are extracted separately.
        """
        if not self.is_connected or self.socket is None:
            return

        while True:
            try:
                new_bytes = self.socket.recv(self.packet_size_bytes)

                # An empty result means the server closed the connection.
                if not new_bytes:
                    self.disconnect()
                    return

                self.byte_buffer.extend(new_bytes)

            except BlockingIOError:
                # No more data available right now - stop reading.
                break
            except OSError:
                # Connection dropped unexpectedly.
                self.disconnect()
                return

        self._extract_packets_from_buffer()

    def _extract_packets_from_buffer(self):
        """
        Turn complete byte packets in ``byte_buffer`` into NumPy arrays and
        append them to both the rolling buffer and the full recording.
        """
        packets = []

        while len(self.byte_buffer) >= self.packet_size_bytes:
            packet_bytes = self.byte_buffer[: self.packet_size_bytes]
            del self.byte_buffer[: self.packet_size_bytes]

            packet = np.frombuffer(packet_bytes, dtype=self.dtype)
            packet = packet.reshape(self.channels, self.samples_per_packet)
            packets.append(packet)

        if not packets:
            return

        new_data = np.concatenate(packets, axis=1)

        # Full recording keeps everything for offline inspection.
        self.full_recording = np.concatenate((self.full_recording, new_data), axis=1)

        # Rolling buffer keeps only the newest window for the live plot.
        self.data_buffer = np.concatenate((self.data_buffer, new_data), axis=1)
        if self.data_buffer.shape[1] > self.window_size:
            self.data_buffer = self.data_buffer[:, -self.window_size :]

        self.total_samples_received += new_data.shape[1]

    # ------------------------------------------------------------------
    # Accessors used by the ViewModel
    # ------------------------------------------------------------------
    def has_data(self):
        """True if the rolling buffer holds enough samples to draw a line."""
        return self.data_buffer.shape[1] >= 2

    def has_recording(self):
        """True if any data was recorded (used to enable offline plotting)."""
        return self.full_recording.shape[1] >= 2

    def get_live_buffer(self):
        """Return the current rolling buffer (channels x samples)."""
        return self.data_buffer

    def get_full_recording(self):
        """Return the complete recording (channels x samples)."""
        return self.full_recording

    def get_signal_time_seconds(self):
        """Total signal time received so far, in seconds."""
        return self.total_samples_received / self.sampling_rate
