"""2026-10-08 dejar datos coherentes

Revision ID: b8f0d5a2848b
Revises: 3a6b0c3f2ed1
Create Date: 2026-10-08 13:50:01.097859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = 'b8f0d5a2848b'
down_revision: Union[str, Sequence[str], None] = '3a6b0c3f2ed1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def _redondear_division(
    numerador: int,
    denominador: int,
) -> int:
    """Redondea al entero más próximo, con mitad hacia arriba."""

    return (
        numerador + denominador // 2
    ) // denominador


def _repartir_importe(
    importe: int,
    locales,
) -> list[int]:
    """Reparte un importe y asigna el residuo al último local."""

    repartos: list[int] = []
    acumulado = 0

    for local in locales[:-1]:
        reparto = _redondear_division(
            importe * local["participacion"],
            10000,
        )

        repartos.append(reparto)
        acumulado += reparto

    repartos.append(
        importe - acumulado
    )

    return repartos


def _regularizar_datos(connection) -> None:
    """Genera distribuciones históricas y elimina movimientos obsoletos."""

    apuntes = connection.execute(
        sa.text(
            """
            SELECT
                a.id,
                a.inmueble_id,
                a.base,
                a.iva_importe,
                a.retencion_importe
            FROM apunte_contable AS a
            JOIN inmueble AS i
              ON i.id = a.inmueble_id
            WHERE i.tipo = 'T'
            ORDER BY a.id
            """
        )
    ).mappings().all()

    for apunte in apuntes:
        locales = connection.execute(
            sa.text(
                """
                SELECT
                    id,
                    referencia,
                    participacion
                FROM inmueble
                WHERE inmueble_padre_id = :inmueble_id
                ORDER BY referencia, id
                """
            ),
            {
                "inmueble_id": apunte[
                    "inmueble_id"
                ],
            },
        ).mappings().all()

        if not locales:
            raise RuntimeError(
                "Un inmueble subdividido con apuntes "
                "históricos no tiene locales."
            )

        if sum(
            local["participacion"]
            for local in locales
        ) != 10000:
            raise RuntimeError(
                "Las participaciones de los locales de "
                "un inmueble subdividido no suman el 100 %."
            )

        distribuciones_existentes = (
            connection.scalar(
                sa.text(
                    """
                    SELECT COUNT(*)
                    FROM distribucion_apunte
                    WHERE apunte_id = :apunte_id
                    """
                ),
                {
                    "apunte_id": apunte["id"],
                },
            )
            or 0
        )

        if distribuciones_existentes:
            continue

        bases = _repartir_importe(
            apunte["base"],
            locales,
        )
        ivas = _repartir_importe(
            apunte["iva_importe"],
            locales,
        )
        retenciones = _repartir_importe(
            apunte["retencion_importe"],
            locales,
        )

        for (
            local,
            base,
            iva,
            retencion,
        ) in zip(
            locales,
            bases,
            ivas,
            retenciones,
            strict=True,
        ):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO distribucion_apunte (
                        apunte_id,
                        inmueble_id,
                        participacion,
                        base,
                        iva_importe,
                        retencion_importe,
                        total
                    )
                    VALUES (
                        :apunte_id,
                        :inmueble_id,
                        :participacion,
                        :base,
                        :iva_importe,
                        :retencion_importe,
                        :total
                    )
                    """
                ),
                {
                    "apunte_id": apunte["id"],
                    "inmueble_id": local["id"],
                    "participacion": local[
                        "participacion"
                    ],
                    "base": base,
                    "iva_importe": iva,
                    "retencion_importe": retencion,
                    "total": (
                        base
                        + iva
                        - retencion
                    ),
                },
            )

    conciliados = connection.execute(
        sa.text(
            """
            SELECT DISTINCT mp.id
            FROM movimiento_previsto AS mp
            JOIN apunte_contable AS a
              ON a.id = mp.apunte_id
            JOIN inmueble AS i
              ON i.id = a.inmueble_id
            JOIN conciliacion AS c
              ON c.movimiento_previsto_id = mp.id
            WHERE i.tipo = 'T'
              AND a.tratamiento = 'REPERCUTIR'
            """
        )
    ).all()

    if conciliados:
        raise RuntimeError(
            "Hay movimientos previstos conciliados asociados "
            "a apuntes REPERCUTIR de inmuebles subdivididos."
        )

    connection.execute(
        sa.text(
            """
            DELETE FROM movimiento_previsto
            WHERE id IN (
                SELECT mp.id
                FROM movimiento_previsto AS mp
                JOIN apunte_contable AS a
                  ON a.id = mp.apunte_id
                JOIN inmueble AS i
                  ON i.id = a.inmueble_id
                WHERE i.tipo = 'T'
                  AND a.tratamiento = 'REPERCUTIR'
            )
            """
        )
    )

def upgrade() -> None:
    """Regulariza las distribuciones históricas."""

    _regularizar_datos(
        op.get_bind()
    )


def downgrade() -> None:
    """La regularización histórica no es reversible automáticamente."""

    pass
