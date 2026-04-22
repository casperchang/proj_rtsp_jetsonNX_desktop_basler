from flask import Flask
from router import router, cleanup
import signal
import sys

app = Flask(__name__)
app.register_blueprint(router)

def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
