from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "TradeGOD System is ALIVE and hunting!"

def run_server():
    # Render assigns a dynamic port via the PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    # Note: Flask's built-in server is fine for a simple health check ping
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    """Starts the Flask server in a background thread."""
    server = threading.Thread(target=run_server, daemon=True)
    server.start()
