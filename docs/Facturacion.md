# Facturación

=============

## Finalidad

---

El módulo de facturación debe permitir gestionar el ciclo completo de los alquileres que requieren factura, integrándolo con contratos, revisiones de renta, gastos repercutibles, contabilidad y conciliación bancaria.

El objetivo final es que Contab pueda preparar y emitir automáticamente las facturas a partir de la información ya registrada, evitando volver a introducir datos y manteniendo la trazabilidad entre:

* contrato y renta;
* factura;
* revisiones de renta;
* gastos repercutidos;
* apunte contable;
* cobro previsto;
* documento emitido.

La primera fase de uso real, a partir de octubre de 2026, utiliza deliberadamente un subconjunto de este objetivo: Contab prepara y controla la facturación y registra sus consecuencias contables, mientras el documento físico continúa elaborándose manualmente.

Esta simplificación permite probar con datos reales el núcleo económico antes de completar la generación documental.

## Principios

---

La facturación sigue los principios generales de Contab:

* los datos se introducen una sola vez y se reutilizan;
* una factura se calcula a partir del contrato y de los hechos económicos registrados;
* el usuario conserva el control antes de emitir;
* factura, contabilidad y conciliación deben permanecer coherentes;
* una operación con varios efectos se registra de forma atómica;
* las excepciones poco frecuentes no deben complicar anticipadamente el flujo ordinario.

La preparación de una factura no debe obligar a persistir borradores. La factura nace cuando el usuario confirma su emisión.

## Preparación mensual

---

La operación habitual parte de una preparación por período.

El usuario indica:

* período, en formato `mm-aaaa`;
* fecha de emisión, en formato `dd-mm-aaaa`.

Por defecto se propone el mes siguiente y su primer día.

La preparación no crea registros. Calcula la situación del mes y presenta una lista de control dividida en:

* **Locales**, para contratos que generan factura;
* **Otros**, para contratos cuyos alquileres se contabilizan sin factura.

Se incluyen los contratos vigentes durante alguna parte del mes.

Esta pantalla debe seguir siendo el punto natural desde el que se realice la facturación mensual, incluso cuando en el futuro Contab genere automáticamente los documentos.

## Facturas ordinarias

---

Para cada contrato facturable se muestran actualmente:

* inmueble;
* número de factura previsto;
* destinatario;
* dirección de facturación;
* base;
* IVA;
* retención;
* total;
* situación de una posible revisión de renta;
* estado de emisión.

El destinatario está formado por todos los titulares del contrato, respetando su orden.

Los datos fiscales y de facturación proceden del contrato y de sus titulares.

No se mantiene una copia histórica específica del destinatario y dirección dentro de la factura. Cuando Contab genere el documento definitivo, éste constituirá la evidencia histórica de los datos con los que realmente se emitió.

Mientras el usuario no confirme la emisión, los datos son una preparación calculada y no existe una `Factura` provisional en la base de datos.

## Numeración

---

La numeración es independiente para cada inmueble y ejercicio y se reinicia anualmente.

Los contratos pertenecientes a un mismo inmueble comparten su secuencia.

Durante la preparación se muestra el siguiente número previsto para permitir revisar y, durante la fase inicial, confeccionar manualmente el documento.

El número definitivo se asigna al confirmar la emisión.

Antes del primer ciclo real de octubre de 2026 se cargarán las facturas reales de septiembre. Esto permitirá conservar el antecedente real y continuar correctamente la numeración utilizada durante 2026.

La carga de septiembre será exclusivamente histórica a efectos de facturación: no generará apuntes contables ni movimientos previstos.

## Composición de una factura

---

Una factura está formada por una o varias líneas.

El caso ordinario contiene una línea de renta.

El modelo contempla además líneas para:

* diferencias derivadas de revisiones de renta;
* repercusiones de gastos;
* otros conceptos.

IVA y retención se calculan sobre la base formada por las líneas de la factura.

El flujo actualmente operativo sólo necesita generar automáticamente la renta ordinaria. Las demás líneas se incorporarán al proceso cuando se desarrollen sus correspondientes casos de uso.

No se añadirá por ahora una interfaz genérica para modificar manualmente facturas preparadas. Si aparece una necesidad real de introducir una línea extraordinaria, deberá poder hacerse sin convertir la preparación mensual en un sistema complejo de borradores.

## Emisión y efectos contables

---

Al confirmar una factura, Contab crea conjuntamente:

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

## Generación del documento

---

El objetivo del módulo incluye la generación automática del documento de factura.

La factura deberá poder producirse a partir de los datos ya calculados y registrados por Contab, sin volver a introducir manualmente:

* emisor;
* destinatario;
* inmueble o concepto;
* período;
* líneas;
* base;
* IVA;
* retención;
* total;
* número y fecha.

Los documentos emitidos continuarán archivándose en el sistema de ficheros.

La generación automática del documento todavía no está implementada. Durante el inicio de las pruebas reales, el usuario confeccionará manualmente la factura física utilizando la información preparada por Contab y después confirmará **Emitir**.

Esta solución es transitoria: se ha elegido para poder probar inmediatamente contratos, cálculos, numeración, contabilidad y conciliación sin hacer depender el inicio de las pruebas del formato definitivo del documento.

Una vez validado el flujo económico con datos reales, podrá completarse la generación automática, previsiblemente utilizando los formatos de documento que resulten más adecuados para el procedimiento real.

## Revisiones de renta

---

Las revisiones de renta forman parte del proceso de facturación y Contab debe ayudar tanto a detectarlas como a aplicarlas.

Una revisión puede requerir varias actuaciones:

* avisar con antelación de que se aproxima;
* esperar a que esté disponible el índice necesario;
* calcular la nueva renta;
* registrar la renta revisada;
* incorporar, cuando proceda, diferencias o atrasos;
* reflejar correctamente el resultado en la factura.

La preparación mensual ya ofrece las primeras ayudas.

Actualmente distingue:

* **Aviso**, cuando existe una revisión pendiente prevista para el mes siguiente;
* **En espera del índice**, cuando la revisión pendiente corresponde al propio mes preparado.

La situación se recalcula al emitir y queda asociada a la factura.

Todavía no está automatizado el cálculo completo de la revisión ni la generación de las posibles diferencias. Se desarrollará cuando llegue el primer caso real, de forma que las reglas se basen en la operativa necesaria y no en supuestos.

El objetivo sigue siendo que una revisión correctamente registrada pueda incorporarse después a la facturación sin duplicar datos ni cálculos manuales.

## Gastos repercutidos

---

La factura puede contener gastos que deban cobrarse al inquilino además de la renta.

Debe distinguirse claramente entre:

* **distribuir** un gasto entre inmuebles a efectos contables o analíticos;
* **repercutir** al inquilino una cantidad que debe pagar.

Un gasto repercutible deberá poder originar una línea de factura cuando corresponda.

El modelo de facturación ya contempla líneas de repercusión, pero el flujo completo de gastos, distribución y repercusión todavía no está desarrollado.

Esta funcionalidad se abordará a partir de casos reales, especialmente los gastos agrupados que aparecen durante el ejercicio, evitando introducir manualmente en facturación información que ya pueda existir en contabilidad.

## Contratos sin factura

---

No todos los alquileres requieren factura.

Estos contratos aparecen en la sección **Otros** de la misma preparación mensual para que el usuario pueda controlar todos los ingresos de alquiler del período desde un único lugar.

Para cada uno se muestran:

* inmueble;
* nombres de los titulares;
* importe;
* estado de contabilización.

El usuario confirma individualmente cada ingreso mediante **Contabilizar**.

Se crean conjuntamente:

* un apunte contable de ingreso por alquiler;
* un movimiento previsto para conciliación.

No se crea una factura.

Después de registrarlo, la fila aparece como **Contabilizado**.

La confirmación individual se ha elegido deliberadamente para la primera fase de uso real: existen pocas operaciones y proporciona un control sencillo y visible.

Contab identifica que el alquiler de un contrato y mes ya está contabilizado a través del movimiento previsto vinculado al contrato y del período de su apunte contable.

El importe, las fechas previstas de cobro o el posterior estado de conciliación no forman parte de esta identidad, porque pueden cambiar legítimamente sin que desaparezca el hecho contable.

## Facturas emitidas

---

Una vez emitida, la factura es un hecho económico registrado.

Al volver a preparar el mismo período, Contab utiliza los importes y número persistidos en la factura, no vuelve a calcularlos a partir de la situación actual del contrato.

Esto permite que cambios posteriores en rentas o porcentajes no alteren el contenido económico de una factura ya emitida.

La anulación existe en el modelo, pero todavía no se ha definido un flujo completo para sustituciones o rectificaciones. Cuando sea necesario se diseñará explícitamente para conservar la trazabilidad.

## Situación actual

---

Está completado el núcleo necesario para iniciar las pruebas reales:

* preparación mensual de contratos;
* separación entre contratos con factura y sin factura;
* cálculo de renta, IVA, retención y total;
* composición de destinatarios con varios titulares;
* previsión de numeración;
* reconocimiento de facturas ya emitidas;
* avisos básicos de revisión de renta;
* emisión confirmada de facturas;
* creación atómica de factura, apunte y movimiento previsto;
* contabilización de alquileres que no generan factura;
* reconocimiento de esos ingresos al volver a preparar el período;
* integración de ambos flujos con la conciliación mediante movimientos previstos.

Durante el comienzo de las pruebas, la única parte manual importante del flujo ordinario de facturación será la confección del documento físico.

## Inicio de las pruebas reales

---

Contab comenzará a utilizarse en paralelo con el procedimiento actual a partir de octubre de 2026.

Antes se cargarán las facturas reales de septiembre para establecer correctamente el historial y la numeración de cada inmueble.

La prueba paralela debe comprobar con datos reales:

* contratos incluidos en cada período;
* rentas aplicables;
* destinatarios;
* cálculos fiscales;
* numeración;
* avisos de revisión;
* apuntes generados;
* movimientos previstos;
* conciliación de los cobros;
* excepciones que aparezcan en la operativa cotidiana.

Durante esta fase se priorizará corregir problemas reales sobre ampliar funcionalidad hipotética.

## Evolución prevista

---

La reducción de alcance realizada para comenzar las pruebas no modifica el objetivo final del módulo.

Tras validar el núcleo actual, la evolución deberá completar progresivamente:

* generación automática de los documentos de factura;
* ayudas para calcular y aplicar revisiones de renta;
* incorporación de diferencias de revisión cuando proceda;
* integración de gastos repercutibles;
* líneas extraordinarias cuando exista una necesidad real;
* tratamiento explícito de anulaciones, sustituciones y rectificaciones;
* mejoras operativas que surjan de la prueba con datos reales.

El orden concreto dependerá de la experiencia de uso.

La prioridad seguirá siendo automatizar aquello que evita trabajo repetitivo o errores, manteniendo sencillo el caso ordinario y permitiendo resolver manualmente las excepciones poco frecuentes.
