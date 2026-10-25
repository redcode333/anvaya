import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY come from the repo-root .env; only VITE_* names reach the bundle.
  envDir: "..",
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:5000" } },
});
