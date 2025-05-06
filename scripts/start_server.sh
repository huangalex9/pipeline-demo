#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app

# Load the OpenAI API key into this (ec2-user) shell
if [ -f /etc/profile.d/openai.sh ]; then
  source /etc/profile.d/openai.sh
fi

cd "$APP_DIR"
source venv/bin/activate

# Bind to 0.0.0.0:8000 so the load balancer or SG can reach it
nohup gunicorn -w 3 -b 0.0.0.0:8000 app:app > gunicorn.log 2>&1 &