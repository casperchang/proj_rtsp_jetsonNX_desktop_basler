import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib
import socket

# --- Test Configuration ---
FRAMERATE = 30
COMPOSITE_WIDTH = 2048
COMPOSITE_HEIGHT = 768
RTSP_PORT = "8554"
RTSP_MOUNT_POINT = "/dualcam"

class TestPatternRtspFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(TestPatternRtspFactory, self).__init__(**properties)
        self.set_shared(True)

    def do_create_element(self, url):
        print("Client connected, creating TEST PATTERN pipeline...")
        # This pipeline uses videotestsrc instead of pylonsrc
        pipeline_str = (
            f"videotestsrc pattern=ball is-live=true ! "
            f"video/x-raw,width=1024,height=768,framerate={FRAMERATE}/1 ! "
            f"queue ! comp.sink_0 "
            
            f"videotestsrc pattern=smpte is-live=true ! "
            f"video/x-raw,width=1024,height=768,framerate={FRAMERATE}/1 ! "
            f"queue ! comp.sink_1 "

            f"compositor name=comp sink_0::xpos=0 sink_0::ypos=0 sink_1::xpos=1024 sink_1::ypos=0 ! "
            f"nvvidconv ! nvv4l2h264enc bitrate=8000000 ! "
            f"rtph264pay name=pay0 pt=96 "
        )
        print(f"Launching pipeline: {pipeline_str}")
        return Gst.parse_launch(pipeline_str)

class GstServer():
    def __init__(self):
        self.server = GstRtspServer.RTSPServer()
        self.server.set_service(RTSP_PORT)
        factory = TestPatternRtspFactory()
        mount_points = self.server.get_mount_points()
        mount_points.add_factory(RTSP_MOUNT_POINT, factory)
        self.server.attach(None)
        
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: s.connect(('10.255.255.255', 1)); IP = s.getsockname()[0]
        except Exception: IP = '127.0.0.1'
        finally: s.close()
        print(f"✅ Test RTSP server ready. Stream available at: rtsp://{IP}:{RTSP_PORT}{RTSP_MOUNT_POINT}")

def main():
    Gst.init(None)
    server = GstServer()
    loop = GLib.MainLoop()
    try: loop.run()
    except KeyboardInterrupt: print("\nStopping RTSP server...")

if __name__ == '__main__':
    main()