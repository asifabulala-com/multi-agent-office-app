import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/",
  plugins: [react()],
  server: {
    proxy: {
      "/run-sync": "http://localhost:8000",
      "/status": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/project": "http://localhost:8000",
      "/interactions": "http://localhost:8000",
      "/reset": "http://localhost:8000",
    },
  },
});
