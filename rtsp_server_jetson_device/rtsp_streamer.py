import gi, os, sys, glob
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

def must_make(factory, name):
    el = Gst.ElementFactory.make(factory, name)
    if el is None:
        print(f"❌ could not create element: {factory} (name={name})", file=sys.stderr)
        print("   GST_PLUGIN_PATH =", os.environ.get("GST_PLUGIN_PATH", ""))
        # 常見檢查：Basler 插件位置
        for path in ["/opt/pylon/lib64/gstreamer-1.0", "/opt/pylon5/lib64/gstreamer-1.0", "/opt/pylon6/lib64/gstreamer-1.0"]:
            if os.path.exists(path):
                so = glob.glob(os.path.join(path, "libgstpylonsrc*.so"))
                print(f"   check {path}: {'FOUND' if so else 'NO .so'} ->", so)
        sys.exit(1)
    return el

class DualCamRtspFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **props):
        super().__init__(**props)
        self.set_shared(True)
    def do_create_element(self, url):
        print("Client connected, creating GStreamer pipeline...")
        pipe = Gst.Pipeline.new("rtsp-pipeline")

        # 逐一建立（若缺會立即報哪個）
        source1 = must_make("pylonsrc", "source1")
        capsfilter1 = must_make("capsfilter", "capsfilter1")
        nvvidconv1 = must_make("nvvidconv", "nvvidconv1")
        scale_caps1 = must_make("capsfilter", "scalecaps1")

        source2 = must_make("pylonsrc", "source2")
        capsfilter2 = must_make("capsfilter", "capsfilter2")
        nvvidconv2 = must_make("nvvidconv", "nvvidconv2")
        scale_caps2 = must_make("capsfilter", "scalecaps2")

        compositor = must_make("compositor", "compositor")
        nvvidconv_main = must_make("nvvidconv", "nvvidconv_main")
        caps_i420 = must_make("capsfilter", "caps_i420")
        encoder = must_make("nvv4l2h264enc", "encoder")
        h264parse = must_make("h264parse", "h264parse")
        rtppay = must_make("rtph264pay", "pay0")

        # 若全部能建立成功，就到這裡為止，不繼續連線（只為了診斷）
        print("✅ All elements created successfully. (Next step: link them)")
        return pipe  # 先回空管線以避免後續干擾

class GstServer:
    def __init__(self):
        self.server = GstRtspServer.RTSPServer()
        self.server.set_service("8554")
        mounts = self.server.get_mount_points()
        mounts.add_factory("/dualcam", DualCamRtspFactory())
        self.server.attach(None)

def main():
    # 你若有自定義外掛路徑，先在這裡 export 再 init
    # os.environ["GST_PLUGIN_PATH"] = os.environ.get("GST_PLUGIN_PATH","") + ":/opt/pylon/lib64/gstreamer-1.0"
    Gst.init(None)
    server = GstServer()
    print("🎯 RTSP on: rtsp://0.0.0.0:8554/dualcam")
    GLib.MainLoop().run()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopping RTSP server...")
