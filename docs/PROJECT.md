# Proyecto contab

## 1. Objetivo

`contab` es una aplicación destinada a facilitar la gestión administrativa y
contable de un pequeño conjunto de inmuebles alquilados.

El usuario gestiona aproximadamente una decena de inmuebles y actualmente
mantiene la información contable de cada uno mediante hojas de cálculo de
LibreOffice. Las facturas de alquiler se generan manualmente modificando una
plantilla.

Sin embargo, el principal problema que pretende resolver `contab` no es la
facturación ni la contabilidad en sí misma, sino el tiempo dedicado a la
conciliación de los movimientos bancarios.

El objetivo fundamental del proyecto es reducir al máximo ese trabajo manual,
manteniendo siempre la supervisión y confirmación del usuario.

## 2. Principios

El desarrollo seguirá los siguientes principios:

- Aplicación sencilla y fácil de mantener.
- Ejecución local en Linux.
- Aplicación web accesible mediante un navegador local.
- Base de datos SQLite.
- Desarrollo incremental mediante pequeñas versiones útiles.
- Automatización de tareas repetitivas sin eliminar el control del usuario.
- Conservación del histórico de los datos.
- Posibilidad de corregir y deshacer conciliaciones.
- Pruebas automatizadas para detectar regresiones al ampliar la aplicación.
- Evitar funcionalidades propias de un sistema contable general que no sean
  necesarias para el problema que se pretende resolver.

## 3. Datos principales

La aplicación mantendrá información sobre:

- Inmuebles.
- Inquilinos.
- Contratos de alquiler.
- Histórico de rentas y sus revisiones.
- Facturas emitidas.
- Ingresos pendientes y recibidos.
- Gastos y previsiones de gastos.
- Movimientos bancarios importados.
- Conciliaciones entre movimientos bancarios e ingresos o gastos.

El modelo de datos se ampliará gradualmente a medida que se implementen las
distintas funcionalidades.

## 4. Contratos y rentas

Un inmueble podrá tener sucesivos contratos e inquilinos.

Los contratos conservarán su histórico, incluyendo:

- Inmueble.
- Inquilino.
- Fecha de inicio.
- Fecha de finalización o rescisión.
- Renta.
- Revisiones de renta.
- Fechas de vigencia de cada renta.

Las modificaciones posteriores no deberán alterar la información histórica
correspondiente a periodos anteriores.

## 5. Facturación

La aplicación permitirá generar automáticamente las facturas periódicas de
alquiler a partir de los contratos vigentes.

Para cada periodo de facturación determinará:

- Contrato vigente.
- Inquilino.
- Datos fiscales necesarios.
- Renta vigente.
- Número de factura.
- Fecha y periodo facturado.
- Impuestos y retenciones que correspondan.

Antes de la emisión definitiva, el usuario podrá revisar las facturas
propuestas.

La emisión de una factura generará automáticamente el correspondiente ingreso
pendiente de cobro.

Las facturas conservarán una copia de los datos utilizados en el momento de su
emisión para evitar que modificaciones posteriores del inquilino, contrato o
renta alteren documentos históricos.

## 6. Previsión de gastos

La aplicación permitirá registrar gastos previstos, incluyendo información
como:

- Inmueble.
- Proveedor u organismo.
- Concepto.
- Importe aproximado.
- Fecha estimada.
- Periodicidad.
- Tolerancias de fecha e importe cuando sean necesarias.

Ejemplos:

- IBI anual.
- Gastos mensuales de comunidad.
- Agua.
- Electricidad.
- Gas.
- Seguros.
- Mantenimiento.
- Otros impuestos y servicios.

Estas previsiones serán especialmente importantes para facilitar la posterior
identificación de cargos bancarios.

## 7. Importación bancaria

Periódicamente, el usuario descargará de la entidad bancaria un fichero CSV
con los movimientos de la cuenta.

La aplicación importará estos movimientos conservando los datos originales y
evitando duplicados cuando se importen periodos solapados.

Los movimientos bancarios importados se considerarán información original y
no deberán modificarse para reflejar decisiones contables posteriores.

Un movimiento podrá clasificarse, entre otras posibilidades, como:

- Relacionado con un inmueble.
- Personal.
- Pendiente de identificar.

Los movimientos personales podrán excluirse de posteriores intentos de
conciliación.

## 8. Conciliación bancaria

La conciliación bancaria constituye el objetivo principal de `contab`.

La aplicación intentará relacionar automáticamente los movimientos bancarios
con:

- Facturas emitidas pendientes de cobro.
- Gastos previstos.
- Gastos previamente conocidos.
- Proveedores, inquilinos y conceptos identificados anteriormente.

El conciliador podrá utilizar diferentes criterios:

- Coincidencia de importes.
- Proximidad de fechas.
- Texto del concepto bancario.
- Nombre del inquilino.
- Nombre del proveedor.
- Periodicidad.
- Gastos previstos.
- Relaciones confirmadas anteriormente por el usuario.

El resultado será una propuesta de conciliación acompañada de un nivel o
puntuación de confianza.

Inicialmente, las propuestas no se confirmarán automáticamente.

El usuario podrá:

- Confirmar una propuesta.
- Rechazarla.
- Seleccionar otra correspondencia.
- Clasificar el movimiento como personal.
- Mantenerlo pendiente.
- Deshacer posteriormente una conciliación errónea.

Las confirmaciones del usuario podrán servir para mejorar las reglas aplicadas
a futuras conciliaciones.

No se considera inicialmente necesario utilizar técnicas de inteligencia
artificial o aprendizaje automático. Se priorizará un sistema determinista de
reglas y puntuaciones que sea sencillo, comprensible y verificable.

## 9. Informes

La aplicación permitirá consultar, entre otros:

- Facturas emitidas pendientes de cobro.
- Gastos previstos todavía no conciliados.
- Movimientos bancarios pendientes de identificar.
- Conciliaciones realizadas.

Trimestralmente podrá exportarse la contabilidad de cada inmueble a un formato
compatible con LibreOffice.

La información incluirá básicamente:

- Fecha.
- Concepto.
- Ingresos.
- Gastos.
- Totales.

## 10. Estrategia de desarrollo

El desarrollo será incremental.

El orden inicial previsto es:

1. Infraestructura básica de la aplicación.
2. Inmuebles, inquilinos y contratos, incluyendo la renta vigente.
3. Generación automática de facturas.
4. Registro automático de ingresos pendientes.
5. Histórico y revisión de rentas.
6. Previsiones de gastos.
7. Importación de movimientos bancarios.
8. Conciliación asistida.
9. Informes y exportaciones.

Cada incremento deberá aportar una funcionalidad verificable y, cuando sea
posible, utilidad inmediata al usuario.

La prioridad a largo plazo seguirá siendo la automatización de la conciliación
bancaria, aunque las primeras versiones se centren en los datos necesarios
para poder realizarla posteriormente.
