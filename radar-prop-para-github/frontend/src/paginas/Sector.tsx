/* Mapa de valores y Captación: son las mismas pantallas de El Ojo de Dios (páginas aparte), dentro de la app.
   Le piden el token a esta ventana (window.__radarToken), así nunca queda guardado en ningún lado. */
export default function Sector({ cual }: { cual: "mercado" | "captacion" }) {
  return <iframe className="iframe-sector" title={cual === "mercado" ? "Mapa de valores" : "Captación"} src={`/sectores/${cual}.html`} />;
}
