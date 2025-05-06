#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app
mkdir -p "$APP_DIR"
cd "$APP_DIR"
python3 -m venv venv
sudo chown -R ec2-user:ec2-user "$APP_DIR"
su - ec2-user -c "source $APP_DIR/venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"