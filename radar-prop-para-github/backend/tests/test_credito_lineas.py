"""Topes reales de las líneas de crédito leídos del texto de cada banco."""
from app.services.credito_lineas import condiciones, simular

UVA = 2213.19
BNA = {"banco": "Nación", "linea": "MAS HOGARES CON BNA", "tea": 6.91, "plazo": 360, "ltv": 75.0, "rci": 25.0,
       "monto_max": 325711575.0, "ingreso_min": 800665.0, "cft": 8.06,
       "nota": "ADQUISICION VIV UNICA HABERES MONTO MAXIMO OTORGABLE 157500 UVAS Y VALOR DE VIVIENDA DE HASTA 210000 UVAS "
               "AJUSTABLES A LA COTIZACION INFORMADA POR BCRA"}


def test_lee_topes_del_nacion():
    d = condiciones(BNA)
    assert d["monto_max_uva"] == 157500 and d["valor_max_uva"] == 210000 and d["valor_min_uva"] is None
    assert d["ingreso_min"] == 800665 and d["cft"] == 8.06 and 6.6 < d["tna"] < 6.8


def test_vivienda_cara_no_califica_y_barata_si():
    d = condiciones(BNA)
    caro = simular(300000 * 1667, d, UVA, 20)
    assert caro["califica"] is False and "valor máximo" in caro["motivos"][0]
    ok = simular(150000 * 1667, d, UVA, 20)
    assert ok["califica"] and ok["ltv"] == 75 and ok["tope"] is None
    # el préstamo nunca pasa el tope en UVAs con la UVA del día
    medio = simular(270000 * 1667, d, UVA, 20)
    assert medio["prestamo"] <= 157500 * UVA + 1 and medio["tope"] is not None


def test_rango_superior_y_rellenos():
    d = condiciones({**BNA, "nota": "MONTO MAXIMO OTORGABLE 315000 UVAS Y VALOR DE VIVIENDA SUPERIOR A 210000 UVAS HASTA 350000 UVAS"})
    assert (d["valor_min_uva"], d["valor_max_uva"]) == (210000, 350000)
    assert simular(150000 * 1667, d, UVA, 20)["califica"] is False
    assert simular(400000 * 1667, d, UVA, 20)["califica"] is True
    r = condiciones({**BNA, "monto_max": 999999999.0, "ingreso_min": 999999.0, "nota": "N/A"})
    assert r["monto_max"] is None and r["ingreso_min"] is None and r["nota"] == ""
    icbc = condiciones({**BNA, "ingreso_min": 999999.0, "nota": "COMISION POR CANCELACION 3   INGRESO M$NIMO  1.400.000  EL CAMPO"})
    assert icbc["ingreso_min"] == 1400000


def test_plazo_limitado_por_la_linea():
    d = condiciones({**BNA, "plazo": 180})
    assert simular(100000 * 1667, d, UVA, 30)["anios"] == 15
