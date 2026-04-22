# mini_rtsp_onecam.py  (Jetson-friendly: NVMM + NV12)
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

class OneCamFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self):
        super().__init__()
        self.set_shared(True)

    def do_create_element(self, url):
        # pylonsrc -> nvvidconv -> NVMM+NV12 -> nvv4l2h264enc -> h264parse -> rtph264pay(pay0)
        desc = (
            "pylonsrc device-index=0 ! "
            "video/x-raw,format=YUY2,width=1600,height=1200,framerate=30/1 ! "
            "nvvidconv ! "
            "video/x-raw(memory:NVMM),format=NV12,width=1280,height=720,framerate=30/1 ! "
            "nvv4l2h264enc bitrate=8000000 insert-sps-pps=true iframeinterval=30 maxperf-enable=1 ! "
            "h264parse config-interval=1 ! "
            "rtph264pay name=pay0 pt=96"
        )
        return Gst.parse_launch(desc)

def main():
    Gst.init(None)
    server = GstRtspServer.RTSPServer()
    server.set_service("8554")
    mounts = server.get_mount_points()
    mounts.add_factory("/cam0", OneCamFactory())
    server.attach(None)
    print("🎯 RTSP on: rtsp://0.0.0.0:8554/cam0")
    GLib.MainLoop().run()

if __name__ == "__main__":
    main()
