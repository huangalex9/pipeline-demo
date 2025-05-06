#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app

# Load the OpenAI API key into this (ec2-user) shell
[ -f /etc/profile.d/openai.sh ]      && source /etc/profile.d/openai.sh
[ -f /etc/profile.d/chatgpt_env.sh ] && source /etc/profile.d/chatgpt_env.sh

cd "$APP_DIR"
source venv/bin/activate

# Bind to 0.0.0.0:8000 so the load balancer or SG can reach it
nohup gunicorn -w 3 -b 0.0.0.0:8000 app:app > gunicorn.log 2>&1 &