#!/usr/bin/env python3
"""RTSP dual-camera recorder with GUI preview."""

import argparse
import os
import time
from collections import deque
from datetime import datetime

import cv2

WINDOW = "Dual Camera"

# Hardware-accelerated decoder candidates, tried in order.
# vah264dec = Intel/AMD VA-API (iGPU); nvh264dec = NVIDIA NVDEC.
_GST_DECODERS = ["nvh264dec", "vah264dec", "avdec_h264"]


def _gst_pipeline(url: str, decoder: str) -> str:
    return (
        f"rtspsrc location={url} latency=0 ! rtph264depay ! h264parse ! "
        f"{decoder} ! videoconvert ! video/x-raw,format=BGR ! "
        f"appsink drop=true sync=false"
    )


def build_gst_capture(url: str) -> tuple[cv2.VideoCapture, str]:
    for dec in _GST_DECODERS:
        cap = cv2.VideoCapture(_gst_pipeline(url, dec), cv2.CAP_GSTREAMER)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                return cap, dec
            cap.release()
    return cv2.VideoCapture(), "none"


def open_writer(path: str, side_w: int, side_h: int, fps: float) -> cv2.VideoWriter:
    gst_out = (
        f"appsrc ! video/x-raw,format=BGR,width={side_w},height={side_h},"
        f"framerate={int(fps)}/1 ! videoconvert ! x264enc speed-preset=ultrafast "
        f"tune=zerolatency ! mp4mux ! filesink location={path}"
    )
    writer = cv2.VideoWriter(gst_out, cv2.CAP_GSTREAMER, 0, fps, (side_w, side_h))
    if not writer.isOpened():
        writer = cv2.VideoWriter(
            path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (side_w, side_h)
        )
    return writer


def format_elapsed(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="RTSP dual-camera recorder")
    parser.add_argument(
        "--url",
        default="rtsp://192.168.0.151:8554/dualcam",
        help="RTSP stream URL",
    )
    parser.add_argument("--side_w", type=int, default=1280, help="Per-camera width")
    parser.add_argument("--side_h", type=int, default=1024, help="Frame height")
    parser.add_argument("--fps", type=float, default=60.0, help="Expected stream fps")
    parser.add_argument(
        "--output_dir", default="./recordings", help="Directory for recorded files"
    )
    args = parser.parse_args()

    # --- open capture ---
    cap, decoder_used = build_gst_capture(args.url)
    if cap.isOpened():
        print(f"[Decoder] GStreamer / {decoder_used}")
    else:
        print("WARNING: All GStreamer pipelines failed, falling back to default OpenCV. "
              "60 fps is unlikely without hardware decode.")
        cap = cv2.VideoCapture(args.url)
    if not cap.isOpened():
        print(f"ERROR: Cannot open stream {args.url}")
        return

    # detect actual frame dimensions from first frame
    # (build_gst_capture already consumed one frame; read another for dimension probe)
    ret, probe = cap.read()
    if not ret:
        print("ERROR: Could not read first frame.")
        cap.release()
        return
    actual_h, actual_w = probe.shape[:2]
    detected_side_w = actual_w // 2
    detected_side_h = actual_h
    if detected_side_w != args.side_w or detected_side_h != args.side_h:
        print(f"INFO: stream is {actual_w}x{actual_h}, "
              f"using side_w={detected_side_w} side_h={detected_side_h} "
              f"(overriding args {args.side_w}x{args.side_h})")
        args.side_w = detected_side_w
        args.side_h = detected_side_h

    preview_w = 1280
    preview_h = int(preview_w * args.side_h / (args.side_w * 2))

    # create window once — title changes via overlay text, not window name
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)

    recording = False
    writer0: cv2.VideoWriter | None = None
    writer1: cv2.VideoWriter | None = None
    rec_start: float = 0.0
    rec_frames: int = 0
    rec_ts: str = ""

    fps_buf: deque[float] = deque(maxlen=30)
    last_frame_time = time.monotonic()

    frame = probe  # use probed frame as first iteration
    try:
        while True:
            now = time.monotonic()
            fps_buf.append(now - last_frame_time)
            last_frame_time = now
            rolling_fps = len(fps_buf) / sum(fps_buf) if fps_buf else 0.0

            # split — contiguous copies needed for VideoWriter (GStreamer appsrc
            # reads raw bytes sequentially; non-contiguous strides cause stripe artifacts)
            left = frame[:, : args.side_w].copy()
            right = frame[:, args.side_w :].copy()

            if recording:
                writer0.write(left)
                writer1.write(right)
                rec_frames += 1

            # --- preview ---
            preview = cv2.resize(frame, (preview_w, preview_h))

            # red midpoint line
            mid_x = preview_w // 2
            cv2.line(preview, (mid_x, 0), (mid_x, preview_h - 1), (0, 0, 255), 1)

            # status tag top-left
            tag = "[REC]" if recording else "[LIVE]"
            tag_color = (0, 255, 0) if recording else (200, 200, 200)
            cv2.putText(preview, tag, (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, tag_color, 2, cv2.LINE_AA)

            # FPS overlay bottom-left
            cv2.putText(preview, f"FPS: {rolling_fps:.1f}",
                        (8, preview_h - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

            # REC elapsed
            if recording:
                elapsed = time.monotonic() - rec_start
                cv2.putText(preview, f"REC {format_elapsed(elapsed)}",
                            (8, preview_h - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)

            cv2.imshow(WINDOW, preview)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("r") and not recording:
                rec_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                os.makedirs(args.output_dir, exist_ok=True)
                path0 = os.path.join(args.output_dir, f"cam0_{rec_ts}.mp4")
                path1 = os.path.join(args.output_dir, f"cam1_{rec_ts}.mp4")
                writer0 = open_writer(path0, args.side_w, args.side_h, args.fps)
                writer1 = open_writer(path1, args.side_w, args.side_h, args.fps)
                rec_start = time.monotonic()
                rec_frames = 0
                recording = True
                print(f"[Recording] started → {path0}, {path1}")

            elif key == ord("s") and recording:
                recording = False
                _stop_recording(writer0, writer1, rec_frames, rec_start, args.output_dir, rec_ts)
                writer0 = writer1 = None

            elif key in (ord("q"), 27):  # q or ESC
                break

            ret, frame = cap.read()
            if not ret:
                print("Stream ended or frame read failed.")
                break

    finally:
        if recording and writer0 is not None:
            _stop_recording(writer0, writer1, rec_frames, rec_start, args.output_dir, rec_ts)
        cap.release()
        cv2.destroyAllWindows()


def _stop_recording(
    writer0: cv2.VideoWriter,
    writer1: cv2.VideoWriter,
    rec_frames: int,
    rec_start: float,
    output_dir: str,
    rec_ts: str,
) -> None:
    elapsed = time.monotonic() - rec_start
    actual_fps = rec_frames / elapsed if elapsed > 0 else 0.0
    writer0.release()
    writer1.release()
    path0 = os.path.join(output_dir, f"cam0_{rec_ts}.mp4")
    path1 = os.path.join(output_dir, f"cam1_{rec_ts}.mp4")
    print(f"[Recording] cam0: {rec_frames} frames, actual {actual_fps:.1f} fps → {path0}")
    print(f"[Recording] cam1: {rec_frames} frames, actual {actual_fps:.1f} fps → {path1}")


if __name__ == "__main__":
    main()
