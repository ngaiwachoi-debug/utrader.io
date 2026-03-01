"use client"

// Re-export the root admin page so /en/admin and /zh/admin work (middleware rewrites /admin to locale-prefixed)
export { default } from "../../admin/page"
