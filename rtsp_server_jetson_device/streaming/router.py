# router.py
from flask import Blueprint, Response, render_template_string
from camera import DualCamera

config_path = "camera_setting.yaml"
camera = DualCamera(config_path=config_path)
router = Blueprint('router', __name__)

HTML_PAGE = '''
<html>
  <head>
    <title>雙鏡頭預覽</title>
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body {
        display: flex;
        flex-wrap: wrap;
        justify-content: space-around;
        align-items: center;
        padding: 20px;
        gap: 20px;
        background: #f0f0f0;
        font-family: sans-serif;
      }
      .camera-container {
        width: 1600px;
        height: 1200px;
        border: 2px solid #333;
        background: #000;
        overflow: hidden;
      }
      .camera-container img {
        width: 1600px;
        height: 1200px;
        object-fit: none;
        display: block;
      }
      .camera-wrapper {
        display: flex;
        flex-direction: column;
        align-items: center;
        width: 1600px;
      }
      .camera-wrapper p {
        margin-bottom: 8px;
        font-weight: bold;
        font-size: 16px;
      }
    </style>
  </head>
  <body>
    <div class="camera-wrapper">
        <p>相機1</p>
        <div class="camera-container">
            <img src="/video_feed1" />
        </div>
    </div>
    <div class="camera-wrapper">
        <p>相機2</p>
        <div class="camera-container">
            <img src="/video_feed2" />
        </div>
    </div>
    <script>
    </script>
  </body>
</html>
'''

@router.route('/')
def index():
    return render_template_string(HTML_PAGE)

@router.route('/video_feed1')
def video_feed1():
    def generate():
        while True:
            frame = camera.get_image(camera.camera1)
            if frame is None:
                break
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@router.route('/video_feed2')
def video_feed2():
    def generate():
        while True:
            frame = camera.get_image(camera.camera2)
            if frame is None:
                break
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

def cleanup():
    camera.release()
