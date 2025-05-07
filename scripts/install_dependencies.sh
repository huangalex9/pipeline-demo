#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app
mkdir -p "$APP_DIR"
cd "$APP_DIR"

python3 -m venv venv
chown -R ec2-user:ec2-user "$APP_DIR"

# ── system packages (FFmpeg for video thumbnails) ───────────────
# Amazon Linux 2 has FFmpeg in EPEL; enable & install in one go.
sudo yum -y install epel-release
sudo yum -y install ffmpeg

# ── Python dependencies ─────────────────────────────────────────
sudo -u ec2-user bash -c "
  source /home/ec2-user/app/venv/bin/activate
  pip install --upgrade pip
  if [ -f /home/ec2-user/app/requirements.txt ]; then
    pip install -r /home/ec2-user/app/requirements.txt
  fi
"
