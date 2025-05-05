#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app
mkdir -p "$APP_DIR"
# CodeDeploy copied files here, but root owns them. Fix ownership so ec2-user can write.
sudo chown -R ec2-user:ec2-user "$APP_DIR"
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt