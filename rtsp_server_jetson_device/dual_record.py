"""
dual_record.py — Record two Basler cameras simultaneously to separate video files.

Features:
  - Synchronized start: both grab threads launch together via a threading.Barrier
  - Green datetime overlay, font width ≈ 30% of 1280 px (≈ 384 px)
  - Correct shutdown: StopGrabbing before thread join to avoid camera deadlock
  - Reports actual achieved FPS at the end
  - Stop with Ctrl+C or --duration

Usage:
    python dual_record.py
    python dual_record.py --fps 60 --duration 10
    python dual_record.py --pfs0 camera1_config_gray.pfs --pfs1 camera2_config_gray.pfs
"""

import argparse
import datetime
import os
import sys
import threading
import time

import cv2
import numpy as np
from pypylon import pylon

# ── font sizing ───────────────────────────────────────────────────────────────
_FONT      = cv2.FONT_HERSHEY_SIMPLEX
_THICKNESS = 2
_REF_TEXT  = "2026-04-20 16:59:00.000"
_TARGET_W  = int(1280 * 0.30)   # 384 px


def _calc_font_scale() -> float:
    scale = 1.0
    for _ in range(40):
        (w, _), _ = cv2.getTextSize(_REF_TEXT, _FONT, scale, _THICKNESS)
        if w == 0:
            break
        prev, scale = scale, scale * _TARGET_W / w
        if abs(scale - prev) < 1e-4:
            break
    return scale


FONT_SCALE = _calc_font_scale()
(_, _TH), _BL = cv2.getTextSize(_REF_TEXT, _FONT, FONT_SCALE, _THICKNESS)
TEXT_Y = _TH + _BL + 4


# ── camera setup ─────────────────────────────────────────────────────────────

def open_cameras(pfs0: str, pfs1: str, force_fmt: str, fps: int):
    tl      = pylon.TlFactory.GetInstance()
    devices = tl.EnumerateDevices()
    if len(devices) < 2:
        print(f"[ERROR] Found {len(devices)} camera(s), need 2.")
        sys.exit(1)

    cameras = pylon.InstantCameraArray(2)
    for i, cam in enumerate(cameras):
        cam.Attach(tl.CreateDevice(devices[i]))
    cameras.Open()

    fmt_map   = {"YUY2": "YUV422Packed", "BGRx": "BGR8", "GRAY8": "Mono8"}
    pylon_fmt = fmt_map.get(force_fmt, force_fmt)

    for idx, (cam, pfs) in enumerate(zip(cameras, [pfs0, pfs1])):
        sn = cam.DeviceInfo.GetSerialNumber()
        if pfs and os.path.exists(pfs):
            pylon.FeaturePersistence.Load(pfs, cam.GetNodeMap(), True)
            print(f"[Cam {idx}] SN={sn}  PFS: {pfs}")
        else:
            print(f"[Cam {idx}] SN={sn}  no PFS")

        for fmt in (pylon_fmt, force_fmt):
            try:
                cam.PixelFormat.SetValue(fmt)
                break
            except Exception:
                pass

        try:
            cam.AcquisitionFrameRateEnable.SetValue(True)
            cam.AcquisitionFrameRate.SetValue(float(fps))
        except Exception as e:
            print(f"[Cam {idx}] FPS warning: {e}")

        # Cap exposure so shutter doesn't bottleneck frame rate
        max_exp_us = 1_000_000 / fps
        try:
            cur = cam.ExposureTime.GetValue()
            if cur > max_exp_us:
                cam.ExposureTime.SetValue(max_exp_us)
                print(f"[Cam {idx}] Exposure capped {cur:.0f} → {max_exp_us:.0f} µs")
        except Exception:
            pass

    return cameras


# ── recording thread ──────────────────────────────────────────────────────────

def _make_converter():
    c = pylon.ImageFormatConverter()
    c.OutputPixelFormat  = pylon.PixelType_BGR8packed
    c.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
    return c


def _record_thread(cam_idx: int, cam,
                   writer: cv2.VideoWriter,
                   out_w: int, out_h: int,
                   barrier: threading.Barrier,
                   stop: threading.Event,
                   counter: list):
    """
    Grab → BGR convert → datetime overlay → VideoWriter.write().
    Each thread owns its own ImageFormatConverter (not thread-safe to share).
    Uses LatestImageOnly so pylon drops frames we can't process fast enough.
    Barrier ensures both cameras start grabbing at the same instant.
    """
    converter = _make_converter()   # thread-local converter
    barrier.wait()

    while not stop.is_set():
        try:
            result = cam.RetrieveResult(1000, pylon.TimeoutHandling_ThrowException)
        except pylon.TimeoutException:
            continue
        except Exception as e:
            if not stop.is_set():
                print(f"\n[Cam {cam_idx}] grab error: {e}")
            break

        if result.GrabSucceeded():
            arr = converter.Convert(result).Array
            if arr.ndim == 2:
                arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            if arr.shape[1] != out_w or arr.shape[0] != out_h:
                arr = cv2.resize(arr, (out_w, out_h))

            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            cv2.putText(arr, ts, (10, TEXT_Y),
                        _FONT, FONT_SCALE, (0, 255, 0), _THICKNESS, cv2.LINE_AA)
            writer.write(arr)
            counter[0] += 1
        result.Release()


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Synchronized dual Basler recording with datetime overlay")
    ap.add_argument("--pfs0",         default="camera1_config_gray.pfs")
    ap.add_argument("--pfs1",         default="camera2_config_gray.pfs")
    ap.add_argument("--force_format", default="GRAY8", choices=["YUY2", "BGRx", "GRAY8"])
    ap.add_argument("--fps",          type=int,   default=30)
    ap.add_argument("--width",        type=int,   default=1280)
    ap.add_argument("--height",       type=int,   default=1024)
    ap.add_argument("--output_dir",   default="videos")
    ap.add_argument("--duration",     type=float, default=0,
                    help="Recording duration in seconds (0 = run until Ctrl+C)")
    ap.add_argument("--codec",        default="nv",
                    help="'nv' (default, Jetson HW H.264), MJPG, mp4v, XVID")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"[Info] Font scale={FONT_SCALE:.3f}, text-y={TEXT_Y}px, target text width={_TARGET_W}px")

    cameras = open_cameras(args.pfs0, args.pfs1, args.force_format, args.fps)
    ts_str  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fourcc = cv2.VideoWriter_fourcc(*args.codec) if args.codec.lower() != "nv" else 0
    writers, out_paths = [], []
    for i in range(2):
        if args.codec.lower() == "nv":
            ext  = "mp4"
            path = os.path.join(args.output_dir, f"cam{i}_{ts_str}.{ext}")
            gst  = (
                f"appsrc ! video/x-raw,format=BGR,width={args.width},height={args.height},"
                f"framerate={args.fps}/1 ! videoconvert ! video/x-raw,format=I420 ! "
                f"nvvidconv ! video/x-raw(memory:NVMM),format=NV12 ! "
                f"nvv4l2h264enc bitrate=8000000 insert-sps-pps=true ! "
                f"h264parse ! mp4mux ! filesink location={path}"
            )
            w = cv2.VideoWriter(gst, cv2.CAP_GSTREAMER, 0, args.fps, (args.width, args.height))
        else:
            ext  = "avi" if args.codec.upper() in ("MJPG", "XVID") else "mp4"
            path = os.path.join(args.output_dir, f"cam{i}_{ts_str}.{ext}")
            w    = cv2.VideoWriter(path, fourcc, args.fps, (args.width, args.height))
        if not w.isOpened():
            print(f"[ERROR] Cannot open VideoWriter: {path}")
            sys.exit(1)
        writers.append(w)
        out_paths.append(path)
        print(f"[Cam {i}] → {path}")

    # Start grabbing BEFORE threads so hardware pipeline is warm
    for cam in cameras:
        cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    stop     = threading.Event()
    barrier  = threading.Barrier(2)
    counters = [[0], [0]]

    threads = [
        threading.Thread(
            target=_record_thread,
            args=(i, cameras[i], writers[i],
                  args.width, args.height, barrier, stop, counters[i]),
            daemon=True,
        )
        for i in range(2)
    ]
    for t in threads:
        t.start()

    print(f"[Recording] Started.  Press Ctrl+C to stop"
          + (f" (auto-stop after {args.duration}s)" if args.duration else "") + ".")

    t0 = time.time()
    try:
        while True:
            elapsed = time.time() - t0
            fps0 = counters[0][0] / elapsed if elapsed > 0 else 0
            fps1 = counters[1][0] / elapsed if elapsed > 0 else 0
            print(f"\r[Recording] {elapsed:7.1f}s  actual fps: cam0={fps0:.1f} cam1={fps1:.1f}   ",
                  end="", flush=True)
            if args.duration > 0 and elapsed >= args.duration:
                print(f"\n[Recording] Duration {args.duration}s reached.")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[Recording] Ctrl+C received.")

    elapsed_total = time.time() - t0
    stop.set()

    # Stop grabbing FIRST so RetrieveResult unblocks and threads can exit cleanly
    for cam in cameras:
        if cam.IsGrabbing():
            cam.StopGrabbing()

    for t in threads:
        t.join(timeout=5)

    for w in writers:
        w.release()
    for cam in cameras:
        if cam.IsOpen():
            cam.Close()

    print(f"\n[Recording] Finished after {elapsed_total:.1f}s")
    for i in range(2):
        n = counters[i][0]
        actual_fps = n / elapsed_total if elapsed_total > 0 else 0
        size_mb = os.path.getsize(out_paths[i]) / 1e6
        print(f"  cam{i}: {n} frames @ actual {actual_fps:.1f} fps "
              f"({n/args.fps:.1f}s video @ {args.fps}fps) — {size_mb:.1f} MB → {out_paths[i]}")


if __name__ == "__main__":
    main()
