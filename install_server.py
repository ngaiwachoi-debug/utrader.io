#!/usr/bin/env python3
"""
install_server.py

One-time installer for utrader.io on Ubuntu 22.04 (Alibaba ECS).

Actions:
- Install PostgreSQL (local)
- Create Postgres DB + user
- Create /opt/utrader.io/.env (if missing)
- Create systemd services for backend + worker
- Create Nginx vhost for lendfinex.com (HTTP only; you run certbot later)
"""

import os
import secrets
import subprocess
from pathlib import Path


def run(cmd: str, check: bool = True) -> None:
    print(f"\n>> {cmd}")
    subprocess.run(cmd, shell=True, check=check)


def prompt_default(prompt: str, default: str) -> str:
    val = input(f"{prompt} [{default}]: ").strip()
    return val or default


def main() -> None:
    if os.geteuid() != 0:
        print("ERROR: Please run this script as root, e.g. `sudo python3.11 install_server.py`")
        return

    print("=== utrader.io server installer ===")

    app_dir = prompt_default("App directory", "/opt/utrader.io")
    domain = prompt_default("Primary domain", "lendfinex.com")

    db_name = prompt_default("Postgres DB name", "utrader")
    db_user = prompt_default("Postgres DB user", "utrader")
    db_pass = input("Postgres DB password (leave blank to auto-generate): ").strip()
    if not db_pass:
        db_pass = secrets.token_urlsafe(16)
        print(f"Generated Postgres password: {db_pass}")

    nextauth_secret = input("NEXTAUTH_SECRET (paste your hex string or leave blank to fill later): ").strip()

    db_url = f"postgresql://{db_user}:{db_pass}@127.0.0.1:5432/{db_name}"
    print(f"\nUsing DATABASE_URL: {db_url}")

    # 1) Install PostgreSQL (idempotent)
    print("\n=== Installing PostgreSQL (if not already installed) ===")
    run("apt update")
    run("apt install -y postgresql postgresql-contrib", check=False)

    # 2) Create DB + user (idempotent)
    print("\n=== Configuring PostgreSQL ===")
    # create database if not exists
    run(
        f"sudo -u postgres psql -tAc \"SELECT 1 FROM pg_database WHERE datname='{db_name}'\" | "
        f"grep -q 1 || sudo -u postgres createdb {db_name}",
        check=False,
    )
    # create role if not exists
    run(
        f"sudo -u postgres psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='{db_user}'\" | "
        f"grep -q 1 || sudo -u postgres psql -c \"CREATE USER {db_user} WITH PASSWORD '{db_pass}';\"",
        check=False,
    )
    # ensure db owner
    run(f"sudo -u postgres psql -c \"ALTER DATABASE {db_name} OWNER TO {db_user};\"", check=False)

    # 3) Create .env if missing
    print("\n=== Creating / Updating .env ===")
    app_path = Path(app_dir)
    env_path = app_path / ".env"
    if env_path.exists():
        print(f"{env_path} already exists. I will NOT overwrite it. Edit it manually if needed.")
    else:
        env_template = f"""# Backend environment for utrader.io on lendfinex.com

# Local PostgreSQL
DATABASE_URL="{db_url}"

# Local Redis on this ECS
REDIS_URL="redis://127.0.0.1:6379/0"

# Google OAuth (fill with your real values)
GOOGLE_CLIENT_ID=""
GOOGLE_CLIENT_SECRET=""

# Admin email (for admin panel access)
ADMIN_EMAIL="your-admin@gmail.com"

# NextAuth configuration
NEXTAUTH_SECRET="{nextauth_secret}"
NEXTAUTH_URL="https://{domain}"

# Stripe (test or live; fill from Stripe Dashboard)
STRIPE_API_KEY=""
STRIPE_WEBHOOK_SECRET=""
STRIPE_PRICE_PRO_MONTHLY=""
# ... other STRIPE_PRICE_* as needed

# Encryption for API vault (32-byte hex)
ENCRYPTION_KEY=""

# Public API base for frontend
NEXT_PUBLIC_API_BASE="https://{domain}/api-backend"

# CORS
CORS_ORIGINS="https://{domain},https://www.{domain}"

# Other existing keys from your .env.example can be added here as needed.
"""
        env_path.write_text(env_template)
        os.chmod(env_path, 0o600)
        print(f"Created {env_path} (remember to fill GOOGLE_*, STRIPE_*, ENCRYPTION_KEY, etc.)")

    # 4) systemd units for backend + worker
    print("\n=== Creating systemd units ===")
    api_service_path = Path("/etc/systemd/system/bifinexbot-api.service")
    worker_service_path = Path("/etc/systemd/system/bifinexbot-worker.service")

    api_unit = f"""[Unit]
Description=Bifinexbot FastAPI
After=network.target redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory={app_dir}
Environment="PATH={app_dir}/venv/bin"
ExecStart={app_dir}/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

    worker_unit = f"""[Unit]
Description=Bifinexbot ARQ Worker
After=network.target redis-server.service bifinexbot-api.service

[Service]
Type=simple
User=root
WorkingDirectory={app_dir}
Environment="PATH={app_dir}/venv/bin"
ExecStart={app_dir}/venv/bin/python scripts/run_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""

    api_service_path.write_text(api_unit)
    worker_service_path.write_text(worker_unit)
    print(f"Wrote {api_service_path} and {worker_service_path}")

    # 5) Nginx vhost for lendfinex.com (HTTP only)
    print("\n=== Creating Nginx site config ===")
    nginx_site_path = Path("/etc/nginx/sites-available/utrader")
    nginx_conf = f"""server {{
    listen 80;
    server_name {domain} www.{domain};

    # API backend (FastAPI on 8000)
    location /api-backend/ {{
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    # Frontend (Next.js) on 3000 (optional)
    location / {{
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }}
}}
"""
    nginx_site_path.write_text(nginx_conf)
    enabled_link = Path("/etc/nginx/sites-enabled/utrader")
    if not enabled_link.exists():
        enabled_link.symlink_to(nginx_site_path)
    print(f"Wrote {nginx_site_path} and enabled it")

    # Test and reload Nginx
    run("nginx -t")
    run("systemctl reload nginx")

    # 6) Enable and start services
    print("\n=== Enabling and starting backend + worker ===")
    run("systemctl daemon-reload")
    run("systemctl enable bifinexbot-api bifinexbot-worker", check=False)
    run("systemctl start bifinexbot-api bifinexbot-worker", check=False)
    run("systemctl status bifinexbot-api --no-pager -l || true", check=False)
    run("systemctl status bifinexbot-worker --no-pager -l || true", check=False)

    print("\n=== DONE ===")
    print("Next steps:")
    print(f"- Edit {env_path} to fill GOOGLE_*, STRIPE_* and ENCRYPTION_KEY.")
    print(f"- Once DNS for {domain} works, run certbot for HTTPS, e.g.:")
    print(f"    sudo apt install -y certbot python3-certbot-nginx")
    print(f"    sudo certbot --nginx -d {domain} -d www.{domain}")
    print("- Ensure frontend (Next.js) is built and running on port 3000 if you are using it.")
    print("- Update Stripe Dashboard redirect/webhook URLs to https://{domain}/... when ready.")


if __name__ == "__main__":
    main()
