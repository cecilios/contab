# Proyecto Contab

## 1. Propósito del documento

Este documento resume el contexto, el alcance y los principios rectores de
Contab. Su objetivo es permitir que cualquier persona que retome el proyecto
entienda rápidamente:

- qué problemas reales debe resolver;
- cómo trabaja actualmente el usuario;
- qué resultado se espera alcanzar;
- qué está construido y qué queda pendiente;
- qué decisiones de alcance se han tomado;
- y qué criterios deben guiar cualquier desarrollo futuro.

Las reglas detalladas del dominio se documentan en `BUSINESS_RULES.md` y las
decisiones técnicas y de desarrollo en `DEVELOPMENT.md`. En caso de duda, este
documento debe servir para comprobar si una funcionalidad aporta valor a los
objetivos principales del proyecto.

## 2. Contexto y alcance

Contab es una aplicación personal para gestionar la actividad de alquiler de
un pequeño propietario. El usuario dispone de menos de diez inmuebles: pisos y
locales comerciales, alguno de ellos dividido en varias unidades arrendadas.

No es un producto comercial ni pretende convertirse en un sistema contable
generalista. Se desarrolla para un único usuario conocido, con necesidades
concretas y un volumen reducido de datos. Esta circunstancia permite elegir
soluciones sencillas y evitar código destinado a casuísticas improbables.

La aplicación se ejecuta localmente en Linux, mediante una interfaz web Flask,
y utiliza SQLite. Los documentos justificativos y las facturas continúan
archivándose en el sistema de ficheros del usuario.

## 3. Objetivos fundamentales

Contab tiene dos objetivos prioritarios.

### 3.1. Conciliación bancaria

Reducir el tiempo que el usuario dedica a revisar los movimientos bancarios y
averiguar a qué ingreso o gasto y a qué inmueble corresponde cada uno.

La aplicación debe ayudar a:

- registrar los cobros y pagos esperados;
- importar los movimientos reales del banco;
- proponer correspondencias de forma transparente;
- identificar rápidamente las excepciones;
- y producir un resultado de conciliación comprensible y verificable.

### 3.2. Información contable flexible

Registrar una sola vez los ingresos y gastos de cada inmueble y poder
agruparlos posteriormente con distintos criterios.

Las exigencias de los formularios fiscales, especialmente las del IRPF, pueden
cambiar de un ejercicio a otro. La contabilidad no debe quedar atada a la
estructura del formulario de un año concreto. Contab debe conservar datos
económicos suficientemente desglosados y permitir que su agrupación para los
informes se configure por ejercicio.

Los demás módulos —contratos, rentas, revisiones y facturación— son medios para
alimentar correctamente estos dos objetivos, no fines independientes.

## 4. Operativa manual actual

### 4.1. Facturación

El usuario genera las facturas manualmente a partir de plantillas de
LibreOffice Calc (`.ods`), normalmente la última factura emitida para cada
inmueble. Actualiza el número, la fecha, el periodo, la renta y, cuando
corresponde, el texto de revisión. Después exporta el documento a PDF, lo
archiva en la carpeta del inmueble y lo envía al inquilino.

Mantiene además una hoja de control con la renta vigente y la próxima fecha de
revisión. Como existen pocos contratos, la facturación mensual completa tarda
aproximadamente media hora. El método actual ofrece mucha flexibilidad para
corregir errores, añadir conceptos o emitir facturas extraordinarias.

Por ello, informatizar únicamente la introducción de los datos de la factura,
sin generar automáticamente el PDF, duplicaría trabajo y aportaría poco valor.

### 4.2. Contabilidad y conciliación

La mayoría de las facturas de gastos llegan por correo electrónico. Al
recibirlas, el usuario anota manualmente el gasto en un cuaderno dedicado a la
contabilidad del inmueble.

Periódicamente, como mínimo una vez al mes y antes de la siguiente
facturación, revisa los movimientos bancarios. Concilia los cobros y pagos y
descarga los justificantes de aquellos gastos que no producen una factura por
correo, como determinados impuestos o seguros. Esos gastos también se anotan
en el cuaderno.

Trimestralmente, los apuntes del cuaderno se transcriben a la hoja de cálculo
que actúa como contabilidad oficial. Se suman ingresos y gastos, se comprueba
que todo cuadra y se resuelven las diferencias antes de preparar las
declaraciones fiscales correspondientes.

Anualmente, al preparar el IRPF, la contabilidad del ejercicio anterior debe
reagruparse conforme al formulario vigente de Hacienda. Cuando dicho formulario
cambia o exige más detalle, parte del trabajo realizado durante el año debe
reconstruirse manualmente.

## 5. Situación futura con Contab

### 5.1. Registro único de la información

Cada hecho económico debe introducirse una sola vez. A partir de ese registro,
Contab generará o relacionará, cuando corresponda:

- el apunte contable;
- el movimiento esperado para conciliación;
- la referencia al documento justificativo;
- y, en el futuro, la factura emitida y sus archivos.

La aplicación debe evitar transcripciones sucesivas entre cuadernos, hojas de
cálculo y herramientas de conciliación.

### 5.2. Trabajo contable habitual

Cuando se reciba una factura de gasto, el usuario la registrará directamente
como apunte contable. En la misma operación podrá crearse el movimiento
previsto correspondiente, sin volver a introducir los datos.

Los ingresos periódicos podrán generarse a partir de los contratos y sus
rentas vigentes, incluso antes de automatizar la emisión de facturas.

Si aparece en el banco un gasto que aún no estaba registrado, la futura
pantalla de conciliación permitirá crear el apunte desde el propio movimiento
bancario, reutilizando su fecha, importe, concepto y ordenante o emisor. El
usuario sólo completará los datos que el banco no pueda proporcionar, como el
inmueble y la clasificación contable.

### 5.3. Conciliación periódica

El usuario descargará del banco un fichero CSV y lo importará en Contab. La
aplicación conservará los datos originales y buscará correspondencias con los
movimientos previstos mediante reglas deterministas y comprensibles.

El resultado destacará principalmente las excepciones:

- movimientos bancarios sin correspondencia;
- apuntes o cobros previstos que aún no aparecen en el banco;
- diferencias de importe o fecha;
- posibles duplicados;
- justificantes pendientes;
- y rentas pendientes de cobro.

El usuario confirmará las propuestas dudosas. No se prevé utilizar aprendizaje
automático: con pocos inmuebles resultan preferibles reglas transparentes,
fáciles de probar y de mantener.

### 5.4. Declaraciones e informes

La contabilidad se mantendrá validada durante el año. Trimestralmente, el
usuario obtendrá directamente los datos necesarios para sus declaraciones,
sin transcribir previamente un cuaderno a una hoja de cálculo.

Anualmente, Contab agrupará los ingresos y gastos conforme a la configuración
del ejercicio fiscal. Un cambio en el formulario de Hacienda deberá resolverse,
si los datos originales tienen suficiente detalle, modificando la agrupación
del informe y no reconstruyendo la contabilidad.

En una primera etapa se ofrecerá una exportación CSV compatible con
LibreOffice. Después se incorporarán los informes contables que el usuario
necesite realmente.

### 5.5. Facturación futura

La automatización de la facturación sólo volverá a ser prioritaria cuando
incluya la generación efectiva de los archivos `.ods` y PDF. En ese momento
aportará sobre todo control, coherencia y reducción de errores, además de crear
automáticamente los apuntes contables y los movimientos previstos.

El PDF enviado al inquilino y archivado en el sistema de ficheros será el
documento operativo y justificativo. Contab conservará los datos necesarios
para sus procesos, pero no pretende sustituir el archivo documental del
usuario.

## 6. Principios rectores

### 6.1. Priorizar el valor real

Toda funcionalidad debe evaluarse por su contribución a la conciliación o a la
información contable. Si no reduce trabajo, evita errores relevantes o resulta
necesaria para esos objetivos, debe aplazarse.

La aplicación debe adaptarse al volumen real: menos de diez inmuebles y un
único usuario. No se desarrollarán flujos complejos para supuestos hipotéticos
propios de una aplicación comercial.

### 6.2. Modelo previsor, código e interfaz mínimos

El modelo de datos puede incorporar algún campo adicional cuando su necesidad
futura sea estable, clara y barata de prever. Esto evita migraciones y cambios
transversales posteriores.

En cambio, la lógica, las pantallas y los procesos sólo se implementarán cuando
sean necesarios. Se distinguen tres categorías:

1. **Necesario:** se conoce el uso actual y se implementa.
2. **Previsible:** el dato o la relación futura están suficientemente claros;
   pueden prepararse en el modelo, pero no se construye aún su operativa.
3. **Hipotético:** depende de necesidades desconocidas; se aplaza por completo.

Guardar un dato no obliga a crear pantallas para consultar su historia ni a
desarrollar todas las operaciones imaginables sobre él.

### 6.3. Simplicidad y mantenibilidad

Contab debe ser una aplicación pequeña, comprensible y fácil de modificar. Se
prefiere un monolito modular Flask/SQLAlchemy a una arquitectura distribuida.

Las reglas de negocio deben residir en funciones o servicios de dominio, no en
las rutas. Las operaciones coordinadas deben ejecutarse en una única
transacción.

Se evitará JavaScript para cálculos o reglas de negocio. Puede utilizarse de
forma puntual para pequeñas mejoras de interfaz, como imprimir la página o
limpiar un campo. Los cálculos relevantes se realizan y validan en el servidor.

### 6.4. Robustez mediante pruebas

El código de pruebas no se considera complejidad innecesaria. Cuantas más
pruebas útiles protejan las reglas del dominio y las pequeñas modificaciones
de mantenimiento, mejor.

Cada incremento debe ser pequeño, verificable y acompañado de pruebas. Las
migraciones se revisarán expresamente y se probarán sobre copias antes de
aplicarlas a los datos del usuario.

### 6.5. Control del usuario

El usuario debe conservar la capacidad de revisar y corregir la información.
La automatización propone y ejecuta operaciones claras, pero no oculta sus
decisiones ni crea dependencias innecesarias.

La conciliación será inicialmente asistida: las coincidencias dudosas requieren
confirmación. Los documentos permanecen accesibles en el sistema de ficheros y
los procesos manuales continúan siendo una alternativa válida ante una
excepción.

### 6.6. Datos independientes de los informes

La clasificación económica estable de un apunte no debe confundirse con la
casilla o agrupación exigida por Hacienda en un ejercicio concreto.

Los apuntes guardan categorías y subcategorías económicas. La configuración
anual de informes traduce esas categorías a las agrupaciones fiscales de cada
año. Así, cambiar un informe no obliga a alterar los hechos contables.

### 6.7. Preservación de las fuentes

Los movimientos bancarios importados deberán conservarse sin modificaciones.
La conciliación y las clasificaciones se almacenarán aparte. Los documentos
justificativos seguirán archivados en el sistema de ficheros y se referenciarán
desde Contab cuando resulte útil.

### 6.8. Convenciones económicas

- Los importes monetarios se almacenan en céntimos.
- Los porcentajes se almacenan en puntos básicos cuando corresponda.
- Los importes de los apuntes contables son positivos; su naturaleza
  (`INGRESO` o `GASTO`) determina el signo económico.
- Los números y registros definitivos se asignan dentro de transacciones
  atómicas.

## 7. Alcance funcional y situación actual

### 7.1. Versión 0.1.0 entregada

La primera versión está instalada en el equipo del cliente y permite iniciar
la carga de datos y obtener feedback real. Incluye, en esencia:

- configuración y selección de bases de datos;
- inmuebles;
- inquilinos;
- contratos y titulares;
- rentas e histórico de rentas;
- revisiones previstas;
- anexos y ajustes temporales de renta;
- migraciones Alembic;
- empaquetado e instalación de la aplicación;
- y la interfaz básica de administración.

### 7.2. Desarrollo 0.2.0

La rama `develop` contiene además la base de los siguientes dominios:

- `Factura` y `FacturaLinea`, junto con funciones de cálculo y numeración;
- `ApunteContable`;
- `MovimientoPrevisto` para conciliación;
- `Inmueble.ruta_documentos` como futura ruta base del archivo documental;
- `Factura.ruta_pdf`, por ahora vacía y reservada para la futura emisión;
- y líneas de factura de tipo `OTRO` para conceptos añadidos por el usuario.

Tras estos cambios, la suite completa alcanzó 254 pruebas superadas. El módulo
de facturación no dispone todavía de su operativa completa ni genera archivos.

### 7.3. Estado de los módulos

| Módulo | Estado | Decisión actual |
|---|---|---|
| Datos maestros y contratos | Operativo | Mantener y mejorar según feedback |
| Rentas, revisiones y anexos | Base operativa | Ampliar cuando un caso real lo exija |
| Apuntes contables | Modelo creado | Siguiente funcionalidad prioritaria |
| Movimientos previstos | Modelo creado | Integrarlos con los apuntes y preparar conciliación |
| Exportación e informes | Pendiente | Después del CRUD contable |
| Importación bancaria | Pendiente | Desarrollar con CSV reales del cliente |
| Conciliación | Pendiente | Objetivo principal tras importación |
| Facturación automática | Pausada | Retomar cuando incluya generación ODS/PDF |

## 8. Modelo contable acordado

Un `ApunteContable` representa un hecho económico atribuible a un inmueble.
Actualmente contempla:

- fecha e inmueble;
- naturaleza: ingreso o gasto;
- categoría y subcategoría;
- concepto;
- base, IVA, retención y total;
- nombre y NIF del tercero;
- referencia textual del documento;
- ruta del documento justificativo;
- y notas.

La referencia documental es texto, no una clave foránea a una factura. De este
modo, la contabilidad no depende de que un registro operativo de facturación se
conserve indefinidamente. Puede contener, por ejemplo, el número de una factura
emitida, el número y proveedor de una factura recibida o la identificación de
un recibo.

### 8.1. Categorías contables

Las categorías y subcategorías se definirán en `contab.ini`; no se construirá
por ahora una tabla ni una pantalla de mantenimiento.

Los códigos deben ser estables. Una categoría usada históricamente no se
elimina: se marca como inactiva para impedir su selección en nuevos apuntes,
pero continúa siendo reconocible en los anteriores. La etiqueta descriptiva
puede cambiar sin modificar el código.

La configuración anual de informes, por ejemplo `[informe_irpf_2027]`, asociará
los códigos económicos a las agrupaciones exigidas ese año. Si sólo cambia el
formulario fiscal, bastará con modificar esa configuración.

Si se descubre que los apuntes de un año necesitan una reclasificación real,
se realizará excepcionalmente mediante copia de seguridad y un script o una
consulta SQL específica. No se desarrollará ahora una interfaz genérica para
una necesidad infrecuente.

## 9. Modelo de movimientos previstos y conciliación

Un `MovimientoPrevisto` representa un cobro o pago que se espera encontrar en
el banco. Puede relacionarse opcionalmente con:

- un inmueble;
- un contrato;
- y un apunte contable mediante `apunte_id`.

La relación con el apunte es opcional porque puede conocerse un pago previsto
antes de recibir su factura, o existir previsiones que todavía no tengan reflejo
contable. Un apunte puede originar más de un movimiento previsto, por ejemplo
si se paga en varios plazos.

El modelo actual contiene fecha prevista, naturaleza, concepto, importe
esperado, contraparte, estado y notas. No se añadirán todavía columnas para
posibles literales o reglas de identificación hasta analizar ficheros bancarios
reales.

Para asociar en el futuro un movimiento bancario con una previsión serán
relevantes, previsiblemente:

- banco y cuenta;
- fecha de operación y fecha valor;
- importe;
- concepto bancario;
- emisor, ordenante o beneficiario;
- referencia aportada por el emisor;
- e identificador bancario del movimiento.

Si hacen falta varios patrones de reconocimiento, se modelarán probablemente
como registros relacionados y no como una sucesión de columnas fijas. Esa
decisión se pospone hasta disponer de CSV reales.

## 10. Primera operativa contable prevista

### 10.1. Consulta y mantenimiento

La primera interfaz nueva será una lista de apuntes ordenada por fecha, con
filtros sencillos por inmueble, ejercicio y naturaleza. Al haber pocos datos,
no se añadirá paginación hasta que resulte necesaria.

Desde esa lista se podrá:

- crear un apunte;
- consultar o modificar el seleccionado;
- y eliminarlo cuando sea procedente.

### 10.2. Coordinación con conciliación

Al crear un apunte, el formulario permitirá crear a la vez su movimiento
previsto, reutilizando los datos comunes y proponiendo fecha, concepto, importe
y contraparte.

Después, ambos registros podrán modificarse conforme a sus propias necesidades.
Si se elimina un apunte que tiene un movimiento pendiente vinculado, se podrán
eliminar ambos dentro de la misma transacción. Un movimiento ya conciliado no
se eliminará mediante este flujo simple; su corrección requerirá una operativa
específica que se definirá al desarrollar la conciliación.

## 11. Decisiones sobre rentas y carga inicial

Se ha descartado desarrollar un subsistema especial para reconstruir todo el
histórico de rentas anterior a Contab. El cliente no necesita esa trazabilidad
y actualmente no tiene reducciones temporales vigentes.

No se añadirán:

- un estado de carga histórica del contrato;
- una renta vigente de apertura separada;
- un asistente de cierre de carga;
- ni un proceso para solicitar todos los índices históricos.

Para la carga inicial:

- si no hay anexos relevantes, la renta introducida en el contrato será la
  renta vigente;
- si los hay, el último anexo reflejará la renta vigente;
- la descripción podrá explicar que el importe original del anexo era otro y
  que se utiliza el vigente para iniciar la gestión;
- y se indicará directamente la próxima revisión futura.

No se crearán anexos ficticios. La trazabilidad completa de las modificaciones
de renta sólo se exige desde la entrada del contrato en Contab.

## 12. Facturación: diseño acordado y motivo de la pausa

Se llegó a definir una operativa sencilla para la facturación, pero se ha
aplazado su implementación completa porque, sin generación automática del PDF,
obliga al usuario a introducir los mismos datos dos veces.

Cuando se retome, el diseño de referencia será el siguiente:

- una pantalla-resumen mensual mostrará los contratos y su estado;
- para los contratos con factura, el usuario abrirá un formulario con líneas
  propuestas, podrá modificar datos, añadir líneas `OTRO` y observaciones;
- el botón **Calcular** realizará en el servidor todos los cálculos;
- **Finalizar** sólo se permitirá si los datos no han cambiado desde el último
  cálculo;
- **Cancelar** no guardará nada;
- el número de factura se asignará únicamente al finalizar;
- y la creación de factura, líneas, apunte contable y movimiento previsto será
  atómica.

Para los contratos que no generan factura, la pantalla-resumen permitirá
aceptar directamente el ingreso y crear el apunte y el movimiento previsto. Un
detalle adicional sólo será necesario para casos excepcionales.

También se contempla emitir facturas excepcionales mediante el mismo formulario.

### 12.1. Revisiones de renta dentro de la facturación

Para una revisión efectiva en el mes `M`, el ciclo previsto es:

- `M-1`: aviso de que la revisión se realizará el mes siguiente;
- `M`: espera del índice, facturando todavía la renta anterior;
- `M+1`: introducción manual del porcentaje, aplicación de la nueva renta y
  cobro de los atrasos correspondientes a `M`.

El usuario introducirá siempre el porcentaje; Contab no consultará índices en
fuentes externas. `IPC_NACIONAL`, `IPC_AUTONOMICO` e `IRAV` indican qué índice
debe buscar, pero comparten el mismo tratamiento matemático.

La pantalla-resumen mostrará, cuando corresponda, `Aviso`, `Esperando índice` o
`Actualizada`. Los cálculos se realizarán al pulsar **Calcular**, no con cada
pulsación de teclado.

### 12.2. Correcciones posteriores

Antes de finalizar, una factura puede modificarse o cancelarse sin guardar.
Después de finalizar, el registro será inmutable:

- si la operación nunca existió, se anulará la factura, manteniendo consumido
  su número y neutralizando sus efectos contables y de conciliación;
- si la factura fue emitida pero contenía un error, se generará una factura
  rectificativa con número propio y referencia a la original.

No se construirá esta operativa hasta retomar el módulo completo.

## 13. Documentos y conservación de datos

El sistema de ficheros seguirá siendo el archivo documental. Cada inmueble
dispone de `ruta_documentos` como futura ruta base; las facturas se organizan
actualmente por inmueble y año.

`Factura.ruta_pdf` se conserva con valor vacío por defecto hasta implementar la
generación automática. Los registros de factura se mantendrán por ahora sin un
proceso de borrado. En el futuro podría estudiarse una limpieza anual, por
ejemplo conservando los últimos cinco ejercicios, siempre que ninguna relación
técnica o necesidad operativa dependa de ellos.

No se guardarán copias históricas innecesarias de los datos del destinatario en
la factura: durante la generación se obtendrán del contrato. El PDF archivado
será el soporte documental definitivo.

## 14. Hoja de ruta acordada

El orden de desarrollo actual es:

1. **Gestión de apuntes contables**: alta, consulta, modificación y eliminación.
2. **Integración con movimientos previstos**: creación coordinada y
   mantenimiento básico.
3. **Exportación contable a CSV** por inmueble, ejercicio y naturaleza,
   compatible con LibreOffice.
4. **Informes contables básicos** que el cliente utilice realmente.
5. **Importación de movimientos bancarios** desde CSV reales.
6. **Conciliación asistida** y emisión de su informe de resultados.
7. **Mejora incremental de las reglas de conciliación** a partir de casos
   reales.
8. **Reanudación paralela de la facturación**, cuando se aborde también la
   creación y archivo de `.ods` y PDF.

Esta hoja de ruta puede variar como consecuencia del feedback del cliente,
pero cualquier cambio debe mantener la prioridad de la conciliación y los
informes contables.

## 15. Fuera de alcance por ahora

Quedan expresamente aplazados:

- la generación automática de facturas sin generación simultánea de PDF;
- un archivo documental interno o un visor de facturas y justificantes;
- consultas históricas de facturación sin una necesidad concreta;
- la reconstrucción completa de rentas anteriores a Contab;
- la importación automática de IPC o IRAV desde fuentes externas;
- pantallas para mantener categorías contables;
- una interfaz genérica de reclasificación masiva;
- algoritmos de conciliación basados en aprendizaje automático;
- automatizaciones para casuísticas excepcionales no observadas;
- y características propias de una aplicación multiusuario o comercial.

## 16. Criterios de éxito

Contab tendrá éxito si consigue que el usuario:

- registre cada ingreso o gasto una sola vez;
- dedique la revisión bancaria principalmente a resolver excepciones;
- identifique rápidamente cobros pendientes, gastos desconocidos y
  justificantes ausentes;
- obtenga la contabilidad trimestral sin transcribir un cuaderno;
- genere informes anuales con nuevas agrupaciones sin reconstruir los datos;
- y pueda entender, revisar y mantener el funcionamiento de la aplicación sin
  perder el control de su información ni de sus documentos.

El número de funciones no es una medida de éxito. Lo son el tiempo ahorrado,
la reducción de errores, la trazabilidad útil y la sencillez de mantenimiento.

