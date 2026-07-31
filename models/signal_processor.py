import numpy as np
from scipy import signal as sp_signal


class SignalProcessor:
    """
    Signal-processing helper for the three display modes.

    This mirrors the processing from Exercise 2 and is deliberately kept
    free of any GUI code so it can be reused by both the live and offline
    views.

    Modes:
    - "original" : the raw signal, unchanged
    - "filtered" : 4th-order Butterworth bandpass, 20-450 Hz
    - "rms"      : moving-window RMS envelope of the filtered signal

    Filter / RMS parameters (documented in the README):
    - bandpass low cut  : 20 Hz
    - bandpass high cut  : 450 Hz
    - filter order      : 4 (Butterworth, zero-phase via filtfilt)
    - RMS window        : 50 ms
    """

    MODES = ("original", "rms", "filtered")

    def __init__(
        self,
        sampling_rate=2000,
        low_cut=20.0,
        high_cut=450.0,
        filter_order=4,
        rms_window_ms=50.0,
    ):
        self.sampling_rate = sampling_rate
        self.low_cut = low_cut
        self.high_cut = high_cut
        self.filter_order = filter_order
        self.rms_window_ms = rms_window_ms

        # Pre-compute the Butterworth coefficients once, in second-order
        # sections (SOS) form. SOS is numerically more stable than b/a for
        # higher orders, and sosfiltfilt can process every channel of a 2-D
        # array in one vectorized call instead of looping in Python.
        nyquist = 0.5 * self.sampling_rate
        high_cut = min(self.high_cut, nyquist * 0.99)
        low = self.low_cut / nyquist
        high = high_cut / nyquist
        self._sos = sp_signal.butter(
            self.filter_order, [low, high], btype="band", output="sos"
        )
        # Minimum length filtfilt needs, given the padding it applies.
        self._min_len = 3 * (2 * self._sos.shape[0] + 1)

        # RMS window length in samples.
        self.rms_window_samples = max(
            1, int(self.rms_window_ms * self.sampling_rate / 1000.0)
        )

    def process(self, data, mode):
        """
        Apply the selected processing ``mode`` to ``data``.

        ``data`` may be a single channel (1-D) or many channels (2-D, shaped
        channels x samples). The output has the same shape as the input.
        """
        if mode == "original":
            return data

        data = np.asarray(data, dtype=float)
        n_samples = data.shape[-1]

        # filtfilt pads the signal, so very short inputs would raise. Early in
        # a stream this happens for a moment - return the raw data instead of
        # crashing.
        if n_samples <= self._min_len:
            return data

        # sosfiltfilt filters every channel at once along the last axis.
        # This is far faster than looping over channels in Python.
        filtered = sp_signal.sosfiltfilt(self._sos, data, axis=-1)

        if mode == "filtered":
            return filtered

        if mode == "rms":
            return self._moving_rms(filtered)

        return data

    def _moving_rms(self, data):
        """
        Moving-window RMS envelope, vectorized over channels.

        Implemented with a cumulative sum so the cost does not grow with the
        window length: the mean of every window is obtained from two lookups
        into the running sum, rather than re-summing each window.
        """
        window = self.rms_window_samples
        squared = data ** 2

        # Pad at the edges so the output keeps the input length and the
        # window stays centred (equivalent to np.convolve(..., mode="same")).
        pad_left = window // 2
        pad_right = window - 1 - pad_left
        padded = np.pad(
            squared,
            [(0, 0)] * (squared.ndim - 1) + [(pad_left, pad_right)],
            mode="edge",
        )

        cumsum = np.cumsum(padded, axis=-1)
        # Prepend a zero column so the first window is handled uniformly.
        zeros_shape = list(cumsum.shape)
        zeros_shape[-1] = 1
        cumsum = np.concatenate(
            [np.zeros(zeros_shape, dtype=cumsum.dtype), cumsum], axis=-1
        )

        window_sums = cumsum[..., window:] - cumsum[..., :-window]
        return np.sqrt(window_sums / window)
