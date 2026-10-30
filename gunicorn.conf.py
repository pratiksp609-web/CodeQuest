import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
worker_class = "gthread"
workers = int(os.environ.get("WEB_CONCURRENCY", 2))
threads = int(os.environ.get("GUNICORN_THREADS", 4))
timeout = 120  # compiling Java/Rust/Go can take several seconds
accesslog = "-"
errorlog = "-"
forwarded_allow_ips = "*"
