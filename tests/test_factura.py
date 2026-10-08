"""Pruebas de los modelos ORM Factura y FacturaLinea."""

import pytest

from datetime import date

from sqlalchemy.exc import IntegrityError

from contab.models import (
    ApunteContable,
    Factura,
    FacturaDestinatario,
    FacturaLinea,
)



def _crear_factura(
    contrato,
    **cambios,
) -> Factura:
    datos = {
        "contrato": contrato,
        "numero_secuencia": 1,
        "anio": 2026,
        "numero_factura": "01/2026A1",
        "fecha_emision": date(2026, 10, 1),
        "periodo": date(2026, 10, 1),
        "referencia_inmueble": "LOCAL-1",
        "descripcion_inmueble": "Local comercial",
        "direccion_facturacion": "Calle 10",
        "codigo_postal_facturacion": "36001",
        "poblacion_facturacion": "Pontevedra",
        "provincia_facturacion": "Pontevedra",
        "base": 100000,
        "iva_porcentaje": 2100,
        "iva_importe": 21000,
        "retencion_porcentaje": 1900,
        "retencion_importe": 19000,
        "total": 102000,
    }

    datos.update(cambios)

    return Factura(**datos)


def test_crear_factura_con_lineas(session, contrato) -> None:
    """Comprueba que una factura puede contener varias líneas económicas."""

    factura = _crear_factura(
        contrato,
        base=108347,
        iva_importe=22753,
        retencion_importe=20586,
        total=110514,
        ruta_pdf="facturas/01-2026A1.pdf",
    )

    factura.lineas.extend(
        [
            FacturaLinea(
                orden=1,
                concepto="Alquiler del local por el mes de septiembre de 2026",
                importe=100000,
            ),
            FacturaLinea(
                orden=2,
                concepto="Agua del 15/03/2026 al 18/05/2026",
                importe=8347,
            ),
        ]
    )

    session.add(factura)
    session.commit()

    assert factura.id is not None
    assert factura.estado == "EMITIDA"
    assert len(factura.lineas) == 2
    assert factura.lineas[0].importe == 100000
    assert factura.lineas[1].importe == 8347


def test_numero_factura_debe_ser_unico(
    session,
    contrato,
) -> None:
    """Comprueba que no pueden existir dos facturas con el mismo número."""

    factura_1 = _crear_factura(contrato)

    factura_2 = _crear_factura(
        contrato,
        numero_secuencia=2,
    )

    session.add_all([factura_1, factura_2])

    with pytest.raises(IntegrityError):
        session.commit()


def test_factura_linea_admite_diferencia_negativa(session, contrato) -> None:
    """Comprueba que una diferencia de revisión puede tener importe negativo."""

    factura = _crear_factura(
        contrato,
        base=97500,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=97500,
    )

    factura.lineas.extend(
        [
            FacturaLinea(
                orden=1,
                concepto="Alquiler",
                importe=100000,
            ),
            FacturaLinea(
                orden=2,
                concepto="Diferencia de revisión",
                importe=-2500,
            ),
        ]
    )

    session.add(factura)
    session.commit()

    assert factura.lineas[1].importe == -2500


def test_factura_no_admite_estado_desconocido(session, contrato) -> None:
    """Comprueba que sólo pueden almacenarse estados de factura conocidos."""

    factura = _crear_factura(
        contrato,
        estado="DESCONOCIDO",
    )

    session.add(factura)

    with pytest.raises(IntegrityError):
        session.commit()


def test_factura_admite_ruta_pdf_vacia_por_defecto(
    session,
    contrato,
) -> None:

    factura = _crear_factura(contrato)

    session.add(factura)
    session.commit()

    assert factura.ruta_pdf == ""


def test_factura_conserva_datos_historicos_del_documento(
    session,
    contrato,
) -> None:
    """La factura conserva sus datos aunque cambie el contrato."""

    factura = _crear_factura(
        contrato,
        direccion_facturacion="Calle Antigua 10",
    )

    factura.destinatarios.extend(
        [
            FacturaDestinatario(
                orden=1,
                nombre="Ana Pérez",
                nif="11111111A",
            ),
            FacturaDestinatario(
                orden=2,
                nombre="Luis Pérez",
                nif="22222222B",
            ),
        ]
    )

    session.add(factura)
    session.commit()

    contrato.direccion_facturacion = "Dirección nueva"
    contrato.inmueble.referencia = "REFERENCIA-NUEVA"
    contrato.inmueble.descripcion = "Descripción nueva"

    for titular in contrato.titulares:
        titular.inquilino.nombre = "Nombre modificado"

    session.commit()
    session.expire_all()

    factura = session.get(Factura, factura.id)

    assert factura is not None
    assert factura.referencia_inmueble == "LOCAL-1"
    assert factura.descripcion_inmueble == "Local comercial"
    assert factura.direccion_facturacion == "Calle Antigua 10"
    assert factura.codigo_postal_facturacion == "36001"
    assert factura.poblacion_facturacion == "Pontevedra"
    assert factura.provincia_facturacion == "Pontevedra"

    assert [
        (destinatario.nombre, destinatario.nif)
        for destinatario in factura.destinatarios
    ] == [
        ("Ana Pérez", "11111111A"),
        ("Luis Pérez", "22222222B"),
    ]


def test_factura_puede_vincular_su_apunte_contable(
    session,
    contrato,
) -> None:
    """Una factura conoce el apunte contable generado al emitirla."""

    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler octubre 2026",
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 31),
        criterio_periodo="INCLUIR_AMBOS",
        tratamiento="CONTABILIZAR",
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        total=102000,
        tercero_nombre="Ana Pérez",
        tercero_nif="11111111A",
        referencia_documento="01/2026A1",
    )

    factura = _crear_factura(
        contrato,
        apunte_contable=apunte,
    )

    session.add(factura)
    session.commit()
    session.expire_all()

    factura = session.get(Factura, factura.id)

    assert factura is not None
    assert factura.apunte_contable is not None
    assert factura.apunte_contable.id == apunte.id


def test_factura_linea_no_necesita_tipo(
    session,
    contrato,
) -> None:
    """Una línea se define sólo por orden, concepto e importe."""

    factura = _crear_factura(
        contrato,
        base=3500,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=3500,
    )

    factura.lineas.append(
        FacturaLinea(
            orden=1,
            concepto="Consumo de agua",
            importe=3500,
        )
    )

    session.add(factura)
    session.commit()

    assert factura.lineas[0].concepto == "Consumo de agua"
    assert factura.lineas[0].importe == 3500


