#!/bin/bash
set -e
cd /home/ec2-user/app
source venv/bin/activate
# Keep logs in the background & bind to 0.0.0.0:8000 (security‑group must allow 8000)
nohup gunicorn -w 3 -b 0.0.0.0:8000 app:app > gunicorn.log 2>&1 &