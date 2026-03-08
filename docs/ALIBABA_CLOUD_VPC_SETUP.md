# Alibaba Cloud VPC + ECS Setup — Step-by-Step Guide

This guide walks you through deploying the bifinexbot/utrader stack on Alibaba Cloud using a **VPC** and **ECS**, with **Redis on the same server** (no separate Redis instance).

---

## Overview

- **VPC**: Private network where your ECS and (optionally) RDS live.
- **ECS**: One server that runs FastAPI (uvicorn), ARQ worker, and Redis. Optionally PostgreSQL and/or Node for the frontend.
- **Flow**: Create VPC → Create ECS in VPC → Install Redis + Python + app → Configure env → Run services.

---

## Step 1: Create a VPC

1. Log in to **Alibaba Cloud Console** → **VPC** (or search "VPC").
2. Go to **VPCs** → **Create VPC**.
3. Set:
   - **Name**: e.g. `bifinexbot-vpc`
   - **IPv4 CIDR**: e.g. `10.0.0.0/8` or `192.168.0.0/16` (default is fine).
   - **Description**: optional.
4. Under **Create vSwitch** (same form):
   - **Zone**: Pick one (e.g. Singapore Zone A).
   - **vSwitch CIDR**: e.g. `10.0.1.0/24` (must be within VPC CIDR).
   - **Name**: e.g. `bifinexbot-vsw`.
5. Click **OK**. Note your **VPC ID** and **vSwitch ID** — you’ll need them when creating ECS.

---

## Step 2: Create a Security Group (in the same region as the vSwitch)

1. In **VPC** console, go to **Security Groups** (or **ECS** → **Security Groups**).
2. **Create Security Group**:
   - **Name**: e.g. `bifinexbot-sg`
   - **VPC**: Select the VPC you created.
   - **Network Type**: VPC.
3. **Add rules** (Inbound):
   - **SSH**: Port 22, Source `0.0.0.0/0` (or your IP only for security).
   - **HTTP**: Port 80, Source `0.0.0.0/0` (for Nginx/Next.js).
   - **HTTPS**: Port 443, Source `0.0.0.0/0`.
   - **Custom (optional)**: Port 8000 if you want to hit the API directly before putting Nginx in front; otherwise leave closed and use Nginx only.
4. Save. Note the **Security Group ID**.

---

## Step 3: Create an ECS Instance (in the VPC)

1. **ECS** → **Instances** → **Create Instance** (or **Instance Creation Wizard**).
2. **Billing**: Subscription or Pay-As-You-Go.
3. **Region & Zone**: Same region as your vSwitch (e.g. Singapore, Zone A).
4. **Instance type**: e.g. **ecs.g6.large** (2 vCPU, 4 GiB) or **ecs.t6-c1m2.large** (2 vCPU, 2 GiB for minimal).
5. **Image**: **Ubuntu 22.04 LTS** (or Alibaba Linux 2).
6. **Storage**: System disk 40 GiB (or more); add data disk if needed.
7. **Network**:
   - **VPC**: Select the VPC from Step 1.
   - **vSwitch**: Select the vSwitch from Step 1.
   - **Public IP**: Assign (so you can SSH and serve traffic), or attach an **EIP** later.
   - **Security Group**: Select the security group from Step 2.
8. **Login**:
   - Set **root** or a new user **password**, or upload an **SSH key** (recommended).
9. **Instance name**: e.g. `bifinexbot-app`.
10. Create and wait until **Running**. Note **Public IP** (or bind EIP).

---

## Step 4: Connect to ECS (SSH)

From your laptop (PowerShell or bash):

```bash
ssh root@<PUBLIC_IP>
# or
ssh ubuntu@<PUBLIC_IP>
```

If you use a key:

```bash
ssh -i /path/to/your-key.pem root@<PUBLIC_IP>
```

---

## Step 5: Install Dependencies on ECS

Run on the ECS (Ubuntu 22.04):

```bash
# Update system
apt update && apt upgrade -y

# Python 3.10+, pip, venv
apt install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt update
apt install -y python3.11 python3.11-venv python3.11-dev build-essential

# Redis (server’s Redis — same machine)
apt install -y redis-server

# Optional: PostgreSQL (if DB on same server)
# apt install -y postgresql postgresql-contrib
# sudo -u postgres createuser -s your_app_user
# sudo -u postgres createdb -O your_app_user your_db
```

**Configure Redis to listen only on localhost** (default on many images):

```bash
# Edit Redis config
nano /etc/redis/redis.conf
# Ensure:
# bind 127.0.0.1
# (and optionally: maxmemory 256mb, maxmemory-policy allkeys-lru)

systemctl enable redis-server
systemctl start redis-server
systemctl status redis-server
```

---

## Step 6: Deploy Your Application Code

**Option A — Git (recommended)**

```bash
# Install git if needed
apt install -y git

# Clone (use your repo URL; consider deploy key for private repo)
cd /opt
git clone https://github.com/ngaiwachoi-debug/utrader.io.git
cd utrader.io
git checkout 2026-02-26-5ila-2ae8a   # or your branch
```

**Option B — Upload via SCP/SFTP**

From your laptop:

```bash
scp -r /path/to/buildnew root@<PUBLIC_IP>:/opt/utrader.io
```

Then on ECS:

```bash
cd /opt/utrader.io
```

---

## Step 7: Python Virtual Environment and Backend Dependencies

On ECS:

```bash
cd /opt/utrader.io
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Step 8: Environment Variables on the Server

Create `.env` in the project root (e.g. `/opt/utrader.io/.env`). Use your real values; below is a template matching `.env.example`:

```bash
nano /opt/utrader.io/.env
```

Minimum for backend + worker + **server’s Redis**:

```env
# Database (same ECS or RDS in VPC)
DATABASE_URL="postgresql://user:password@127.0.0.1:5432/dbname"
# If RDS in VPC: postgresql://user:password@<rds-private-ip>:5432/dbname?sslmode=require

# Redis on this server
REDIS_URL="redis://127.0.0.1:6379/0"

# Google OAuth
GOOGLE_CLIENT_ID="..."
GOOGLE_CLIENT_SECRET="..."

# Admin
ADMIN_EMAIL="your-admin@example.com"

# NextAuth (must match frontend)
NEXTAUTH_SECRET="your-base64-secret"
NEXTAUTH_URL="https://your-domain.com"

# Stripe (live keys in production)
STRIPE_API_KEY="sk_live_..."
STRIPE_WEBHOOK_SECRET="whsec_..."
STRIPE_PRICE_PRO_MONTHLY="price_..."
# ... other STRIPE_PRICE_* as in .env.example

# Encryption for API vault
ENCRYPTION_KEY="your-32-byte-hex"

# API base (for cron/callbacks; use public URL or internal)
NEXT_PUBLIC_API_BASE="https://api.your-domain.com"
# CORS
CORS_ORIGINS="https://your-domain.com,https://www.your-domain.com"
```

Save and restrict permissions:

```bash
chmod 600 /opt/utrader.io/.env
```

---

## Step 9: Run Backend and Worker (systemd)

Create two systemd units so the backend and worker start on boot and restart on failure.

**Backend (FastAPI):**

```bash
sudo nano /etc/systemd/system/bifinexbot-api.service
```

Contents:

```ini
[Unit]
Description=Bifinexbot FastAPI
After=network.target redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/utrader.io
Environment="PATH=/opt/utrader.io/venv/bin"
ExecStart=/opt/utrader.io/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Worker (ARQ):**

```bash
sudo nano /etc/systemd/system/bifinexbot-worker.service
```

Contents:

```ini
[Unit]
Description=Bifinexbot ARQ Worker
After=network.target redis-server.service bifinexbot-api.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/utrader.io
Environment="PATH=/opt/utrader.io/venv/bin"
ExecStart=/opt/utrader.io/venv/bin/python scripts/run_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable bifinexbot-api bifinexbot-worker
sudo systemctl start bifinexbot-api bifinexbot-worker
sudo systemctl status bifinexbot-api bifinexbot-worker
```

Check logs:

```bash
journalctl -u bifinexbot-api -f
journalctl -u bifinexbot-worker -f
```

---

## Step 10: Frontend (Next.js) — Optional on Same ECS

If you run the frontend on the same ECS:

```bash
# Install Node 18+ (e.g. via NodeSource)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
apt install -y nodejs

cd /opt/utrader.io/frontend
cp .env.example .env.local
# Edit .env.local: NEXT_PUBLIC_API_BASE, NEXTAUTH_URL, NEXTAUTH_SECRET
npm ci
npm run build
# Run with PM2 or systemd
npm run start   # listens on 3000 by default
```

Or serve the built output with **Nginx** (recommended for production):

- Build on the server (or in CI) then point Nginx `root` to `frontend/out` (if static export) or proxy to `http://127.0.0.1:3000` if using `next start`.

---

## Step 11: Nginx Reverse Proxy (Recommended)

Install Nginx and proxy to the API (and optionally to the Next.js app):

```bash
apt install -y nginx
```

Example config (adjust domain and paths):

```bash
sudo nano /etc/nginx/sites-available/bifinexbot
```

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # If Next.js on same server
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/bifinexbot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## Step 12: SSL (HTTPS) with Let’s Encrypt

```bash
apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

Follow prompts. Certbot will update Nginx for HTTPS.

---

## Step 13: Database — Same ECS vs RDS in VPC

- **Same ECS**: If you installed PostgreSQL in Step 5, create DB and user, set `DATABASE_URL` to `postgresql://user:pass@127.0.0.1:5432/dbname`. Run migrations from the app directory: `source venv/bin/activate && alembic upgrade head` (or your migration command).
- **RDS in VPC**: Create **ApsaraDB RDS for PostgreSQL** in the **same VPC** and vSwitch. Allow ECS security group in RDS whitelist. Set `DATABASE_URL` to the RDS **private** endpoint. No public DB access needed.

---

## Step 14: Firewall (Security Group) Check

- Ports **22, 80, 443** open to the internet (or to your IP only for 22).
- Port **8000** only if you expose the API directly; otherwise Nginx handles it.
- **Redis** should not be exposed (bind 127.0.0.1 only; no security group rule for 6379 from internet).

---

## Quick Reference

| Item        | Value / Command |
|------------|------------------|
| VPC        | Create in console; note VPC ID and vSwitch ID. |
| ECS        | Create in that VPC; note public IP or EIP. |
| Redis      | `redis://127.0.0.1:6379/0` on same ECS. |
| Backend    | `uvicorn main:app --host 0.0.0.0 --port 8000` (or systemd). |
| Worker     | `python scripts/run_worker.py` (or systemd). |
| Env file   | `/opt/utrader.io/.env` (see Step 8). |
| Logs       | `journalctl -u bifinexbot-api -f` and `-u bifinexbot-worker -f`. |

---

## Troubleshooting

- **502 Bad Gateway**: Backend not running or wrong port; check `systemctl status bifinexbot-api` and Nginx `proxy_pass` port.
- **Worker not processing jobs**: Check `REDIS_URL` and that Redis is running (`redis-cli ping` → `PONG`). Check `journalctl -u bifinexbot-worker`.
- **DB connection failed**: Check `DATABASE_URL`, security group (if RDS), and that DB is running.
- **Stripe webhooks**: Use your **public** HTTPS URL (e.g. `https://your-domain.com/api/webhook/stripe`) and the correct `STRIPE_WEBHOOK_SECRET` for that endpoint.

For more on env vars, see project root **.env.example** and **frontend/.env.example**.
