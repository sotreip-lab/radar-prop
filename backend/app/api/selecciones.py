"""Mi selección (la "canasta" para armar fichas). Cada usuario ve y toca solo la suya: el user_id sale siempre de la
sesión, nunca de lo que mande el navegador."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.deps import Actual, usuario_actual
from app.db import get_db
from app.models import Propiedad, Seleccion

router = APIRouter(prefix="/selecciones", tags=["selección"])


class AgregarIn(BaseModel):
    propiedad_ids: list[int] = Field(min_length=1, max_length=200)


class ImportarLegadoIn(BaseModel):
    """ids de El Ojo de Dios guardados en el navegador (localStorage bp_sel)."""
    ids_legado: list[int] = Field(min_length=1, max_length=2000)


@router.get("", response_model=list[int])
def mi_seleccion(a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    return list(db.scalars(select(Seleccion.propiedad_id).where(Seleccion.user_id == a.id)
                           .order_by(Seleccion.agregada_en)))


@router.post("", response_model=list[int])
def agregar(datos: AgregarIn, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    existentes = set(db.scalars(select(Propiedad.id).where(Propiedad.id.in_(datos.propiedad_ids))))
    faltan = set(datos.propiedad_ids) - existentes
    if faltan:
        raise HTTPException(404, "Alguna de esas propiedades no existe.")
    db.execute(insert(Seleccion).values([{"user_id": a.id, "propiedad_id": p} for p in existentes])
               .on_conflict_do_nothing())
    db.commit()
    return mi_seleccion(a, db)


@router.post("/importar-ojo-de-dios", response_model=dict)
def importar_legado(datos: ImportarLegadoIn, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    ids = list(db.scalars(select(Propiedad.id).where(Propiedad.id_legado.in_(datos.ids_legado))))
    if ids:
        db.execute(insert(Seleccion).values([{"user_id": a.id, "propiedad_id": p} for p in ids]).on_conflict_do_nothing())
        db.commit()
    return {"importadas": len(ids), "no_encontradas": len(set(datos.ids_legado)) - len(ids)}


@router.delete("/{propiedad_id}", status_code=204)
def quitar(propiedad_id: int, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    db.execute(delete(Seleccion).where(Seleccion.user_id == a.id, Seleccion.propiedad_id == propiedad_id))
    db.commit()


@router.delete("", status_code=204)
def vaciar(a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    db.execute(delete(Seleccion).where(Seleccion.user_id == a.id))
    db.commit()
