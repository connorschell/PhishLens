# VPS provisioning and baseline hardening

**WBS 5.1** · PhishLens · Connor Schell · CYBR 498W

Host: DigitalOcean Basic droplet, Ubuntu 24.04 LTS, 1 vCPU / 2 GB / 50 GB, TOR1.
Created 2026-10-28. Public IPv4 **165.245.229.4** (private 10.118.0.2).

Every step here is run once, in order, on a fresh droplet. The point of writing
it down is that the server can be rebuilt from this file if it is ever lost.

---

## 1. First connection

```powershell
ssh root@165.245.229.4
```

Accept the host key fingerprint when prompted. If this refuses with a permission
error, the SSH key was not attached at creation and the droplet has to be
rebuilt with it.

## 2. Patch before anything else

```bash
apt update && apt upgrade -y
```

A fresh image is already behind by however long since it was published.

## 3. Create a non-root user

Running the stack as root means any flaw in any component is a flaw with full
control of the machine.

```bash
adduser --gecos "" phishlens
usermod -aG sudo phishlens
rsync --archive --chown=phishlens:phishlens ~/.ssh /home/phishlens
```

The `rsync` line copies the authorised key so the new user can log in with the
same key, with the right ownership.

Test it in a **second terminal**, before closing the first:

```powershell
ssh phishlens@165.245.229.4
sudo whoami      # must print: root
```

Keep the root session open until this works. Locking yourself out of a fresh
droplet is recoverable only through the provider's console.

## 4. Firewall

Default deny inbound, allow only what the project needs.

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp     # Let's Encrypt HTTP-01 challenge and the redirect to HTTPS
ufw allow 443/tcp    # the API and dashboard
ufw enable
ufw status verbose
```

Postgres on 5432 is deliberately absent. The database is reachable only from
inside the Docker network, never from the internet, which is the same decision
the local Compose file makes by binding to 127.0.0.1.

## 5. SSH hardening

Written as a drop-in rather than an edit to `sshd_config`. The main file is
locally modified by the provider image, so editing it again produces a conflict
prompt on every `openssh-server` upgrade. A drop-in avoids that, and the `00-`
prefix makes it win: OpenSSH takes the first occurrence of each keyword and
reads `sshd_config.d/` in alphabetical order.

```bash
ls -la /etc/ssh/sshd_config.d/

cat > /etc/ssh/sshd_config.d/00-phishlens-hardening.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
EOF
```

Check the config parses, confirm the values resolved, then restart:

```bash
sshd -t && echo "config OK"
sshd -T | grep -Ei "permitrootlogin|passwordauthentication|kbdinteractive"
systemctl restart ssh
```

`sshd -t` before restarting is what prevents a lockout. `sshd -T` prints the
*effective* configuration after all includes, which is the only reliable way to
know a setting took.

**Verify from a new terminal before closing the current one:**

```powershell
ssh phishlens@165.245.229.4          # must work
ssh root@165.245.229.4               # must now be refused
```

Everything after this point runs as `phishlens` with `sudo`.

## 6. Automatic security updates

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

A box that sits unpatched for six weeks while being the public face of a
security project is the wrong look.

## 7. Brute-force protection

```bash
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
sudo fail2ban-client status sshd
```

Key-only auth already makes SSH brute force pointless, so this is defence in
depth rather than the primary control.

## 8. Swap

2 GB of RAM is enough to run the stack and tight for building the image, which
compiles lxml and psycopg from source. Swap prevents the build being killed.

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

## 9. Docker

```bash
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker phishlens
```

Log out and back in for the group change to apply, then:

```bash
docker run --rm hello-world
```

## 10. Verification checklist

Run these before calling 5.1 done.

```bash
ufw status verbose                    # only 22, 80, 443 open
sudo sshd -T | grep -Ei "permitrootlogin|passwordauth"   # both no
free -h                               # swap present
docker compose version                # plugin installed
systemctl is-active fail2ban          # active
```

From your laptop:

```powershell
ssh root@165.245.229.4                         # must be refused
ssh phishlens@165.245.229.4                    # must succeed
```

---

## What this deliberately does not do

- **No Postgres port exposed.** The database is reachable only inside the Docker
  network.
- **No application deployed.** That is WBS 5.2 — Compose, Nginx, Let's Encrypt.
- **No secrets on the box yet.** `.env` for production is generated on the
  server in 5.2 and never copied from the laptop, so the development values
  never become production values.

## Record

| Item | Value |
|---|---|
| Provider | DigitalOcean |
| Plan | Basic, Regular SSD, 1 vCPU / 2 GB / 50 GB, $12/mo |
| Region | TOR1 (Toronto) |
| OS | Ubuntu 24.04 LTS x64 |
| Created | 2026-10-28 |
| Public IPv4 | 165.245.229.4 |
| Droplet name | ubuntu-s-1vcpu-2gb-tor1 |
| Admin user | phishlens (sudo, key-only) |
| Open ports | 22, 80, 443 |
