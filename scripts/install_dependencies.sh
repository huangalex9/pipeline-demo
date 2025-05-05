#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app
mkdir -p $APP_DIR
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt