#!/bin/bash
set -e

# Target directory where CodeDeploy places the application
APP_DIR="/home/ec2-user/app"

# Ensure the directory exists and switch into it
mkdir -p "$APP_DIR"
cd "$APP_DIR"

# Create or reuse a Python virtual‑environment
python3 -m venv venv

# Give ec2-user full ownership so it can install packages
chown -R ec2-user:ec2-user "$APP_DIR"

# Install dependencies inside the venv *as ec2-user*
sudo -u ec2-user bash -c '
  source "$APP_DIR/venv/bin/activate"
  pip install --upgrade pip
  if [ -f requirements.txt ]; then
    pip install -r requirements.txt
  fi
'