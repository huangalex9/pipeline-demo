#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app
mkdir -p "$APP_DIR"
cd "$APP_DIR"

python3 -m venv venv
sudo chown -R ec2-user:ec2-user "$APP_DIR"

# install as ec2-user so packages are writable later
sudo -u ec2-user bash -c "
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
"