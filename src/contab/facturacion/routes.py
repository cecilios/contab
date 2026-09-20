"""Define las rutas web del módulo de facturación."""

from datetime import date

from flask import (
    Blueprint,
    redirect,
    request,
    url_for,
)

from contab.models import Contrato
from contab.config import cargar_categorias_contables
from contab.context import get_session_factory
from contab.facturacion.services import (
    FacturacionError,
    emitir_factura,
)


bp = Blueprint(
    "facturacion",
    __name__,
    url_prefix="/facturacion",
)


@bp.post("/emitir/<int:contrato_id>")
def emitir(contrato_id: int):
    """Emite y registra contablemente una factura."""

    periodo = date.fromisoformat(
        request.form["periodo"]
    )
    fecha_emision = date.fromisoformat(
        request.form["fecha_emision"]
    )

    categorias = cargar_categorias_contables()
    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            with session.begin():
                contrato = session.get(
                    Contrato,
                    contrato_id,
                )

                if contrato is None:
                    return "Contrato no encontrado.", 404

                factura, apunte, movimiento = emitir_factura(
                    contrato=contrato,
                    periodo=periodo,
                    fecha_emision=fecha_emision,
                    categorias=categorias,
                )

                session.add(factura)
                session.add(apunte)
                session.add(movimiento)

    except FacturacionError as exc:
        return str(exc), 400

    return redirect(
        url_for("contabilidad.listar_apuntes")
    )


