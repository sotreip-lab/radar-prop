import { defineConfig } from "@playwright/test";

// Necesita la API y la app corriendo (ver docs/pruebas.md). RADAR_E2E_URL, RADAR_E2E_USUARIO, RADAR_E2E_CLAVE.
export default defineConfig({
  testDir: "tests",
  timeout: 60_000,
  use: {
    baseURL: process.env.RADAR_E2E_URL || "http://127.0.0.1:5173",
    launchOptions: process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH, args: ["--no-sandbox"] } : {},
  },
  projects: [
    { name: "celular", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
    { name: "pc", use: { viewport: { width: 1440, height: 900 } } },
  ],
});
