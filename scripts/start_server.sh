#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app

for f in /etc/profile.d/*.sh; do [ -r "$f" ] && source "$f"; done

cd "$APP_DIR"
source venv/bin/activate

# 2 workers × 2 threads each, 4-min timeout
nohup gunicorn \
      -w 2 \
      -k gthread \
      --threads 2 \
      --worker-connections 20 \
      --timeout 240 \
      --graceful-timeout 30 \
      -b 0.0.0.0:8000 app:app > gunicorn.log 2>&1 &
