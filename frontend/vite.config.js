import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In dev, /api is proxied to the FastAPI backend so the client can use relative URLs.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
    },
  },
});
