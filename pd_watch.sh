#!/bin/bash
if [ "$(id -u)" = "0" ]; then
  echo "Do not run as root; run as the figura user (e.g. su figura -c '$0')."
  exit 1
fi
export PATH=/opt/node24/bin:$PATH
RUN_USER=$(id -u)
export XDG_RUNTIME_DIR=/run/user/$RUN_USER
export DISPLAY=:0
export XAUTHORITY=$(ls "$XDG_RUNTIME_DIR"/.mutter-Xwaylandauth.* 2>/dev/null | head -1)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
export HOME=/home/figura
export USER=figura
export LOGNAME=figura
export ELECTRON_DISABLE_SANDBOX=1

SOCK="$XDG_RUNTIME_DIR/podman/podman.sock"
socket_alive() {
  if command -v curl >/dev/null 2>&1; then
    curl -s --max-time 2 --unix-socket "$SOCK" http://d/version >/dev/null 2>&1
  else
    [ -S "$SOCK" ]
  fi
}
if ! socket_alive; then
  mkdir -p "$(dirname "$SOCK")"
  nohup podman system service --time=0 "unix://$SOCK" >> /home/figura/podman-service.log 2>&1 &
  for _ in $(seq 1 15); do
    socket_alive && break
    sleep 1
  done
fi

cd /home/figura/podman-desktop
exec pnpm watch >> /home/figura/podman-desktop-watch.log 2>&1
