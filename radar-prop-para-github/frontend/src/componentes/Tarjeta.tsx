import { fmt, fmtK, PLAT_CORTO, PLAT_NOM, sim } from "../formato";
import type { Item } from "../tipos";

export default function Tarjeta({ it, abrir, marcar, marcada, conDif }: { it: Item; abrir: () => void; marcar: () => void; marcada: boolean; conDif: boolean }) {
  const dorm = it.dormitorios == null ? null : it.dormitorios === 0 ? "Mono" : `${it.dormitorios} dorm${it.dorm_fuente === "descripción" ? "*" : ""}`;
  const m2 = it.sup_cub || it.sup_tot;
  const precio = it.precio ? `${sim(it.moneda)} ${fmt(it.precio)}` : it.precio_falso ? "Precio no real" : "Consultar";
  const titulo = [it.tipo, it.barrio].filter(Boolean).join(" en ") || "Propiedad";
  return (
    <article className={`res ${it.color}${marcada ? " marcada" : ""}${it.foto ? "" : " sin-foto"}`} onClick={abrir} aria-label={`${it.color ? `${it.color}. ` : ""}${titulo}. ${precio}`}>
      <span className="borde" aria-hidden />
      {it.foto ? <img className="foto" src={it.foto} alt="" loading="lazy" decoding="async" /> : null}
      <div className="cuerpo">
        <div className="linea1">
          <span className="titulo">{titulo}</span>
          <span className="precio num" title={it.precio_falso ? `Publicado como ${fmt(it.precio_falso)}: es un precio de relleno, no se usa para comparar` : undefined}>{precio}</span>
        </div>
        <div className="datos">
          {[it.direccion, dorm, m2 ? `${fmt(m2)} m²` : null, it.usdm2 ? `${sim(it.moneda)} ${fmt(it.usdm2)}/m²` : null].filter(Boolean).join(" · ")}
        </div>
        <div className="tags">
          {it.plataformas.map((p) => <span key={p.fuente + p.id} className={`ptag ${p.fuente}`} title={PLAT_NOM[p.fuente]}>{PLAT_CORTO[p.fuente] || p.fuente}</span>)}
          {it.color && <span className="tag" style={{ borderColor: `var(--${it.color.toLowerCase()})` }}>{it.color}</span>}
          {it.estado_aviso === "baja" && <span className="tag baja">Baja</span>}
          {it.nueva && <span className="tag nueva">Nueva</span>}
          {it.bajo && <span className="tag bajo">Bajó</span>}
          {it.otro_precio?.length ? <span className="tag">Otro precio</span> : null}
          {it.zona === "dentro" && <span className="tag zona-dentro">En la zona</span>}
          {it.zona === "cerca" && <span className="tag zona-cerca">Cerca</span>}
          {it.margen && <span className="tag margen">Margen {it.margen}</span>}
          <span className="tag" title={it.pub_titulo}>{it.pub_corta}</span>
          {conDif && it.dif != null && <span className="tag num">{it.dif > 0 ? "+" : ""}{fmt(it.dif)}</span>}
          {it.vsb && <span className={`tag ${it.vsb.pct > 5 ? "caro" : it.vsb.pct < -5 ? "barato" : ""}`} title={`Mediana ${sim(it.moneda)} ${fmt(it.vsb.med)}/m² · ${it.vsb.n} ${it.tipo || ""} en ${it.vsb.donde}`}>
            {it.vsb.pct > 0 ? "+" : ""}{Math.round(it.vsb.pct)}% {it.vsb.nivel}</span>}
          {it.cuota && <span className="tag" title={`Crédito ${it.cuota.banco} · ${it.cuota.anios} años · financia ${it.cuota.ltv}% · ingreso mínimo ≈ $ ${fmt(it.cuota.ingreso)}`}>cuota ≈ $ {fmtK(it.cuota.cuota)}/mes</span>}
          {it.renta && <span className="tag" title={`Alquiler estimado $ ${fmt(it.renta.alq)}/mes (${it.renta.n} alquileres, ${it.renta.nivel})`}>renta ≈ {it.renta.pct.toFixed(1).replace(".", ",")}%</span>}
        </div>
        {it.obs && <div className="obs">{it.obs}</div>}
        <div className="fila-flex" style={{ justifyContent: "space-between" }}>
          <span className="obs">{it.inmobiliaria || ""}</span>
          <label className="check sel" onClick={(e) => e.stopPropagation()}>
            <input type="checkbox" checked={marcada} onChange={marcar} /> Marcar
          </label>
        </div>
      </div>
    </article>
  );
}
