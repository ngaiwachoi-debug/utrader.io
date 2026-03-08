# Operations and deployment

## Bitfinex API Nonce & Redis

The Bitfinex API requires a strictly increasing nonce for authenticated requests. To prevent "10114 nonce: invalid" errors when both the web API and the worker process use the same API keys, a single, shared Redis instance is used to generate nonces.

**Configuration:**
- **`REDIS_URL`**: Used for ARQ queues, terminal logs, and (by default) Bitfinex nonces.
  - *Local*: `REDIS_URL=redis://127.0.0.1:6379`
  - *Upstash (Live)*: `REDIS_URL=rediss://default:PASSWORD@HOST.upstash.io:6379` (Note: if you accidentally use `redis://` for an `.upstash.io` URL, the backend will automatically upgrade it to `rediss://` for TLS)
- **`NONCE_REDIS_URL`** (Optional): If set, *only* the Bitfinex nonce (for both the API and worker) will use this URL. If not set, it falls back to `REDIS_URL`.

**Switching between Local and Upstash:**
You can switch between local Redis and Upstash Redis at any time without code changes. Just update `REDIS_URL` (or `NONCE_REDIS_URL`) in your `.env` file and restart both the backend and the worker. Both will use the same Redis configuration and generate a single monotonic stream of nonces for Bitfinex.

## Response compression

### Frontend (Next.js)

In production, the Next.js frontend uses **default compression** for static assets and server-rendered responses. No extra configuration is required in `next.config.mjs`. Ensure production builds are used when deploying (`next build` / `next start`).

### Backend API (FastAPI)

The FastAPI app uses **Starlette GZipMiddleware**: responses with `Content-Length` ≥ 500 bytes and `Accept-Encoding: gzip` are compressed. Middleware is registered in `main.py` after CORS.

- **In production:** If you put a reverse proxy (e.g. nginx, a cloud load balancer) in front of the API, you can either:
  - Rely on the app’s GZipMiddleware (current setup), or
  - Disable app-level gzip and enable gzip (and optionally brotli) in the proxy for both API and frontend assets.
- For best bandwidth savings, ensure either the app or the proxy enables gzip for API responses; brotli can be added at the proxy for static assets if supported.

### Summary

| Layer   | Compression |
|--------|-------------|
| Next.js (production) | Default built-in compression for assets and SSG. |
| FastAPI API          | GZipMiddleware (responses ≥ 500 bytes when client sends `Accept-Encoding: gzip`). |
| Reverse proxy (optional) | Can add gzip/brotli for API and assets; document per environment. |
