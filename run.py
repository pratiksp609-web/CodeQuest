"""Development server. For production use gunicorn (see gunicorn.conf.py)."""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # 127.0.0.1 keeps the debug server private to this computer. Set HOST=0.0.0.0 to open it on your network.
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1", host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", 5000)))
