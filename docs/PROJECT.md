# Proyecto Contab
=================

## 1. Propósito del documento
-----------------------------

Este documento define el propósito, el alcance y los principios rectores de Contab.

Debe servir para comprobar si una decisión o funcionalidad encaja en el proyecto, especialmente cuando se retome el desarrollo después de un tiempo o participe una persona que no conozca su origen.

No describe el estado de implementación ni la operativa detallada de los módulos. Esa información se mantiene en sus documentos específicos:

- `Inmuebles, inquilinos y contratos.md`;
- `Ajustes-contables.md`;
- `Informes-contables.md`;
- `Importacion-bancaria.md`;
- `Conciliacion.md`;
- `Facturacion.md`;
- `DEVELOPMENT.md`, para el contexto técnico de desarrollo.

## 2. Contexto y alcance
-----------------------

Contab es una aplicación personal para gestionar la actividad económica derivada del alquiler de un pequeño número de inmuebles.

El usuario es un propietario particular con menos de diez unidades alquilables. Existen pisos, plazas de garaje y locales comerciales, algunos pertenecientes a un inmueble subdividido.

No es un producto comercial ni pretende convertirse en:

- un programa contable generalista;
- una plataforma de gestión inmobiliaria para terceros;
- una aplicación multiempresa o multiusuario compleja;
- un sistema de banca electrónica;
- un gestor documental completo.

Se desarrolla para un usuario conocido, con necesidades concretas y un volumen reducido de datos. Esta circunstancia debe aprovecharse para elegir soluciones sencillas y evitar código destinado a situaciones hipotéticas.

La aplicación se ejecuta localmente en Linux mediante una interfaz web. Cada contabilidad se mantiene en una base de datos independiente. Los documentos justificativos y las facturas continúan archivándose en el sistema de ficheros del usuario.

## 3. Objetivos fundamentales
-----------------------------

Contab tiene dos objetivos prioritarios.

### 3.1. Conciliación bancaria
.............................

Reducir el tiempo dedicado a revisar movimientos bancarios y averiguar a qué ingreso, gasto e inmueble corresponde cada uno.

La aplicación debe ayudar a:

- registrar cobros y pagos esperados;
- importar los movimientos reales del banco;
- proponer correspondencias mediante criterios comprensibles;
- destacar las excepciones que requieren investigación;
- identificar cobros pendientes y justificantes ausentes;
- producir un resultado verificable por el usuario.

La conciliación será asistida. Contab propone, pero el usuario conserva la decisión final.

### 3.2. Información contable flexible
.......................................

Registrar cada hecho económico una sola vez y poder agruparlo posteriormente con criterios diferentes.

Las exigencias fiscales, especialmente las relativas al IRPF, pueden variar entre ejercicios. La contabilidad no debe quedar ligada a la estructura del formulario de un año concreto.

Contab debe conservar los datos económicos con suficiente detalle para generar informes y agrupaciones nuevas sin reconstruir manualmente la contabilidad del ejercicio.

### 3.3. Funciones auxiliares
............................

Inmuebles, inquilinos, contratos, rentas, revisiones y facturación sirven para alimentar correctamente la contabilidad y la conciliación.

No son fines independientes. Su desarrollo debe justificarse por su aportación a los dos objetivos principales, por el ahorro de trabajo o por la reducción de errores relevantes.

## 4. Resultado esperado
------------------------

Contab debe conseguir que el usuario:

- registre cada ingreso o gasto una sola vez;
- sustituya sus anotaciones provisionales en papel por apuntes directamente utilizables;
- dedique la revisión bancaria principalmente a resolver excepciones;
- conozca qué cobros, pagos o justificantes siguen pendientes;
- obtenga la información trimestral sin transcribir previamente un cuaderno;
- adapte los informes anuales a nuevos criterios fiscales sin rehacer los datos;
- mantenga el control sobre las decisiones automáticas;
- pueda recurrir a su operativa manual ante una situación excepcional.

La aplicación debe reducir trabajo sin imponer procesos más pesados que los que sustituye.

## 5. Principios rectores
-------------------------

### 5.1. Priorizar el valor real
...............................

Toda funcionalidad debe evaluarse por su contribución a la conciliación, a la información contable o al ahorro comprobable de trabajo.

Si una función no reduce esfuerzo, no evita errores importantes y no resulta necesaria para los objetivos principales, debe aplazarse.

El número de funciones no es una medida de éxito. Lo son el tiempo ahorrado, la reducción de errores y la claridad del resultado.

### 5.2. Diseñar para el usuario real
....................................

Las decisiones deben responder al volumen y la operativa reales: un usuario conocido y menos de diez inmuebles.

No se desarrollarán flujos complejos para cubrir anticipadamente necesidades propias de una aplicación comercial. Una operación excepcional puede resolverse manualmente si automatizarla añade más coste que valor.

El feedback del cliente y los casos reales tienen prioridad sobre las posibilidades teóricas.

### 5.3. Modelo previsor, operativa mínima
..........................................

El modelo de datos puede incorporar algún dato adicional cuando su necesidad futura sea estable, clara y barata de prever. Esto puede evitar migraciones y revisiones transversales posteriores.

En cambio, las pantallas, procesos y reglas sólo se desarrollarán cuando exista una necesidad concreta.

Se distinguen tres categorías:

1. **Necesario:** existe un uso actual y se implementa.
2. **Previsible:** el dato o la relación futura están suficientemente claros; pueden prepararse sin construir todavía su operativa.
3. **Hipotético:** depende de necesidades desconocidas y se aplaza por completo.

Guardar un dato no obliga a construir consultas históricas ni todas las operaciones imaginables sobre él.

### 5.4. Simplicidad y mantenibilidad
.....................................

Contab debe seguir siendo una aplicación pequeña, comprensible y fácil de modificar.

Se prefiere:

- código directo frente a abstracciones prematuras;
- módulos claros frente a arquitecturas distribuidas;
- procesos cortos y explícitos;
- reglas de negocio centralizadas y reutilizables;
- configuraciones editables cuando eviten pantallas de mantenimiento sin valor;
- mejoras incrementales que puedan comprobarse de forma aislada.

Una solución sencilla que cubra el caso real es preferible a otra más general que incremente el mantenimiento.

### 5.5. Robustez mediante pruebas
..................................

El código de pruebas no se considera complejidad innecesaria. Las pruebas aportan seguridad para realizar pequeñas modificaciones y mantener la aplicación durante años.

Cada cambio debe proteger:

- las reglas relevantes del dominio;
- los flujos completos de los formularios;
- la presentación de los errores al usuario;
- las operaciones coordinadas entre varios registros;
- las migraciones de datos.

Las pruebas deben ser comprensibles y, cuando representen varios pasos, incluir comentarios que expliquen la acción simulada.

### 5.6. Control del usuario
...........................

La automatización debe ser transparente. El usuario debe poder revisar, confirmar y corregir la información.

Contab no debe:

- ocultar por qué propone una decisión;
- confirmar conciliaciones dudosas sin intervención;
- impedir resolver manualmente una excepción;
- crear una dependencia innecesaria respecto a la aplicación.

Los documentos permanecen accesibles en el sistema de ficheros y la operativa manual continúa siendo una alternativa válida.

### 5.7. Introducción única de datos
....................................

Cada hecho económico debe registrarse una sola vez.

A partir de ese registro, Contab debe reutilizar los datos para contabilidad, conciliación, informes y, cuando corresponda, facturación.

Debe evitarse que el usuario transcriba la misma información entre cuadernos, hojas de cálculo o distintas pantallas de la aplicación.

### 5.8. Datos independientes de los informes
..............................................

La clasificación económica estable de un apunte no debe confundirse con la agrupación exigida por Hacienda en un ejercicio determinado.

Los apuntes conservan la naturaleza económica del hecho. Los informes traducen después esa clasificación a los criterios fiscales o de gestión necesarios.

Un cambio en un formulario fiscal debe resolverse modificando la agrupación del informe, siempre que los datos originales tengan detalle suficiente, y no alterando o reconstruyendo los hechos contables.

### 5.9. Preservación de las fuentes
....................................

La información original debe conservarse cuando sea necesaria para verificar el resultado:

- los movimientos bancarios mantienen los textos proporcionados por el banco;
- los apuntes conservan la referencia del documento justificativo;
- las facturas y justificantes permanecen archivados en el sistema de ficheros;
- las clasificaciones y conciliaciones no sustituyen ni deforman la fuente original.

Contab registra relaciones e interpretaciones, pero no debe destruir la evidencia que permite revisarlas.

### 5.10. Operaciones coherentes
...............................

Las acciones que producen varios efectos deben completarse de forma conjunta.

Por ejemplo, una futura emisión de factura deberá coordinar la factura, sus líneas, el apunte contable y el movimiento previsto. Si una parte falla, no debe quedar una operación incompleta.

Las correcciones deben respetar las relaciones ya confirmadas, especialmente cuando existan movimientos conciliados.

### 5.11. Desarrollo guiado por casos reales
.............................................

Los algoritmos y automatizaciones se mejorarán a partir de datos reales del cliente.

En conciliación se prefieren inicialmente reglas deterministas y comprensibles. Sólo se añadirá complejidad cuando se compruebe que mejora de forma apreciable el resultado.

En facturación, informes y tratamiento fiscal se implementarán las variantes que el usuario necesite realmente, no todas las que puedan imaginarse.

## 6. Criterios económicos y documentales
------------------------------------------

Se aplican las siguientes convenciones generales:

- los importes monetarios se manejan con precisión de céntimos;
- los porcentajes se conservan con la precisión necesaria para los cálculos;
- los importes contables son positivos y su naturaleza indica si son ingresos o gastos;
- los números definitivos, como los de factura, se asignan únicamente al confirmar la operación;
- el sistema de ficheros sigue siendo el archivo principal de facturas y justificantes;
- Contab conserva las referencias necesarias para relacionar los documentos con la contabilidad.

No se almacenarán datos únicamente por si algún día pudieran resultar útiles. Todo dato debe tener una finalidad necesaria o razonablemente previsible.

## 7. Criterios para decidir nuevas funciones
---------------------------------------------

Antes de incorporar una nueva funcionalidad deben responderse estas preguntas:

1. ¿Contribuye a la conciliación o a los informes contables?
2. ¿Reduce trabajo real o evita un error relevante?
3. ¿Existe un caso de uso observado?
4. ¿Puede resolverse de forma manual con un coste razonable?
5. ¿La solución propuesta es proporcional a menos de diez inmuebles?
6. ¿Añade mantenimiento permanente para resolver una necesidad temporal?
7. ¿Puede prepararse sólo el dato y posponer la operativa?
8. ¿Quedará protegida por pruebas claras?

Si las respuestas no justifican el coste, la función debe aplazarse.

## 8. Criterios de éxito
------------------------

Contab tendrá éxito si:

- reduce de forma apreciable el tiempo dedicado a la conciliación;
- permite mantener la contabilidad al día con una sola entrada de datos;
- facilita localizar errores, ausencias y movimientos pendientes;
- genera información fiscal adaptable sin reconstrucciones anuales;
- mantiene una operativa sencilla para el usuario;
- continúa siendo comprensible y barata de mantener;
- conserva la confianza y el control del usuario sobre sus datos y documentos.

El alcance debe permanecer subordinado a estos resultados.
