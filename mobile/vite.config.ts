import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

const shop = process.env.VITE_SHOP_URL || "http://127.0.0.1:8787";

const apiPaths = [
  "/health",
  "/version",
  "/people",
  "/session",
  "/ros",
  "/messages",
  "/shifts",
  "/assigned",
  "/advisor",
  "/parts",
  "/events",
  "/technicians",
  "/advisors",
  "/push",
];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5174,
    proxy: Object.fromEntries(
      apiPaths.map((p) => [p, { target: shop, changeOrigin: true }]),
    ),
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
