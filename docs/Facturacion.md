# Facturación
=============

## Finalidad
------------

La facturación es una función auxiliar de Contab. Su valor principal no está en sustituir un proceso manual ya rápido, sino en:

- reducir errores;
- mantener el control de la numeración;
- generar automáticamente los apuntes contables y movimientos previstos;
- integrar las revisiones de renta;
- emitir y archivar las facturas en PDF.

Los objetivos prioritarios de Contab siguen siendo la conciliación bancaria y los informes contables. La facturación se desarrollará en la medida en que contribuya a esos objetivos o ahorre trabajo real al usuario.

## Operativa manual actual
--------------------------

El usuario mantiene una plantilla de LibreOffice Calc para cada inmueble. La plantilla contiene la última factura emitida.

Cada mes:

1. Abre la plantilla correspondiente.
2. Incrementa el número de factura.
3. Actualiza la fecha, el mes facturado y, cuando procede, la renta.
4. Añade avisos o atrasos relacionados con revisiones de renta.
5. Exporta la factura a PDF.
6. Archiva el PDF en la carpeta del inmueble y del año.
7. Envía el documento al inquilino.

Como existen menos de diez inmuebles, el proceso completo ocupa aproximadamente media hora. Además, permite resolver con facilidad correcciones, facturas extraordinarias y situaciones no previstas.

## Conclusión sobre la automatización parcial
---------------------------------------------

Un módulo que sólo prepare datos y registre apuntes, pero obligue al usuario a confeccionar después la factura manualmente, duplica parte del trabajo y aporta poco valor.

Por ello, se decidió detener temporalmente el desarrollo funcional de la facturación y priorizar:

1. la gestión de apuntes contables;
2. los informes contables;
3. la importación bancaria;
4. la conciliación.

La facturación se retomará cuando incluya la generación automática de los documentos, especialmente el PDF que se envía al inquilino.

## Principios de diseño
-----------------------

Cuando se retome, el proceso deberá ser:

- muy sencillo para el usuario;
- rápido para un número reducido de inmuebles;
- controlado y confirmado por el usuario;
- fácil de comprender y mantener;
- capaz de resolver manualmente cualquier excepción;
- integrado con contabilidad y conciliación;
- desarrollado con el mínimo código necesario.

La aplicación no debe imponer más pasos que el método manual si esos pasos no aportan control o ahorro de tiempo.

## Preparación mensual
----------------------

La facturación ordinaria partirá de una pantalla resumen correspondiente al mes que se va a facturar.

La pantalla mostrará, para cada contrato vigente:

- el inmueble;
- el destinatario;
- la renta aplicable;
- si el contrato genera factura;
- la situación de una posible revisión de renta;
- el estado del trabajo de ese mes.

Normalmente el período podrá proponerse automáticamente: si las facturas se preparan al final de un mes, corresponderán al mes siguiente. El usuario podrá cambiarlo cuando necesite emitir una factura excepcional o trabajar con otro período.

La propia pantalla servirá como resumen de control y podrá imprimirse desde el navegador. No se necesita inicialmente un sistema específico de impresión.

## Contratos que generan factura
--------------------------------

Para cada contrato facturable, el usuario abrirá el formulario de factura desde la pantalla resumen.

Contab propondrá los datos conocidos:

- número de factura;
- fecha;
- destinatario;
- concepto principal;
- renta vigente;
- IVA y retención;
- posibles atrasos de una revisión;
- líneas pendientes que deban facturarse al inquilino.

El concepto principal combinará el concepto definido en el contrato con el mes facturado. Por ejemplo:

> Alquiler del local 7. Mes de abril de 2027

El usuario podrá:

- revisar y modificar los importes propuestos;
- añadir líneas adicionales;
- escribir observaciones;
- cancelar sin guardar;
- calcular y finalizar la factura.

Las líneas adicionales se introducirán mediante su importe base y recibirán el mismo tratamiento de IVA y retención previsto para la factura. No se contemplan inicialmente otros tratamientos fiscales.

## Calcular y finalizar
-----------------------

El formulario tendrá una acción **Calcular** y otra **Finalizar**.

**Calcular** actualizará bases, impuestos, retenciones y total. Será necesario después de cambiar importes, añadir líneas o introducir un porcentaje de revisión.

**Finalizar** sólo estará permitido sobre los datos previamente calculados. Si el usuario modifica algún valor después del cálculo, Contab volverá a mostrar el formulario y pedirá calcular y confirmar de nuevo.

Al finalizar:

- se reserva definitivamente el número de factura;
- se guardan los datos necesarios;
- se genera el apunte contable de ingreso;
- se genera el movimiento previsto para la conciliación;
- en el futuro, se crearán el archivo editable y el PDF;
- se vuelve a la pantalla resumen con la fila marcada como realizada.

Cancelar no guardará ninguno de los cambios introducidos.

## Contratos sin factura
------------------------

Los contratos que no generan factura también producen un ingreso esperado para la conciliación y un apunte contable.

Como sus datos habituales ya se conocen, no será obligatorio abrir un formulario para cada uno. La pantalla resumen permitirá aceptar directamente la fila.

Sólo en casos excepcionales se abrirá un detalle para modificar los datos antes de confirmar el ingreso previsto.

## Revisión de renta
--------------------

Los métodos IPC nacional, IPC autonómico e IRAV tienen el mismo tratamiento dentro de Contab. El nombre sólo indica al usuario qué índice debe consultar. Contab no obtendrá porcentajes de fuentes externas: el usuario los introducirá.

Para una revisión con efecto el 1 de enero, el ciclo será:

- **Diciembre:** aviso de que la revisión corresponde al mes siguiente.
- **Enero:** espera del índice; se mantiene provisionalmente la renta anterior.
- **Febrero:** aplicación de la nueva renta y cobro de los atrasos de enero.

La pantalla resumen indicará el estado: aviso, esperando índice, actualizada o vacío cuando no exista revisión.

## Aviso de revisión
--------------------

En el primer mes del ciclo, el formulario mostrará marcado por defecto:

> Iniciar proceso de revisión

Si permanece marcado al finalizar, la factura incluirá el aviso correspondiente.

## Espera del índice
--------------------

En el mes de espera aparecerá marcado:

> Revisión en espera del índice

Si permanece marcado, se incluirá el mensaje de espera y continuará el proceso.

Si el usuario lo desmarca, se cancela la revisión de ese año y se mantiene la renta vigente hasta la siguiente revisión anual.

## Aplicación de la revisión
----------------------------

En el último mes aparecerá:

> Aplicar la revisión

Junto a esta opción se solicitará el porcentaje.

Hasta introducirlo y pulsar **Calcular**, no se mostrarán como definitivos los nuevos importes. El cálculo aplicará la nueva renta y añadirá una línea con los atrasos del mes anterior.

Al finalizar:

- la nueva renta se guarda con efecto desde la fecha contractual de revisión;
- el mes de aviso conserva la renta anterior;
- el mes de espera se factura con la renta anterior;
- el mes de aplicación incluye la renta nueva y los atrasos.

Si el usuario desmarca la aplicación, se elimina el porcentaje introducido, se mantienen los importes anteriores y se cancela la revisión de ese año.

## Factura excepcional
----------------------

Una factura excepcional podrá emitirse fuera del ciclo mensual.

El usuario seleccionará el contrato y Contab propondrá los datos habituales. Podrá modificar los conceptos e importes y añadir las líneas necesarias, pero el número y el destinatario seguirán controlados por la aplicación.

Después de calcular y finalizar, recibirá el mismo tratamiento contable, de conciliación y documental que una factura ordinaria.

## Errores, anulaciones y rectificaciones
-----------------------------------------

Debe distinguirse entre:

- corregir una factura todavía no finalizada;
- anular una factura que finalmente no debe emitirse;
- rectificar una factura ya emitida y enviada.

Antes de finalizar, los datos pueden modificarse libremente o cancelarse sin guardar.

Si una factura finalizada contiene un error detectado inmediatamente y todavía no se ha enviado, podrá anularse y repetirse manteniendo el control de la numeración y deshaciendo sus efectos contables y de conciliación.

Si ya fue emitida y enviada, deberá utilizarse una factura rectificativa. Su diseño detallado se abordará al implementar la generación documental, para ajustarlo a las necesidades reales y a la normativa aplicable.

## Facturas realizadas fuera de Contab
---------------------------------------

El usuario siempre conservará la posibilidad de emitir manualmente una factura desde sus plantillas.

Para mantener coherentes la numeración, la contabilidad y la conciliación, Contab deberá permitir registrar posteriormente esa factura mediante una entrada sencilla asociada al contrato.

No será necesario indicar de nuevo el inmueble, porque se deduce del contrato.

## Documentos y archivo
-----------------------

Se mantendrán separados:

- la plantilla base;
- el archivo editable generado para una factura concreta;
- el PDF definitivo.

Esta separación facilita emitir manualmente una factura y evita modificar accidentalmente la plantilla.

La ruta base de los documentos pertenece al inmueble. Las facturas se archivarán dentro de su estructura de carpetas por inmueble y año.

Contab no pretende ofrecer una consulta documental completa. El PDF archivado en el sistema de archivos es el soporte válido y el usuario seguirá accediendo a él desde sus carpetas habituales.

## Datos conservados
--------------------

Se conservarán los datos necesarios para:

- controlar la numeración;
- completar la factura y sus líneas;
- generar los documentos;
- registrar el ingreso contable;
- crear y conciliar el movimiento previsto;
- gestionar anulaciones o rectificaciones próximas a la emisión.

No se duplicarán en la factura copias históricas innecesarias de todos los datos del destinatario. El contrato contiene los datos de trabajo y el PDF conserva el contenido definitivo enviado.

Aunque inicialmente se mantendrán todos los registros de facturas, podría incorporarse en el futuro una limpieza anual que conserve, como mínimo, los últimos cinco años y nunca elimine información todavía necesaria.

## Alcance actual
-----------------

Actualmente Contab ya dispone de parte de la base necesaria:

- contratos con indicación de si generan factura;
- datos de facturación e impuestos;
- rentas y revisiones previstas;
- modelos básicos para facturas y líneas;
- apuntes contables;
- movimientos previstos para conciliación;
- rutas documentales previstas para futuras exportaciones.

La generación mensual completa y la creación automática de archivos ODS y PDF permanecen pospuestas.

## Próximos pasos
-----------------

La facturación se retomará cuando estén suficientemente avanzadas la contabilidad y la conciliación.

El orden previsible será:

1. Validar nuevamente la operativa con el uso real del cliente.
2. Completar la pantalla resumen mensual.
3. Completar el formulario de cálculo y finalización.
4. Integrar las revisiones de renta en un caso real.
5. Generar los apuntes y movimientos previstos definitivos.
6. Crear las facturas a partir de plantillas ODS.
7. Exportar y archivar automáticamente los PDF.
8. Incorporar anulaciones y facturas rectificativas con el alcance estrictamente necesario.

El desarrollo sólo se considerará útil cuando reduzca el trabajo respecto al método manual y mantenga el control que el usuario tiene actualmente.
