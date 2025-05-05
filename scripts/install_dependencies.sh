#!/bin/bash
set -e
ls
ls home
cd /home/ec2-user/app
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt