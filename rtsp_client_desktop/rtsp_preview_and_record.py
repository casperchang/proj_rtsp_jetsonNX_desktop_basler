#!/usr/bin/env python3
import gi, sys, signal, argparse
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import datetime

'''
use on my 5080 desktop with:
    conda env: kfe
    (make sure the rtsp server is running on the Jetson firstly)
    command: env -i   PATH=/usr/bin:/bin   GST_PLUGIN_SYSTEM_PATH=/usr/lib/x86_64-linux-gnu/gstreamer-1.0   GST_PLUGIN_PATH=/usr/lib/x86_64-linux-gnu/gstreamer-1.0   DISPLAY=:0   XDG_RUNTIME_DIR=/run/user/1000   /usr/bin/python3 rtsp_preview_and_record.py rtsp://192.168.0.62:8554/dualcam ignore.mp4 --segment-seconds 300
    terminate with Ctrl+C, the video files will be finalized properly
'''

def build_pipeline(rtsp_url: str, out_mp4: str, latency_ms: int, segment_secs: int | None, hwdec: str, keyword: str):
    # choose preview decoder
    if hwdec == "nv":
        decoder = "nvh264dec"
    elif hwdec == "cpu":
        decoder = "avdec_h264"
    else:
        decoder = None  # use decodebin (tries NV first if available)

    base = (
        f"rtspsrc location={rtsp_url} protocols=tcp "
        f"! rtpjitterbuffer latency={latency_ms} drop-on-latency=true "
        "! rtph264depay "
        "! h264parse disable-passthrough=true config-interval=1 "
        "! tee name=t "
    )

    # recording branch (no re-encode)
    if segment_secs and segment_secs > 0:
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        record = (
            "t. ! queue leaky=2 max-size-buffers=0 max-size-time=0 max-size-bytes=0 "
            " ! splitmuxsink name=sm "
            "     muxer-factory=mp4mux "
            f"     max-size-time={int(segment_secs*1e9)} "
            f"     location=\"{keyword}_{now_str}_%05d.mp4\" "
        )
    else:
        record = (
            "t. ! queue leaky=2 max-size-buffers=0 max-size-time=0 max-size-bytes=0 "
            " ! mp4mux faststart=true fragment-duration=1000 "
            f" ! filesink location=\"{out_mp4}\" sync=false "
        )

    # preview branch
    if decoder is None:
        preview = (
            "t. ! queue leaky=2 max-size-buffers=0 max-size-time=0 max-size-bytes=0 "
            " ! decodebin name=dec "
            " dec. ! videoconvert ! fpsdisplaysink video-sink=autovideosink text-overlay=true sync=false "
        )
    else:
        preview = (
            "t. ! queue leaky=2 max-size-buffers=0 max-size-time=0 max-size-bytes=0 "
            f" ! {decoder} ! videoconvert "
            " ! fpsdisplaysink video-sink=autovideosink text-overlay=true sync=false "
        )

    return Gst.parse_launch(base + record + preview)

def main():
    ap = argparse.ArgumentParser(description="RTSP preview + record (remux MP4; optional segmenting)")
    ap.add_argument("rtsp_url", help="rtsp://<JETSON_IP>:8554/dualcam")
    ap.add_argument("output", help="Output MP4 (ignored if --segment-seconds > 0)")
    ap.add_argument("--latency", type=int, default=200, help="JitterBuffer latency ms")
    ap.add_argument("--segment-seconds", type=int, default=0, help="Rotate files every N seconds (splitmuxsink)")
    ap.add_argument("--hwdec", choices=["auto", "nv", "cpu"], default="auto", help="Preview decode: auto/nv/cpu")
    ap.add_argument("--keyword", type=str, default="mice", help="Prefix keyword for output segment files")
    args = ap.parse_args()

    Gst.init(None)
    pipeline = build_pipeline(
        args.rtsp_url,
        args.output,
        args.latency,
        args.segment_seconds,
        args.hwdec if args.hwdec != "auto" else "auto",
        args.keyword
    )

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    loop = GLib.MainLoop()

    def on_msg(bus, msg):
        t = msg.type
        if t == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print("❌ ERROR:", err, "\n   debug:", dbg)
            try: pipeline.send_event(Gst.Event.new_eos())
            except Exception: pass
            loop.quit()
        elif t == Gst.MessageType.EOS:
            print("✅ EOS received; finalizing.")
            loop.quit()

    bus.connect("message", on_msg)

    def handle_sigint(sig, frame):
        print("\n⏹️  Ctrl+C → EOS to finalize file(s)…")
        try: pipeline.send_event(Gst.Event.new_eos())
        except Exception: pass

    signal.signal(signal.SIGINT, handle_sigint)

    mode = "segments" if args.segment_seconds and args.segment_seconds > 0 else "single file"
    print(f"🎥 preview + recording ({mode}) from {args.rtsp_url} → {args.output}")
    print(f"   transport=TCP | latency={args.latency} ms | hwdec={args.hwdec} | keyword={args.keyword}")

    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    finally:
        pipeline.set_state(Gst.State.NULL)

if __name__ == "__main__":
    main()
