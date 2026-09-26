import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API URL is NOT configured here. It is read at build time from
// VITE_API_BASE_URL (see src/services/api.js), so no host is baked into code.
export default defineConfig({
  plugins: [react()],
});
