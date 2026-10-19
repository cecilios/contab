# Conciliación bancaria

## Finalidad

Contab facilita la revisión periódica de movimientos bancarios y su correspondencia con los cobros y pagos previstos. **Contab propone y el usuario confirma.** Los importes originales nunca se alteran para hacerlos coincidir.

La conciliación y el control económico responden a dos preguntas distintas:

- **Conciliación:** ¿a qué cobro o pago previsto corresponde este movimiento bancario y qué importe se ha asociado?
- **Situación del contrato:** ¿cuánto es exigible, cuánto se ha cobrado efectivamente y cuál es la deuda o el crédito acumulado?

Aceptar una pequeña diferencia al conciliar **no implica condonarla**, ni crear un apunte artificial. La diferencia permanece en el saldo económico del contrato.

## Movimientos y estados

Un **movimiento bancario** conserva la fecha, el importe, la naturaleza (ingreso o gasto) y la descripción original del banco. Un **movimiento previsto** representa un cobro o pago esperado, normalmente vinculado a un apunte o una factura.

Los movimientos pueden estar **Pendiente**, **Parcial** o **Conciliado**. El bancario puede estar también **Descartado** (ajeno a Contab) y el previsto **Cancelado**. Descarte y cancelación son reversibles.

**Parcial** significa que sólo se ha asociado parte del importe y que el saldo restante puede participar en conciliaciones posteriores.


## Revisar conciliación

La pantalla **Revisar conciliación** distingue dos zonas:

- **Propuestas automáticas.** Contab identifica correspondencias
  probables entre movimientos bancarios y previstos. El usuario puede
  aceptarlas o rechazarlas. Rechazar una propuesta libera sus movimientos
  para seleccionarlos manualmente durante la sesión, sin modificar la
  base de datos.
- **Conciliación manual.** Se divide en dos formularios independientes,
  **Ingresos** y **Gastos**, cada uno con sus movimientos previstos,
  bancarios, totales, diferencia y botones de confirmación. Así se evita
  mezclar movimientos de distinta naturaleza.

Se admiten conciliaciones **1:1, 1:n y m:1**, exactas o parciales,
y la aceptación explícita de diferencias. No se permite seleccionar
simultáneamente varios previstos y varios bancarios (m:n).

Las propuestas automáticas priorizan las correspondencias exactas.
También pueden proponer diferencias 1:1 cuando son pequeñas
(como máximo el 5 % del saldo previsto), las fechas son compatibles,
la contraparte está identificada y no existen alternativas ambiguas.

Las propuestas automáticas agrupadas abarcan actualmente 1:2 y 2:1.
La detección automática de 1:3 y 3:1 queda aplazada, aunque esas
cardinalidades pueden conciliarse mediante selección manual.

Cuando los importes pendientes coinciden, se ofrece la confirmación
exacta. Cuando difieren, se puede elegir entre **Conciliar parcialmente**
y **Aceptar diferencia**.

Los movimientos bancarios ajenos a Contab pueden **Descartarse**
y restaurarse posteriormente.


## Conciliación manual sin banco

Es una función diferente de la selección manual de movimientos bancarios. Permite dar por resuelto un previsto sin asociarle un movimiento de la cuenta importada: por ejemplo, por un cobro en metálico o un pago desde otra cuenta.

Es **obligatorio escribir el motivo** en las notas. No se inventa un movimiento bancario y la operación debe poder deshacerse.

La acción **Conciliar sin banco** está disponible en la pantalla
de revisión para los movimientos previstos. Requiere indicar un motivo
en las notas, no crea un movimiento bancario ficticio y puede deshacerse.


## Conciliación exacta, progresiva y con diferencia

- **Exacta:** coinciden los importes pendientes. Se confirman las
  asociaciones y los movimientos correspondientes quedan conciliados.
- **Progresiva:** se asocia el importe realmente disponible, dejando
  el resto pendiente para conciliaciones posteriores. Por ejemplo,
  una factura de 1.000 € y un ingreso de 600 € producen una asociación
  de 600 €; el bancario queda conciliado y el previsto queda parcial,
  con 400 € disponibles.
- **Aceptar diferencia:** el usuario reconoce una correspondencia
  aunque los importes sean diferentes y cierra la revisión de los
  movimientos afectados. Por ejemplo, frente a 1.000 € previstos,
  un ingreso de 995 € se asocia por 995 €, pero el previsto queda
  marcado como conciliado. Los 5 € no se consideran condonados.

El sistema conserva siempre los importes originales. Las asociaciones
registran exclusivamente los importes efectivamente aplicados.

La conciliación progresiva y el cierre con diferencias admiten
selecciones **1:1, 1:n y m:1**. Los importes de una selección agrupada
se distribuyen cronológicamente, de los movimientos más antiguos a
los más recientes, utilizando el identificador para resolver empates.

Todos los movimientos seleccionados deben participar en alguna
asociación. La operación se rechaza si alguno queda completamente
sin asociar.

Al aceptar una diferencia agrupada entre varios movimientos previstos,
todos deben pertenecer al **mismo contrato identificado**. No se permite
atribuir automáticamente la diferencia entre contratos distintos ni
entre movimientos cuyo contrato se desconoce.

Esta exigencia de contrato común no se aplica a las conciliaciones
progresivas sin cierre de diferencia.

La aceptación de una diferencia se registra en la asociación,
permitiendo distinguir un movimiento completamente aplicado de uno
cuya revisión se ha cerrado expresamente. Ambas operaciones pueden
deshacerse y los estados se recalculan.

No se implementa una operación m:n independiente ni un sistema
adicional de grupos de conciliación.

Aceptar una diferencia no significa perdonarla, reclamarla ni
compensarla. Esas decisiones no corresponden a la conciliación bancaria.


## Situación económica del contrato

La futura pantalla de situación por contrato o local mostrará, a una fecha dada, las **facturas y otros importes exigibles** frente a los **ingresos reales atribuidos al contrato**, y sus totales:

**Saldo del contrato = total exigible − total efectivamente cobrado.**

Un saldo positivo indica deuda del inquilino; uno negativo, crédito a su favor. Se acumulan las diferencias entre períodos, también los céntimos.

Ejemplo: en octubre se debían 920 € y se ingresaron 900 €; quedan 20 € de deuda. En noviembre se debían 920 € y se ingresaron 940 €; el saldo acumulado pasa a cero, aunque ambas conciliaciones bancarias se hayan cerrado con diferencia.

**Esta pantalla aún está pendiente de desarrollar.** La atribución de ingresos al contrato, incluidos los cobros en efectivo y los pagos a cuenta sin factura específica, debe ser inequívoca y evitar dobles cómputos.

## Principios

1. Contab propone; el usuario confirma.
2. Los importes originales y las correspondencias quedan trazables.
3. El estado **Parcial** conserva la posibilidad de seguir aplicando saldos.
4. Una diferencia aceptada no desaparece de la situación económica.
5. Las decisiones deben poder corregirse; no se crean movimientos ficticios para cuadrar importes.
6. No se crea una operación m:n ni un sistema de grupos de conciliación adicional.
