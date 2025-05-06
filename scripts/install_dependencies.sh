#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app
mkdir -p "$APP_DIR"
cd "$APP_DIR"

python3 -m venv venv
chown -R ec2-user:ec2-user "$APP_DIR"

# Install deps as ec2-user
sudo -u ec2-user bash -c "
  source /home/ec2-user/app/venv/bin/activate
  pip install --upgrade pip
  if [ -f /home/ec2-user/app/requirements.txt ]; then
    pip install -r /home/ec2-user/app/requirements.txt
  fi
"