# Reglas de negocio de contab

Este documento recoge las reglas de negocio y la casuística conocida del
usuario que condicionan el diseño y funcionamiento de `contab`.

Su finalidad es documentar el modelo del dominio independientemente de su
implementación técnica.

Las decisiones técnicas y la arquitectura se documentan en `DEVELOPMENT.md`.
Los objetivos y alcance general de la aplicación se documentan en
`PROJECT.md`.

## 1. Inmuebles

### 1.1. Identificación

Cada inmueble gestionado tendrá una referencia interna única que permita al
usuario identificarlo fácilmente.

También tendrá un código de facturación único, utilizado en la numeración de
sus facturas.

La referencia catastral se almacenará cuando esté disponible.

### 1.2. Datos administrativos

Para el usuario son obligatorios:

- Referencia interna.
- Código de facturación.
- Descripción.
- Dirección.
- Población.
- Provincia.

Son opcionales:

- Código postal.
- Referencia catastral.
- Número de póliza de seguro.
- Notas.

El número de póliza de seguro se almacena como información administrativa y
podrá resultar útil posteriormente para la identificación y conciliación de
gastos relacionados con seguros.

### 1.3. Inmuebles activos

Un inmueble puede estar activo o inactivo.

Un inmueble activo forma parte del conjunto de inmuebles actualmente
gestionados.

Un inmueble puede pasar a estar inactivo, por ejemplo, si se vende, pero debe
conservarse en la base de datos para mantener toda su información histórica.

Un inmueble sólo puede marcarse como inactivo cuando no tenga contratos
vigentes.

### 1.4. Participación

Existen inmuebles que se alquilan en su totalidad y otros que, aunque
constituyen una única unidad catastral, están físicamente subdivididos en
varias partes que se alquilan de forma independiente.

Cada una de esas partes se trata inicialmente en `contab` como un inmueble
independiente.

Cada inmueble tendrá un porcentaje de participación que representa qué parte
del inmueble catastral completo le corresponde.

Ejemplos:

    Inmueble completo: 100,00 %
    Parte A:            32,56 %
    Parte B:            41,20 %
    Parte C:            26,24 %

Esta participación permitirá posteriormente repartir gastos comunes, como
seguros, tasas o determinados impuestos.

La participación se almacenará como un entero expresado en centésimas de
punto porcentual:

    100,00 % -> 10000
     32,56 % ->  3256

Debe cumplirse:

    0 < participacion <= 10000

Por defecto:

    participacion = 10000

### 1.5. Posible evolución del modelo

En el futuro puede resultar conveniente distinguir explícitamente entre:

- Inmueble fiscal o catastral.
- Parte o unidad arrendable.

En ese modelo, un inmueble catastral podría contener una o varias partes.

Esta separación no se implementará inicialmente. Se utilizarán inmuebles
independientes con su correspondiente porcentaje de participación.

Esta decisión deberá revisarse si las necesidades de fiscalidad, gastos o
informes hacen conveniente la separación.

## 2. Inquilinos

### 2.1. Concepto de inquilino

Un inquilino representa una única persona física o jurídica.

Puede ser:

- Una empresa.
- Una persona física.
- Un ciudadano extranjero.

No se agruparán varios titulares dentro de un mismo registro de inquilino.

### 2.2. Identificación

Cada inquilino tendrá:

- Nombre o razón social.
- NIF o identificador equivalente.

El campo `nif` se interpreta de forma genérica como el identificador fiscal o
personal utilizado para identificar al titular.

Puede contener:

- NIF.
- NIE.
- Identificador equivalente de otro país.

Inicialmente no se distinguirán estos tipos mediante campos separados.

El NIF o identificador no tendrá inicialmente una restricción `UNIQUE`.

### 2.3. Datos de contacto

Podrán almacenarse:

- Dirección.
- Código postal.
- Población.
- Provincia.
- Correo electrónico.
- Teléfono.
- Notas administrativas.

Se procurará que exista al menos un correo electrónico o teléfono de contacto,
pero inicialmente no se impondrá esta condición como una restricción de la
base de datos.

### 2.4. Vigencia

Un inquilino no tendrá un campo `activo`.

La vigencia se deduce de sus contratos.

Un inquilino se considera vigente cuando participa como titular en al menos un
contrato vigente.

Cuando deja de participar en contratos vigentes, su registro se conserva como
información histórica.

## 3. Titulares de un contrato

### 3.1. Titular único

Lo habitual en locales comerciales es que un contrato tenga un único titular,
que puede ser una empresa o una persona física.

### 3.2. Titulares múltiples

En viviendas es habitual que un contrato sea firmado solidariamente por dos o
más personas.

Cada una de ellas se almacenará como un inquilino independiente.

Un contrato podrá relacionarse con uno o varios inquilinos.

No se establece un límite máximo de titulares.

### 3.3. Orden de titulares

Los titulares de un contrato tendrán un orden.

Este orden permitirá determinar cómo deben aparecer en documentos, facturas u
otras presentaciones.

Un mismo inquilino no puede aparecer dos veces en el mismo contrato.

Dos inquilinos de un mismo contrato no pueden tener el mismo número de orden.

## 4. Contratos

### 4.1. Relación con el inmueble

Cada contrato corresponde a un único inmueble o unidad arrendable.

Inicialmente no se admitirán dos contratos simultáneamente vigentes para un
mismo inmueble.

Un inmueble podrá tener sucesivos contratos a lo largo del tiempo.

### 4.2. Relación con los inquilinos

Todo contrato debe tener al menos un titular.

La relación entre contratos e inquilinos se realizará mediante una tabla
intermedia, permitiendo que un contrato tenga varios titulares y que un
inquilino pueda aparecer en diferentes contratos.

### 4.3. Fecha de inicio

`fecha_inicio` representa la fecha de inicio del contrato.

Es obligatoria.

### 4.4. Fecha de vencimiento

Todo contrato tiene inicialmente una fecha de vencimiento.

`fecha_vencimiento` representa la fecha hasta la cual el contrato estará
vigente si no se produce una prórroga o una finalización anticipada.

Es obligatoria.

Debe cumplirse:

    fecha_vencimiento >= fecha_inicio

El vencimiento es un dato importante porque permitirá posteriormente avisar
con antelación de contratos próximos a vencer.

### 4.5. Fecha de finalización efectiva

`fecha_fin` representa la fecha en la que el contrato terminó efectivamente o
quedó legalmente rescindido.

Mientras el contrato no haya finalizado:

    fecha_fin = NULL

Cuando termina:

    fecha_fin >= fecha_inicio

`fecha_fin` y `fecha_vencimiento` representan conceptos diferentes.

La fecha de vencimiento indica cuándo debería terminar el contrato según sus
condiciones vigentes.

La fecha de fin indica cuándo terminó realmente.

### 4.6. Contrato vigente

Mientras no se definan reglas adicionales, un contrato se considerará
finalizado cuando tenga informada `fecha_fin`.

La fecha de vencimiento no implica por sí sola que se deba eliminar ni
modificar automáticamente el contrato.

El tratamiento posterior de contratos que alcanzan su fecha de vencimiento
sin haberse registrado todavía una prórroga deberá definirse cuando se
implemente esta funcionalidad.

## 5. Rentas

### 5.1. Periodicidad

Todas las rentas gestionadas actualmente son mensuales.

No es necesario soportar inicialmente otras periodicidades.

### 5.2. Histórico de rentas ordinarias

La renta no se almacenará directamente en `contrato`.

Cada contrato tendrá un histórico de rentas ordinarias mediante
`renta_contrato`.

Cada entrada indica la renta mensual ordinaria aplicable desde una determinada
fecha.

Los importes monetarios se almacenarán como enteros expresados en céntimos.

Ejemplos:

    1.000,00 EUR -> 100000
    1.250,37 EUR -> 125037

Esto evita utilizar valores de coma flotante para cantidades monetarias.

La primera entrada de `renta_contrato` representará la renta inicial del
contrato y deberá tener:

    fecha_desde = contrato.fecha_inicio

Por tanto, la primera renta puede comenzar en cualquier día del mes.

Las rentas posteriores, derivadas normalmente de revisiones, tendrán
`fecha_desde` correspondiente al primer día del mes desde el que sean
aplicables.

Ejemplo:

    contrato.fecha_inicio = 2026-06-15
    primera renta:
        fecha_desde = 2026-06-15
        importe     = 100000

    revisión posterior:
        fecha_desde = 2027-06-01
        importe     = 102300

La renta ordinaria vigente para una determinada fecha será la última entrada de
`renta_contrato` cuya `fecha_desde` sea anterior o igual a la fecha consultada.

La existencia de una renta contractual vigente no implica necesariamente que
deba facturarse desde esa misma fecha.

`contrato.fecha_inicio_facturacion` determina el primer mes por el que la renta
es exigible y debe facturarse.

Esto permite representar periodos de carencia sin modificar la renta
contractual.

### 5.3. Revisiones de renta

Los contratos pueden prever revisiones periódicas de la renta.

Una revisión tiene una fecha prevista y un método de cálculo.

Los métodos concretos se definirán cuando se implemente el proceso de revisión.
Provisionalmente se contemplan valores como:

- `IPC_NACIONAL`.
- `IPC_REGIONAL`.
- `MANUAL`.
- `OTRO`.

Estos valores son provisionales y no constituyen todavía una definición
funcional definitiva.

Una revisión puede encontrarse en los estados:

- `PENDIENTE`.
- `APLICADA`.
- `NO_APLICADA`.

La fecha prevista será siempre el día 1 del mes en el que corresponde revisar
la renta.

Cuando se aplique una revisión se registrará el porcentaje utilizado y se
creará una nueva entrada en `renta_contrato` con:

    fecha_desde = fecha_prevista

El porcentaje se almacenará en centésimas de punto porcentual:

     2,30 % ->  230
    -1,25 % -> -125

El porcentaje puede ser negativo.

La fecha en la que administrativamente se resuelve la revisión puede ser
anterior, igual o posterior a la fecha prevista.

Si el usuario decide no aplicar una revisión, ésta quedará registrada como
`NO_APLICADA` y no se creará una nueva entrada en `renta_contrato`.

Tanto si la revisión se aplica como si no se aplica, se generará
automáticamente la revisión correspondiente al año siguiente, manteniendo el
mismo mes y método.

### 5.4. Ajustes temporales de renta

Una modificación temporal de la cantidad facturada no altera la renta
ordinaria registrada en `renta_contrato`.

Se representará mediante `ajuste_renta`.

Esto permite, por ejemplo, reflejar reducciones temporales pactadas mediante
anexos al contrato.

Un ajuste siempre tendrá fecha de inicio y fecha de finalización.

Ambas fechas representarán meses y utilizarán el día 1.

Inicialmente se contemplan tres tipos:

- `REDUCCION_PORCENTUAL`.
- `REDUCCION_FIJA`.
- `IMPORTE_FIJO`.

Para `REDUCCION_PORCENTUAL`, `valor` se expresa en centésimas de punto
porcentual:

    40,00 % -> 4000

Para `REDUCCION_FIJA`, `valor` se expresa en céntimos:

    200,00 EUR -> 20000

Para `IMPORTE_FIJO`, `valor` representa directamente la renta mensual
facturable durante el periodo:

    50,00 EUR -> 5000

Una reducción temporal se aplica sobre la renta ordinaria vigente en cada mes.

Por tanto, si durante el periodo de reducción se produce una revisión de
renta, primero se determina la nueva renta ordinaria y después se aplica el
ajuste temporal.

Ejemplo:

    Renta ordinaria inicial:          1.000,00 EUR
    Reducción temporal:                   40,00 %
    Renta facturable:                    600,00 EUR

    Revisión posterior:                    2,30 %
    Nueva renta ordinaria:             1.023,00 EUR
    Reducción temporal vigente:            40,00 %
    Nueva renta facturable:               613,80 EUR

Al terminar el ajuste temporal se vuelve automáticamente a facturar el 100 %
de la renta ordinaria vigente.

No se almacenará un importe resultante del ajuste, ya que sería redundante y
podría quedar desactualizado si cambia la renta ordinaria durante su vigencia.

No se permitirán dos ajustes simultáneos para un mismo contrato.

Si una modificación no tiene una fecha prevista de finalización, no deberá
representarse como un ajuste temporal sino como una modificación de la renta
ordinaria.

## 6. Fianza

Cada contrato tendrá registrada su fianza.

Se almacenará como un entero expresado en céntimos.

Debe cumplirse:

    fianza >= 0

## 7. IVA y retención

Cada contrato podrá especificar:

- Porcentaje de IVA.
- Porcentaje de retención.

Los porcentajes se almacenarán como enteros expresados en centésimas de punto
porcentual.

Ejemplos:

    21,00 % -> 2100
    19,00 % -> 1900

Un valor cero indica que no se aplica el correspondiente concepto.

Inicialmente el usuario será responsable de establecer correctamente estos
porcentajes.

`contab` no intentará deducir automáticamente el tratamiento fiscal aplicable
a un contrato.

## 8. Facturación de los contratos

### 8.1. Periodicidad

Todas las facturas ordinarias de alquiler corresponden a periodos mensuales.

### 8.2. Fecha habitual de emisión

Las facturas mensuales se emiten habitualmente con fecha del día 1 del mes al
que corresponden.

El usuario genera conjuntamente la facturación mensual de todos los inmuebles.

Por tanto, el contrato no necesita almacenar un día individual de
facturación.

### 8.3. Inicio de facturación

La fecha de inicio del contrato y la fecha de inicio de facturación pueden ser
diferentes.

Cada contrato tendrá:

    fecha_inicio_facturacion

Esta fecha representa el primer mes que debe facturarse.

Por convenio se utilizará siempre el día 1 del correspondiente mes.

Ejemplo:

    fecha_inicio              = 15/06/2026
    fecha_inicio_facturacion  = 01/09/2026

Debe cumplirse:

    fecha_inicio_facturacion >= fecha_inicio

La aplicación deberá validar además que `fecha_inicio_facturacion` corresponde
al día 1 de un mes.

### 8.4. Periodos de carencia

Al inicio de algunos contratos, especialmente en locales comerciales, puede
concederse un periodo de carencia de uno o varios meses para permitir que el
inquilino adapte el inmueble a su actividad.

Durante los meses de carencia no se emiten facturas de alquiler.

La carencia no se almacenará inicialmente como un número de meses.

Quedará representada implícitamente mediante la diferencia entre:

    fecha_inicio
    fecha_inicio_facturacion

### 8.5. Primera factura anticipada

Es habitual que al firmar un nuevo contrato se emita inmediatamente la factura
correspondiente al primer mes que será facturable, aunque exista un periodo de
carencia.

Ejemplo:

    Firma del contrato:       15/06/2026
    Inicio de facturación:    01/09/2026
    Periodo primera factura:  septiembre de 2026
    Emisión primera factura:  15/06/2026

Por tanto, deben distinguirse claramente:

- Fecha de emisión de una factura.
- Periodo mensual al que corresponde.

Esta situación se resolverá en el modelo de facturas y no requiere campos
adicionales en el contrato.

### 8.6. Avisos relacionados con revisiones de renta

La facturación deberá tener en cuenta las revisiones previstas.

Si corresponde revisar la renta en el mes M, la mecánica habitual es:

- En la factura de M-1 se avisa de que el mes siguiente corresponde revisar
  la renta.
- En la factura de M, si el índice todavía no está disponible, se mantiene
  provisionalmente la renta anterior y se informa de que la actualización se
  realizará posteriormente incluyendo la diferencia correspondiente a M.
- En M+1, cuando se disponga del porcentaje, se aplica la nueva renta y se
  incluye, cuando corresponda, la diferencia de renta correspondiente a M.

La aplicación deberá asistir al usuario en este proceso y permitirle confirmar
las decisiones antes de emitir las facturas.

Los avisos realmente incluidos deberán conservarse posteriormente como parte
de la información histórica de la factura.

No se utilizarán banderas temporales en `contrato` que deban ser reseteadas
manualmente. El estado se deducirá de las revisiones y de las facturas
existentes.

## 9. Dirección de facturación

Cada contrato tendrá una única dirección de facturación.

Puede ser:

- La dirección del inmueble.
- La dirección de uno de los titulares.
- Otra dirección establecida contractualmente.

Se almacenará directamente en el contrato mediante:

- Dirección.
- Código postal.
- Población.
- Provincia.

La dirección, población y provincia serán obligatorias.

El código postal será opcional.

Posteriormente, cada factura deberá conservar una copia de los datos utilizados
en el momento de su emisión para evitar que cambios posteriores alteren
documentos históricos.

## 10. Concepto de factura

Cada contrato tendrá un concepto base de factura obligatorio.

Ejemplo:

    Alquiler del local

Al generar una factura, la aplicación añadirá el periodo correspondiente.

Ejemplo:

    Alquiler del local por el mes de septiembre de 2026

El texto definitivo se establecerá cuando se implemente la generación de
facturas.

## 11. Numeración de facturas

### 11.1. Numeración independiente por inmueble

Cada inmueble mantiene su propia numeración de facturas.

La numeración se reinicia al comienzo de cada año.

La primera factura del año para cada inmueble tiene número 01.

Los números deben ser consecutivos dentro de cada inmueble y año.

### 11.2. Formato actual

El formato utilizado actualmente es:

    01/2026A6

donde:

    01    número secuencial de factura para el inmueble
    2026  año de facturación
    A6    código de facturación del inmueble

### 11.3. Código de facturación

El código visible de facturación no dependerá directamente de la clave primaria
interna de la base de datos.

Cada inmueble tendrá:

    codigo_facturacion TEXT NOT NULL UNIQUE

Ejemplos:

    A6
    A7
    A12

Esto permite conservar la numeración fiscal aunque en el futuro se migren o
reorganicen los datos internos.

### 11.4. Secuencia

No se almacenará inicialmente en el inmueble un contador con el siguiente
número de factura.

Cuando se implemente `factura`, se estudiará obtener el siguiente número a
partir de las facturas existentes para ese inmueble y año.

El modelo deberá impedir números duplicados para una misma combinación de:

    inmueble
    año
    número secuencial

Los meses de carencia no generan facturas y, por tanto, no consumen números de
la secuencia.

## 12. Anexos contractuales

Durante la vida de un contrato pueden firmarse anexos.

Entre otros motivos:

- Prórroga del vencimiento.
- Modificación de la renta.
- Reducción temporal de la renta.
- Otras modificaciones contractuales.

Inicialmente no se implementará una tabla específica de anexos.

Las consecuencias económicas de los anexos podrán quedar reflejadas mediante:

- `renta_contrato`, para modificaciones de la renta ordinaria.
- `ajuste_renta`, para modificaciones temporales.

Una prórroga actualizará inicialmente `fecha_vencimiento`.

En una fase posterior se estudiará si resulta conveniente conservar también
los anexos como entidades independientes.

## 13. Conservación del histórico

La información histórica tiene especial importancia.

En general, los registros que hayan intervenido en contratos, facturas,
ingresos, gastos o conciliaciones no deberán eliminarse físicamente simplemente
porque hayan dejado de estar vigentes.

En particular:

- Un inmueble vendido se conservará como inmueble inactivo.
- Un inquilino sin contratos vigentes se conservará.
- Un contrato finalizado se conservará.
- Las rentas ordinarias anteriores se conservarán.
- Las revisiones aplicadas y no aplicadas se conservarán.
- Los ajustes temporales se conservarán.
- Las facturas emitidas deberán conservar los datos utilizados en el momento
  de su emisión.

## 14. Modelo de datos inicial acordado

### 14.1. inmueble

    inmueble
    --------
    id                   INTEGER PRIMARY KEY
    referencia           TEXT NOT NULL UNIQUE
    codigo_facturacion   TEXT NOT NULL UNIQUE
    descripcion          TEXT NOT NULL
    direccion            TEXT NOT NULL
    codigo_postal        TEXT
    poblacion            TEXT NOT NULL
    provincia            TEXT NOT NULL
    ref_catastral        TEXT
    seguro               TEXT
    participacion        INTEGER NOT NULL DEFAULT 10000
    activo               BOOLEAN NOT NULL DEFAULT true
    notas                TEXT

Restricción:

    CHECK (participacion > 0 AND participacion <= 10000)

### 14.2. inquilino

    inquilino
    ---------
    id               INTEGER PRIMARY KEY
    nombre           TEXT NOT NULL
    nif              TEXT NOT NULL
    direccion        TEXT
    codigo_postal    TEXT
    poblacion        TEXT
    provincia        TEXT
    email            TEXT
    telefono         TEXT
    notas            TEXT

`nif` no tendrá inicialmente una restricción `UNIQUE`.

No existe un campo `activo`. La vigencia se deriva de los contratos.

### 14.3. contrato

    contrato
    --------
    id                          INTEGER PRIMARY KEY
    inmueble_id                 INTEGER NOT NULL

    fecha_inicio                DATE NOT NULL
    fecha_vencimiento           DATE NOT NULL
    fecha_fin                   DATE
    fecha_inicio_facturacion    DATE NOT NULL

    fianza                      INTEGER NOT NULL

    iva_porcentaje              INTEGER NOT NULL DEFAULT 0
    retencion_porcentaje        INTEGER NOT NULL DEFAULT 0

    direccion_facturacion       TEXT NOT NULL
    codigo_postal_facturacion   TEXT
    poblacion_facturacion       TEXT NOT NULL
    provincia_facturacion       TEXT NOT NULL

    concepto_factura            TEXT NOT NULL
    notas                       TEXT

Relación:

    FOREIGN KEY (inmueble_id) REFERENCES inmueble(id)

Restricciones iniciales:

    CHECK (fecha_vencimiento >= fecha_inicio)
    CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio)
    CHECK (fecha_inicio_facturacion >= fecha_inicio)
    CHECK (fianza >= 0)
    CHECK (iva_porcentaje >= 0)
    CHECK (retencion_porcentaje >= 0)

La aplicación validará que `fecha_inicio_facturacion` sea el primer día de un
mes.

La renta no se almacena directamente en esta tabla.

### 14.4. contrato_inquilino

    contrato_inquilino
    ------------------
    contrato_id      INTEGER NOT NULL
    inquilino_id     INTEGER NOT NULL
    orden            INTEGER NOT NULL

    PRIMARY KEY (contrato_id, inquilino_id)

    FOREIGN KEY (contrato_id) REFERENCES contrato(id)
    FOREIGN KEY (inquilino_id) REFERENCES inquilino(id)

    UNIQUE (contrato_id, orden)

    CHECK (orden > 0)

Todo contrato deberá tener al menos un inquilino.

### 14.5. renta_contrato

    renta_contrato
    --------------
    id             INTEGER PRIMARY KEY
    contrato_id    INTEGER NOT NULL
    fecha_desde    DATE NOT NULL
    importe        INTEGER NOT NULL
    notas          TEXT

    FOREIGN KEY (contrato_id) REFERENCES contrato(id)

    UNIQUE (contrato_id, fecha_desde)

    CHECK (importe >= 0)

La primera `fecha_desde` será igual a `contrato.fecha_inicio`.

Las posteriores serán normalmente el día 1 del mes desde el que se aplique la
nueva renta.



### 14.6. revision_renta

    revision_renta
    --------------
    id                    INTEGER PRIMARY KEY
    contrato_id           INTEGER NOT NULL
    fecha_prevista        DATE NOT NULL
    metodo                TEXT NOT NULL
    estado                TEXT NOT NULL DEFAULT 'PENDIENTE'
    porcentaje_aplicado   INTEGER
    fecha_resolucion      DATE
    notas                 TEXT

    FOREIGN KEY (contrato_id) REFERENCES contrato(id)

    UNIQUE (contrato_id, fecha_prevista)

    CHECK (
        estado IN ('PENDIENTE', 'APLICADA', 'NO_APLICADA')
    )

`fecha_prevista` será siempre el día 1 de un mes.

`porcentaje_aplicado` se expresa en centésimas de punto porcentual y puede ser
positivo, cero o negativo.

Los valores definitivos de `metodo` se decidirán al implementar el proceso de
revisión de rentas.

### 14.7. ajuste_renta

    ajuste_renta
    ------------
    id              INTEGER PRIMARY KEY
    contrato_id     INTEGER NOT NULL
    fecha_desde     DATE NOT NULL
    fecha_hasta     DATE NOT NULL
    tipo            TEXT NOT NULL
    valor           INTEGER NOT NULL
    notas           TEXT

    FOREIGN KEY (contrato_id) REFERENCES contrato(id)

    CHECK (fecha_hasta >= fecha_desde)

    CHECK (
        tipo IN (
            'REDUCCION_PORCENTUAL',
            'REDUCCION_FIJA',
            'IMPORTE_FIJO'
        )
    )

`fecha_desde` y `fecha_hasta` serán siempre el día 1 de un mes.

Para `REDUCCION_PORCENTUAL`:

    0 <= valor <= 10000

Para `REDUCCION_FIJA` e `IMPORTE_FIJO`:

    valor >= 0

No se permitirán ajustes temporalmente solapados para un mismo contrato.

## 15. Reglas de integridad y negocio identificadas

Además de las restricciones directamente expresables en la base de datos, la
lógica de la aplicación deberá controlar inicialmente:

1. Un contrato debe tener al menos un titular.
2. No debe haber contratos simultáneamente vigentes sobre el mismo inmueble.
3. Un inmueble sólo puede marcarse como inactivo si no tiene contratos
   vigentes.
4. `fecha_inicio_facturacion` debe corresponder al primer día de un mes.
5. Los titulares de un contrato deben tener órdenes diferentes.
6. Un mismo inquilino no puede aparecer dos veces en el mismo contrato.
7. Los importes monetarios se expresan internamente en céntimos.
8. Los porcentajes se expresan internamente en centésimas de punto porcentual.
9. La numeración de facturas será independiente para cada inmueble y año.
10. Los meses sin factura no consumirán números de la secuencia.
11. La primera `renta_contrato.fecha_desde` debe ser igual a
    `contrato.fecha_inicio`.
12. Las rentas posteriores deben tener `fecha_desde` correspondiente al primer
    día del mes desde el que sean aplicables.
13. No puede existir una renta ordinaria anterior al inicio del contrato.
14. `revision_renta.fecha_prevista` debe corresponder al primer día de un mes.
15. Una revisión aplicada debe generar la correspondiente entrada en
    `renta_contrato`.
16. Una revisión resuelta debe generar la revisión prevista para el año
    siguiente, manteniendo mes y método.
17. `ajuste_renta.fecha_desde` y `fecha_hasta` deben corresponder al primer día
    de sus respectivos meses.
18. Un ajuste temporal no puede comenzar antes del inicio del contrato.
19. No pueden existir dos ajustes temporalmente solapados para un mismo
    contrato.
20. Una reducción fija no puede producir una renta facturable negativa.
21. Una revisión de renta modifica la renta ordinaria aunque exista un ajuste
    temporal vigente; el ajuste se aplica posteriormente sobre la nueva renta.
22. Los datos históricos necesarios para reproducir una factura no dependerán
    de valores que puedan modificarse posteriormente.

## 16. Decisiones pendientes

Se han identificado cuestiones que deliberadamente no se resolverán todavía.

### 16.1. Inmueble y parte arrendable

Revisar si debe existir un modelo explícito:

    inmueble catastral -> parte arrendable

en lugar de representar inicialmente cada parte como un inmueble con un
porcentaje de participación.

### 16.2. Métodos de revisión

Definir los métodos reales de actualización de rentas utilizados por los
contratos y las reglas correspondientes a cada uno.

Los valores actualmente considerados son provisionales.

### 16.3. Anexos

Determinar si se necesita una entidad específica para conservar los anexos
contractuales y cómo relacionarla con:

- Prórrogas.
- Cambios de renta.
- Ajustes temporales.
- Otras modificaciones.

### 16.4. Vencimientos

Definir el comportamiento cuando un contrato alcanza `fecha_vencimiento` y no
se ha registrado todavía una prórroga ni una fecha de finalización.

También se estudiará la generación de avisos previos al vencimiento.

### 16.5. Facturas

Diseñar posteriormente la entidad `factura`, incluyendo:

- Fecha de emisión.
- Periodo facturado.
- Numeración.
- Datos históricos del destinatario.
- Renta ordinaria aplicable.
- Ajustes temporales.
- Diferencias derivadas de revisiones.
- Avisos de revisión incluidos.
- Base imponible.
- IVA.
- Retención.
- Total.
- Estado.
- Generación del ingreso pendiente correspondiente.

### 16.6. Validación de datos

Determinar qué validaciones deben imponerse directamente en SQLite y cuáles
deben permanecer como reglas de aplicación.

Entre otras:

- Formato de NIF o identificador.
- Existencia de email o teléfono.
- Límites razonables para IVA y retención.
- Normalización de textos y códigos.
