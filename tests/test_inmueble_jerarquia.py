"""Pruebas de la jerarquía de inmuebles."""

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Inmueble



def test_inmueble_subdividido_contiene_locales(
    session,
) -> None:
    inmueble_subdividido = Inmueble(
        referencia="ALOPEZ-COMUN",
        tipo="T",
        codigo_facturacion="ALC",
        descripcion="Inmueble completo",
        direccion="Avenida López, 1",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=10000,
    )

    local_1 = Inmueble(
        referencia="ALOPEZ-LOCAL1",
        tipo="L",
        codigo_facturacion="AL1",
        descripcion="Local 1",
        direccion="Avenida López, 1",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=3250,
        inmueble_padre=inmueble_subdividido,
    )

    local_2 = Inmueble(
        referencia="ALOPEZ-LOCAL2",
        tipo="L",
        codigo_facturacion="AL2",
        descripcion="Local 2",
        direccion="Avenida López, 1",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=6750,
        inmueble_padre=inmueble_subdividido,
    )

    session.add_all([
        inmueble_subdividido,
        local_1,
        local_2,
    ])
    session.commit()

    assert local_1.inmueble_padre is inmueble_subdividido
    assert local_2.inmueble_padre is inmueble_subdividido

    assert {
        local.referencia
        for local in inmueble_subdividido.locales
    } == {
        "ALOPEZ-LOCAL1",
        "ALOPEZ-LOCAL2",
    }


def test_inmueble_subdividido_exige_participacion_completa(
    session,
) -> None:
    inmueble_subdividido = Inmueble(
        referencia="TOTAL-INCORRECTO",
        tipo="T",
        codigo_facturacion="TI",
        descripcion="Inmueble incorrecto",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=5000,
    )

    session.add(inmueble_subdividido)

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


