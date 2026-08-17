# Desarrollo de contab

## 1. Entorno objetivo

La aplicación se desarrolla inicialmente para:

- Linux LMDE 7.
- Escritorio Xfce.
- Python 3.13.
- Ejecución local.
- Acceso mediante navegador web.

No se requiere ningún servicio externo para ejecutar la aplicación.

## 2. Tecnologías

Tecnologías iniciales:

- Python.
- Flask.
- SQLite.
- SQLAlchemy.
- Alembic.
- pytest.
- Jinja2/HTML para la interfaz web.
- Git.
- GitHub.

Se evitarán inicialmente frameworks JavaScript u otras dependencias que no
aporten una ventaja clara al proyecto.

Las nuevas dependencias se incorporarán sólo cuando exista una necesidad
concreta.

## 3. Arquitectura

La aplicación deberá mantener separadas:

- Presentación web.
- Lógica de negocio.
- Persistencia de datos.
- Generación de documentos e informes.

La lógica de negocio no deberá depender innecesariamente de Flask.

Por ejemplo, la generación de una factura deberá poder ejecutarse y probarse
sin necesidad de realizar una petición HTTP.

Esto facilitará las pruebas automatizadas y permitirá modificar la interfaz
sin afectar al núcleo de la aplicación.

## 4. Estructura inicial

La estructura inicial del repositorio es:

    contab/
    ├── docs/
    │   ├── PROJECT.md
    │   └── DEVELOPMENT.md
    ├── src/
    │   └── contab/
    │       ├── __init__.py
    │       └── app.py
    ├── tests/
    │   └── test_app.py
    ├── .gitignore
    ├── LICENSE.md
    ├── README.md
    └── pyproject.toml

Se utiliza el esquema `src/` para separar claramente el paquete Python del
resto del repositorio.

## 5. Entorno virtual

Cada árbol de trabajo dispone de su propio entorno virtual:

    .venv/

El entorno no se almacena en Git.

Creación:

    python3 -m venv .venv

Activación:

    source .venv/bin/activate

El proyecto se instala durante el desarrollo en modo editable:

    python -m pip install -e .

De esta forma las modificaciones realizadas en `src/contab` están
inmediatamente disponibles sin reinstalar el paquete.

## 6. Base de datos

Se utilizará SQLite.

SQLAlchemy proporcionará la capa de acceso y modelado.

Las modificaciones del esquema se gestionarán mediante Alembic para permitir
actualizar bases de datos existentes sin destruir sus datos.

La base de datos real y cualquier información privada del usuario nunca se
almacenarán en el repositorio Git.

Los datos utilizados por las pruebas serán ficticios.

## 7. Pruebas

Se utilizará pytest.

El proyecto tendrá:

- Pruebas unitarias para lógica aislada.
- Pruebas de integración para operaciones completas.
- Bases de datos temporales específicas para las pruebas.

Las pruebas nunca deberán utilizar la base de datos real.

Antes de considerar estable un cambio deberá ejecutarse:

    pytest

Las pruebas automatizadas deberán crecer junto con la funcionalidad del
programa.

## 8. Git

El repositorio remoto se mantiene en GitHub.

Ramas principales:

### master

Contiene versiones consideradas estables y potencialmente utilizables por el
usuario.

### develop

Rama habitual de desarrollo e integración.

La nueva funcionalidad se incorpora inicialmente a `develop` y posteriormente
se consolida en `master` cuando constituye un incremento suficientemente
estable.

### Ramas auxiliares

Cuando sea necesario interrumpir temporalmente el trabajo de `develop` para
realizar una modificación aislada, podrá crearse una rama específica.

Por ejemplo:

    feature/nombre
    fix/nombre
    PR227

No se establece una categoría especial para hotfixes: una corrección urgente
se tratará como cualquier otro desarrollo aislado que deba completarse antes
de continuar con el trabajo principal.

## 9. Git worktree

Los diferentes árboles de trabajo se gestionan mediante `git worktree`.

La estructura inicial es:

    contab/
    ├── master/
    └── develop/

Cada árbol dispone de su propio `.venv`.

No se prevé normalmente trabajar simultáneamente en varias ramas, pero esta
estructura permite mantener árboles separados cuando sea necesario.

## 10. Estado actual

La infraestructura inicial está operativa.

Actualmente se dispone de:

- Repositorio Git local.
- Repositorio privado en GitHub.
- Ramas `master` y `develop`.
- Worktrees independientes.
- Entorno virtual Python.
- Proyecto instalable en modo editable.
- Flask funcionando localmente.
- pytest funcionando.
- Primer smoke test de la aplicación web.

El servidor de desarrollo puede ejecutarse mediante:

    flask --app contab.app:create_app run

La prueba actual verifica que la aplicación responde correctamente a una
petición HTTP básica.

## 11. Próximo paso

El siguiente incremento será diseñar la primera versión del modelo de datos.

Inicialmente se estudiarán las entidades necesarias para:

- Inmuebles.
- Inquilinos.
- Contratos.
- Histórico de rentas.

El esquema se diseñará antes de implementar los modelos SQLAlchemy y las
migraciones Alembic.
