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

## Licencia

Este proyecto se distribuye bajo la [Licencia MIT](LICENSE.md).
