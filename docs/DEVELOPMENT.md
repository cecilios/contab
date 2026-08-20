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

Por ejemplo, el cálculo de la renta aplicable a un mes, una revisión de renta
o la generación de una factura deberán poder ejecutarse y probarse sin
necesidad de realizar una petición HTTP.

Esto facilitará las pruebas automatizadas y permitirá modificar la interfaz
sin afectar al núcleo de la aplicación.

Las reglas de negocio se documentan en:

    docs/BUSINESS_RULES.md

Este documento constituye la referencia funcional para la implementación del
modelo de datos y de la lógica de negocio.

## 4. Estructura inicial

La estructura actual del repositorio es:

    contab/
    ├── docs/
    │   ├── BUSINESS_RULES.md
    │   ├── DEVELOPMENT.md
    │   └── PROJECT.md
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

La estructura interna de `src/contab` se ampliará cuando se implementen la
persistencia y la lógica de negocio.

No se crearán módulos anticipadamente sin una necesidad concreta.

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

## Arquitectura de la aplicación

Contab se desarrollará como un **monolito modular**.

La aplicación utilizará:

- un único proceso;
- un único servidor web Flask;
- una única base de datos SQLite;
- módulos funcionales claramente separados.

La modularidad se realizará dentro de la propia aplicación, evitando
servidores, procesos o bases de datos independientes para cada módulo.
Flask actuará como punto de entrada y ensamblará los distintos módulos,
preferentemente mediante *Blueprints*.

La estructura funcional prevista inicialmente es:

- `inmuebles`: mantenimiento de inmuebles;
- `inquilinos`: mantenimiento de inquilinos;
- `contratos`: contratos, rentas, revisiones y ajustes de renta;
- `previsiones`: previsiones de gastos;
- `facturacion`: generación y gestión de facturas;
- `conciliacion`: importación y conciliación de movimientos bancarios;
- `contabilidad`: elaboración de la información contable;
- `informes`: informes que combinen información de distintas áreas.

Esta división es inicial y podrá evolucionar conforme se desarrolle la
aplicación. En particular, las previsiones de gastos y los informes podrán
reorganizarse si la lógica de negocio aconseja otra agrupación.

Cada módulo deberá mantener separadas, en la medida en que resulte útil,
la interfaz web y la lógica de negocio. Una estructura típica será:

    modulo/
        routes.py
        services.py
        templates/

`routes.py` se ocupará de la interacción HTTP y la interfaz web, mientras
que `services.py` contendrá la lógica de negocio. La lógica de negocio no
deberá depender innecesariamente de Flask, de forma que pueda probarse
directamente mediante tests automatizados.

`app.py` tendrá principalmente la responsabilidad de crear y configurar
la aplicación Flask, registrar los módulos y proporcionar la entrada
general a la aplicación. No deberá acumular lógica propia de los módulos.

Los distintos módulos compartirán los modelos SQLAlchemy y la misma base
de datos. La separación modular es una separación de responsabilidades
del código, no una arquitectura de microservicios.

Las URL seguirán igualmente una organización modular, por ejemplo:

    /
    /inmuebles/
    /inquilinos/
    /contratos/
    /facturacion/
    /previsiones/
    /conciliacion/
    /contabilidad/
    /informes/

Todos estos recursos serán servidos por el mismo servidor Flask y el mismo
puerto.

Los informes específicos de una funcionalidad pertenecerán, en principio,
al módulo correspondiente. El módulo `informes` se reservará principalmente
para informes que combinen información procedente de varias áreas.

Esta arquitectura deberá favorecer que una implementación pueda sustituirse
o convivir temporalmente con otra durante su desarrollo y pruebas, sin
afectar innecesariamente al resto de la aplicación.



## 6. Base de datos

Se utilizará SQLite.

SQLAlchemy proporcionará la capa de acceso y modelado.

Las modificaciones del esquema se gestionarán mediante Alembic para permitir
actualizar bases de datos existentes sin destruir sus datos.

La base de datos real y cualquier información privada del usuario nunca se
almacenarán en el repositorio Git.

Los datos utilizados por las pruebas serán ficticios.

### 6.1. Criterios de modelado

Los campos de texto se representarán generalmente mediante `TEXT`.

Los importes monetarios se almacenarán como enteros expresados en céntimos.

Los porcentajes que necesiten dos decimales se almacenarán como enteros
expresados en centésimas de punto porcentual.

Ejemplos:

    1.250,37 EUR -> 125037
       21,00 %   -> 2100
       32,56 %   -> 3256

Se evitará almacenar información derivable cuando mantenerla duplicada pueda
producir inconsistencias.

Las restricciones estructurales sencillas se implementarán en la base de
datos mediante:

- `NOT NULL`.
- `UNIQUE`.
- claves externas.
- `CHECK`.

Las reglas que dependan de varias entidades, periodos temporales o procesos de
negocio se implementarán principalmente en la lógica de aplicación y estarán
cubiertas por pruebas automatizadas.

### 6.2. Modelo inicial

El modelo funcional inicial está compuesto por:

    inmueble
    inquilino
    contrato
    contrato_inquilino
    renta_contrato
    revision_renta
    ajuste_renta

La definición funcional y las reglas de estas entidades se mantienen en
`BUSINESS_RULES.md`.

La renta vigente no se almacenará directamente en `contrato`.

Se obtendrá del histórico `renta_contrato`.

Las revisiones previstas y realizadas se almacenarán separadamente mediante
`revision_renta`.

Las modificaciones temporales de la cantidad facturada se representarán
mediante `ajuste_renta`, sin modificar la renta ordinaria.

Esta separación permitirá calcular la renta facturable para un mes siguiendo
conceptualmente:

    renta ordinaria vigente
            ↓
    ajuste temporal vigente, si existe
            ↓
    renta facturable

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

Las reglas de negocio relevantes deberán tener pruebas específicas.

En particular, el modelo inicial deberá probar, entre otras situaciones:

- Restricciones de las tablas.
- Relaciones entre entidades.
- Contratos con varios titulares.
- Ausencia de contratos simultáneos para un mismo inmueble.
- Histórico de rentas.
- Revisiones positivas, negativas y no aplicadas.
- Generación de la siguiente revisión anual.
- Ajustes temporales.
- Cambios de renta ordinaria durante un ajuste temporal.
- Rechazo de ajustes solapados.
- Inactivación de inmuebles con contratos vigentes.

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

### 8.1. Mensajes de commit

Los mensajes de commit se redactarán preferentemente en español y comenzarán
con un verbo en infinitivo.

Ejemplos:

    Añadir documentación inicial del proyecto
    Crear modelos iniciales de la base de datos
    Implementar revisión anual de rentas
    Corregir cálculo de ajustes temporales

## 9. Git worktree

Los diferentes árboles de trabajo se gestionan mediante `git worktree`.

La estructura inicial es:

    contab/
    ├── master/
    └── develop/

Cada árbol dispone de su propio `.venv`.

No se prevé normalmente trabajar simultáneamente en varias ramas, pero esta
estructura permite mantener árboles separados cuando sea necesario.

## 10. Estrategia de desarrollo

El desarrollo será incremental y cada etapa deberá dejar una aplicación
verificable.

El orden inicial previsto es:

1. Infraestructura básica de la aplicación.
2. Modelo de inmuebles, inquilinos y contratos.
3. Histórico de rentas y datos necesarios para sus revisiones.
4. Interfaz web para introducir y mantener estos datos.
5. Generación automática de facturas.
6. Registro automático de ingresos pendientes.
7. Previsiones de gastos.
8. Importación de movimientos bancarios.
9. Conciliación bancaria asistida.
10. Informes y exportaciones.

Aunque la conciliación bancaria constituye el principal objetivo funcional de
`contab`, las primeras etapas proporcionarán los datos fiables necesarios para
poder realizarla posteriormente.

La facturación constituye la primera funcionalidad que aportará utilidad
directa al usuario después de introducir los datos iniciales.

Por ello, el modelo de rentas y revisiones debe estar suficientemente definido
antes de implementar la facturación.

## 11. Estado actual

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
- Documentación de objetivos del proyecto.
- Documentación de desarrollo.
- Documento de reglas de negocio.
- Primera definición conceptual del modelo de datos.

El servidor de desarrollo puede ejecutarse mediante:

    flask --app contab.app:create_app run

La prueba actual verifica que la aplicación responde correctamente a una
petición HTTP básica.

Todavía no se ha implementado la base de datos ni existen modelos SQLAlchemy.

## 12. Próximo paso

Antes de escribir los modelos SQLAlchemy se realizará una revisión conjunta
final del modelo compuesto por:

    inmueble
    inquilino
    contrato
    contrato_inquilino
    renta_contrato
    revision_renta
    ajuste_renta

Se comprobarán:

- Campos.
- Tipos.
- Obligatoriedad y valores nulos.
- Claves primarias.
- Claves externas.
- Restricciones `UNIQUE`.
- Restricciones `CHECK`.
- Relaciones.
- Reglas que deben implementarse en la lógica de negocio.

Una vez aprobado el modelo se procederá a:

1. Configurar SQLAlchemy y SQLite.
2. Implementar los modelos.
3. Configurar Alembic.
4. Crear la primera migración.
5. Crear las pruebas del modelo y sus restricciones.
6. Verificar la creación y consulta de datos de prueba.

Sólo después se comenzará la interfaz web de mantenimiento de estos datos.
