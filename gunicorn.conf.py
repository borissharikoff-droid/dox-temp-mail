"""Gunicorn production config for Railway."""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = 2
timeout = 60
max_requests = 1000
max_requests_jitter = 50
preload_app = False
accesslog = "-"
errorlog = "-"
loglevel = "info"
