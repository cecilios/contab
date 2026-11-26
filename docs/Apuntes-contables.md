# Apuntes contables
====================

## Finalidad
------------

Los apuntes contables de Contab sirven principalmente para:

- preparar informes de ingresos y gastos con distintas agrupaciones fiscales;
- facilitar la conciliación con los movimientos bancarios;
- sustituir las anotaciones en papel y evitar la transcripción trimestral a hojas de cálculo.

Contab no pretende gestionar un archivo documental. Las facturas, recibos y justificantes continúan archivándose en el sistema de archivos.

## Apuntes contables y movimientos relacionados

Contab distingue tres cuestiones: **qué ingreso o gasto se ha producido**, **qué dinero debe entrar o salir del banco** y **a quién corresponde económicamente ese ingreso o gasto**. Son cuestiones relacionadas, pero no equivalentes.

### El apunte contable: el hecho económico

`ApunteContable` registra el ingreso o gasto: su fecha, inmueble, categoría, concepto, importes y tratamiento. Es la base de la contabilidad y de los informes fiscales.

Un apunte no acredita por sí mismo que se haya cobrado o pagado.

### El movimiento previsto: la expectativa de cobro o pago

`MovimientoPrevisto` representa una operación monetaria que debe comprobarse mediante conciliación bancaria o confirmación manual.

Todo movimiento previsto guardado tiene **exactamente un origen**:

- Un `ApunteContable`, por ejemplo, el pago de una factura de electricidad o el cobro de un alquiler.
- Una `SolicitudReembolso`, cuando se espera recuperar del inquilino un gasto previamente soportado.

No puede carecer de origen ni tener ambos simultáneamente.

Un apunte puede originar varios movimientos previstos, aunque normalmente genera uno. También puede no generar ninguno si no corresponde una operación monetaria.

### La conciliación: comprobar el cobro o pago

`MovimientoBancario` representa una operación registrada por el banco. La conciliación relaciona los movimientos bancarios con los previstos y permite comprobar pagos y cobros, incluso parciales o agrupados.

Cuando la operación se acredita por otra vía, puede confirmarse mediante una **conciliación manual**, con una explicación obligatoria y sin movimiento bancario.

La conciliación no crea ni sustituye el hecho contable: confirma su realización monetaria.

### Distribuciones e imputaciones: atribuir el gasto

`DistribucionApunte` reparte un gasto común de un inmueble subdividido entre sus locales.

`ImputacionContrato` determina qué parte de un gasto corresponde al propietario y qué parte se atribuye a cada contrato, teniendo en cuenta los períodos y las proporciones aplicables.

Estas operaciones **no representan movimientos bancarios adicionales**. Las imputaciones pueden calcularse para preparar una operación, pero solo se guardan cuando se utilizan efectivamente en una factura o solicitud de reembolso.

Por ejemplo, una factura de electricidad de 100 € atribuida en 40 € al propietario y 60 € al inquilino produce:

- Un apunte contable por 100 €.
- Un movimiento previsto de pago al proveedor por 100 €.
- Una atribución económica de 40 € al propietario y 60 € al inquilino.
- Si se solicita el reembolso, otro movimiento previsto de cobro por 60 €, cuyo origen es la solicitud de reembolso.

**Principio fundamental:** los apuntes registran hechos económicos; los movimientos previstos permiten conciliar cobros y pagos; las distribuciones e imputaciones determinan a quién corresponde cada importe. Ninguna de estas funciones debe confundirse con las demás.


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

- La facturación crea automáticamente los apuntes de ingresos al contabilizar una factura o un alquiler sin factura.
- Los gastos y otros ingresos se introducen manualmente al recibir su documento soporte.
- Al crear manualmente un apunte se genera por defecto un movimiento previsto para conciliación; el usuario puede desactivar expresamente esta generación cuando no corresponda.
- La generación de ese movimiento previsto es independiente del tratamiento contable elegido. Un gasto `CONTABILIZAR`, `REPERCUTIR` o `FACTURAR` puede producir igualmente un pago al proveedor que debe conciliarse.
- Los apuntes pueden corregirse mientras los efectos posteriores ya persistidos lo permitan. Una conciliación total o parcial protege el inmueble, la naturaleza y el importe. Una `ImputacionContrato` persistida protege además los datos que determinan su reparto: inmueble, fecha, base, IVA, retención, período, inclusión del día final y tratamiento
- Los datos descriptivos que no alteran esos efectos históricos, como las notas, pueden seguir corrigiéndose.
- Un apunte no puede eliminarse si tiene movimientos previstos conciliados total o parcialmente ni si existen `ImputacionContrato` persistidas, directamente o a través de sus distribuciones.
- Los informes sustituirán la transcripción trimestral y facilitarán las agrupaciones fiscales anuales.
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

### Inclusión del día final

Los períodos se representan mediante `periodo_desde`,
`periodo_hasta` y el indicador booleano `dia_hasta_incluido`.

La fecha inicial siempre está incluida. Para un intervalo entre
dos fechas, el usuario elige si la fecha final está incluida
o excluida:

- `dia_hasta_incluido=True`: se incluyen ambas fechas.
- `dia_hasta_incluido=False`: se incluye la fecha inicial
  y se excluye la final.

Los períodos mensuales introducidos como `mm/aaaa` incluyen
automáticamente todos los días del mes.

Cuando un apunte no tiene período, las dos fechas y
`dia_hasta_incluido` son `NULL`.

No puede excluirse la fecha final de un período que comienza
y termina el mismo día, porque no contendría días efectivos.

Para los suministros de agua, gas y electricidad, Contab
avisa de posibles huecos o solapamientos con el recibo
anterior, teniendo en cuenta si su fecha final estaba incluida.

### Importes negativos

Contab permite registrar apuntes negativos para representar devoluciones,
abonos y correcciones que disminuyen un ingreso o un gasto previamente
contabilizado.

Por ejemplo, la devolución de un recibo de gas se registra como un gasto
negativo en la categoría original de gas, no como un ingreso de otra naturaleza.

El usuario introduce el signo directamente en el importe de la base:

- `100,00`: apunte positivo.
- `-100,00`: apunte negativo.

Internamente, los importes monetarios se almacenan siempre como magnitudes
positivas. El campo booleano `importe_negativo` conserva el signo del apunte.

El total es un campo calculado y utiliza el mismo signo que la base.
No existen indicadores independientes para el signo de la base y del total.

Al consultar o editar un apunte negativo, los importes se presentan con
el signo menos.

El signo se aplica al apunte completo, sin cambiar su naturaleza
contable ni su clasificación.

Los gastos negativos admiten los mismos tratamientos que los positivos.
Los ingresos, positivos o negativos, solo admiten el tratamiento
Contabilizar.

Los gastos negativos con tratamiento Facturar se incorporan
automáticamente a las facturas como líneas de importe negativo,
minorando su base imponible.

Si la base o el total de la factura resultan negativos, se permite
modificar y previsualizar la propuesta, pero no contabilizarla.
El usuario puede retirar alguna de las devoluciones, que permanecerá
pendiente para una factura posterior.

## Integración con la conciliación
----------------------------------

Al crear un apunte, el formulario propone generar también un movimiento previsto para conciliación. Esta opción está activada por defecto, pero el usuario puede desactivarla cuando el apunte no deba producir una expectativa bancaria.

La creación del movimiento previsto asociado al apunte es independiente de su tratamiento contable. El tratamiento determina cómo se atribuye posteriormente el gasto, pero no elimina el hecho bancario original.

Por tanto, un gasto marcado como `CONTABILIZAR`, `REPERCUTIR` o `FACTURAR`
puede generar un movimiento previsto correspondiente al pago al proveedor.

En los apuntes negativos, el movimiento previsto invierte la naturaleza
bancaria respecto de la naturaleza contable del apunte:

- Un `GASTO` negativo genera un movimiento previsto `INGRESO`, como sucede
  cuando un proveedor devuelve un importe.
- Un `INGRESO` negativo genera un movimiento previsto `GASTO`, como sucede
  cuando se devuelve un ingreso.

El importe esperado del movimiento previsto se mantiene positivo.

En los dos últimos casos podrán aparecer posteriormente operaciones bancarias distintas:

- en `REPERCUTIR`, el ingreso correspondiente al reembolso del inquilino;
- en `FACTURAR`, el cobro de la factura en la que se incorpore el gasto.

Esas operaciones posteriores tendrán sus propios movimientos previstos y no sustituyen al
movimiento previsto del pago original.

El tratamiento determina cómo se utilizará posteriormente el apunte,
pero no elimina el movimiento bancario correspondiente al pago original.
Si se genera, el movimiento previsto reutiliza automáticamente:

- el inmueble;
- la naturaleza;
- el concepto;
- el importe total del apunte;
- el nombre del tercero como contraparte.

Las fechas previstas son datos propios de la conciliación y se introducen separadamente.
Son opcionales y nunca se deducen de la fecha contable del apunte.

El apunte y su movimiento previsto se crean dentro de la misma operación, evitando que un
fallo deje sólo una de las dos partes.

Cuando posteriormente se modifica el apunte, sus movimientos previstos
vinculados se mantienen sincronizados en inmueble, naturaleza bancaria
derivada del signo, concepto, importe esperado y contraparte.

Si cambia el signo de un apunte cuyo movimiento previsto todavía puede
modificarse, se actualiza también la naturaleza del movimiento previsto.

No se modifican durante esa sincronización:

- las fechas previstas;
- el estado del movimiento;
- el método de conciliación;
- las notas utilizadas para documentar una conciliación manual.

Los movimientos pendientes y cancelados no imponen restricciones propias sobre la
modificación del apunte. No obstante, pueden existir otros efectos históricos, como `ImputacionContrato` persistidas, que protejan los datos utilizados para calcularlos.

Un apunte no puede eliminarse mientras tenga un movimiento previsto conciliado total o parcialmente. Los movimientos pendientes o cancelados se eliminan junto con el apunte.


## Edición de apuntes

Desde el listado de apuntes contables pueden corregirse los datos de un apunte existente, siempre que se respeten sus operaciones relacionadas.

Las restricciones dependen de la situación del apunte:

- **Factura vinculada:** solo pueden corregirse los datos descriptivos y documentales. Los datos propios de la factura están protegidos.
- **Alquiler vinculado a un contrato:** no pueden cambiarse el inmueble, la naturaleza, la categoría, el período, el signo ni el tratamiento. La fecha debe permanecer dentro de la vigencia del contrato.
- **Conciliación total o parcial:** no pueden cambiarse el inmueble, la naturaleza, el importe total ni su signo.
- **Imputaciones realizadas:** no pueden cambiarse el inmueble, la naturaleza, la fecha, los importes, el signo, el período, su criterio de cómputo ni el tratamiento.

Cuando coinciden varias situaciones, se aplican todas sus restricciones.

Un ingreso ordinario puede reclasificarse como alquiler si sus movimientos no están conciliados y, cuando existen movimientos previstos, puede identificarse el contrato correspondiente sin duplicar un alquiler ya contabilizado.

El formulario informa de las restricciones, bloquea los campos protegidos y limita las opciones disponibles.

Los apuntes históricos pueden conservar su inmueble y clasificación originales aunque estén inactivos. No pueden asignarse otros elementos inactivos.

Las modificaciones deben validarse antes de guardarse.


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

- **Contabilizar (`CONTABILIZAR`)**: el ingreso o gasto pertenece al propietario y forma parte de su contabilidad.
- **Trasladar el gasto (`REPERCUTIR`)**: el propietario paga inicialmente el gasto, pero la parte atribuible a un inquilino deberá ser reembolsada por éste. Esa parte no constituye gasto fiscal del propietario ni el reembolso constituye ingreso fiscal.
- **Facturar (`FACTURAR`)**: el gasto pertenece al propietario y forma parte de su contabilidad. Además, la parte atribuible a un inquilino se incorporará posteriormente a una factura, cuyo ingreso se contabilizará normalmente.

El tratamiento contable no modifica la conciliación del pago original al proveedor.

Los ingresos solo admiten el tratamiento Contabilizar. Los gastos admiten cualquiera de los tres tratamientos,
independientemente de su signo.

El formulario limita las opciones de tratamiento según la clasificación seleccionada.

La existencia de un contrato vigente en la fecha del apunte no es requisito para seleccionar `REPERCUTIR` o `FACTURAR`. La atribución efectiva a contratos se determina posteriormente utilizando el período del gasto y los contratos que correspondan a ese período.

Cuando una parte del gasto no pueda atribuirse a ningún contrato, queda a cargo del propietario.

No existe un indicador genérico de «gestionado». El estado se deduce del proceso correspondiente: imputación a contratos, solicitud de reembolso o inclusión en factura.


## Control de duplicados
-------------------------

Actualmente se bloquea un documento con el mismo emisor y referencia ya registrado para el mismo inmueble.

Si coincide con un documento de otro inmueble, se muestra un aviso y se permite guardarlo, porque una factura puede repartirse excepcionalmente entre varios inmuebles.

Más adelante se añadirán avisos de duplicado probable para apuntes sin emisor o referencia, comparando inmueble, clasificación, período, importes y concepto. Estos avisos no serán bloqueantes.

## Inmuebles subdivididos
--------------------------

Los gastos comunes de un inmueble de tipo `T` se registran en el inmueble subdividido.

Al crear el apunte, Contab genera automáticamente una distribución persistente entre los locales hijo según sus participaciones. La distribución conserva una copia de los coeficientes y de los importes atribuidos en ese momento.

El pago al proveedor sigue correspondiendo al apunte original del inmueble `T` y su movimiento previsto se vincula a ese apunte, no a cada distribución.

Posteriormente, cada parte distribuida puede atribuirse temporalmente a uno o varios contratos según el período del gasto.

Se mantiene esta distinción terminológica:

- **distribuir**: repartir espacialmente un gasto común entre los locales;
- **repercutir**: exigir al inquilino el reembolso de un gasto;
- **facturar**: incorporar a una factura un gasto que sigue siendo contablemente del propietario.
