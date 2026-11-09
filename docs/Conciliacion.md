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

Las propuestas automáticas priorizan las correspondencias **exactas**, tanto 1:1 como agrupadas. También admiten propuestas con diferencia de hasta el **5 % del total previsto pendiente**, calculada en céntimos y sin redondeos, para las cardinalidades 1:1, 1:2 y 2:1.

Las propuestas con diferencia requieren fechas y naturalezas compatibles e **identificación de contraparte en todas las parejas** de la propuesta. Las candidatas individuales y agrupadas compiten entre sí: se favorece la combinación que explica mejor los movimientos y deja menor diferencia, conservando las protecciones frente a alternativas ambiguas.

Por ejemplo, ante un ingreso de 1.021,00 €, un alquiler previsto de 1.000,00 € y un reembolso de agua de 20,69 €, Contab puede preferir la agrupación de ambos previstos, cuya diferencia es de sólo **+0,31 €**, frente a conciliar exclusivamente el alquiler, que dejaría una diferencia de +21,00 €.

Si varias agrupaciones alternativas presentan la misma puntuación de identificación y fechas, Contab evita decidir únicamente por una pequeña diferencia de importes y deja el caso para revisión manual.

La detección automática de agrupaciones 1:3 y 3:1 queda aplazada, aunque esas cardinalidades pueden conciliarse mediante selección manual.

Cuando los importes pendientes coinciden, se ofrece la confirmación
exacta. Cuando difieren, se puede elegir entre **Conciliar parcialmente**
y **Aceptar diferencia**.

Los movimientos bancarios ajenos a Contab pueden **Descartarse**
y restaurarse posteriormente.


## Identificación de contrapartes

Para las propuestas automáticas con diferencia, Contab debe identificar la contraparte del movimiento bancario. La identificación se realiza comparando el texto bancario (tipo, descripción y referencia) con la contraparte informada en el movimiento previsto y con los alias configurados en `contab.ini`.

Los alias se definen mediante secciones con esta estructura:

```ini
[conciliacion:<base_de_datos>:<tipo>:<referencia_inmueble>]
```

### Alias de inquilino

Para identificar los ingresos de un inquilino se recomienda utilizar el tipo especial `inquilino`:

```ini
[conciliacion:demo:inquilino:AVLOGRO]
alias =
    FRUTERIAS EL
    GERARDO LOPEZ
```

Estos alias se aplican a **todos los movimientos previstos de naturaleza INGRESO del inmueble indicado**, independientemente de su concepto: alquiler, reembolso de agua, repercusión de gastos u otros ingresos.

Así, una única identificación del pagador permite proponer conciliaciones que agrupen varias obligaciones pendientes del mismo inmueble.

El alias identifica al pagador y el inmueble, pero **no determina por sí solo qué previstos deben conciliarse ni identifica inequívocamente un contrato**. La selección automática sigue comprobando importes, fechas, naturaleza y posibles conflictos.

### Alias específicos por concepto

Las secciones anteriores continúan siendo válidas:

```ini
[conciliacion:demo:comunidad:AVLOGRO]
alias =
    C.P. AV. LOGROÑ
    CP.AV.LOGROÑO
    C.P. AVENIDA LO
```

En este caso, el alias sólo se aplica a movimientos previstos del inmueble cuyo concepto contenga el tipo `comunidad`.

También siguen admitiéndose secciones específicas como `alquiler` o `reembolso`, aunque para identificar ingresos habituales del inquilino resulta preferible una única sección `inquilino`.

Los alias están asociados a una base de datos concreta y a una referencia de inmueble. No se aplican automáticamente a otras bases de datos ni a otros inmuebles.

**La conciliación manual no exige identificar la contraparte mediante estos mecanismos**, porque el usuario establece expresamente la correspondencia entre los movimientos.


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

Al aceptar una diferencia agrupada entre varios movimientos previstos, todos deben pertenecer al **mismo contrato identificado** o, si ninguno tiene contrato asociado, al **mismo inmueble**. Se rechaza el cierre cuando los previstos pertenecen a contratos diferentes, corresponden a inmuebles distintos sin contrato o mezclan movimientos con contrato identificado y movimientos sin contrato.

Estas restricciones de cierre no se aplican a las conciliaciones progresivas que dejan la diferencia pendiente. La conciliación manual tampoco requiere que se haya identificado automáticamente la contraparte.

La aceptación de una diferencia se registra en la asociación,
permitiendo distinguir un movimiento completamente aplicado de uno
cuya revisión se ha cerrado expresamente. Ambas operaciones pueden
deshacerse y los estados se recalculan.

No se implementa una operación m:n independiente ni un sistema
adicional de grupos de conciliación.

Aceptar una diferencia no significa perdonarla, reclamarla ni
compensarla. Esas decisiones no corresponden a la conciliación bancaria.



## Situación económica del contrato

Contab dispone de una pantalla de situación económica por
contrato que compara las obligaciones exigibles al inquilino
con los cobros y devoluciones efectivamente atribuidos.

La consulta se realiza siempre hasta la fecha actual.
El usuario puede indicar la fecha inicial del período.

La situación económica es independiente del estado de
revisión de las conciliaciones. Una diferencia aceptada
al conciliar no se considera automáticamente perdonada.

### Obligaciones exigibles

Se incluyen las obligaciones del contrato procedentes de:

- facturas emitidas, desde su fecha de emisión;
- alquileres contabilizados sin factura, desde la fecha
  del apunte contable;
- solicitudes de reembolso enviadas, desde su fecha
  de envío.

Las correcciones negativas reducen el exigible.

Una factura asociada a un apunte no se cuenta dos veces.

Los gastos propios del propietario no se consideran
automáticamente deudas del inquilino.

### Cobros y devoluciones

Los movimientos bancarios se incorporan por el importe
efectivamente asociado mediante `Conciliacion.importe_asociado`.

Se utiliza la fecha del movimiento bancario.

Un cobro parcial se incorpora por su importe asociado,
sin dar por ingresada la cantidad pendiente.

Las diferencias aceptadas al cerrar una conciliación
permanecen reflejadas en el saldo económico del contrato.

Las devoluciones al inquilino se incorporan con signo
negativo cuando corresponden a reembolsos o correcciones
negativas de alquiler atribuidas al contrato.

No se incluyen movimientos bancarios sin atribución
al contrato.

### Conciliaciones manuales sin banco

Un movimiento previsto confirmado manualmente se considera
realizado por su importe completo, aunque no tenga
movimiento bancario asociado.

Su fecha de referencia se determina por este orden:

1. Fecha del apunte contable que originó el previsto,
   si existe.
2. Fecha prevista inicial del movimiento, en otro caso.
3. Fecha desconocida, si no existe ninguna de las anteriores.

En el último caso, el importe confirmado se incluye en
el saldo actual y se presenta en el detalle como
**Fecha desconocida**. No se inventa una fecha.

Las fechas previstas originales no se modifican al
conciliar; siguen siendo información orientativa
conservada en el movimiento previsto.

### Saldos y períodos

La pantalla separa:

- **Saldo anterior:** obligaciones menos cobros fechados
  antes de la fecha inicial seleccionada.
- **Total a ingresar:** obligaciones exigibles del período.
- **Total ingresado:** cobros netos del período.
- **Saldo pendiente:** saldo anterior más total a ingresar
  menos total ingresado.

Los movimientos manuales sin ninguna fecha conocida
se incluyen en el período consultado, nunca en el
saldo anterior.

Un saldo positivo representa deuda del inquilino.
Un saldo negativo representa crédito a su favor.

Las diferencias entre obligaciones y cobros se acumulan
entre períodos, también los céntimos.

Por ejemplo, si en octubre eran exigibles 920 € y se
cobraron 900 €, quedan 20 € pendientes. Si en noviembre
eran exigibles otros 920 € y se cobraron 940 €, el saldo
acumulado pasa a cero.

Cada cálculo se limita al contrato seleccionado.
No se trasladan deudas entre contratos sucesivos
de un mismo inmueble.

La pantalla muestra la situación actual utilizando
las fechas de referencia disponibles. No pretende
reconstruir retrospectivamente cuándo se confirmó
cada conciliación manual.

## Principios

1. Contab propone; el usuario confirma.
2. Los importes originales y las correspondencias quedan trazables.
3. El estado **Parcial** conserva la posibilidad de seguir aplicando saldos.
4. Una diferencia aceptada no desaparece de la situación económica.
5. Las decisiones deben poder corregirse; no se crean movimientos ficticios para cuadrar importes.
6. No se crea una operación m:n ni un sistema de grupos de conciliación adicional.
