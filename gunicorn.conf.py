import os
import multiprocessing

# ── Workers ──
# Formula: (2 × CPU cores) + 1  — optimal for I/O-bound Django
workers     = int(os.environ.get("WEB_CONCURRENCY", (multiprocessing.cpu_count() * 2) + 1))
worker_class = "gthread"   # threaded worker — better for 20k concurrent users than sync
threads     = 4            # 4 threads per worker

# ── Binding ──
bind        = f"0.0.0.0:{os.environ.get('PORT', 8000)}"

# ── Timeouts ──
timeout     = 120
keepalive   = 5
graceful_timeout = 30

# ── Logging ──
accesslog   = "-"
errorlog    = "-"
loglevel    = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)sµs'

# ── Reload (dev only) ──
reload      = os.environ.get("DJANGO_ENV") == "development"

# ── Max requests — prevents memory leaks on long-running workers ──
max_requests          = 1000
max_requests_jitter   = 100
