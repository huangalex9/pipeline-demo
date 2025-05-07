#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app
mkdir -p "$APP_DIR"
cd "$APP_DIR"

python3 -m venv venv
chown -R ec2-user:ec2-user "$APP_DIR"

# ── Install FFmpeg ───────────────────────────────────────────────
# • AL2023 → dnf has ffmpeg in the main repo.
# • AL2    → yum needs EPEL first; enable if amazon-linux-extras exists.

if command -v dnf &>/dev/null; then
  # Amazon Linux 2023
  sudo dnf -y install ffmpeg
elif command -v yum &>/dev/null; then
  # Amazon Linux 2
  if command -v amazon-linux-extras &>/dev/null; then
    sudo amazon-linux-extras enable epel -y
    sudo yum clean metadata
  fi
  sudo yum -y install ffmpeg
fi

# ── Python dependencies ──────────────────────────────────────────
sudo -u ec2-user bash -c "
  source /home/ec2-user/app/venv/bin/activate
  pip install --upgrade pip
  if [ -f /home/ec2-user/app/requirements.txt ]; then
    pip install -r /home/ec2-user/app/requirements.txt
  fi
"
