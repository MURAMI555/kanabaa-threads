# Render の Start Command は gunicorn app:app。workers は1（スケジューラを二重に動かさないため）
workers = 1
threads = 4
timeout = 120
keepalive = 5
