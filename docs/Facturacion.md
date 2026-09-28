# Facturación

=============

## Finalidad

---

El módulo de facturación gestiona el ciclo de los alquileres que requieren factura, integrándolo con contratos, revisiones de renta, contabilidad y conciliación bancaria.

El objetivo es que Contab prepare la factura a partir de la información ya registrada, permita al usuario revisarla antes de emitirla y mantenga la trazabilidad entre:

* contrato y renta;
* factura;
* revisiones de renta;
* líneas extraordinarias;
* apunte contable;
* cobro previsto;
* documento emitido.

A partir de octubre de 2026 Contab dispone del flujo necesario para realizar la facturación mensual ordinaria desde la preparación del período hasta la impresión y contabilización de la factura.

## Principios

---

La facturación sigue los principios generales de Contab:

* los datos se introducen una sola vez y se reutilizan;
* una factura se calcula a partir del contrato y de los hechos económicos registrados;
* el usuario conserva el control antes de emitir;
* factura, contabilidad y conciliación deben permanecer coherentes;
* una operación con varios efectos se registra de forma atómica;
* las excepciones poco frecuentes no deben complicar anticipadamente el flujo ordinario.

La preparación de una factura no persiste borradores.

`FacturaPreparada` representa transitoriamente la factura calculada. La `Factura` persistente nace únicamente cuando el usuario confirma su contabilización.

## Preparación mensual

---

La operación habitual parte de una preparación por período.

El usuario indica:

* período;
* fecha de emisión.

Por defecto se propone el mes siguiente y su primer día.

La preparación no crea registros. Calcula la situación del mes y presenta una lista de control dividida en:

* **Locales**, para contratos que generan factura;
* **Otros**, para contratos cuyos alquileres se contabilizan sin factura.

Se incluyen los contratos vigentes durante alguna parte del mes.

Esta pantalla es el punto natural desde el que se realiza la facturación mensual.

## Facturas ordinarias

---

Para cada contrato facturable se muestran:

* inmueble;
* número de factura previsto;
* destinatario;
* dirección de facturación;
* base;
* IVA;
* retención;
* total;
* situación de una posible revisión de renta;
* estado de emisión;
* acciones disponibles.

El destinatario está formado por todos los titulares del contrato, respetando su orden.

Los datos fiscales y de facturación proceden del contrato y de sus titulares.

No se mantiene una copia histórica específica del destinatario y dirección dentro de la factura. El documento emitido constituye la evidencia histórica de los datos con los que realmente se confeccionó.

Mientras el usuario no confirme la contabilización, los datos son una preparación calculada y no existe una `Factura` provisional en la base de datos.

## Numeración

---

La numeración es independiente para cada inmueble y ejercicio y se reinicia anualmente.

Los contratos pertenecientes a un mismo inmueble comparten su secuencia.

Durante la preparación se muestra el siguiente número previsto.

El número definitivo se asigna al confirmar la emisión.

Las facturas reales de septiembre de 2026 se cargaron como antecedente histórico para continuar correctamente la numeración utilizada durante 2026.

Esta carga histórica no genera apuntes contables ni movimientos previstos.

## Composición de una factura

---

Una factura está formada por una o varias líneas.

El caso ordinario contiene una línea de renta.

`FacturaPreparada.lineas` contiene las líneas definitivas de la factura preparada que deben utilizar las distintas interfaces. La ruta o plantilla que muestra una factura no debe reconstruir por su cuenta conceptos que ya forman parte de la preparación.

El concepto de la línea ordinaria incluye el período facturado. Por ejemplo:

```text
Alquiler local. Octubre de 2026
```

Cuando una revisión de renta aplicada genera atrasos, la preparación puede contener además una segunda línea con la diferencia correspondiente al mes en el que todavía se facturó la renta anterior.

El formulario de modificación permite introducir o modificar transitoriamente líneas adicionales cuando sea necesario.

IVA y retención se calculan sobre la suma de las líneas.

El modelo `FacturaLinea` conserva actualmente un campo `tipo` con estos valores posibles:

```text
RENTA
DIFERENCIA_REVISION
REPERCUSION_GASTO
OTRO
```

La utilidad real de esta clasificación es actualmente escasa, especialmente desde que las líneas pueden editarse antes de contabilizar. Se mantiene por ahora para evitar una migración innecesaria antes del comienzo del uso real. Su simplificación queda como deuda técnica.

## Modificación de una factura preparada

---

Una factura todavía no emitida puede abrirse mediante **Modificar**.

El formulario parte de las líneas ya calculadas en `FacturaPreparada`, no vuelve a construirlas a partir del contrato.

El usuario puede revisar o modificar:

* conceptos;
* importes;
* IVA;
* retención;
* notas.

La edición es transitoria. No se persiste ningún borrador.

Las líneas vacías del formulario se ignoran al preparar la factura editada.

El formulario mantiene un número limitado de líneas y notas porque la factura está diseñada para ocupar aproximadamente medio DIN A4 y la operativa real utiliza muy pocos conceptos.

Las notas automáticas calculadas durante la preparación también llegan al formulario de modificación, de forma que no se pierden al pasar por este camino.

Una revisión en estado `PENDIENTE` bloquea la modificación y contabilización hasta que se resuelva.

## Previsualización y documento

---

La factura puede previsualizarse tanto directamente desde la preparación mensual como después de pasar por el formulario **Modificar**.

La previsualización utiliza la plantilla HTML de factura configurada para la base de datos.

El documento recibe los datos ya preparados:

* emisor;
* destinatario;
* inmueble;
* período;
* líneas;
* notas;
* base;
* IVA;
* retención;
* total;
* número;
* fecha de emisión.

La misma factura preparada debe producir el mismo contenido independientemente del camino seguido para llegar a la previsualización.

Desde la previsualización puede imprimirse el documento.

La factura está diseñada actualmente para un formato compacto, aproximadamente de medio DIN A4.

La previsualización contiene además los datos necesarios para contabilizar exactamente la factura mostrada.

Antes de contabilizar, el servidor vuelve a calcular los importes a partir de las líneas y porcentajes recibidos y comprueba que coincidan con los totales previsualizados. Si han cambiado, obliga a volver a previsualizar.

## Notas automáticas

---

Las notas que forman parte de la factura se preparan junto con ésta.

`FacturaPreparada.notas` contiene las notas automáticas correspondientes a la situación del contrato.

Actualmente pueden proceder de:

* una retención del 24 %;
* una revisión de renta próxima;
* una revisión cuyo índice todavía no está disponible;
* una revisión ya aplicada.

Las notas se muestran de la misma forma al previsualizar directamente y al pasar por **Modificar**.

La factura editada puede añadir además notas introducidas por el usuario.

Al contabilizar, las notas definitivas se almacenan en la factura.

## Emisión y efectos contables

---

La confirmación definitiva se realiza mediante **Contabilizar** desde la previsualización.

Contab crea conjuntamente:

* la factura;
* sus líneas;
* el apunte contable;
* el movimiento previsto para conciliación.

La operación es atómica.

El apunte generado es un ingreso de alquiler y conserva:

* base;
* IVA;
* retención;
* total;
* período;
* destinatario;
* NIF;
* número de factura como referencia documental.

El movimiento previsto se vincula al contrato y al apunte y utiliza como importe esperado el total de la factura.

El intervalo previsto de cobro comprende actualmente todo el mes facturado. Es deliberadamente amplio para no perjudicar la conciliación cuando el inquilino paga con retraso.

No puede emitirse dos veces una factura ordinaria para el mismo contrato y período.

Las facturas extraordinarias, rectificativas o sustitutorias requerirán flujos explícitos cuando sean necesarios; no deben obtenerse relajando las reglas de la factura ordinaria.

## Revisiones de renta

---

Las revisiones de renta están integradas en la preparación de la facturación.

Contab distingue las situaciones relevantes para el ciclo mensual.

### Aviso

Cuando existe una revisión pendiente prevista para el mes siguiente:

```text
revision_estado = AVISO
```

La preparación muestra:

```text
Aviso
```

y la factura incorpora una nota indicando que el próximo mes corresponde actualizar la renta según el índice establecido en el contrato.

### Esperando índice

Cuando la revisión pendiente corresponde al propio mes preparado:

```text
revision_estado = ESPERANDO_INDICE
```

La preparación muestra:

```text
Esperando índice
```

La factura mantiene la renta anterior e incorpora una nota explicando que el índice todavía no está disponible y que la diferencia se repercutirá cuando pueda calcularse.

### Pendiente

Cuando la revisión requiere una actuación del usuario antes de continuar:

```text
revision_estado = PENDIENTE
```

la facturación queda bloqueada hasta resolverla.

No se permite modificar o contabilizar una factura cuya revisión esté pendiente.

### Aplicada

Cuando la revisión ya ha sido resuelta y debe reflejarse en la facturación:

```text
revision_estado = APLICADA
```

la preparación muestra:

```text
Aplicada
```

Este estado sólo se presenta en el período en el que la aplicación de la revisión tiene efectos específicos sobre la factura.

La renta revisada se obtiene de las rentas del contrato.

Si durante el mes previsto para la revisión se facturó todavía la renta anterior porque el índice no estaba disponible, la factura posterior incorpora automáticamente:

* la renta mensual ya revisada;
* una segunda línea por los atrasos del mes de revisión.

También incorpora dos notas:

* una indicando el índice y porcentaje aplicado y el incremento de renta;
* otra explicando que se cargan los atrasos del mes correspondiente, conforme se había indicado en su factura.

Los atrasos y el estado `APLICADA` no deben repetirse indefinidamente en meses posteriores.

La descripción del índice se obtiene a partir del método de revisión configurado. Entre los índices contemplados está IRAV.

La lógica de nombres de meses está centralizada en las utilidades de formato para evitar mantener tablas de meses duplicadas.

## Gastos repercutidos

---

La factura puede contener gastos que deban cobrarse al inquilino además de la renta.

Debe distinguirse claramente entre:

* **distribuir** un gasto entre inmuebles a efectos contables o analíticos;
* **repercutir** al inquilino una cantidad que debe pagar.

El modelo contempla líneas de repercusión de gastos, pero el flujo completo de gastos, distribución y repercusión todavía no está desarrollado.

Esta funcionalidad se abordará a partir de casos reales, especialmente los gastos agrupados que aparecen durante el ejercicio, evitando introducir manualmente en facturación información que ya pueda existir en contabilidad.

## Contratos sin factura

---

No todos los alquileres requieren factura.

Estos contratos aparecen en la sección **Otros
