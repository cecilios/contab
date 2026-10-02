"""consolidar datos historicos de facturas

Revision ID: 2bfe0e7876a3
Revises: 747c5aaf52f9
Create Date: 2026-10-02 13:57:56.897029

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '2bfe0e7876a3'
down_revision: Union[str, Sequence[str], None] = '747c5aaf52f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Consolida el snapshot histórico de las facturas."""

    # 1. Añadir primero las columnas snapshot como nullable para poder
    #    migrar las facturas ya existentes.
    with op.batch_alter_table(
        "factura",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "referencia_inmueble",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "descripcion_inmueble",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "direccion_facturacion",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "codigo_postal_facturacion",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "poblacion_facturacion",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "provincia_facturacion",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "apunte_contable_id",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.create_unique_constraint(
            "uq_factura_apunte_contable_id",
            ["apunte_contable_id"],
        )

        batch_op.create_foreign_key(
            "fk_factura_apunte_contable_id",
            "apunte_contable",
            ["apunte_contable_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    # 2. Crear los destinatarios históricos.
    op.create_table(
        "factura_destinatario",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "factura_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "orden",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "nombre",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "nif",
            sa.Text(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "orden > 0",
            name="ck_factura_destinatario_orden",
        ),
        sa.ForeignKeyConstraint(
            ["factura_id"],
            ["factura.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "factura_id",
            "orden",
            name="uq_factura_destinatario_orden",
        ),
    )

    # 3. Reconstruir el snapshot histórico de las facturas existentes
    #    a partir de su contrato e inmueble actuales.
    op.execute(
        """
        UPDATE factura
        SET
            referencia_inmueble = (
                SELECT inmueble.referencia
                FROM contrato
                JOIN inmueble
                  ON inmueble.id = contrato.inmueble_id
                WHERE contrato.id = factura.contrato_id
            ),
            descripcion_inmueble = (
                SELECT inmueble.descripcion
                FROM contrato
                JOIN inmueble
                  ON inmueble.id = contrato.inmueble_id
                WHERE contrato.id = factura.contrato_id
            ),
            direccion_facturacion = (
                SELECT contrato.direccion_facturacion
                FROM contrato
                WHERE contrato.id = factura.contrato_id
            ),
            codigo_postal_facturacion = (
                SELECT contrato.codigo_postal_facturacion
                FROM contrato
                WHERE contrato.id = factura.contrato_id
            ),
            poblacion_facturacion = (
                SELECT contrato.poblacion_facturacion
                FROM contrato
                WHERE contrato.id = factura.contrato_id
            ),
            provincia_facturacion = (
                SELECT contrato.provincia_facturacion
                FROM contrato
                WHERE contrato.id = factura.contrato_id
            )
        """
    )

    # 4. Reconstruir los destinatarios históricos conservando su orden.
    op.execute(
        """
        INSERT INTO factura_destinatario (
            factura_id,
            orden,
            nombre,
            nif
        )
        SELECT
            factura.id,
            contrato_inquilino.orden,
            inquilino.nombre,
            inquilino.nif
        FROM factura
        JOIN contrato_inquilino
          ON contrato_inquilino.contrato_id =
             factura.contrato_id
        JOIN inquilino
          ON inquilino.id =
             contrato_inquilino.inquilino_id
        ORDER BY
            factura.id,
            contrato_inquilino.orden
        """
    )

    conexion = op.get_bind()

    # 5. No enlazar automáticamente una factura si existen varios
    #    apuntes candidatos.
    ambiguas = conexion.execute(
        sa.text(
            """
            SELECT
                factura.id,
                factura.numero_factura,
                COUNT(apunte_contable.id) AS numero_apuntes
            FROM factura
            JOIN contrato
              ON contrato.id = factura.contrato_id
            JOIN apunte_contable
              ON apunte_contable.referencia_documento =
                 factura.numero_factura
             AND apunte_contable.inmueble_id =
                 contrato.inmueble_id
            GROUP BY
                factura.id,
                factura.numero_factura
            HAVING COUNT(apunte_contable.id) > 1
            """
        )
    ).fetchall()

    if ambiguas:
        raise RuntimeError(
            "Hay facturas con varios apuntes contables candidatos: "
            f"{ambiguas}"
        )

    # 6. Relacionar cada factura con el apunte que hasta ahora se
    #    identificaba mediante referencia_documento.
    op.execute(
        """
        UPDATE factura
        SET apunte_contable_id = (
            SELECT apunte_contable.id
            FROM apunte_contable
            JOIN contrato
              ON contrato.id = factura.contrato_id
            WHERE apunte_contable.referencia_documento =
                  factura.numero_factura
              AND apunte_contable.inmueble_id =
                  contrato.inmueble_id
        )
        """
    )

    # 7. Una factura emitida existente debería tener su apunte.
    sin_apunte = conexion.execute(
        sa.text(
            """
            SELECT id, numero_factura
            FROM factura
            WHERE estado = 'EMITIDA'
              AND apunte_contable_id IS NULL
            """
        )
    ).fetchall()

    if sin_apunte:
        raise RuntimeError(
            "Hay facturas emitidas sin apunte contable asociado: "
            f"{sin_apunte}"
        )

    # 8. Comprobar que el snapshot obligatorio pudo reconstruirse.
    snapshot_incompleto = conexion.execute(
        sa.text(
            """
            SELECT id, numero_factura
            FROM factura
            WHERE referencia_inmueble IS NULL
               OR descripcion_inmueble IS NULL
               OR direccion_facturacion IS NULL
               OR poblacion_facturacion IS NULL
               OR provincia_facturacion IS NULL
            """
        )
    ).fetchall()

    if snapshot_incompleto:
        raise RuntimeError(
            "No se pudo reconstruir el snapshot de estas facturas: "
            f"{snapshot_incompleto}"
        )

    # 9. Toda factura existente debe conservar al menos un destinatario.
    sin_destinatario = conexion.execute(
        sa.text(
            """
            SELECT factura.id, factura.numero_factura
            FROM factura
            WHERE NOT EXISTS (
                SELECT 1
                FROM factura_destinatario
                WHERE factura_destinatario.factura_id =
                      factura.id
            )
            """
        )
    ).fetchall()

    if sin_destinatario:
        raise RuntimeError(
            "Hay facturas sin destinatario histórico: "
            f"{sin_destinatario}"
        )

    # 10. Una vez migrados los datos, aplicar los NOT NULL definitivos.
    with op.batch_alter_table(
        "factura",
        schema=None,
    ) as batch_op:
        batch_op.alter_column(
            "referencia_inmueble",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch_op.alter_column(
            "descripcion_inmueble",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch_op.alter_column(
            "direccion_facturacion",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch_op.alter_column(
            "poblacion_facturacion",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch_op.alter_column(
            "provincia_facturacion",
            existing_type=sa.Text(),
            nullable=False,
        )

    # 11. FacturaLinea ya no distingue tipos semánticos.
    with op.batch_alter_table(
        "factura_linea",
        schema=None,
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_factura_linea_tipo",
            type_="check",
        )
        batch_op.drop_column("tipo")

    # La migración 747c5aaf52f9 intentaba crear este CHECK fuera
    # del batch_alter_table y el esquema quedó desalineado del modelo.
    with op.batch_alter_table(
        "movimiento_previsto",
        schema=None,
    ) as batch_op:
        batch_op.create_check_constraint(
            "ck_movimiento_previsto_metodo_conciliacion",
            """
            metodo_conciliacion IS NULL
            OR metodo_conciliacion IN ('INDIVIDUAL', 'MANUAL')
            """,
        )


def downgrade() -> None:
    """Revierte el snapshot histórico de las facturas."""

    # Reparación realizada por este upgrade.
    with op.batch_alter_table(
        "movimiento_previsto",
        schema=None,
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_movimiento_previsto_metodo_conciliacion",
            type_="check",
        )

    # Recuperar tipo con un valor genérico. La clasificación histórica
    # original ya no puede reconstruirse de forma fiable.
    with op.batch_alter_table(
        "factura_linea",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tipo",
                sa.Text(),
                nullable=True,
            )
        )

    op.execute(
        """
        UPDATE factura_linea
        SET tipo = CASE
            WHEN orden = 1 THEN 'RENTA'
            ELSE 'OTRO'
        END
        """
    )

    with op.batch_alter_table(
        "factura_linea",
        schema=None,
    ) as batch_op:
        batch_op.alter_column(
            "tipo",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_factura_linea_tipo",
            """
            tipo IN (
                'RENTA',
                'DIFERENCIA_REVISION',
                'REPERCUSION_GASTO',
                'OTRO'
            )
            """,
        )

    op.drop_table("factura_destinatario")

    with op.batch_alter_table(
        "factura",
        schema=None,
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_factura_apunte_contable_id",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "uq_factura_apunte_contable_id",
            type_="unique",
        )

        batch_op.drop_column("apunte_contable_id")
        batch_op.drop_column("provincia_facturacion")
        batch_op.drop_column("poblacion_facturacion")
        batch_op.drop_column("codigo_postal_facturacion")
        batch_op.drop_column("direccion_facturacion")
        batch_op.drop_column("descripcion_inmueble")
        batch_op.drop_column("referencia_inmueble")

