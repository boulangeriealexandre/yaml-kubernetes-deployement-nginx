# How to start Podman Desktop (this machine)

Podman Desktop runs as a **development build from source** at `/home/figura/podman-desktop`.

## Start

```bash
su - figura -c 'export PATH=/opt/node24/bin:$PATH && export DISPLAY=:0 && export XAUTHORITY=/run/user/1000/.mutter-Xwaylandauth.* && cd /home/figura/podman-desktop && pnpm watch'
```

## What happens

- `pnpm watch` runs `scripts/watch.mjs`
- Vite builds the main process, preload scripts, UI, renderer, and extensions in watch mode
- Electron launches with `--remote-debugging-port=9223`
- Hot reload on file changes

## Environment

- Node.js: `/opt/node24/bin/node` (v24)
- Display: Wayland via XWayland (`DISPLAY=:0`, Xauth in `/run/user/1000/.mutter-Xwaylandauth.*`)
- Electron uses X11 via XWayland (not native Wayland)

## Troubleshooting

- **X auth error** ("Authorization required, but no authorization protocol specified"): The XAUTHORITY path changes on each login. Use the glob: `/run/user/1000/.mutter-Xwaylandauth.*`
- **Port 44875 already in use**: The AI Lab's built-in model server binds this port. Our custom llama-server-avx uses port 44876 instead (see `ai-models/HOWTO.md`)
- **Container start fails from CLI**: Use Podman Desktop GUI or `systemd-run` to start containers (polkit requires login session)



# How to start Podman Desktop (dev mode)

## One-liner (as root shell)

```bash
su - figura -c 'export PATH=/opt/node24/bin:$PATH && export DISPLAY=:0 && export XAUTHORITY=/run/user/1000/gdm/Xauthority && cd /home/figura/podman-desktop && pnpm watch'
```

## Prerequisites (one-time setup)

### 1. Fix chrome-sandbox permissions

```bash
chown root:root /home/figura/podman-desktop/node_modules/electron/dist/chrome-sandbox
chmod 4755 /home/figura/podman-desktop/node_modules/electron/dist/chrome-sandbox
```

### 2. Allow figura to access the X display

```bash
xhost +local:figura
```

### 3. Fix file ownership (if needed)

```bash
chown -R figura:figura /home/figura/podman-desktop
```

## Notes

- Node.js 24 is required (`/opt/node24/bin/node`, currently v24.19.0)
- The default system node is v22, which pnpm rejects
- `pnpm install` must be run with Node 24 in PATH
- Podman socket may need to be started separately: `podman system service --time=0 &`
