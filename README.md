# RTSP Dual-Camera Streaming and Recording — Jetson Orin NX + Desktop

Stream two Basler cameras from a Jetson Orin NX to a desktop over RTSP,
with live GUI preview and per-camera MP4 recording.

---

## System Architecture

```
┌─────────────────────────────────────────┐        ┌────────────────────────────────────────┐
│         Jetson Orin NX (server)         │        │         Desktop / ZBOX (client)         │
│                                         │        │                                        │
│  Basler cam0 (GRAY8)                    │        │  GStreamer RTSP receive                 │
│      │                                  │  RTSP  │      │                                 │
│  Basler cam1 (GRAY8)                    │ ──────▶│  Hardware decode (vah264dec /           │
│      │                                  │        │   nvh264dec / avdec_h264 fallback)      │
│  pylonsrc × 2                           │        │      │                                 │
│  → nvvidconv → textoverlay (datetime)   │        │  cv2.imshow  preview @ 1280px wide     │
│  → compositor (side-by-side 2×W)        │        │  numpy slice → VideoWriter             │
│  → nvvidconv → nvv4l2h264enc (NVENC)    │        │      cam0_<ts>.mp4  (left half)         │
│  → rtph264pay → GstRTSPServer           │        │      cam1_<ts>.mp4  (right half)        │
└─────────────────────────────────────────┘        └────────────────────────────────────────┘
```

**Key design points:**
- The Jetson encodes in hardware (NVENC), so the entire camera→network path never bottlenecks on Python.
- The stream is a single H.264 feed: a side-by-side composite `(2×side_w) × side_h` with a green datetime overlay baked in by the server.
- The client splits the composite with zero-copy numpy slices for preview; contiguous copies are made only when writing to the VideoWriter.
- The client auto-detects frame dimensions from the first frame, so `--side_w` / `--side_h` do not need to be passed manually.

---

## Project Structure

```
├── rtsp_server_jetson_device/
│   │
│   │   # --- Main script ---
│   ├── mini_rtsp_dualcam_pfs.py          # Current working dual-camera RTSP server
│   │
│   │   # --- Historical / reference variants ---
│   ├── mini_rtsp_dualcam_launch.py       # Earliest launch version — baseline reference
│   ├── mini_rtsp_dualcam_launch_60fps.py # Hardcoded 60fps variant
│   ├── mini_rtsp_dualcam_launch_v3.py    # Crash-hardened: set_reusable, num-extra-surfaces
│   ├── mini_rtsp_onecam.py               # Single-camera RTSP server (/cam0)
│   ├── mini_rtsp_onecam_launch.py        # Single-camera launch wrapper
│   │
│   │   # --- Diagnostic tools ---
│   ├── rtsp_streamer.py                  # Tests each GStreamer element individually — debug missing plugins
│   ├── rtsp_test.py                      # Pipeline test using videotestsrc (no camera needed)
│   │
│   │   # --- Local camera utilities (no RTSP) ---
│   ├── dual_preview.py                   # Live side-by-side OpenCV preview
│   ├── dual_record.py                    # Local dual-camera recording (no RTSP)
│   │
│   │   # --- Flask / MJPEG alternative streaming ---
│   ├── streaming/
│   │   ├── camera.py                     # pypylon + Flask MJPEG streaming server
│   │   ├── main.py                       # Flask app entry point
│   │   ├── router.py                     # Flask routes
│   │   └── camera_setting.yaml          # Exposure/gain config for Flask streamer
│   │
│   │   # --- Camera PFS configuration files ---
│   ├── camera1_config_gray.pfs           # Basler PFS — cam0, grayscale
│   ├── camera2_config_gray.pfs           # Basler PFS — cam1, grayscale
│   ├── camera1_config_color.pfs          # Basler PFS — cam0, color
│   ├── camera2_config_color.pfs          # Basler PFS — cam1, color
│   ├── color.pfs                         # PFS for daA1920-160uc color model
│   │
│   │   # --- Camera serial number profiles ---
│   ├── camera_profiles/
│   │   ├── camera_features_40535833.txt  # Full feature dump — SN 40535833 (daA1920-160uc)
│   │   └── camera_features_40535835.txt  # Full feature dump — SN 40535835
│   │
│   └── requirements.txt                  # Minimal server dependencies
│
└── rtsp_client_desktop/
    ├── rtsp_dual_recorder.py             # Current working client (GUI preview + record)
    ├── pyproject.toml                    # uv project config
    └── rtsp_preview_and_record.py        # Older single-file client (reference)
```

---

## Quick Start

### Server — Jetson Orin NX

> **Hardware:** Jetson Orin NX, two Basler cameras, GStreamer with Jetson multimedia plugins (`nvvidconv`, `nvv4l2h264enc`).
>
> **Dependencies:**
> ```bash
> pip install -r requirements.txt
> ```

```bash
cd /home/casper/Dual_Camera

python mini_rtsp_dualcam_pfs.py \
  --fps 60 \
  --side_w 1024 --side_h 768 \
  --pfs0 camera1_config_gray.pfs \
  --pfs1 camera2_config_gray.pfs \
  --force_format GRAY8 \
  --bitrate 12000000
```

The server listens on **`rtsp://<jetson_ip>:8554/dualcam`**.

**Server arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `--fps` | 30 | Target stream frame rate |
| `--side_w` | 1024 | Per-camera width (each half of composite) |
| `--side_h` | 768 | Frame height |
| `--pfs0` | — | PFS config file for camera 0 (left) |
| `--pfs1` | — | PFS config file for camera 1 (right) |
| `--force_format` | — | Force pixel format after pylonsrc (e.g. `GRAY8`, `BGRx`) |
| `--bitrate` | 8000000 | H.264 encoding bitrate in bps |
| `--port` | 8554 | RTSP server port |
| `--mount` | `/dualcam` | RTSP mount point |

---

### Client — Desktop (ZBOX or any Linux machine)

> **Requirements:** Python 3.12, `uv`, system `python3-opencv` with GStreamer support.
>
> ```bash
> sudo apt install python3-opencv   # Ubuntu — provides GStreamer-enabled cv2
> uv venv --python 3.12 --system-site-packages .venv
> ```

```bash
cd rtsp_client_desktop

uv run python rtsp_dual_recorder.py --url rtsp://192.168.0.151:8554/dualcam
```

**Client arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `--url` | `rtsp://192.168.0.151:8554/dualcam` | RTSP stream URL |
| `--side_w` | 1280 | Per-camera width (auto-detected from stream) |
| `--side_h` | 1024 | Frame height (auto-detected from stream) |
| `--fps` | 60.0 | Expected stream fps (used by VideoWriter) |
| `--output_dir` | `./recordings` | Directory for recorded MP4 files |

**Keyboard controls:**

| Key | Action |
|-----|--------|
| `r` | Start recording — saves `cam0_<ts>.mp4` and `cam1_<ts>.mp4` to `--output_dir` |
| `s` | Stop recording |
| `q` / ESC | Quit (stops any active recording first) |

**GUI overlay:**
- Top-left: `[LIVE]` (grey) or `[REC]` (green) status tag
- Bottom-left: rolling 30-frame FPS counter
- Bottom-left (while recording): elapsed recording time `REC MM:SS`
- Red vertical line at horizontal midpoint marking the cam0/cam1 split

---

## Hardware Decoder Selection (client)

The client tries hardware decoders in this order and prints which one was selected at startup:

1. `nvh264dec` — NVIDIA NVDEC (RTX GPU) — best performance
2. `vah264dec` — Intel/AMD VA-API — good performance
3. `avdec_h264` — software decode fallback — ~43 fps on 2560×1024

On Ubuntu 24.04 with NVIDIA driver 570+, `nvh264dec` via the apt GStreamer package
may fail to initialize CUDA despite the driver being present (ABI mismatch). In that
case `vah264dec` is used automatically and delivers ~60 fps on Intel integrated graphics.

---

## Diagnostic Tools (server-side)

**`rtsp_test.py`** — test the full GStreamer/RTSP pipeline without any cameras attached.
Uses `videotestsrc` in place of `pylonsrc`. Run this first when setting up a new machine.

**`rtsp_streamer.py`** — builds the pipeline element by element and reports exactly which
plugin fails to load. Use this when `gst-inspect-1.0` passes but the pipeline refuses to start.

---

## Known Issues & Fixes Applied

### Stream lag and camera freeze (server-side)
**Symptom:** One camera half freezes; the other accumulates ~1 min of lag.  
**Cause:** GStreamer compositor blocking on timestamp sync between the two camera branches.  
**Fix:** `compositor sync=false` + pre-compositor queues capped at `max-size-buffers=2 leaky=downstream`.

### Stripe artifact in recorded files (client-side)
**Symptom:** Recorded MP4 shows horizontal stripes; GUI preview is correct.  
**Cause:** `frame[:, :side_w]` is a non-contiguous numpy view; GStreamer `appsrc` reads raw bytes ignoring stride, interleaving rows from both camera halves.  
**Fix:** `.copy()` called on each half before passing to `VideoWriter.write()`.
