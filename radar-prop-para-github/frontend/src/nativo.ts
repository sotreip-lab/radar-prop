// Ajustes para cuando la web corre dentro de la app de Android (Capacitor).
// En el navegador no hace nada. Dentro de la app:
//  - los links a otros sitios (avisos, WhatsApp) se abren en la app que corresponda del celular;
//  - las descargas (Excel, CSV) se guardan y se abre el menú "Compartir" para mandarlas o guardarlas;
//  - window.open() de páginas propias (fichas) se abre dentro de la misma app.

type Cap = {
  isNativePlatform?: () => boolean;
  Plugins?: Record<string, Record<string, (o: unknown) => Promise<unknown>>>;
  nativePromise?: (plugin: string, metodo: string, opciones: unknown) => Promise<unknown>;
};

const cap = (): Cap | undefined => (window as unknown as { Capacitor?: Cap }).Capacitor;

export const enApp = (): boolean => !!cap()?.isNativePlatform?.();

function llamar(plugin: string, metodo: string, opciones: unknown): Promise<unknown> {
  const c = cap();
  const p = c?.Plugins?.[plugin]?.[metodo];
  if (p) return p(opciones);
  if (c?.nativePromise) return c.nativePromise(plugin, metodo, opciones);
  return Promise.reject(new Error(`Falta ${plugin}.${metodo} en la app`));
}

function abrir(url: string) {
  const u = new URL(url, location.href);
  if (u.origin === location.origin) {
    location.href = u.href; // página propia (ficha, mapa de valores): dentro de la app
  } else {
    void llamar("AppLauncher", "openUrl", { url: u.href }); // WhatsApp, avisos: en la app del celular
  }
}

async function guardarYCompartir(href: string, nombre: string) {
  const blob = await (await fetch(href)).blob();
  const base64 = await new Promise<string>((ok, mal) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] || "");
    r.onerror = () => mal(r.error);
    r.readAsDataURL(blob);
  });
  const res = (await llamar("Filesystem", "writeFile", { path: nombre, data: base64, directory: "CACHE" })) as { uri: string };
  await llamar("Share", "share", { title: nombre, files: [res.uri], dialogTitle: "Guardar o mandar el archivo" });
}

export function prepararApp() {
  if (!enApp()) return;
  document.documentElement.classList.add("en-app");

  // window.open: devuelve una "ventana" mínima para el código que hace v.location.href = ... después
  window.open = ((url?: string | URL) => {
    if (url && String(url)) {
      abrir(String(url));
      return null;
    }
    return {
      location: { set href(u: string) { abrir(u); } },
      close() { /* nada que cerrar */ },
    } as unknown as Window;
  }) as typeof window.open;

  // links con target="_blank"
  document.addEventListener("click", (e) => {
    const a = (e.target as HTMLElement | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
    if (!a || a.download || a.target !== "_blank") return;
    e.preventDefault();
    abrir(a.href);
  }, true);

  // descargas armadas en el navegador (a.download + blob:)
  const clickOriginal = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function (this: HTMLAnchorElement) {
    if (this.download && this.href.startsWith("blob:")) {
      guardarYCompartir(this.href, this.download).catch((e) => alert("No se pudo guardar el archivo: " + (e as Error).message));
      return;
    }
    return clickOriginal.call(this);
  };
}
