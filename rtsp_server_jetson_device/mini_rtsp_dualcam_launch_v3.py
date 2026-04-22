# mini_rtsp_dualcam_launch_v3.py — dual cam, crash-hardened for Jetson + gst-rtsp-server
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
        # --- Cam0 branch → compositor.sink_0 ---
        " pylonsrc device-index=0 ! "
        " video/x-raw,format=YUY2,width=1600,height=1200,framerate=60/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " nvvidconv ! video/x-raw,format=I420,width=1024,height=768,framerate=60/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " c.sink_0 "
        " "
        # --- Cam1 branch → compositor.sink_1 ---
        " pylonsrc device-index=1 ! "
        " video/x-raw,format=YUY2,width=1600,height=1200,framerate=60/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " nvvidconv ! video/x-raw,format=I420,width=1024,height=768,framerate=60/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " c.sink_1 "
        " "
        # --- compositor + main chain ---
        " compositor name=c sink_0::xpos=0 sink_1::xpos=1024 ! "
        " video/x-raw,format=I420,width=2048,height=768,framerate=60/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " nvvidconv ! video/x-raw(memory:NVMM),format=NV12,width=2048,height=768,framerate=60/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " nvv4l2h264enc bitrate=10000000 insert-sps-pps=true iframeinterval=30 "
        "                 maxperf-enable=1 preset-level=1 control-rate=1 num-extra-surfaces=8 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " h264parse config-interval=1 ! "
        " rtph264pay name=pay0 pt=96 "
        ")"
    )
    factory.set_shared(True)
    # 關閉 suspend，避免「media not prepared」路徑
    try:
        from gi.repository import GstRtspServer as R
        factory.set_suspend_mode(R.RTSPSuspendMode.NONE)
        # 部分版本支援 reusable，可再提高穩定度
        factory.set_reusable(True)
    except Exception:
        pass

    mounts = server.get_mount_points()
    mounts.add_factory("/dualcam", factory)
    server.attach(None)

    print("🎯 RTSP on: rtsp://0.0.0.0:8554/dualcam")
    GLib.MainLoop().run()

if __name__ == "__main__":
    main()
