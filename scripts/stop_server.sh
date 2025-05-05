#!/bin/bash
# Gracefully stop any old Gunicorn processes (ignore if none)
pkill gunicorn || true