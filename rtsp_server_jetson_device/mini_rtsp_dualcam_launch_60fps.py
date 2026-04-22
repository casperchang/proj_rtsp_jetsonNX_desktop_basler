# mini_rtsp_dualcam_launch_60fps.py
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
        # Cam0 → compositor sink_0
        " pylonsrc device-index=0 ! "
        " video/x-raw,format=YUY2,width=1600,height=1200,framerate=60/1 ! "
        " nvvidconv ! video/x-raw,format=I420,width=1024,height=768,framerate=60/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " c.sink_0 "
        " "
        # Cam1 → compositor sink_1
        " pylonsrc device-index=1 ! "
        " video/x-raw,format=YUY2,width=1600,height=1200,framerate=60/1 ! "
        " nvvidconv ! video/x-raw,format=I420,width=1024,height=768,framerate=60/1 ! "
        " queue leaky=2 max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
        " c.sink_1 "
        " "
        # 拼接 + 硬編
        " compositor name=c sink_0::xpos=0 sink_1::xpos=1024 ! "
        " video/x-raw,format=I420,width=2048,height=768,framerate=60/1 ! "
        " nvvidconv ! video/x-raw(memory:NVMM),format=NV12,width=2048,height=768,framerate=60/1 ! "
        " nvv4l2h264enc bitrate=12000000 insert-sps-pps=true iframeinterval=60 maxperf-enable=1 preset-level=1 ! "
        " h264parse config-interval=1 ! "
        " rtph264pay name=pay0 pt=96 "
        ")"
    )
    factory.set_shared(True)
    try:
        factory.set_suspend_mode(GstRtspServer.RTSPSuspendMode.NONE)
    except Exception:
        pass

    mounts = server.get_mount_points()
    mounts.add_factory("/dualcam", factory)
    server.attach(None)

    print("🎯 RTSP on: rtsp://0.0.0.0:8554/dualcam")
    GLib.MainLoop().run()

if __name__ == "__main__":
    main()
