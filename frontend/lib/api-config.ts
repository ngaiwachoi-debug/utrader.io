// Always use same-origin proxy so Next.js rewrites to backend (port from BACKEND_PORT in .env.local, default 8000).
// This avoids CORS and ensures frontend connects after theme or env changes.
export const API_BASE = "/api-backend"
