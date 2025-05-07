#!/bin/bash
set -e
APP_DIR=/home/ec2-user/app
mkdir -p "$APP_DIR"
cd "$APP_DIR"

python3 -m venv venv
chown -R ec2-user:ec2-user "$APP_DIR"

# ── Install FFmpeg ───────────────────────────────────────────────
install_ffmpeg_pkg() {
  if command -v dnf &>/dev/null; then
    # Amazon Linux 2023
    sudo dnf -y install 'dnf-command(config-manager)'
    sudo dnf config-manager --set-enabled crb
    sudo dnf -y install ffmpeg || return 1
  elif command -v yum &>/dev/null; then
    # Amazon Linux 2
    if command -v amazon-linux-extras &>/dev/null; then
      sudo amazon-linux-extras enable ffmpeg4 -y
      sudo yum clean metadata
    fi
    sudo yum -y install ffmpeg || return 1
  fi
}

install_ffmpeg_static() {
  echo "Falling back to static FFmpeg build..."
  cd /usr/local/bin
  curl -L -o ffmpeg.tar.xz \
    https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
  tar -xf ffmpeg.tar.xz --strip-components=1 ffmpeg-*/ffmpeg ffmpeg-*/ffprobe
  rm ffmpeg.tar.xz
  chmod +x ffmpeg ffprobe
  cd "$APP_DIR"
}

if ! command -v ffmpeg &>/dev/null; then
  echo "Installing FFmpeg..."
  install_ffmpeg_pkg || install_ffmpeg_static
fi

# ── Python dependencies ──────────────────────────────────────────
sudo -u ec2-user bash -c "
  source $APP_DIR/venv/bin/activate
  pip install --upgrade pip
  if [ -f $APP_DIR/requirements.txt ]; then
    pip install -r $APP_DIR/requirements.txt
  fi
"
