// Single source of truth for the backend base URL.
// Override via VITE_API_BASE when deploying.
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
