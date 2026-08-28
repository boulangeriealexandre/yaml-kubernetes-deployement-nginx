# HOWTO — System maintenance, updates & hardening (this machine)

Everything done on this box, why, and how to redo/blow it back out. Machine: Ubuntu 26.04 VM (Ivy Bridge, AVX-only), KVM/libvirt NAT on `192.168.122.0/24`.

- Host gateway: `192.168.122.1`
- Hostname: `figura-Ubuntu-24-04-PC-Q35-ICH9-2009`
- Login users: `figura` (password) and `root` (password locked)

---

## 1. System package update (apt)

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get autoclean
sudo apt-get autoremove -y
```

- `update` refreshes the package indexes (extra repos: Docker, Mega, HashiCorp, Grafana, MS Edge, Broadcom Salt).
- `upgrade` applies security + regular updates. On this machine everything was already current.
- `autoclean` / `autoremove` delete stale `.deb` cache files and orphaned dependencies.

> Always run `update` first; otherwise `upgrade` works against a stale index.

---

## 2. App "up to date" verification

```bash
# Git repos — compare local to upstream (0 ahead / 0 behind = in sync)
git -C /home/figura/llama.cpp      fetch && git -C /home/figura/llama.cpp      status -sb
git -C /home/figura/podman-desktop fetch && git -C /home/figura/podman-desktop status -sb

# Snaps
snap refresh --list

# apt / docker / podman versions
apt list --upgradable
docker --version && podman --version
```

### Python packages (system pip)
The machine's system Python is externally managed (PEP 668) and packages live in `/usr/local/lib/python3.14/dist-packages`. To upgrade them:

```bash
sudo pip3 install --break-system-packages -U <package>...
```

Caveats learned the hard way:
- **Skip `pip` itself** — it is apt-managed (`/usr/lib/python3/dist-packages`).
- **Skip apt-managed (Debian) packages** — pip cannot uninstall them ("no RECORD file"). They stay at the distro version; upgrading them belongs to `apt`, which already serves the latest. Detect with:
  ```bash
  dpkg -S /usr/lib/python3/dist-packages/<pkg>-*.dist-info
  ```
- Some upgrades need build deps because newer `pycairo`/`PyGObject` ship as source:
  ```bash
  sudo apt-get install -y libcairo2-dev libgirepository-1.0-dev libgirepository-2.0-dev
  ```
- A whole-list `pip install -U a b c …` **aborts on the first deb-managed package** (`Cannot uninstall … installed by debian`). Loop one-by-one and let failures skip:
  ```bash
  for p in pkg1 pkg2 ...; do sudo pip3 install --break-system-packages -U "$p" || echo "SKIP $p (apt-managed)"; done
  ```

### Currently shipped versions
node v22.22.1 (also v24.20.0 at `/opt/node24/bin`), npm 9.2, pnpm 11.23, go 1.26, python 3.14.4, gcc 15.2, cmake 4.2.3, git 2.53, docker 29.7.2 / docker-desktop 4.87, podman 5.7, VS Code 1.135.0, Firefox (snap) 154.0.1.

---

## 3. Cache & temp file cleanup

```bash
sudo rm -rf /tmp/* /var/tmp/*
rm -rf /home/figura/.cache/*
sudo rm -rf /root/.cache/{go-build,pnpm,electron,node,pip,mesa_shader_cache}
sudo apt-get clean                                   # /var/cache/apt
sudo journalctl --rotate && sudo journalctl --vacuum-time=7d
sudo rm -f /var/log/syslog.1 /var/log/syslog.[2-9].gz /var/log/kern.log.1 ...
sudo truncate -s 0 /var/log/syslog /var/log/kern.log
```

### ⚠️ The one thing you must NOT break: `/tmp/snap-private-tmp`
Snaps mount their private temp dirs under `/tmp/snap-private-tmp`. Wiping `/tmp/*` deletes it, and **every snap app breaks** with:

```
cannot create temporary directory for the root file system: No such file or directory
```

Recreate it (mode is defined in `/usr/lib/tmpfiles.d/snapd.conf` and is also auto-recreated at boot):

```bash
sudo mkdir -p /tmp/snap-private-tmp && sudo chmod 700 /tmp/snap-private-tmp
```

Affected on this box: Firefox, VS Code (both worked again immediately after the fix).

---

## 4. Health check fixes

### salt-master was failing
Symptoms: `SaltCacheError: key master.pem is not a valid key path` and `Permission denied` on `/etc/salt/pki/master`.

Two problems:
1. `master.pem` was a **symlink pointing outside the pki dir** — Salt's localfs cache rejects keys that resolve outside `pki_dir`. Fix: replace symlinks with real files:
   ```bash
   sudo rm -f /etc/salt/pki/master/master.pem /etc/salt/pki/master/master.pub
   sudo install -o salt -g salt -m 600 /etc/salt/pki/master-1.pem /etc/salt/pki/master/master.pem
   sudo install -o salt -g salt -m 644 /etc/salt/pki/master-1.pub /etc/salt/pki/master/master.pub
   ```
2. `/etc/salt/pki` was `root:root 750`, so the `salt` user (uid 997) could not traverse into it even to stat its own 700 key dir. Fix:
   ```bash
   sudo chgrp salt /etc/salt/pki && sudo chmod 750 /etc/salt/pki
   sudo systemctl restart salt-master   # => active
   ```

### openipmi was failing at every boot
The service loads IPMI drivers, but this VM has no IPMI hardware (`no /dev/ipmi*`). It can never succeed → disable + mask so it no longer appears as failed:

```bash
sudo systemctl disable --now openipmi
sudo systemctl mask openipmi
```

### General status commands
```bash
systemctl --failed
systemctl is-active salt-master salt-minion docker containerd
```

---

## 5. Podman Desktop (local dev build)

**Repo path:** `/home/figura/podman-desktop` — NOT `~/podman-desktop/podman-desktop` (no built binary; it runs from source).

**Launch Podman Desktop** (from a root shell; Wayland/XWayland session):

```bash
su - figura -c 'export PATH=/opt/node24/bin:$PATH && export DISPLAY=:0 && export XAUTHORITY=/run/user/1000/.mutter-Xwaylandauth.* && cd /home/figura/podman-desktop && pnpm watch'
```

- `pnpm watch` runs `scripts/watch.mjs` — Vite builds main/preload/UI/renderer/extensions in watch mode and launches Electron (`--remote-debugging-port=9223`).
- Requires Node 24 (`/opt/node24/bin`) on this machine.
- If launched as root, prefix `ELECTRON_DISABLE_SANDBOX=1`.
- The packaged binary (if a release build is ever wanted): `pnpm build && pnpm compile:current`.

---

## 6. Security audit & firewall (UFW)

### Audit findings
| Area | State |
|---|---|
| Login accounts | only `root` (pw locked) + `figura`; all service accounts locked |
| SSH | not running; `authorized_keys` empty |
| sudoers | stock (`use_pty`, `env_reset`); no stray UID-0 users |
| Auto security updates | `unattended-upgrades` enabled (daily) |
| AppArmor / snap | enforcing (164 profiles) |
| Docker | unix socket only (`-H fd://`), no TCP exposure |
| Setuid binaries | standard + `rust-coreutils` + Chromium/Electron sandboxes (all package-provided) |
| **Before hardening** | **UFW inactive; salt `:4505`, prometheus `:9090`, node-exporter `:9100` bound to `0.0.0.0`** |

### What was changed
UFW enabled with default-deny inbound. Only the hypervisor host (`192.168.122.1`) is allowed to the monitoring/admin ports; everything else inbound is dropped. Loopback is always allowed; outbound is allowed; ICMP echo stays allowed.

```bash
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from 192.168.122.1 to any port 4505,4506,9090,9100 proto tcp
sudo ufw allow in on lo
sudo ufw --force enable && sudo systemctl enable --now ufw
```

Verify:

```bash
sudo ufw status verbose
sudo iptables -L ufw-user-input -n -v
```

### Proof of blocking (black-box test)
Simulated an external host on the same subnet with a throwaway network namespace and confirmed external TCP to 9090/9100/4505 is dropped while localhost still works:

```bash
sudo ip netns add tsec
sudo ip link add vT type veth peer name vH
sudo ip link set vT netns tsec
sudo ip netns exec tsec ip addr add 192.168.122.201/24 dev vT
sudo ip netns exec tsec ip link set vT up
sudo ip addr add 192.168.122.202/24 dev vH && sudo ip link set vH up
sudo ip netns exec tsec ip route add 192.168.122.154 dev vT
# each attempt hangs/times out (DROP) — not refused:
sudo ip netns exec tsec timeout 4 bash -c 'echo > /dev/tcp/192.168.122.154/9090' && echo OPEN || echo BLOCKED
# cleanup
sudo ip link del vH; sudo ip netns del tsec
```

### Toggles
- Switch firewall off entirely: `sudo ufw disable`
- Allow a port for everyone: `sudo ufw allow <port>/tcp`
- Allow a port for one host: `sudo ufw allow from <ip> to any port <port> proto tcp`
- Block external ping: `sudo ufw deny icmp echo-request` (not applied — ICMP left allowed)

---

## 7. Network hardening (sysctl)

Standard IPv4 hardening, persisted in `/etc/sysctl.d/99-server-hardening.conf` (survives reboots):

```bash
sudo nano /etc/sysctl.d/99-server-hardening.conf   # see file below
sudo sysctl --system                               # apply now without reboot
```

```text
net.ipv4.tcp_syncookies = 1            # SYN flood protection (was already 1)
net.ipv4.conf.all.rp_filter = 1        # strict reverse-path filtering (was 2/loose)
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0 # ignore ICMP redirects
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0   # don't emit redirects (was 1)
net.ipv4.conf.default.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
```

Verify applied: `sysctl net.ipv4.conf.all.rp_filter net.ipv4.conf.all.send_redirects`

Caveat: strict `rp_filter=1` can interfere with Docker published ports. If container traffic misbehaves later, add `net.ipv4.conf.docker0.rp_filter = 0` on a line **below** the `all` setting.

---

## 8. ClamAV hardening

ClamAV was installed as *client + freshclam only*; `clamav-daemon` (1.5.3) was added and hardened. Signature DB updated (freshclam enabled + running, current at 28106).

### Config (`/etc/clamav/clamd.conf`)
Hardened values: `LocalSocketMode 660` (was 666), `MaxRecursion 10` (was 16). Everything else was already hardened by defaults: `User clamav`, `MaxScanTime 120000`, `MaxScanSize 100M`, `MaxFileSize 25M`, `MaxFiles 10000`, `MaxEmbeddedPE 10M`, `MaxScriptNormalize 5M`, `StreamMaxLength 25M`, `ScanArchive/PE/ELF/OLE2/PDF/SWF/HTML/Mail true`, `PhishingScanURLs true`. No TCP socket configured.

### Systemd unit — how it actually ended up
The packaged setup uses **socket activation** (`clamav-daemon.socket`), which **does not work** on this system (clamd aborts with `Not listening on any interfaces`, `No local AF_UNIX SOCK_STREAM socket received from systemd`). The daemon now runs standalone:

```bash
sudo systemctl mask clamav-daemon.socket
# full override, no socket dependency:
cat /etc/systemd/system/clamav-daemon.service   # see notes below
```

Effective hardened service directives (verified working):
```
NoNewPrivileges=true
RestrictAddressFamilies=AF_UNIX   # no TCP/IP at all
RestrictSUIDSGID=true
ProtectKernelTunables=true
ProtectControlGroups=true
```

> **Gotcha:** the mount-namespace directives from common guides — `PrivateTmp`, `ProtectHome`, `ProtectSystem=strict`, `PrivateDevices` — **break clamd** on this box: `PrivateTmp` shadows `/tmp` & `/var/tmp` (scans return ENOENT), `--fdpass` returns `Not a regular file`, and `ProtectSystem=strict` yields `Access denied`. The fdpass-by-path `Not a regular file` quirk persists under systemd even without them. Use the above working set. (Deals: daemon scans files it can read by path; for /home content use `clamscan` as the own user — the CLI is not daemon-confined.)

Socket is `660` `clamav:clamav`, unix-only; no `:3310` TCP in ufw or clamd.

### Access, quarantine, users
```bash
sudo install -d -o clamav -g clamav -m 700 /var/lib/clamav/quarantine
sudo usermod -aG clamav figura     # member of clamav group can talk to the socket
```
Quarantine instead of deleting: move detections into `/var/lib/clamav/quarantine` and review false positives before removal.

### Update & verify
```bash
sudo systemctl enable --now clamav-freshclam    # auto signature updates
sudo systemctl status clamav-daemon clamav-freshclam
sudo -u figura clamdscan /path/to/file          # daemon scan (path must be readable by clamav)
sudo -u figura clamscan /path/to/file           # direct scan, runs as the user — works for ~/ etc.
# official NOT-a-virus test file:
curl -L -o /tmp/eicar.com https://secure.eicar.org/eicar.com
sudo -u figura clamdscan /tmp/eicar.com         # expect: Eicar-Test-Signature FOUND
```
Symptom-free notes: the EICAR string hand-typed in a shell rarely matches the canonical file (hash `275a021b…`) — always fetch the official file for tests. ClamAV deliberately never scans inside its own database dir.

---

## 9. AI stack (for reference)

Full chain, rebuild steps, and troubleshooting live in:
- `/home/figura/ai-models/HOWTO.md`
- `/home/figura/ai-models/HOWTO-rebuild-llama-server.md`
- `/home/figura/ai-models/HOWTO-podman-desktop.md`

Containers are rootless under user `figura`; start them from the login session (polkit) with:
`bash /home/figura/ai-models/start-ai.sh`
