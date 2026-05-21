"""
SqueezeOS launcher — ensures the project root is on sys.path before
importing core.app, so PM2 can launch with `python run.py` from any cwd.
"""
import sys
import os

# Force project root onto path so `from core.xxx import ...` resolves
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Also set PYTHONPATH env so any subprocess picks it up
os.environ.setdefault("PYTHONPATH", ROOT)

# Now run the Flask app
from core.app import create_app

if __name__ == "__main__":
    import ssl
    app = create_app()
    port = int(os.environ.get("PORT", 8182))

    cert_file = os.path.join(ROOT, "domain.cert.pem")
    key_file  = os.path.join(ROOT, "private.key.pem")
    ssl_ctx   = None

    force_ssl = os.environ.get("FORCE_SSL", "false").lower() == "true"
    if force_ssl and os.path.exists(cert_file) and os.path.exists(key_file):
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(cert_file, key_file)

    app.run(host="0.0.0.0", port=port, debug=False, threaded=True, ssl_context=ssl_ctx)
