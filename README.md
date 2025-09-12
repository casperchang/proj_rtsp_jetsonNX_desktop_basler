# RTSP Dual-Camera Streaming and Recording for Jetson NX

This project provides a complete solution for capturing video from two Basler cameras on a Jetson NX device, streaming the combined video over RTSP, and then receiving, previewing, and recording that stream on a separate desktop machine.

## Architecture

The system is composed of two main components:

1.  **RTSP Server (Jetson Device)**: A Python script that runs on a Jetson Orin NX and uses GStreamer to:
    *   Capture video from two connected Basler cameras.
    *   Optionally apply camera settings from `.pfs` configuration files.
    *   Combine the two camera feeds into a single side-by-side video stream.
    *   Encode the combined stream in H.264 format.
    *   Serve the H.264 stream over RTSP.

2.  **RTSP Client (Desktop)**: A Python script that runs on a desktop computer and uses GStreamer to:
    *   Connect to the RTSP stream from the Jetson device.
    *   Display a live preview of the video stream.
    *   Record the stream to an MP4 file, with options for single-file or segmented recording.

## Project Structure

```
├── rtsp_client_desktop/
│   └── rtsp_preview_and_record.py
└── rtsp_server_jetson_device/
    ├── camera1_config_gray.pfs
    └── mini_rtsp_dualcam_pfs.py
```

## Usage

### 1. Server (Jetson Device)

The server script `mini_rtsp_dualcam_pfs.py` is run on the Jetson device.

**Example command:**

```bash
python mini_rtsp_dualcam_pfs.py --fps 60 --side_w 1024 --side_h 768 --bitrate 12000000 --pfs0 camera1_config_gray.pfs --force_format "GRAY8"
```

**Arguments:**

*   `--pfs0`, `--pfs1`: Path to the `.pfs` configuration file for each camera.
*   `--fps`: Target frames per second for the output stream.
*   `--side_w`, `--side_h`: Width and height for each camera's video feed after resizing.
*   `--bitrate`: The H.264 encoding bitrate in bits per second.
*   `--mount`: The RTSP mount point (e.g., `/dualcam`).
*   `--port`: The TCP port for the RTSP server.
*   `--force_format`: Force a specific color format after `pylonsrc` (e.g., `YUY2`, `BGRx`, `GRAY8`).

### 2. Client (Desktop)

The client script `rtsp_preview_and_record.py` is run on a desktop machine to view and record the stream.

**Example command:**

```bash
python rtsp_preview_and_record.py rtsp://<JETSON_IP>:8554/dualcam output.mp4 --segment-seconds 300
```

**Arguments:**

*   `rtsp_url`: The URL of the RTSP stream from the Jetson device.
*   `output`: The name of the output MP4 file (ignored if using segmentation).
*   `--latency`: Jitter buffer latency in milliseconds.
*   `--segment-seconds`: If specified, rotates the output video file every N seconds.
*   `--hwdec`: Hardware decoding option (`auto`, `nv`, `cpu`).
*   `--keyword`: A prefix for the output segmented video files.

## Configuration

*   **Camera Configuration**: The server script can use `.pfs` files to configure the Basler cameras. An example `camera1_config_gray.pfs` is provided.
*   **Stream Parameters**: The resolution, frame rate, and bitrate of the stream can be configured via command-line arguments on the server-side script.
*   **Recording**: The client script allows for flexible recording options, including continuous recording to a single file or segmented recording.
