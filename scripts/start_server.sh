#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app

# Ensure the OpenAI API key is in the environment for this non‑login shell
if [ -f /etc/profile.d/openai.sh ]; then
  sudo bash /etc/profile.d/openai.sh
fi

cd "$APP_DIR"
source venv/bin/activate
# Bind to 0.0.0.0:8000 so the load balancer or SG can reach it
nohup gunicorn -w 3 -b 0.0.0.0:8000 app:app > gunicorn.log 2>&1 &
```bash
#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app
cd "$APP_DIR"
source venv/bin/activate
# Bind to 0.0.0.0:8000 so the load balancer or SG can reach it
nohup gunicorn -w 3 -b 0.0.0.0:8000 app:app > gunicorn.log 2>&1 &