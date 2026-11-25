import pytest

from app.scraper.ids import IdInvalido, id_externo, plataforma_de_url


def test_bbp_usa_numero_del_sitio():
    assert id_externo("BBP", 95448, None) == "95448"
    assert id_externo("", 140, None) == "140"  # fuente vacía = BBP
    assert id_externo("BBP", 1, "https://www.bahiablancapropiedades.com/propiedad/777/") == "777"


def test_zonaprop_usa_numero_del_link_y_no_el_id_inventado():
    url = "https://www.zonaprop.com.ar/propiedades/-60773311.html"
    assert id_externo("ZP", 1000002369, url) == "60773311"


def test_ibb_usa_slug_del_link():
    url = "https://ibb.com.ar/listings/departamento-en-venta-monoambiente-en-soler-111"
    assert id_externo("IBB", 1000000001, url) == "departamento-en-venta-monoambiente-en-soler-111"


def test_mismo_numero_en_distintas_plataformas_no_se_mezcla():
    a = ("BBP", id_externo("BBP", 60773311, None))
    b = ("ZP", id_externo("ZP", 1000000005, "https://www.zonaprop.com.ar/propiedades/-60773311.html"))
    assert a[1] == b[1] and a != b  # mismo número, clave distinta por plataforma


def test_bbp_con_id_inventado_o_ibb_sin_link_falla_en_vez_de_inventar():
    with pytest.raises(IdInvalido):
        id_externo("BBP", 1000000001, None)
    with pytest.raises(IdInvalido):
        id_externo("IBB", 1000000001, None)


def test_plataforma_de_url():
    assert plataforma_de_url("https://www.zonaprop.com.ar/x.html") == "ZP"
    assert plataforma_de_url("https://ibb.com.ar/listings/a") == "IBB"
    assert plataforma_de_url("nada") is None
