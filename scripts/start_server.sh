#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app

# ---- bring env-vars into this ec2-user shell -----------------------------
[ -f /etc/profile.d/openai.sh ]      && source /etc/profile.d/openai.sh
[ -f /etc/profile.d/chatgpt_env.sh ] && source /etc/profile.d/chatgpt_env.sh
[ -f /etc/profile.d/budget.sh ]      && source /etc/profile.d/budget.sh   # <-- NEW

cd "$APP_DIR"
source venv/bin/activate

# ---- run the server ------------------------------------------------------
nohup gunicorn -w 3 -b 0.0.0.0:8000 app:app > gunicorn.log 2>&1 &
