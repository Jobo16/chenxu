import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/static/dashboard/",
  plugins: [react()],
  build: {
    outDir: "../src/static/dashboard",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "assets/dashboard.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
  server: {
    proxy: {
      "/dashboard/api": "http://localhost:3000",
      "/dashboard/logout": "http://localhost:3000",
    },
  },
});
