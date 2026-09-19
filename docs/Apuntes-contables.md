# Apuntes contables
====================

## Finalidad
------------

Los apuntes contables de Contab sirven principalmente para:

- preparar informes de ingresos y gastos con distintas agrupaciones fiscales;
- facilitar la conciliación con los movimientos bancarios;
- sustituir las anotaciones en papel y evitar la transcripción trimestral a hojas de cálculo.

Contab no pretende gestionar un archivo documental. Las facturas, recibos y justificantes continúan archivándose en el sistema de archivos.

## Operativa manual actual
--------------------------

- Las facturas recibidas se descargan, renombran y archivan en la carpeta del inmueble.
- Cada ingreso o gasto se anota de forma resumida en un cuaderno.
- Trimestralmente, los apuntes se transcriben a una hoja de cálculo para preparar el IVA.
- Anualmente, la información se reorganiza según el desglose exigido por Hacienda para el IRPF.
- Los errores se descubren al revisar facturas, períodos, movimientos bancarios o datos esperados.

Esta operativa obliga a registrar información varias veces y a rehacer agrupaciones cuando cambian las exigencias fiscales.

## Operativa prevista con Contab
--------------------------------

- La facturación creará automáticamente los apuntes de ingresos cuando se implemente su emisión completa.
- Los gastos y otros ingresos se introducirán manualmente al recibir su documento soporte.
- Al crear manualmente un apunte se genera por defecto un movimiento previsto para conciliación; el usuario puede desactivar expresamente esta generación cuando no corresponda.
- Los apuntes pueden corregirse mientras sus movimientos previstos no estén conciliados. Si existe una conciliación total o parcial, no pueden modificarse el inmueble, la naturaleza ni el importe, aunque sí los datos descriptivos.
- Los apuntes pueden eliminarse mientras no tengan movimientos previstos conciliados total o parcialmente.- Los informes sustituirán la transcripción trimestral y facilitarán las agrupaciones fiscales anuales.
- La conciliación bancaria permitirá concentrar la revisión en movimientos no conciliados, duplicados o ausencias esperadas.

## Entrada de un apunte
-----------------------

El usuario selecciona el inmueble e introduce los datos contables esenciales: fecha, clasificación, concepto, período cuando exista, importes y, opcionalmente, datos del emisor y referencia del documento.

La clasificación se muestra mediante literales comprensibles, aunque internamente permanezca estable para poder agrupar los datos en informes.

El período puede ser:

- inexistente;
- un mes completo, introducido como `mm/aaaa`;
- un intervalo entre dos fechas.

Los períodos servirán más adelante para detectar recibos duplicados, huecos y solapamientos.

## Integración con la conciliación
----------------------------------

Al crear un apunte, el formulario propone generar también un movimiento previsto para conciliación. Esta opción está activada por defecto, pero el usuario puede desactivarla cuando el apunte no deba producir una expectativa bancaria.

Si se genera, el movimiento previsto reutiliza automáticamente:

- el inmueble;
- la naturaleza;
- el concepto;
- el importe total del apunte;
- el nombre del tercero como contraparte.

Las fechas previstas son datos propios de la conciliación y se introducen separadamente. Son opcionales y nunca se deducen de la fecha contable del apunte.

El apunte y su movimiento previsto se crean dentro de la misma operación, evitando que un fallo deje sólo una de las dos partes.

Cuando posteriormente se modifica el apunte, sus movimientos previstos vinculados se mantienen sincronizados en inmueble, naturaleza, concepto, importe esperado y contraparte.

No se modifican durante esa sincronización:

- las fechas previstas;
- el estado del movimiento;
- el método de conciliación;
- las notas utilizadas para documentar una conciliación manual.

Los movimientos pendientes y cancelados permiten modificar todos los datos del apunte.

Si existe algún movimiento conciliado total o parcialmente, no pueden modificarse el inmueble, la naturaleza ni el importe. La validación del formulario detecta esta situación antes de guardar y no habilita el guardado.

Los datos descriptivos sí pueden corregirse después de conciliar. El movimiento previsto se actualiza conservando intacta la conciliación existente.

Un apunte tampoco puede eliminarse mientras tenga un movimiento previsto conciliado total o parcialmente. Los movimientos pendientes o cancelados se eliminan junto con el apunte.

## Ayudas para reducir la entrada manual
----------------------------------------

Al seleccionar la clasificación, Contab propone un concepto comprensible. El usuario puede completarlo o sustituirlo.

Cuando el concepto sigue siendo automático, al validar se completa con el período:

- `Comunidad 03/2026`;
- `Gas. 17/03/2026 a 14/05/2026`.

Contab propone también el nombre del documento a partir del inmueble, concepto y período:

- `LOCAL-1-Impuesto IBI 2026.pdf`;
- `LOCAL-1-Comunidad 2026-03.pdf`;
- `LOCAL-1-Gas 2026-03-17 a 2026-05-14.pdf`.

Las propuestas automáticas se recalculan cuando cambia un dato relevante. Los valores modificados expresamente por el usuario se respetan.

El formulario sigue el proceso `Validar` y después `Guardar`:

- `Validar` comprueba el apunte, calcula el importe a pagar y prepara concepto y nombre documental;
- `Guardar` sólo está disponible después de validar;
- si se modifica algún dato, es obligatorio validar otra vez.

## Tratamiento del apunte
--------------------------

Cada apunte tiene uno de estos tratamientos:

- **Contabilizar**: forma parte de la contabilidad y de los informes.
- **Trasladar el gasto**: queda pendiente de trasladarlo al inquilino o, en un inmueble subdividido, de distribuirlo entre sus locales.
- **Facturar**: queda pendiente de incorporarlo a una factura.

Inicialmente, los apuntes marcados para trasladar o facturar se excluyen de los informes contables.

En un inmueble normal, trasladar o facturar exige que exista un contrato vigente. Un inmueble sin contrato puede seguir registrando apuntes ordinarios. Un inmueble subdividido puede contabilizar gastos comunes o marcarlos para distribuirlos, pero no facturarlos directamente.

No existe un indicador genérico de «gestionado». El estado se deducirá del proceso correspondiente: distribución, traslado al inquilino o inclusión en factura. Así se evitan estados incoherentes.

## Control de duplicados
-------------------------

Actualmente se bloquea un documento con el mismo emisor y referencia ya registrado para el mismo inmueble.

Si coincide con un documento de otro inmueble, se muestra un aviso y se permite guardarlo, porque una factura puede repartirse excepcionalmente entre varios inmuebles.

Más adelante se añadirán avisos de duplicado probable para apuntes sin emisor o referencia, comparando inmueble, clasificación, período, importes y concepto. Estos avisos no serán bloqueantes.

## Inmuebles subdivididos
--------------------------

Los gastos comunes se registran en el inmueble subdividido. Su distribución analítica entre los locales se abordará con los informes contables.

Se mantiene esta distinción terminológica:

- **distribuir**: repartir un gasto común entre los locales para informes;
- **trasladar o repercutir**: exigir al inquilino el pago de un gasto.

## Trabajo pendiente relacionado
---------------------------------

- Distribución de gastos comunes entre locales.
- Gestión de gastos pendientes de trasladar o facturar.
- Avisos de duplicados probables, huecos y solapamientos de períodos.
- Plantillas de conceptos habituales configurables en `contab.ini`.
- Ajustes finales de presentación del formulario y del listado.
