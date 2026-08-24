"""Define las rutas web para consultar y mantener inquilinos."""

from flask import Blueprint, redirect, render_template, request, url_for
from sqlalchemy import select

from contab.context import get_database_name, get_session_factory
from contab.models import Inquilino


bp = Blueprint(
    "inquilinos",
    __name__,
    url_prefix="/inquilinos",
    template_folder="templates",
)


def _validar_datos_inquilino(datos) -> tuple[dict, str | None]:
    """Valida los datos del formulario y devuelve valores normalizados."""
    if not datos["nombre"].strip():
        return {}, "El nombre es obligatorio."

    if not datos["nif"].strip():
        return {}, "El NIF es obligatorio."

    valores = {
        "nombre": datos["nombre"].strip(),
        "nif": datos["nif"].strip(),
        "direccion": datos["direccion"].strip() or None,
        "codigo_postal": datos["codigo_postal"].strip() or None,
        "poblacion": datos["poblacion"].strip() or None,
        "provincia": datos["provincia"].strip() or None,
        "email": datos["email"].strip() or None,
        "telefono": datos["telefono"].strip() or None,
        "notas": datos["notas"].strip() or None,
    }

    return valores, None


def _buscar_nif_duplicado(
    session,
    nif: str,
    excluir_id: int | None = None,
) -> str | None:
    """Detecta si el NIF ya pertenece a otro inquilino."""
    inquilino = session.scalar(
        select(Inquilino).where(
            Inquilino.nif == nif
        )
    )

    if inquilino is not None and inquilino.id != excluir_id:
        return "Ya existe un inquilino con ese NIF."

    return None


@bp.get("/")
def listar_inquilinos():
    """Muestra el listado de inquilinos registrados."""
    session_factory = get_session_factory()

    with session_factory() as session:
        inquilinos = session.scalars(
            select(Inquilino).order_by(Inquilino.nombre)
        ).all()

        return render_template(
            "inquilinos/lista.html",
            inquilinos=inquilinos,
            database_name=get_database_name(),
        )


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo_inquilino():
    """Permite introducir y guardar un nuevo inquilino."""
    if request.method == "GET":
        return render_template(
            "inquilinos/formulario.html",
            titulo="Nuevo inquilino",
            datos={},
            error=None,
            database_name=get_database_name(),
        )

    valores, error = _validar_datos_inquilino(request.form)

    if error:
        return (
            render_template(
                "inquilinos/formulario.html",
                titulo="Nuevo inquilino",
                datos=request.form,
                error=error,
                database_name=get_database_name(),
            ),
            400,
        )

    session_factory = get_session_factory()

    with session_factory() as session:
        with session.begin():
            error = _buscar_nif_duplicado(
                session,
                valores["nif"],
            )

            if error:
                return (
                    render_template(
                        "inquilinos/formulario.html",
                        titulo="Nuevo inquilino",
                        datos=request.form,
                        error=error,
                        database_name=get_database_name(),
                    ),
                    400,
                )

            inquilino = Inquilino(**valores)
            session.add(inquilino)

    return redirect(url_for("inquilinos.listar_inquilinos"))


@bp.route("/<int:inquilino_id>/editar", methods=["GET", "POST"])
def editar_inquilino(inquilino_id: int):
    """Permite modificar los datos de un inquilino existente."""
    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            inquilino = session.get(Inquilino, inquilino_id)

            if inquilino is None:
                return "Inquilino no encontrado.", 404

            datos = {
                "nombre": inquilino.nombre,
                "nif": inquilino.nif,
                "direccion": inquilino.direccion or "",
                "codigo_postal": inquilino.codigo_postal or "",
                "poblacion": inquilino.poblacion or "",
                "provincia": inquilino.provincia or "",
                "email": inquilino.email or "",
                "telefono": inquilino.telefono or "",
                "notas": inquilino.notas or "",
            }

            return render_template(
                "inquilinos/formulario.html",
                titulo="Editar inquilino",
                datos=datos,
                error=None,
                database_name=get_database_name(),
            )

    valores, error = _validar_datos_inquilino(request.form)

    if error:
        return (
            render_template(
                "inquilinos/formulario.html",
                titulo="Editar inquilino",
                datos=request.form,
                error=error,
                database_name=get_database_name(),
            ),
            400,
        )

    with session_factory() as session:
        with session.begin():
            inquilino = session.get(Inquilino, inquilino_id)

            if inquilino is None:
                return "Inquilino no encontrado.", 404

            error = _buscar_nif_duplicado(
                session,
                valores["nif"],
                excluir_id=inquilino.id,
            )

            if error:
                return (
                    render_template(
                        "inquilinos/formulario.html",
                        titulo="Editar inquilino",
                        datos=request.form,
                        error=error,
                        database_name=get_database_name(),
                    ),
                    400,
                )

            for campo, valor in valores.items():
                setattr(inquilino, campo, valor)

    return redirect(url_for("inquilinos.listar_inquilinos"))



def test_formulario_editar_inquilino_muestra_datos_actuales() -> None:
    """Comprueba que el formulario de edición muestra los datos existentes."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
            direccion="Dirección inicial",
            email="ana@example.com",
        )
        session.add(inquilino)
        session.commit()
        inquilino_id = inquilino.id

    response = client.get(f"/inquilinos/{inquilino_id}/editar")

    assert response.status_code == 200
    assert "Editar inquilino" in response.text
    assert 'value="Ana Pérez"' in response.text
    assert 'value="11111111A"' in response.text
    assert 'value="ana@example.com"' in response.text


def test_editar_inquilino_guarda_cambios() -> None:
    """Comprueba que los cambios realizados en un inquilino se guardan."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )
        session.add(inquilino)
        session.commit()
        inquilino_id = inquilino.id

    response = client.post(
        f"/inquilinos/{inquilino_id}/editar",
        data={
            "nombre": "Ana Pérez García",
            "nif": "11111111A",
            "direccion": "Nueva dirección",
            "codigo_postal": "36001",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "email": "nueva@example.com",
            "telefono": "600123456",
            "notas": "Actualizado",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Ana Pérez García" in response.text

    with session_factory() as session:
        inquilino = session.get(Inquilino, inquilino_id)

        assert inquilino.nombre == "Ana Pérez García"
        assert inquilino.direccion == "Nueva dirección"
        assert inquilino.email == "nueva@example.com"


def test_editar_inquilino_rechaza_nif_de_otro_inquilino() -> None:
    """Comprueba que la edición no puede duplicar el NIF de otro inquilino."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        primero = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )
        segundo = Inquilino(
            nombre="Luis García",
            nif="22222222B",
        )

        session.add_all([primero, segundo])
        session.commit()

        segundo_id = segundo.id

    response = client.post(
        f"/inquilinos/{segundo_id}/editar",
        data={
            "nombre": "Luis García",
            "nif": "11111111A",
            "direccion": "",
            "codigo_postal": "",
            "poblacion": "",
            "provincia": "",
            "email": "",
            "telefono": "",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "Ya existe un inquilino con ese NIF." in response.text


def test_editar_inquilino_inexistente_devuelve_404() -> None:
    """Comprueba que editar un inquilino inexistente devuelve 404."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.get("/inquilinos/99999/editar")

    assert response.status_code == 404

