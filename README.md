# contab

Aplicación web local de uso personal para la gestión económica derivada del alquiler de un pequeño número de inmuebles alquilados: facturación, control de ingresos y gastos y, especialmente, automatización asistida de la conciliación de movimientos bancarios.

No es un producto comercial ni pretende convertirse en:

- un programa contable generalista;
- una plataforma de gestión inmobiliaria para terceros;
- una aplicación multiempresa o multiusuario compleja;
- un sistema de banca electrónica;
- un gestor documental completo.


La descripción funcional, objetivos y alcance del proyecto se encuentran en [PROJECT.md](docs/PROJECT.md).

Se ha desarrollado para un amigo, con necesidades muy concretas y un volumen reducido de datos.

Se ha buscado una solución sencilla, evitando código destinado a situaciones hipotéticas. Y pensando que en caso de problemas con la aplicación, el usuario pueda seguir trabajando manualmente como hasta ahora.

La aplicación, escrita en Python con Flask, SQLAlchemy y SQLite, se ejecuta localmente en Linux (u otros OS) mediante una interfaz web. Cada contabilidad se mantiene en una base de datos independiente. Los documentos justificativos y las facturas continúan archivándose en el sistema de ficheros del usuario.

La arquitectura, herramientas, convenciones y estado del desarrollo se documentan en los distintos documentos en la carpeta docs:

- [Inmuebles, inquilinos y contratos](docs/Inmuebles, inquilinos y contratos.md).
- [Apuntes contables](docs/Ajustes-contables.md)
- [Importacion de datos bancarios](docs/Importacion-bancaria.md)
- [Conciliacion](docs/Conciliacion.md)
- [Facturacion](docs/Facturacion.md)
- [Informes contables](docs/Informes-contables.md)

## Entorno Python

Contab utiliza un entorno virtual independiente del Python y de los paquetes instalados globalmente en el sistema.

La rama de Python actualmente soportada es:

```text
Python 3.13
```

El entorno de referencia utilizado para desarrollo y pruebas se ha validado con Python 3.13.5.

`pyproject.toml` declara los rangos de versiones admitidos para las dependencias directas del proyecto.

`requirements.lock` conserva las versiones exactas del entorno conocido y probado. Su finalidad es permitir reconstruir ese entorno sin incorporar accidentalmente versiones nuevas de Flask, SQLAlchemy, Alembic u otras dependencias.

Las dependencias no deben actualizarse simplemente porque exista una versión nueva. Las actualizaciones se realizarán de forma deliberada, ejecutando después la suite completa de pruebas y las comprobaciones manuales que correspondan.

### Reconstrucción del entorno

Desde el directorio raíz del proyecto:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install -e .
pytest
```

La última orden debe dejar la suite completa en verde antes de considerar válido el entorno reconstruido.

El directorio `.venv` se considera regenerable y no forma parte de los datos permanentes de Contab.

Al adoptar en el futuro una nueva rama de Python o nuevas versiones de las dependencias, debe actualizarse de forma controlada:

1. crear un entorno virtual de prueba;
2. instalar las nuevas versiones;
3. ejecutar la suite completa;
4. realizar las pruebas manuales necesarias;
5. actualizar `pyproject.toml` si cambia la compatibilidad declarada;
6. regenerar `requirements.lock` con las versiones finalmente aceptadas.

## Licencia

Este proyecto se distribuye bajo la [Licencia MIT](LICENSE.md).
