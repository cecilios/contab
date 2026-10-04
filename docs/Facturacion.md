# Facturación

=============

## Finalidad

---

El módulo de facturación gestiona el ciclo de los alquileres, tanto de los contratos que requieren factura como de los que se contabilizan directamente, integrándolo con contratos, revisiones de renta, contabilidad y conciliación bancaria.

El objetivo es que Contab prepare los importes a partir de la información ya registrada, permita al usuario revisarlos antes de contabilizar y mantenga la trazabilidad entre:

- contrato y renta;
- factura, cuando proceda;
- revisiones de renta;
- líneas extraordinarias;
- apunte contable;
- cobro previsto;
- documento emitido.

A partir de octubre de 2026 Contab dispone del flujo necesario para realizar la facturación mensual ordinaria desde la preparación del período hasta la impresión y contabilización de la factura.

## Principios

---

La facturación sigue los principios generales de Contab:

- los datos se introducen una sola vez y se reutilizan;
- una factura se calcula a partir del contrato y de los hechos económicos registrados;
- el usuario conserva el control antes de emitir;
- factura, contabilidad y conciliación deben permanecer coherentes;
- una operación con varios efectos se registra de forma atómica;
- las correcciones deben deshacer de forma coherente los efectos que todavía puedan deshacerse;
- las excepciones poco frecuentes no deben complicar anticipadamente el flujo ordinario.

La preparación de una factura no persiste borradores.

`FacturaPreparada` representa transitoriamente la factura calculada. La `Factura` persistente nace únicamente cuando el usuario confirma su contabilización.

Las rutas controlan las transacciones de base de datos. Los servicios realizan los cálculos, aplican las reglas de negocio y preparan los objetos necesarios, pero no confirman transacciones por su cuenta.

## Preparación mensual

---

La operación habitual parte de una preparación por período.

El usuario indica:

- período;
- fecha de emisión.

Por defecto se propone el mes siguiente y su primer día.

La preparación no crea registros. Calcula la situación del mes y presenta una lista de control dividida en:

- **Locales**, para contratos que generan factura;
- **Otros**, para contratos cuyos alquileres se contabilizan sin factura.

Se incluyen los contratos vigentes durante alguna parte del mes.

Esta pantalla es el punto natural desde el que se realiza la facturación mensual.

## Facturas ordinarias

---

Para cada contrato facturable se muestran:

- inmueble;
- número de factura previsto;
- destinatario;
- dirección de facturación;
- base;
- IVA;
- retención;
- total;
- situación de una posible revisión de renta;
- estado de emisión;
- acciones disponibles.

El destinatario está formado por todos los titulares del contrato, respetando su orden.

Los datos fiscales y de facturación proceden del contrato y de sus titulares durante la preparación.

Mientras el usuario no confirme la contabilización, los datos son una preparación calculada y no existe una `Factura` provisional en la base de datos.

Al emitir, la factura conserva los datos históricos necesarios para no depender de cambios posteriores en el contrato o en sus titulares. Entre ellos se encuentran los datos de facturación, la referencia y descripción del inmueble y los destinatarios almacenados en `FacturaDestinatario`.

## Numeración

---

La numeración es independiente para cada inmueble y ejercicio y se reinicia anualmente.

Los contratos pertenecientes a un mismo inmueble comparten su secuencia.

Durante la preparación se muestra el siguiente número previsto.

El número definitivo se asigna al confirmar la emisión.

Las facturas reales de septiembre de 2026 se cargaron como antecedente histórico para continuar correctamente la numeración utilizada durante 2026.

Esta carga histórica no genera necesariamente apuntes contables ni movimientos previstos.

Cuando una factura se elimina correctamente, su número puede volver a utilizarse. Para preservar una secuencia coherente, sólo puede eliminarse la última factura numerada del inmueble dentro del ejercicio.

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

- conceptos;
- importes;
- IVA;
- retención;
- notas.

La edición es transitoria. No se persiste ningún borrador.

Las líneas vacías del formulario se ignoran al preparar la factura editada.

El formulario mantiene un número limitado de líneas y notas porque la factura está diseñada para ocupar aproximadamente medio DIN A4 y la operativa real utiliza muy pocos conceptos.

Las notas automáticas calculadas durante la preparación también llegan al formulario de modificación, de forma que no se pierden al pasar por este camino.

Una revisión en estado `PENDIENTE` que deba resolverse antes de facturar bloquea la modificación y contabilización hasta que se resuelva.

## Previsualización y documento

---

La factura puede previsualizarse tanto directamente desde la preparación mensual como después de pasar por el formulario **Modificar**.

La previsualización utiliza la plantilla HTML de factura configurada para la base de datos.

El documento recibe los datos ya preparados:

- emisor;
- destinatario;
- inmueble;
- período;
- líneas;
- notas;
- base;
- IVA;
- retención;
- total;
- número;
- fecha de emisión.

La misma factura preparada debe producir el mismo contenido independientemente del camino seguido para llegar a la previsualización.

Desde la previsualización puede imprimirse el documento o generarse posteriormente el soporte que se utilice para su archivo.

La factura está diseñada actualmente para un formato compacto, aproximadamente de medio DIN A4.

La previsualización contiene además los datos necesarios para contabilizar exactamente la factura mostrada.

Antes de contabilizar, el servidor vuelve a calcular los importes a partir de las líneas y porcentajes recibidos y comprueba que coincidan con los totales previsualizados. Si han cambiado, obliga a volver a previsualizar.

## Notas automáticas

---

Las notas que forman parte de la factura se preparan junto con ésta.

`FacturaPreparada.notas` contiene las notas automáticas correspondientes a la situación del contrato.

Actualmente pueden proceder de:

- una retención del 24 %;
- una revisión de renta próxima;
- una revisión cuyo índice todavía no está disponible;
- una revisión ya aplicada.

Las notas se muestran de la misma forma al previsualizar directamente y al pasar por **Modificar**.

La factura editada puede añadir además notas introducidas por el usuario.

Al contabilizar, las notas definitivas se almacenan en la factura.

## Emisión y efectos contables

---

La confirmación definitiva se realiza mediante **Contabilizar** desde la previsualización.

Contab crea conjuntamente:

- la factura;
- sus líneas;
- sus destinatarios históricos;
- el apunte contable;
- el movimiento previsto para conciliación.

La operación es atómica.

La factura queda vinculada al apunte contable que produjo.

El apunte generado es un ingreso de alquiler y conserva:

- base;
- IVA;
- retención;
- total;
- período;
- destinatario;
- NIF;
- número de factura como referencia documental.

El movimiento previsto se vincula al contrato y al apunte y utiliza como importe esperado el total de la factura.

El intervalo previsto de cobro comprende actualmente todo el mes facturado. Es deliberadamente amplio para no perjudicar la conciliación cuando el inquilino paga con retraso.

No puede emitirse dos veces una factura ordinaria para el mismo contrato y período.

Las facturas extraordinarias, rectificativas o sustitutorias requerirán flujos explícitos cuando sean necesarios; no deben obtenerse relajando las reglas de la factura ordinaria.

## Eliminación de una factura

---

Una factura emitida incorrectamente puede eliminarse mientras sus efectos todavía sean reversibles.

**Eliminar** significa que la factura desaparece completamente del sistema y que su número queda disponible para volver a utilizarse.

No debe confundirse con una futura operación de anulación, en la que la factura permanecerá como antecedente histórico conservando su número.

Una factura sólo puede eliminarse cuando:

- está en estado `EMITIDA`;
- es la última factura numerada de ese inmueble y ejercicio;
- dispone del apunte contable asociado, salvo las facturas históricas cargadas como antecedente;
- tiene como máximo un movimiento previsto asociado;
- el movimiento, si existe, está todavía en estado `PENDIENTE` o `CANCELADO`.

No se permite eliminar una factura cuyo cobro esté parcial o totalmente conciliado.

La eliminación borra conjuntamente, cuando existen:

- movimiento previsto;
- líneas de factura;
- destinatarios históricos;
- factura;
- apunte contable.

La operación es atómica.

Una vez eliminada la factura, la preparación mensual puede volver a realizarse y el número liberado puede asignarse de nuevo.

Este mecanismo es también necesario antes de corregir determinadas revisiones de renta cuando ya se había emitido la factura afectada.

## Revisiones de renta

---

Las revisiones de renta están integradas en la preparación de la facturación y disponen además de un panel específico de seguimiento.

Cada revisión tiene una fecha prevista y un método de actualización.

La resolución de una revisión puede:

- aplicar un porcentaje y generar una nueva renta;
- decidir que ese año no se aplica actualización.

En ambos casos se registra la resolución y se prepara automáticamente la revisión correspondiente al año siguiente conservando el método de revisión.

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

La revisión no se resuelve desde el panel general. La resolución se realiza desde el contexto de la preparación mensual cuando llega el período en que es necesario conocer el nuevo importe.

### Pendiente

Cuando una revisión anterior al período preparado todavía no se ha resuelto:

```text
revision_estado = PENDIENTE
```

la facturación queda bloqueada hasta resolverla.

La preparación ofrece entonces **Resolver revisión**.

No se permite modificar o contabilizar la factura hasta que la revisión se haya resuelto.

### Aplicada

Cuando la revisión ya ha sido resuelta aplicando un porcentaje:

```text
revision_estado = APLICADA
```

la preparación muestra:

```text
Aplicada
```

en el período en que la aplicación tiene efectos específicos sobre la factura.

La nueva renta se calcula a partir de la renta vigente en la fecha prevista de revisión y del porcentaje aplicado.

Si durante el mes previsto para la revisión se facturó todavía la renta anterior porque el índice no estaba disponible, la factura del mes siguiente incorpora automáticamente:

- la renta mensual ya revisada;
- una segunda línea por los atrasos del mes de revisión.

También incorpora dos notas:

- una indicando el índice y porcentaje aplicado y el incremento de renta;
- otra explicando que se cargan los atrasos del mes correspondiente, conforme se había indicado en su factura.

Los atrasos y el estado `APLICADA` no deben repetirse indefinidamente en meses posteriores.

La descripción del índice se obtiene a partir del método de revisión configurado. Entre los índices contemplados está IRAV.

La lógica de nombres de meses está centralizada en las utilidades de formato para evitar mantener tablas de meses duplicadas.

### No aplicada

El usuario puede decidir que una revisión pendiente no se aplique ese año mediante **No aplicar este año**.

La revisión pasa a:

```text
NO_APLICADA
```

y conserva la fecha en que se tomó la decisión.

No se crea una nueva `RentaContrato`.

La revisión del año siguiente se crea automáticamente con el mismo método.

Esta decisión puede realizarse desde el panel de revisiones mientras la revisión siga pendiente.

## Panel de revisiones de renta

---

La pantalla **Revisiones de renta** ofrece una visión general independiente de la preparación de un mes concreto.

Se muestran los contratos activos agrupados en:

- **Locales**;
- **Otros**.

Los contratos se ordenan por referencia del inmueble.

Para cada contrato se presenta:

- la última revisión resuelta, si existe;
- la próxima revisión pendiente, si existe;
- la situación temporal de esa próxima revisión;
- las acciones que puedan realizarse en ese momento.

La situación de una revisión pendiente puede indicar:

- `AVISO`;
- `ESPERANDO_INDICE`;
- `RESOLVER`;
- `PENDIENTE`.

El panel sirve para seguimiento y para determinadas actuaciones administrativas, pero la aplicación de un índice se realiza desde la preparación mensual para mantenerla ligada al período de facturación al que afecta.

Entre las acciones disponibles se encuentran:

- **No aplicar este año**, para una revisión todavía pendiente;
- **Corregir revisión**, para una revisión aplicada que todavía pueda deshacerse con seguridad.

## Corrección de una revisión aplicada

---

Una revisión aplicada con un porcentaje incorrecto puede corregirse mientras sus efectos posteriores todavía sean completamente reversibles.

La interfaz utiliza el nombre **Corregir revisión**.

Internamente la operación consiste en reabrir la revisión y devolver el contrato al estado inmediatamente anterior a su resolución.

La reapertura:

- cambia la revisión de `APLICADA` a `PENDIENTE`;
- elimina `porcentaje_aplicado`;
- elimina `fecha_resolucion`;
- elimina la `RentaContrato` creada en la fecha prevista de la revisión;
- elimina la revisión del año siguiente que se creó automáticamente al resolverla.

No modifica ni recalcula apuntes contables ni facturas existentes.

Por ello, una revisión sólo puede reabrirse cuando:

- está en estado `APLICADA`;
- existe la renta generada en su fecha prevista;
- existe la revisión correspondiente al año siguiente;
- esa revisión siguiente continúa en estado `PENDIENTE`;
- no existe ninguna factura del contrato correspondiente al período de aplicación o a un período posterior;
- no existe ningún apunte contable de alquiler del contrato correspondiente al período de aplicación o a un período posterior.

A estos efectos, el período de aplicación es el mes siguiente a la fecha prevista de revisión.

Por ejemplo, para una revisión prevista en abril cuyo índice se conoce en mayo:

- la factura de abril puede permanecer, porque todavía utilizó legítimamente la renta anterior;
- una factura de mayo o posterior impide corregir la revisión;
- un apunte contable de alquiler de mayo o posterior también la impide.

En los contratos que generan factura, si ya se ha emitido la factura del mes de aplicación, debe utilizarse primero **Eliminar factura**. Una vez eliminados de forma coherente factura, apunte y movimiento previsto, la revisión vuelve a ser corregible.

En los contratos sin factura, cualquier efecto contable de alquiler desde el período de aplicación impide igualmente la reapertura. La corrección de la revisión no intenta deshacer por sí misma la contabilidad existente.

Tras **Corregir revisión**, el flujo ordinario se reutiliza por completo:

1. la revisión vuelve a quedar pendiente;
2. el usuario prepara de nuevo el mes afectado;
3. Contab vuelve a ofrecer **Resolver revisión**;
4. el usuario introduce el porcentaje correcto;
5. se genera la nueva renta;
6. se crea de nuevo la revisión del año siguiente;
7. la factura o contabilización mensual se prepara otra vez con los importes correctos.

Este mecanismo está pensado para errores detectados antes de que los efectos posteriores de la revisión hayan quedado consolidados.

Cuando ya existen efectos que no pueden eliminarse mediante los flujos ordinarios, la revisión no debe reabrirse. En esos casos será necesario un futuro mecanismo explícito de rectificación.

## Gastos repercutidos

---

La factura puede contener gastos que deban cobrarse al inquilino además de la renta.

Debe distinguirse claramente entre:

- **distribuir** un gasto entre inmuebles a efectos contables o analíticos;
- **repercutir** al inquilino una cantidad que debe pagar.

El modelo contempla líneas de repercusión de gastos, pero el flujo completo de gastos, distribución y repercusión todavía no está desarrollado.

Esta funcionalidad se abordará a partir de casos reales, especialmente los gastos agrupados que aparecen durante el ejercicio, evitando introducir manualmente en facturación información que ya pueda existir en contabilidad.

## Contratos sin factura

---

No todos los alquileres requieren factura.

Estos contratos aparecen en la sección **Otros** de la preparación mensual.

El cálculo de renta, revisiones y período sigue las mismas reglas generales que en los contratos facturables, pero no se crea una `Factura`.

Al contabilizar el ingreso se generan directamente:

- el apunte contable de alquiler;
- el movimiento previsto para conciliación.

La operación debe seguir siendo atómica.

Los efectos contables de estos contratos también se tienen en cuenta al determinar si una revisión aplicada puede corregirse. Si existe un apunte contable de alquiler correspondiente al período de aplicación de la revisión o a un período posterior, la revisión no puede reabrirse mientras ese efecto permanezca registrado.

## Operaciones futuras sobre facturas emitidas

---

Además de **Eliminar**, están previstas otras operaciones con semántica distinta.

### Anular

Una factura anulada permanecerá en el histórico y conservará su número.

La anulación no equivale a eliminar una factura y deberá definir explícitamente sus efectos contables y de conciliación antes de implementarse.

### Rectificar

Una rectificación conservará la factura original y generará una factura rectificativa relacionada con ella.

Este será también el mecanismo adecuado para corregir situaciones que ya no puedan deshacerse mediante la eliminación de una factura o la reapertura de una revisión.

Estas operaciones deben desarrollarse como flujos explícitos y no relajando las condiciones de seguridad de **Eliminar factura** o **Corregir revisión**.

## Criterio general de corrección

---

Contab distingue entre errores que todavía pueden deshacerse y hechos ya consolidados.

Mientras una operación no haya producido efectos posteriores incompatibles, puede deshacerse de forma controlada y volver a ejecutarse correctamente.

Cuando ya existen facturas, apuntes o conciliaciones posteriores que deben conservarse como historia, la corrección debe realizarse mediante una operación compensatoria o rectificativa explícita.

Este criterio permite mantener una operativa sencilla en los errores detectados pronto sin comprometer la trazabilidad contable cuando la operación ya ha producido efectos posteriores.
