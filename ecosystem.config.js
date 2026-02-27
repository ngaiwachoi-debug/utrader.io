/**
 * PM2 ecosystem config: run uTrader backend (uvicorn) persistently.
 * The 09:40 UTC gross-profit snapshot and 10:15 UTC token deduction run in-process;
 * no separate cron needed. Restart on crash; load .env from project root.
 *
 * Usage:
 *   pm2 start ecosystem.config.js
 *   pm2 save && pm2 startup   # persist across reboots (Linux/macOS)
 */
module.exports = {
  apps: [
    {
      name: "utrader-api",
      cwd: __dirname,
      script: "python",
      args: "-m uvicorn main:app --host 0.0.0.0 --port 8000",
      interpreter: "none",
      env: { NODE_ENV: "production" },
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 5000,
      autorestart: true,
      watch: false,
    },
  ],
};
