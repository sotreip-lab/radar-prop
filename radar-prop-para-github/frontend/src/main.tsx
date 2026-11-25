import "@fontsource-variable/archivo/wdth.css";
import "./estilos.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { registerSW } from "virtual:pwa-register";
import App from "./App";
import { ApiError } from "./api";
import { BusquedaProvider } from "./busqueda";
import { SesionProvider } from "./sesion";
import { ToastProvider } from "./toast";

// Modo claro u oscuro: el que elija la persona en "Mi cuenta"; si no eligió, el del teléfono o la PC.
const tema = localStorage.getItem("rp_tema");
const oscuro = tema ? tema === "oscuro" : window.matchMedia("(prefers-color-scheme: dark)").matches;
document.documentElement.dataset.tema = oscuro ? "oscuro" : "claro";

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (n, e) => n < 2 && !(e instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(e.estado)),
      refetchOnWindowFocus: true,
    },
  },
});

const actualizarSW = registerSW({
  onNeedRefresh() {
    // Hay una versión nueva de la app: se aplica sola la próxima vez que se abre, o ya mismo si la persona acepta.
    if (confirm("Hay una versión nueva de Radar Prop. ¿Actualizar ahora?")) actualizarSW(true);
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <SesionProvider>
        <ToastProvider>
          <BusquedaProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </BusquedaProvider>
        </ToastProvider>
      </SesionProvider>
    </QueryClientProvider>
  </StrictMode>,
);
