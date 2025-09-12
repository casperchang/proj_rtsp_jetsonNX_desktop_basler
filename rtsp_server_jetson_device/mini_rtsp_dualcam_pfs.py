# mini_rtsp_dualcam_pfs_v2.py — Dual Basler cams with PFS + forced color format (Jetson-friendly, crash-hardened)
import gi, argparse, os
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

'''
run this code working on Jetson Orin NX with two Basler cameras
command example:
    python mini_rtsp_dualcam_pfs.py --fps 60 --side_w 1024 --side_h 768 --bitrate 12000000 --pfs0 camera1_config_gray.pfs --pfs1 camera2_config_gray.pfs --force_format "GRAY8"
note:
    camera1_config_gray.pfs has been located in the same folder as this script.
'''


def build_cam_branch(idx: int, pfs_path: str, force_fmt: str, w: int, h: int, fps: int) -> str:
    """
    讓 PFS 掌控曝光/增益/ROI 等，但在 pylonsrc 後「立刻」強制成穩定格式（YUY2/BGRx）。
    不在這裡卡幀率（避免與相機實際輸出衝突），統一在 nvvidconv 後才標 framerate。
    """
    pfs_prop = f' pfs-location="{pfs_path}" ' if (pfs_path and os.path.exists(pfs_path)) else " "
    return (
        f" pylonsrc device-index={idx} " + pfs_prop +
        f"! video/x-raw,format={force_fmt} ! "               # ★ 關鍵：強制穩定色彩格式
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        f" nvvidconv ! video/x-raw,format=I420,width={w},height={h},framerate={fps}/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
    )

def main():
    parser = argparse.ArgumentParser(description="Dual Basler RTSP with PFS + forced format")
    parser.add_argument("--pfs0", type=str, default="color.pfs", help="PFS file for camera 0")
    parser.add_argument("--pfs1", type=str, default="color.pfs", help="PFS file for camera 1")
    parser.add_argument("--fps", type=int, default=60, help="Target FPS after resize (30 or 60)")
    parser.add_argument("--side_w", type=int, default=1024, help="Per-camera width after resize")
    parser.add_argument("--side_h", type=int, default=768, help="Per-camera height after resize")
    parser.add_argument("--bitrate", type=int, default=12000000, help="H.264 bitrate (bps)")
    parser.add_argument("--mount", type=str, default="/dualcam", help="RTSP mount point")
    parser.add_argument("--port", type=str, default="8554", help="RTSP TCP port")
    parser.add_argument("--force_format", type=str, default="YUY2", choices=["YUY2","BGRx", "GRAY8"],
                        help="Force color format right after pylonsrc (try BGRx if YUY2 crashes)")
    args = parser.parse_args()

    Gst.init(None)

    total_w = args.side_w * 2
    total_h = args.side_h
    fps     = args.fps

    cam0 = build_cam_branch(0, args.pfs0, args.force_format, args.side_w, args.side_h, fps) + " c.sink_0 "
    cam1 = build_cam_branch(1, args.pfs1, args.force_format, args.side_w, args.side_h, fps) + " c.sink_1 "

    launch = (
        "("
        + cam0 + cam1 +
        # 合成 → I420（CPU mem）→ NVMM/NV12 → 硬編 → parse → pay0
        f" compositor name=c sink_0::xpos=0 sink_1::xpos={args.side_w} ! "
        f" video/x-raw,format=I420,width={total_w},height={total_h},framerate={fps}/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        f" nvvidconv ! video/x-raw(memory:NVMM),format=NV12,width={total_w},height={total_h},framerate={fps}/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        f" nvv4l2h264enc bitrate={args.bitrate} insert-sps-pps=true iframeinterval={fps} "
        "                 maxperf-enable=1 preset-level=1 control-rate=1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " h264parse config-interval=1 ! "
        " rtph264pay name=pay0 pt=96 "
        ")"
    )

    server = GstRtspServer.RTSPServer(); server.set_service(args.port)
    factory = GstRtspServer.RTSPMediaFactory()
    factory.set_launch(launch); factory.set_shared(True)
    try:
        from gi.repository import GstRtspServer as R
        factory.set_suspend_mode(R.RTSPSuspendMode.NONE)
        factory.set_reusable(True)
    except Exception:
        pass

    mounts = server.get_mount_points()
    mounts.add_factory(args.mount, factory)
    server.attach(None)

    print(f"🎯 RTSP on: rtsp://0.0.0.0:{args.port}{args.mount}")
    if args.pfs0: print(f"   cam0 PFS: {args.pfs0} ({'found' if os.path.exists(args.pfs0) else 'NOT FOUND → ignored'})")
    if args.pfs1: print(f"   cam1 PFS: {args.pfs1} ({'found' if os.path.exists(args.pfs1) else 'NOT FOUND → ignored'})")
    print(f"   forced format: {args.force_format} | size: {args.side_w}x{args.side_h} @ {fps}fps | bitrate: {args.bitrate}")

    GLib.MainLoop().run()

if __name__ == "__main__":
    main()
