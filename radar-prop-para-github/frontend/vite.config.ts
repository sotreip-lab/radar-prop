import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// En desarrollo, /api va a la API local. En producción, Netlify reenvía /api/* al servidor (ver public/_redirects).
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "prompt",
      includeAssets: ["icono.svg", "static/*"],
      manifest: {
        name: "Radar Prop",
        short_name: "Radar Prop",
        description: "Búsqueda de propiedades de Bahía Blanca para el equipo de Guillermo Badenheuer Inmobiliaria",
        lang: "es-AR",
        start_url: "/",
        display: "standalone",
        background_color: "#14243F",
        theme_color: "#14243F",
        icons: [
          { src: "icono-192.png", sizes: "192x192", type: "image/png" },
          { src: "icono-512.png", sizes: "512x512", type: "image/png" },
          { src: "icono-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // Se guarda la interfaz para que abra al instante. Los datos (/api) nunca se sirven viejos sin avisar.
        navigateFallbackDenylist: [/^\/api\//, /^\/f\//],
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/[abc]\.tile\.openstreetmap\.org\//,
            handler: "CacheFirst",
            options: { cacheName: "mapa", expiration: { maxEntries: 800, maxAgeSeconds: 30 * 86400 } },
          },
        ],
      },
    }),
  ],
  server: { proxy: { "/api": "http://127.0.0.1:8000", "/f/": "http://127.0.0.1:8000" } },
  build: { chunkSizeWarningLimit: 900 },
});
