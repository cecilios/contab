
"""Pruebas de la carga excepcional de apuntes históricos de 2026."""

import runpy

from datetime import date
from pathlib import Path

import pytest

from sqlalchemy import select

from contab.config import CategoriaContable, SubcategoriaContable
from contab.contabilidad.services import crear_apunte_contable
from contab.models import (
    ApunteContable,
    DistribucionApunte,
    Inmueble,
    MovimientoPrevisto,
)


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "cargar-apuntes-historicos.py"
)

NOTA_HISTORICA = (
    "Conciliado manualmente por carga histórica de datos"
)


@pytest.fixture
def carga():
    """Carga las funciones del script sin ejecutar su main."""
    funciones = runpy.run_path(str(SCRIPT))

    return (
        funciones["leer_apuntes"],
        funciones["preparar_carga"],
    )


@pytest.fixture
def categorias_historicas():
    """Categorías utilizadas en los ejemplos de importación."""
    return {
        "COMUNIDAD": CategoriaContable(
            codigo="COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
        "SUMINISTROS": CategoriaContable(
            codigo="SUMINISTROS",
            naturaleza="GASTO",
            nombre="Suministros",
            activa=True,
            subcategorias=(
                SubcategoriaContable(
                    codigo="AGUA",
                    nombre="Agua",
                    activa=True,
                ),
            ),
        ),
        "OTROS_INGRESOS": CategoriaContable(
            codigo="OTROS_INGRESOS",
            naturaleza="INGRESO",
            nombre="Otros ingresos",
            activa=True,
            subcategorias=(),
        ),
    }


def archivo_temporal(tmp_path, texto):
    """Escribe datos de prueba en un archivo de texto."""
    ruta = tmp_path / "apuntes.txt"
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def crear_inmueble(session, referencia, tipo="L",
                   padre=None, participacion=10000):
    """Crea un inmueble válido para las pruebas."""
    propiedad = {
        "porcentaje_titular": 10000,
        "tipo_derecho": "PLENA_PROPIEDAD",
        "porcentaje_derecho": 10000,
        "fecha_adquisicion": date(2020, 1, 1),
        "tipo_adquisicion": "ONEROSA",
        "importe_adquisicion": 0,
        "gastos_adquisicion": 0,
    }

    if padre is not None:
        propiedad = dict.fromkeys(propiedad)

    inmueble = Inmueble(
        referencia=referencia,
        tipo=tipo,
        inmueble_padre=padre,
        codigo_facturacion=referencia,
        descripcion=referencia,
        direccion="Dirección de prueba",
        poblacion="Madrid",
        provincia="Madrid",
        participacion=participacion,
        **propiedad,
    )

    session.add(inmueble)
    return inmueble


def test_cargar_apunte_ordinario_con_iva_y_retencion(
    session, inmueble, categorias_historicas, carga, tmp_path,
):
    leer_apuntes, preparar_carga = carga

    archivo = archivo_temporal(
        tmp_path,
        "LOCAL-1 ; 2026-02-15 ; COMUNIDAD ; "
        "Gasto histórico ; 100,00 ; 21,00 ; 15,00\n",
    )

    filas = leer_apuntes(archivo)

    # El usuario importa el apunte histórico.
    with session.begin():
        resumen = preparar_carga(
            session, categorias_historicas, filas
        )

    apunte = session.scalar(select(ApunteContable))
    movimiento = session.scalar(select(MovimientoPrevisto))

    assert resumen == (1, 1, 0)
    assert apunte.fecha == date(2026, 2, 15)
    assert apunte.inmueble_id == inmueble.id
    assert apunte.tratamiento == "CONTABILIZAR"
    assert apunte.naturaleza == "GASTO"
    assert apunte.categoria == "COMUNIDAD"
    assert apunte.base == 10000
    assert apunte.iva_importe == 2100
    assert apunte.retencion_importe == 1500
    assert apunte.total == 10600

    assert movimiento.apunte_id == apunte.id
    assert movimiento.inmueble_id == inmueble.id
    assert movimiento.naturaleza == "GASTO"
    assert movimiento.importe_esperado == 10600
    assert movimiento.fecha_prevista_desde is None
    assert movimiento.fecha_prevista_hasta is None
    assert movimiento.estado == "CONCILIADO"
    assert movimiento.metodo_conciliacion == "MANUAL"
    assert movimiento.notas == NOTA_HISTORICA


def test_cargar_apunte_con_columnas_opcionales_y_subcategoria(
    session, inmueble, categorias_historicas, carga, tmp_path,
):
    leer_apuntes, preparar_carga = carga

    archivo = archivo_temporal(
        tmp_path,
        "LOCAL-1 ; 2026-03-10 ; SUMINISTROS.AGUA ; "
        "Agua marzo ; 45,25\n",
    )

    filas = leer_apuntes(archivo)

    # El usuario importa un gasto sin IVA ni retención.
    with session.begin():
        preparar_carga(session, categorias_historicas, filas)

    apunte = session.scalar(select(ApunteContable))

    assert apunte.categoria == "SUMINISTROS"
    assert apunte.subcategoria == "AGUA"
    assert apunte.base == 4525
    assert apunte.iva_importe == 0
    assert apunte.retencion_importe == 0
    assert apunte.total == 4525


def test_cargar_apunte_negativo_invierte_naturaleza_bancaria(
    session, inmueble, categorias_historicas, carga, tmp_path,
):
    leer_apuntes, preparar_carga = carga

    archivo = archivo_temporal(
        tmp_path,
        "LOCAL-1 ; 2026-04-05 ; COMUNIDAD ; "
        "Devolución recibo ; -30,00\n",
    )

    filas = leer_apuntes(archivo)

    # El usuario registra una devolución de un gasto anterior.
    with session.begin():
        preparar_carga(session, categorias_historicas, filas)

    apunte = session.scalar(select(ApunteContable))
    movimiento = session.scalar(select(MovimientoPrevisto))

    assert apunte.naturaleza == "GASTO"
    assert apunte.importe_negativo is True
    assert apunte.base == 3000
    assert apunte.total == 3000

    assert movimiento.naturaleza == "INGRESO"
    assert movimiento.importe_esperado == 3000
    assert movimiento.estado == "CONCILIADO"


def test_cargar_inmueble_t_genera_distribuciones(
    session, categorias_historicas, carga, tmp_path,
):
    leer_apuntes, preparar_carga = carga

    padre = crear_inmueble(
        session, "EDIFICIO-T", tipo="T"
    )
    crear_inmueble(
        session, "LOCAL-A", padre=padre, participacion=6000
    )
    crear_inmueble(
        session, "LOCAL-B", padre=padre, participacion=4000
    )
    session.commit()

    archivo = archivo_temporal(
        tmp_path,
        "EDIFICIO-T ; 2026-05-10 ; COMUNIDAD ; "
        "Gasto común ; 100,00\n",
    )

    filas = leer_apuntes(archivo)

    # El usuario importa un gasto común del edificio.
    with session.begin():
        resumen = preparar_carga(
            session, categorias_historicas, filas
        )

    distribuciones = session.scalars(
        select(DistribucionApunte)
        .order_by(DistribucionApunte.base.desc())
    ).all()

    movimientos = session.scalars(
        select(MovimientoPrevisto)
    ).all()

    assert resumen == (1, 1, 2)
    assert len(distribuciones) == 2
    assert [d.base for d in distribuciones] == [6000, 4000]
    assert [d.participacion for d in distribuciones] == [
        6000, 4000
    ]

    assert len(movimientos) == 1
    assert movimientos[0].inmueble_id == padre.id
    assert movimientos[0].importe_esperado == 10000
    assert movimientos[0].estado == "CONCILIADO"


def test_cargar_sin_alterar_apuntes_historicos_existentes(
    session, inmueble, categorias_historicas, carga, tmp_path,
):
    leer_apuntes, preparar_carga = carga

    existente = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias_historicas,
        fecha=date(2026, 1, 10),
        naturaleza="GASTO",
        categoria="COMUNIDAD",
        concepto="Apunte existente",
        base=5000,
    )

    session.add(existente)
    session.commit()
    existente_id = existente.id

    archivo = archivo_temporal(
        tmp_path,
        "LOCAL-1 ; 2026-06-15 ; COMUNIDAD ; "
        "Nuevo apunte ; 75,00\n",
    )

    filas = leer_apuntes(archivo)

    # El usuario añade datos sin modificar los ya contabilizados.
    with session.begin():
        preparar_carga(session, categorias_historicas, filas)

    apuntes = session.scalars(
        select(ApunteContable).order_by(ApunteContable.id)
    ).all()

    assert len(apuntes) == 2
    assert apuntes[0].id == existente_id
    assert apuntes[0].concepto == "Apunte existente"
    assert apuntes[0].base == 5000
    assert apuntes[1].concepto == "Nuevo apunte"


@pytest.mark.parametrize(
    "linea",
    [
        "LOCAL-1 ; 2025-12-31 ; COMUNIDAD ; Gasto ; 10,00",
        "LOCAL-1 ; 2026-10-01 ; COMUNIDAD ; Gasto ; 10,00",
        "DESCONOCIDO ; 2026-06-01 ; COMUNIDAD ; Gasto ; 10,00",
        "LOCAL-1 ; 2026-06-01 ; INEXISTENTE ; Gasto ; 10,00",
        "LOCAL-1 ; 2026-06-01 ; COMUNIDAD ; Gasto ; abc",
        "LOCAL-1 ; 2026-06-01 ; COMUNIDAD ; Gasto ; 0,00",
    ],
)
def test_datos_invalidos_no_modifican_la_base(
    session, inmueble, categorias_historicas,
    carga, tmp_path, linea,
):
    leer_apuntes, preparar_carga = carga

    archivo = archivo_temporal(
        tmp_path,
        "LOCAL-1 ; 2026-01-15 ; COMUNIDAD ; "
        "Apunte válido ; 50,00\n"
        + linea + "\n",
    )

    # El usuario intenta importar un archivo con una fila incorrecta.
    with pytest.raises(ValueError):
        with session.begin():
            filas = leer_apuntes(archivo)
            preparar_carga(
                session, categorias_historicas, filas
            )

    # Ningún apunte ni movimiento de la carga debe persistir.
    assert session.scalars(select(ApunteContable)).all() == []
    assert session.scalars(select(MovimientoPrevisto)).all() == []


def test_aceptar_filas_iguales_sin_buscar_duplicados(
    session, inmueble, categorias_historicas, carga, tmp_path,
):
    leer_apuntes, preparar_carga = carga

    linea = (
        "LOCAL-1 ; 2026-07-15 ; COMUNIDAD ; "
        "Dos cargos iguales ; 25,00\n"
    )
    archivo = archivo_temporal(tmp_path, linea + linea)

    filas = leer_apuntes(archivo)

    # El usuario confirma cargar ambas filas, aunque sean iguales.
    with session.begin():
        preparar_carga(session, categorias_historicas, filas)

    assert len(
        session.scalars(select(ApunteContable)).all()
    ) == 2
    assert len(
        session.scalars(select(MovimientoPrevisto)).all()
    ) == 2


def test_cancelar_importacion_no_modifica_base(
    tmp_path, categorias_historicas, monkeypatch, capsys,
):
    """Cancelar la confirmación deshace toda la carga preparada."""
    from contab.database import (
        Base,
        create_session_factory,
        create_sqlite_engine,
    )

    ruta_base = tmp_path / "historico.db"
    url_base = f"sqlite:///{ruta_base}"

    engine = create_sqlite_engine(url_base)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    # El usuario ya tiene un apunte anterior en la base.
    with session_factory() as session:
        inmueble = crear_inmueble(session, "LOCAL-1")

        existente = crear_apunte_contable(
            inmueble=inmueble,
            categorias=categorias_historicas,
            fecha=date(2026, 1, 10),
            naturaleza="GASTO",
            categoria="COMUNIDAD",
            concepto="Apunte existente",
            base=5000,
        )

        session.add(existente)
        session.commit()

    # El usuario prepara dos apuntes, uno de ellos con IVA.
    archivo = archivo_temporal(
        tmp_path,
        "LOCAL-1 ; 2026-02-15 ; COMUNIDAD ; "
        "Comunidad febrero ; 100,00\n"
        "LOCAL-1 ; 2026-03-15 ; COMUNIDAD ; "
        "Comunidad marzo ; 100,00 ; 21,00\n",
    )

    # Sustituimos la configuración real por la de pruebas.
    funciones = runpy.run_path(str(SCRIPT))
    main = funciones["main"]
    entorno = main.__globals__

    monkeypatch.setitem(
        entorno,
        "ARCHIVO_DATOS",
        archivo,
    )
    monkeypatch.setitem(
        entorno,
        "cargar_bases_datos",
        lambda: {"pruebas": url_base},
    )
    monkeypatch.setitem(
        entorno,
        "cargar_categorias_contables",
        lambda: categorias_historicas,
    )
    monkeypatch.setattr(
        "sys.argv",
        ["cargar-apuntes-historicos.py", "pruebas"],
    )

    # El usuario rechaza expresamente la importación.
    monkeypatch.setattr(
        "builtins.input",
        lambda mensaje: "N",
    )

    try:
        main()

        salida = capsys.readouterr().out
        assert "Importación cancelada." in salida

        # El usuario comprueba que la base no ha cambiado.
        with session_factory() as session:
            apuntes = session.scalars(
                select(ApunteContable)
            ).all()

            movimientos = session.scalars(
                select(MovimientoPrevisto)
            ).all()

            distribuciones = session.scalars(
                select(DistribucionApunte)
            ).all()

            assert len(apuntes) == 1
            assert apuntes[0].concepto == "Apunte existente"
            assert apuntes[0].base == 5000

            assert movimientos == []
            assert distribuciones == []

    finally:
        engine.dispose()

