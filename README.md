# TCP Signal Visualization Application — Final Project

A PySide6 desktop application for **live** and **offline** visualization of
streamed EMG signal data. The application connects to the TCP server from
Exercise 5, reconstructs the streamed packets, and displays them in real time
with VisPy, with an offline Matplotlib inspection mode after streaming stops.

The project follows an **MVVM** (Model–View–ViewModel) architecture.

---

## Group Information

- **Group name:** U da real Leader aka Mr.Zaddy
- **Group number:** none — individual submission
- **Team member:** Mohammad Zaid (mohammad.zaid@fau.de)

This project was submitted individually. I was not assigned to a project
group, which was confirmed by Daniel Haller by email on 28.07.2026:
*"if you didn't join a group, we did not assign you to any. So you have to
submit alone."*

All parts of the project — TCP client and buffering, signal processing,
ViewModel logic, VisPy live visualisation, the Matplotlib offline view,
documentation, and testing — were therefore done by me.

---

## Features

- Connect to the provided TCP server by entering a **port** and clicking **Connect**
- Live streaming starts automatically on a successful connection
- **Live VisPy plot** with a rolling 10-second window, labelled axes, and adjustable Y scale
- **Channel selection** — view any of the 32 channels
- **Plot All Channels** — all 32 channels stacked with a vertical offset for a full-array overview
- **Signal modes** — switch live between *original*, *RMS*, and *filtered*
- **Offline Matplotlib inspection** — after disconnecting, browse the full recording per channel and per mode
- **Error handling** — missing server, wrong port, lost connection, and empty recordings are all reported in the status bar without crashing

---

## Installation

Requires **Python 3.10+**.

```bash
pip install -r requirements.txt
```

Dependencies (`requirements.txt`): `numpy`, `scipy`, `matplotlib`, `pyside6`,
`PyOpenGL`, `vispy`. `PyOpenGL` is required by VisPy's OpenGL backend on a
clean install.

---

## Running the Application

The application is the **client**. You also need the **server** from Exercise 5
running separately.

**1. Start the TCP server** (in its own terminal):

```bash
python /path/to/TCP_Server/main.py
```

Wait until it prints `Server started on localhost:12345`.

> The server loads an EMG recording from a `.pkl` file. Make sure the
> `pkl_file` path inside the server points to a valid `recording.pkl` on your
> machine.

**2. Start this application** (in a second terminal):

```bash
python main.py
```

---

## How to Use

### Connecting
1. Enter the server **port** (default `12345`).
2. Click **Connect**. The status turns green and streaming begins.
3. Click **Disconnect** to stop. The recorded data is kept for offline inspection.

### Live plot
- **Channel** dropdown — choose which of the 32 channels is displayed. Below a
  separator there is one decorative entry, **67**, which shows an animated
  credit trace instead of data. It is handled entirely in the View, never
  reaches the ViewModel or the TCP model, and does not alter the 32-channel
  pipeline in any way.
- **Mode** dropdown — `original`, `rms`, or `filtered`.
- **Y scale** — sets the visible vertical range to ±(Y scale). The axis is
  deliberately *not* auto-fitted to the data min/max: a single artefact
  (electrode pop, amplifier saturation) would otherwise stretch the axis and
  squash the real signal into a flat line.
- **Auto-fit Y** — sets the Y scale from the 99th percentile of the current
  channel, so isolated artefacts are ignored. Click it once after connecting.
- **Plot All Channels** — toggles the stacked all-channel overview. While active,
  the single-channel controls are disabled.

### Offline inspection
1. **Disconnect** (or let the stream finish).
2. Click **Open Offline Plot**.
3. In the offline window, use the **Channel** and **Mode** dropdowns to inspect
   the full recording.

The offline view is a **snapshot** of the recording taken when the window is
opened, not a live view. If streaming continues afterwards, press **Refresh**
(or change a dropdown) to re-read the buffer. Inspecting after disconnecting
therefore shows the complete recording.

---

## Signal Processing Parameters

Documented so the choices can be reproduced and defended:

| Parameter | Value |
|-----------|-------|
| Sampling rate | 2000 Hz (from the server device info) |
| Bandpass filter | Butterworth, **N = 4** (`scipy.signal.butter`), **20–450 Hz** |
| Filter application | zero-phase, SOS form (`scipy.signal.sosfiltfilt`) |
| RMS window | **50 ms** (100 samples at 2000 Hz), centred moving RMS |

*Rationale:* 20–450 Hz is the standard surface-EMG band — it removes low-frequency
motion artefacts and high-frequency noise while keeping the muscle activity. A
zero-phase filter avoids shifting the signal in time. The RMS mode squares the
filtered signal, applies a 50 ms moving average, and takes the square root to
produce a smooth activation envelope.

*On the filter order:* `N = 4` is the order passed to `scipy.signal.butter`,
which is the usual way this is cited in the EMG literature. Because it is a
**bandpass**, the realised filter has 2 x N = 8 poles (4 second-order sections),
and `sosfiltfilt` applies it forward and backward, so the magnitude response is
squared. The trade-off is deliberate: a steeper effective roll-off with no phase
distortion, which matters because the bursts must stay aligned in time with the
raw trace.

---

## Project Structure (MVVM)

```text
final_project/
├── main.py                        # entry point: assembles the app
├── README.md
├── requirements.txt
├── models/                        # data + logic, no GUI code
│   ├── tcp_client_model.py        # TCP receive, byte buffer, packet reconstruction,
│   │                              #   rolling window + full recording
│   └── signal_processor.py        # original / RMS / filtered processing
├── viewmodels/
│   └── main_viewmodel.py          # state, QTimer polling, channel/mode selection,
│                                  #   emits data to the View via Qt signals
└── views/                         # GUI + plotting widgets only
    ├── main_window.py             # main window and all controls
    ├── vispy_plot_widget.py       # live VisPy plot (single + all-channel)
    ├── offline_plot_window.py     # offline Matplotlib inspection window
    └── signature_window.py        # decorative "About" credit screen (not part
                                   #   of the signal pipeline; safe to delete)
```

### Responsibilities

- **Models** own the data. `tcp_client_model.py` handles the socket, the byte
  buffer, packet reconstruction (32 × 18 × float64 = 4608 bytes), the rolling
  live buffer, and the full recording. `signal_processor.py` implements the
  three signal modes.
- **ViewModel** owns application state (connection status, selected channel,
  current mode, all-channel toggle) and a `QTimer` that periodically asks the
  model for data, processes it, and emits it via Qt signals.
- **Views** contain only GUI and plotting code. The View **never** touches the
  TCP model directly — it forwards user actions to the ViewModel and renders
  whatever the ViewModel emits.

### Data flow

```text
Connect button
      ↓
MainWindow._on_connect()
      ↓
MainViewModel.start_plotting(port)
      ↓
TcpClientModel.connect()        →  QTimer starts
      ↓ (every 10 ms)
MainViewModel.update_plot()
      ↓
TcpClientModel.receive_data()   →  bytes → packets → buffers
      ↓
SignalProcessor.process(...)    →  original / rms / filtered
      ↓
plot_updated / plot_all_updated (Qt signal)
      ↓
VisPyPlotWidget.update_plot(...)
```

---

## Error Handling

The application reports problems in the status bar instead of crashing:

- **Server not running / wrong port** — connection attempt is caught and shown.
- **Connection lost mid-stream** — detected on the next poll; the app disconnects
  cleanly and reports it.
- **No recorded data** — opening the offline plot without a recording shows a
  message instead of an empty crash.
- **Too little data for filtering** — very short signals fall back to the raw
  values rather than raising.

---

## Notes

- The server is provided by the course (Exercise 5); this repository implements
  only the client side.
- The data format matches Exercise 5 exactly: 32 channels, 18 samples per packet,
  `float64`, raw bytes.
