# Conciliación de movimientos

## Finalidad

La conciliación bancaria es uno de los dos objetivos principales de Contab, junto con la obtención de información contable adaptable a las necesidades fiscales.

Su finalidad es reducir el trabajo necesario para revisar los movimientos bancarios, relacionarlos con los ingresos y gastos esperados y localizar las excepciones que requieren intervención.

Contab propone y facilita el trabajo, pero el usuario conserva siempre el control y confirma el resultado final.

La conciliación no debe forzar todos los casos reales a una correspondencia individual entre un movimiento bancario y un movimiento previsto. Lo importante es que cada situación quede resuelta de forma comprensible y trazable.

## El problema real

El usuario revisa periódicamente los movimientos del banco y trata de relacionarlos con alquileres cobrados, facturas y recibos pagados, gastos previstos y otros movimientos conocidos.

La información bancaria no es uniforme. Los textos pueden contener nombres, direcciones, referencias o descripciones genéricas y no siempre permiten identificar directamente el inmueble o concepto correspondiente.

La mayoría de los movimientos ordinarios tienen una correspondencia sencilla:

* los alquileres suelen coincidir con un ingreso bancario;
* los recibos domiciliados suelen coincidir exactamente con el gasto contabilizado;
* las transferencias realizadas para pagar gastos suelen coincidir con el importe previsto.

Sin embargo, existen excepciones reales:

* un pago grande puede dividirse en varias transferencias;
* tributos como IBI y TRU pueden contabilizarse por inmueble pero ser cobrados por el Ayuntamiento de forma agrupada;
* algunos gastos se pagan en efectivo o con tarjeta y no aparecen en la cuenta conciliada;
* algunos ingresos excepcionales pueden cobrarse en efectivo;
* un inquilino con atrasos puede realizar pagos parciales e irregulares cuyo control resulta más útil por saldo total que asignando artificialmente cada ingreso a una mensualidad concreta;
* una diferencia en un recibo domiciliado puede indicar un error en el apunte contable y debe revisarse, no aceptarse automáticamente.

Estas excepciones son poco frecuentes y el número de inmuebles es pequeño. Contab no intenta automatizarlas todas. Debe permitir resolverlas explícitamente y dejar constancia de lo ocurrido.

## Movimientos bancarios y previstos

La conciliación trabaja principalmente con dos clases de movimientos.

Un **movimiento bancario** representa una operación importada de la cuenta bancaria. Conserva la fecha, naturaleza —ingreso o gasto—, importe y los textos originales proporcionados por el banco.

Puede estar:

* **Pendiente:** todavía no está resuelto.
* **Conciliado:** ha sido relacionado y confirmado.
* **Descartado:** es personal o ajeno a Contab.

Descartar es reversible.

Un **movimiento previsto** representa un cobro o pago que Contab espera encontrar o resolver. Actualmente, los movimientos previstos pueden crearse desde los apuntes contables. El modelo permite también movimientos sin apunte asociado, pero no se ha construido una operativa adicional mientras no exista un caso real que la justifique.
Puede estar:

* **Pendiente.**
* **Parcialmente conciliado.**
* **Conciliado.**
* **Cancelado.**

La cancelación es reversible.

El estado expresa si el movimiento está resuelto, no cómo se ha resuelto.

### Relación con los apuntes contables

Al crear manualmente un apunte contable, Contab propone generar también su movimiento previsto. La opción está activada por defecto y puede desactivarse expresamente.

El movimiento reutiliza del apunte el inmueble, naturaleza, concepto, importe total y tercero. Las fechas previstas son independientes de la fecha contable y pueden dejarse vacías.

Mientras el movimiento está pendiente o cancelado, las modificaciones del apunte se trasladan al movimiento previsto.

Una vez conciliado total o parcialmente, el inmueble, la naturaleza y el importe del apunte quedan protegidos. Los cambios descriptivos siguen siendo posibles y se sincronizan sin alterar las fechas previstas, estado, método ni notas de conciliación.

Esta relación permite introducir el hecho económico una sola vez y conservar después la separación entre información contable y resolución bancaria.

## Estado y método de conciliación

Se mantienen separadas dos preguntas:

* **Estado:** ¿está resuelto?
* **Método:** ¿cómo sabemos que está resuelto?

Por ello no existen estados especiales como `MANUAL` o `CONTABILIZADO`.

Actualmente un movimiento previsto conciliado puede tener dos métodos:

* **Individual:** existe una correspondencia normal entre un movimiento bancario y un movimiento previsto.
* **Manual:** el usuario ha comprobado la situación por otro medio y ha explicado cómo se resolvió.

En ambos casos el estado final es **Conciliado**.

Esta separación permite ampliar en el futuro los métodos de resolución sin complicar innecesariamente los estados.

## Propuestas automáticas

La conciliación automática intenta resolver el caso habitual de correspondencia individual entre un movimiento bancario pendiente y un movimiento previsto pendiente.

Las propuestas se calculan mediante reglas sencillas y explícitas basadas en:

* igualdad del importe;
* identificación de la contraparte en el texto bancario;
* alias conocidos que permiten reconocer el inmueble y tipo de movimiento;
* proximidad de las fechas.

Los textos se comparan normalizados para ignorar diferencias de mayúsculas, acentos y espacios.

Sólo se propone una correspondencia cuando existe un candidato suficientemente claro y no hay empate entre los mejores candidatos.

No se utiliza por ahora coincidencia aproximada, aprendizaje automático ni comportamiento histórico. Las reglas se ampliarán únicamente cuando los casos reales demuestren que resulta útil.

## Confirmación automática individual

Una propuesta automática nunca modifica los movimientos hasta que el usuario la confirma.

Para confirmar automáticamente una correspondencia individual, ambos movimientos deben tener la misma naturaleza y exactamente el mismo importe.

Al confirmarla:

* el movimiento bancario queda **Conciliado**;
* el movimiento previsto queda **Conciliado**;
* el método del movimiento previsto queda registrado como **Individual**;
* se conserva la relación entre ambos movimientos.

Las propuestas con importes diferentes se muestran separadamente y no pueden confirmarse mediante el proceso automático normal.

El usuario también puede utilizar **Dejar pendiente** para rechazar temporalmente una propuesta durante la sesión de revisión.

La confirmación conjunta vuelve a calcular las propuestas antes de guardarlas y sólo confirma las correspondencias exactas que continúan siendo válidas.

## Conciliación manual

Cuando una situación real no puede representarse correctamente mediante una correspondencia bancaria individual, el usuario puede conciliar manualmente el movimiento previsto.

La conciliación manual sirve, por ejemplo, para:

* gastos o ingresos en efectivo;
* gastos pagados con una tarjeta que no corresponde a la cuenta importada;
* tributos contabilizados individualmente pero cobrados de forma agrupada;
* situaciones de atrasos controladas externamente por saldo;
* otras excepciones que el usuario haya comprobado por medios distintos de una correspondencia bancaria individual.

Para conciliar manualmente es obligatorio introducir una explicación.

Al confirmarla:

* el movimiento previsto pasa a **Conciliado**;
* su método queda registrado como **Manual**;
* la explicación se conserva en sus notas;
* no se crea artificialmente ningún movimiento bancario ni una relación bancaria inexistente.

En el listado de movimientos previstos se muestra el método junto al estado. Para las conciliaciones manuales se muestra también la explicación, de forma que la excepción pueda entenderse directamente.

Ejemplo:

```
Conciliado · Manual
Incluido en los cargos agrupados del Ayuntamiento.
```

La finalidad de la explicación es poder comprender posteriormente qué ocurrió y por qué el movimiento se consideró resuelto.

## Deshacer una conciliación manual

Una conciliación manual puede haberse confirmado por error y debe ser reversible.

El usuario puede utilizar **Deshacer conciliación** sobre un movimiento conciliado manualmente.

El movimiento vuelve entonces a:

* estado **Pendiente**;
* sin método de conciliación;
* sin la explicación de la conciliación manual.

Esta operación sólo está disponible para conciliaciones manuales.

Una conciliación individual con un movimiento bancario asociado no puede deshacerse mediante esta acción, porque requeriría tratar también la relación y el estado del movimiento bancario.

## Flujo habitual

El proceso normal de conciliación es:

1. El usuario importa el CSV descargado del banco.
2. Contab incorpora los movimientos nuevos evitando duplicados.
3. La revisión considera los movimientos bancarios y previstos pendientes.
4. Contab calcula las propuestas automáticas.
5. El usuario revisa las propuestas antes de que se modifique ningún movimiento.
6. Las propuestas exactas aceptadas se confirman como conciliaciones individuales.
7. Las discrepancias y movimientos sin correspondencia permanecen pendientes para su revisión.
8. Los movimientos bancarios personales o ajenos a Contab pueden descartarse.
9. Los movimientos previstos que hayan sido resueltos por otros medios pueden conciliarse manualmente dejando una explicación.

El objetivo no es conseguir que todo sea automático, sino que los casos normales requieran poco trabajo y que las excepciones queden claramente identificadas.

## Correspondencias complejas

Existen casos reales que podrían requerir relaciones más complejas:

* varios movimientos bancarios para un único movimiento previsto;
* un movimiento bancario que agrupe varios movimientos previstos;
* conciliaciones parciales;
* control de determinados atrasos por saldo.

Contab no implementa todavía estos casos de forma general.

No se desarrollarán por anticipado mientras la conciliación individual y manual permitan resolver adecuadamente el trabajo real. Si el uso diario demuestra que alguno de estos casos es suficientemente frecuente o costoso, se diseñará a partir de ejemplos reales.

## Principios adoptados

Las decisiones de conciliación siguen estos principios:

* **Control del usuario.** Una propuesta automática nunca es una conciliación definitiva sin confirmación.
* **Automatizar lo frecuente.** El caso normal debe resolverse con el menor trabajo posible.
* **No forzar las excepciones.** Una situación que no es realmente 1:1 no debe aparentarlo para satisfacer el modelo.
* **Trazabilidad.** Debe poder entenderse posteriormente por qué un movimiento se consideró resuelto.
* **Reversibilidad.** Las decisiones que puedan tomarse por error deben poder corregirse cuando sea razonable.
* **Simplicidad.** No se implementan relaciones complejas hasta que los casos reales demuestren su necesidad.
* **Separación contable.** La conciliación no crea ni modifica automáticamente apuntes contables para resolver información que desconoce.
* **Conservar la información bancaria original.** Los textos del banco son pistas importantes para la identificación y deben mantenerse.

El propósito final es que la conciliación reduzca trabajo y señale excepciones, sin convertir Contab en un sistema bancario complejo ni ocultar al usuario cómo se ha resuelto cada situación.
