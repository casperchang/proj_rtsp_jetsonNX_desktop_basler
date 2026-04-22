# mini_rtsp_onecam_launch_v2.py — VLC-friendly (no suspend + queues + NVMM/NV12)
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

def main():
    Gst.init(None)

    server = GstRtspServer.RTSPServer()
    server.set_service("8554")

    factory = GstRtspServer.RTSPMediaFactory()
    factory.set_launch(
        "("
        " pylonsrc device-index=0 ! "
        " video/x-raw,format=YUY2,width=1600,height=1200,framerate=30/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " nvvidconv ! "
        " video/x-raw(memory:NVMM),format=NV12,width=1280,height=720,framerate=30/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " nvv4l2h264enc bitrate=8000000 insert-sps-pps=true iframeinterval=30 maxperf-enable=1 preset-level=1 ! "
        " h264parse config-interval=1 ! "
        " rtph264pay name=pay0 pt=96 "
        ")"
    )
    factory.set_shared(True)
    # 🔧 Critical for VLC: avoid suspend/resume races
    factory.set_suspend_mode(GstRtspServer.RTSPSuspendMode.NONE)
    # Optional: allow reusing same media across clients
    try:
        factory.set_reusable(True)
    except Exception:
        pass  # not available on some versions

    mounts = server.get_mount_points()
    mounts.add_factory("/cam0", factory)
    server.attach(None)

    print("🎯 RTSP on: rtsp://0.0.0.0:8554/cam0")
    GLib.MainLoop().run()

if __name__ == "__main__":
    main()
