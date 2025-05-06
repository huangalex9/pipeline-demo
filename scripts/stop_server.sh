#!/bin/bash
# Gracefully stop old Gunicorn processes (ignore if none running)
pkill gunicorn || true