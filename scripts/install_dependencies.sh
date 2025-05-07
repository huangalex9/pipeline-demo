#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app
mkdir -p "$APP_DIR"
cd "$APP_DIR"

python3 -m venv venv
chown -R ec2-user:ec2-user "$APP_DIR"

# ── system packages ────────────────────────────────────────────────
# Detect package manager and install ffmpeg the right way
if command -v yum &>/dev/null; then
  # Amazon Linux 2
  sudo amazon-linux-extras enable epel -y
  sudo yum clean metadata
  sudo yum -y install ffmpeg
elif command -v dnf &>/dev/null; then
  # Amazon Linux 2023 uses dnf
  sudo dnf -y install ffmpeg
fi

# ── Python dependencies ────────────────────────────────────────────
sudo -u ec2-user bash -c "
  source /home/ec2-user/app/venv/bin/activate
  pip install --upgrade pip
  if [ -f /home/ec2-user/app/requirements.txt ]; then
    pip install -r /home/ec2-user/app/requirements.txt
  fi
"
