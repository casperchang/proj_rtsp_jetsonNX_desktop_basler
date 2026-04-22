"""
dual_preview.py — 雙 Basler 相機即時 OpenCV 視窗預覽
用法:
    python dual_preview.py
    python dual_preview.py --pfs0 camera1_config_gray.pfs --pfs1 camera2_config_gray.pfs --force_format GRAY8
    python dual_preview.py --side_w 960 --side_h 720 --fps 30

按 'q' 或 ESC 離開。
"""
import argparse
import os
import sys
import cv2
import numpy as np
from pypylon import pylon


def open_cameras(pfs0: str, pfs1: str, force_fmt: str, fps: int):
    tl_factory = pylon.TlFactory.GetInstance()
    devices = tl_factory.EnumerateDevices()
    if len(devices) < 2:
        print(f"[ERROR] 偵測到 {len(devices)} 顆相機，需要至少 2 顆。")
        sys.exit(1)

    cameras = pylon.InstantCameraArray(2)
    for i, cam in enumerate(cameras):
        cam.Attach(tl_factory.CreateDevice(devices[i]))

    cameras.Open()

    pfs_files = [pfs0, pfs1]
    for idx, cam in enumerate(cameras):
        sn = cam.DeviceInfo.GetSerialNumber()
        pfs = pfs_files[idx]
        if pfs and os.path.exists(pfs):
            pylon.FeaturePersistence.Load(pfs, cam.GetNodeMap(), True)
            print(f"[Cam {idx}] SN={sn}  PFS 載入: {pfs}")
        else:
            print(f"[Cam {idx}] SN={sn}  未使用 PFS")

        # 強制色彩格式（覆蓋 PFS 設定，確保 OpenCV 相容）
        fmt_map = {
            "YUY2":  "YUV422Packed",
            "BGRx":  "BGR8",
            "GRAY8": "Mono8",
        }
        pylon_fmt = fmt_map.get(force_fmt, force_fmt)
        try:
            cam.PixelFormat.SetValue(pylon_fmt)
        except Exception:
            # 有些相機型號格式名稱不同，嘗試直接寫入
            try:
                cam.PixelFormat.SetValue(force_fmt)
            except Exception as e:
                print(f"[Cam {idx}] 無法設定格式 {force_fmt}/{pylon_fmt}: {e}")

        # 幀率
        try:
            cam.AcquisitionFrameRateEnable.SetValue(True)
            cam.AcquisitionFrameRate.SetValue(float(fps))
        except Exception as e:
            print(f"[Cam {idx}] 無法設定幀率: {e}")

        cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    return cameras


def to_bgr(grab_result, converter):
    """將任意格式的抓取結果轉為 BGR numpy array。"""
    img = converter.Convert(grab_result)
    arr = img.Array
    if arr.ndim == 2:
        arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    return arr


def main():
    parser = argparse.ArgumentParser(description="雙 Basler 相機即時 preview")
    parser.add_argument("--pfs0", type=str, default="camera1_config_gray.pfs")
    parser.add_argument("--pfs1", type=str, default="camera2_config_gray.pfs")
    parser.add_argument("--force_format", type=str, default="GRAY8",
                        choices=["YUY2", "BGRx", "GRAY8"],
                        help="相機輸出色彩格式")
    parser.add_argument("--side_w", type=int, default=960, help="每個畫面顯示寬度")
    parser.add_argument("--side_h", type=int, default=720, help="每個畫面顯示高度")
    parser.add_argument("--fps", type=int, default=30, help="相機幀率")
    parser.add_argument("--separate", action="store_true",
                        help="用兩個獨立視窗顯示，預設為並排單視窗")
    args = parser.parse_args()

    cameras = open_cameras(args.pfs0, args.pfs1, args.force_format, args.fps)

    converter = pylon.ImageFormatConverter()
    converter.OutputPixelFormat = pylon.PixelType_BGR8packed
    converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

    print("\n[Preview 啟動] 按 'q' 或 ESC 離開")

    cam0 = cameras[0]
    cam1 = cameras[1]

    while True:
        frame0 = frame1 = None

        try:
            r0 = cam0.RetrieveResult(2000, pylon.TimeoutHandling_ThrowException)
            if r0.GrabSucceeded():
                frame0 = to_bgr(r0, converter)
            r0.Release()
        except Exception as e:
            print(f"[Cam 0] grab error: {e}")

        try:
            r1 = cam1.RetrieveResult(2000, pylon.TimeoutHandling_ThrowException)
            if r1.GrabSucceeded():
                frame1 = to_bgr(r1, converter)
            r1.Release()
        except Exception as e:
            print(f"[Cam 1] grab error: {e}")

        if frame0 is None:
            frame0 = np.zeros((args.side_h, args.side_w, 3), dtype=np.uint8)
            cv2.putText(frame0, "Cam 0: No signal", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        if frame1 is None:
            frame1 = np.zeros((args.side_h, args.side_w, 3), dtype=np.uint8)
            cv2.putText(frame1, "Cam 1: No signal", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        frame0 = cv2.resize(frame0, (args.side_w, args.side_h))
        frame1 = cv2.resize(frame1, (args.side_w, args.side_h))

        cv2.putText(frame0, "CAM 0", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        cv2.putText(frame1, "CAM 1", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        if args.separate:
            cv2.imshow("Camera 0", frame0)
            cv2.imshow("Camera 1", frame1)
        else:
            combined = np.hstack([frame0, frame1])
            cv2.imshow("Dual Camera Preview  [q / ESC to quit]", combined)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):  # 'q' or ESC
            break

    cv2.destroyAllWindows()
    for cam in cameras:
        if cam.IsGrabbing():
            cam.StopGrabbing()
        if cam.IsOpen():
            cam.Close()
    print("已關閉所有相機。")


if __name__ == "__main__":
    main()
