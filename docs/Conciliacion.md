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

La pantalla **Revisar conciliación** tiene dos zonas:

- **Propuestas automáticas.** Contab presenta correspondencias posibles. Se aceptan o rechazan individualmente. Rechazar una propuesta la traslada a la sección manual durante la sesión, sin modificar la base de datos.
- **Selección manual de movimientos.** El usuario selecciona previstos y bancarios que reconoce y confirma la correspondencia. Se muestran los totales de ambos lados y la diferencia.

En la operativa actual pueden confirmarse correspondencias **1:1, 1:n y m:1 de importes coincidentes**, con saldos pendientes incluidos. Las propuestas 1:1 con importes distintos **se muestran, pero aún no pueden aceptarse**.

El algoritmo debe priorizar los importes exactos y proponer sólo diferencias pequeñas y bien identificadas. No debe sugerir pagos parciales muy desiguales como si fuesen pequeñas diferencias. La detección automática de 1:3 y 3:1 está aplazada, aunque la selección manual exacta permite esas cardinalidades.

Los movimientos bancarios ajenos a Contab pueden **Descartarse** y restaurarse posteriormente.

## Conciliación manual sin banco

Es una función diferente de la selección manual de movimientos bancarios. Permite dar por resuelto un previsto sin asociarle un movimiento de la cuenta importada: por ejemplo, por un cobro en metálico o un pago desde otra cuenta.

Es **obligatorio escribir el motivo** en las notas. No se inventa un movimiento bancario y la operación debe poder deshacerse.

Esta función existía en Contab, pero **debemos recuperar o comprobar su acceso en la interfaz renovada**. No debe desaparecer ni confundirse con la selección manual de casillas.

## Conciliación exacta, progresiva y con diferencia

- **Exacta:** coinciden los importes pendientes; se confirma la asociación y quedan conciliados los movimientos cuya parte disponible se ha agotado.
- **Progresiva:** el usuario aplica sólo parte del importe disponible. Por ejemplo, una factura de 1.000 € y un ingreso de 600 €: el bancario queda conciliado y la factura parcial, con 400 € disponibles para asociar más adelante.
- **Aceptar diferencia:** el usuario reconoce una correspondencia, por ejemplo 1.000 € previstos y 995 € ingresados, y cierra su revisión sin esperar otro cobro. La diferencia de 5 € permanece en el saldo económico. **Esta última operación está pendiente de implementar.**

Cuando los importes sean iguales basta con **Aceptar**. Para importes distintos, la futura interfaz ofrecerá dos acciones sencillas: **Conciliar parcialmente** o **Aceptar diferencia**. No preguntará si hay que reclamar, condonar o compensar: eso no se decide al conciliar.

La conciliación progresiva admite sucesivas asociaciones **1:n o m:1** durante meses; **no se implementará una operación m:n independiente**.

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
