# Informes contables
====================

## Finalidad
------------

Los informes contables son uno de los dos objetivos principales de Contab, junto con la conciliación bancaria.

Su finalidad es evitar que el usuario tenga que reconstruir y reclasificar manualmente la contabilidad cada vez que Hacienda modifica el nivel de detalle o la forma de declarar los ingresos y gastos de los inmuebles.

Contab debe conservar los apuntes con suficiente detalle y permitir obtener distintas agrupaciones sin obligar al usuario a cambiar durante el año su forma cotidiana de trabajar.

## Situación anterior a Contab
------------------------------

El usuario anotaba los movimientos de cada inmueble en papel y, trimestralmente, los trasladaba a una hoja de cálculo para preparar la declaración del IVA.

Al finalizar el ejercicio utilizaba esas hojas para preparar la declaración del IRPF. Cuando Hacienda cambiaba el formulario o exigía un desglose diferente, debía revisar y reorganizar manualmente toda la contabilidad del año anterior.

Este trabajo podía ocupar más de un día y hacía inútil parte del esfuerzo de clasificación realizado durante el año.

## Operativa prevista con Contab
--------------------------------

Los apuntes se registran una sola vez, con una clasificación estable y suficientemente detallada.

Cuando el usuario necesita preparar una declaración o revisar la contabilidad:

1. Accede al apartado **Informes**.
2. Elige el informe o exportación que necesita.
3. Indica el ejercicio y, cuando corresponda, el inmueble.
4. Contab selecciona y agrupa los apuntes adecuados.
5. El usuario descarga el resultado y lo abre en LibreOffice Calc.

Los informes deben ser sencillos de revisar y suficientemente flexibles para que una hoja de cálculo permita resolver necesidades nuevas mientras se decide si merece la pena incorporarlas a Contab.

## Organización de los informes
--------------------------------

Contab dispone de un apartado independiente de **Informes**, con una pantalla índice.

Cada opción se presenta mediante:

- un enlace con el nombre del informe;
- una descripción breve de su finalidad.

No se crearán submenús de informes en Inmuebles, Inquilinos o Contratos. Son conjuntos pequeños y sus listados en pantalla, junto con la impresión del navegador, resultan suficientes.

## Formato de exportación
-------------------------

Los primeros informes se generan en CSV para abrirlos con LibreOffice Calc.

El formato acordado utiliza:

- codificación UTF-8;
- punto y coma como separador de campos;
- coma decimal;
- importes mostrados en euros;
- valores calculados, sin fórmulas de hoja de cálculo.

El objetivo es producir archivos fáciles de inspeccionar, reutilizar y adaptar, sin depender de una plantilla compleja.

## Apuntes incluidos
--------------------

Los informes contables ordinarios incluyen únicamente los apuntes con tratamiento **CONTABILIZAR**.

Los tratamientos tienen esta interpretación:

- **CONTABILIZAR:** el ingreso o gasto forma parte de la contabilidad del propietario.
- **REPERCUTIR:** el importe se traslada al inquilino y no forma parte de los informes contables ordinarios.
- **FACTURAR:** el importe se incluirá en una factura al inquilino y queda fuera del informe hasta que el proceso correspondiente genere los apuntes definitivos.

Esta separación evita contabilizar como gasto propio importes que realmente corresponden al inquilino.

## Clasificación contable
-------------------------

Los apuntes se clasifican mediante categorías y, cuando sea necesario, subcategorías.

La clasificación debe permitir:

- obtener los grupos exigidos actualmente por Hacienda;
- conservar detalles útiles, como distinguir IBI, residuos urbanos, agua, electricidad, gas o reparaciones;
- reagrupar los mismos apuntes con criterios distintos en informes futuros.

Las categorías utilizadas históricamente no deben desaparecer aunque dejen de ofrecerse para apuntes nuevos. Si Hacienda cambia sus criterios durante un ejercicio, los apuntes podrán reclasificarse de forma controlada sin desarrollar pantallas específicas para un caso excepcional.

## Exportación para la declaración del IVA
-------------------------------------------

El primer informe implementado es **Exportar apuntes para declaración de IVA**.

Genera un CSV anual para un inmueble con cuatro bloques, uno por trimestre. Cada bloque contiene:

- los apuntes ordenados por fecha;
- ingresos;
- gastos;
- IVA de los ingresos;
- retenciones de los ingresos;
- totales trimestrales;
- una estimación del ingreso neto.

También incluye los totales del ejercicio.

El IVA soportado de los gastos no se traslada a esta hoja porque así trabaja actualmente el usuario y el informe está orientado a reproducir su control habitual.

Los cuatro trimestres aparecen siempre. Cuando uno está vacío se mantiene un espacio antes de sus totales para que el bloque resulte claramente reconocible. Cuando contiene apuntes, la línea de totales sigue inmediatamente al último movimiento.

## Selección individual y exportación conjunta
-----------------------------------------------

El formulario permite elegir:

- un inmueble concreto;
- todos los inmuebles;
- el año del informe.

Si se selecciona un inmueble, se descarga su CSV.

Si se seleccionan todos, Contab genera un archivo ZIP con un CSV independiente para cada inmueble que deba incluirse. Esto permite obtener toda la contabilidad anual en una sola acción y conservar archivos separados, fáciles de importar como hojas distintas en LibreOffice.

Se incluyen:

- los inmuebles activos;
- los inmuebles inactivos que tengan apuntes contabilizables durante el año solicitado.

Los inmuebles subdivididos sin apuntes contabilizables no aparecen en el selector ni en las exportaciones.

## IVA. Resumen anual
---------------------

El informe **IVA. Resumen anual** reúne en una única hoja los totales trimestrales de todos los inmuebles incluidos en el ejercicio.

Dentro de cada trimestre separa:

- locales comerciales y otros contratos que generan factura;
- pisos y demás inmuebles cuyos contratos no generan factura.

La separación se determina por el contrato y su indicador de generación de factura, no únicamente por el tipo del inmueble.

Para cada inmueble se muestran los totales necesarios para revisar ingresos, gastos, IVA, retenciones y una estimación del rendimiento neto.

El resumen incluye también los totales generales del trimestre y del año.

## Estimación del rendimiento neto
----------------------------------

La estimación pretende aproximar el importe que conserva el propietario después de gastos e impuestos.

En contratos con retención se utiliza la retención real registrada.

En los restantes inmuebles se aplica un porcentaje estimado de IRPF o IRNR sobre los ingresos. El formulario permite al usuario indicar ese porcentaje y propone inicialmente un 24 %.

Es una estimación orientativa, no un cálculo fiscal definitivo.

## Inmuebles subdivididos
-------------------------

Un inmueble subdividido representa la propiedad común de varios locales alquilables. Algunos gastos, como el IBI o la comunidad, pertenecen al inmueble completo.

El tratamiento depende del informe:

- En el control del IVA, un apunte **CONTABILIZAR** del inmueble subdividido puede mostrarse como gasto del propio inmueble.
- En informes orientados al IRPF, esos gastos deberán repartirse proporcionalmente entre los locales, porque Hacienda exige declarar ingresos y gastos por inmueble o contrato alquilado.
- Los apuntes **REPERCUTIR** no se incluyen como gastos del propietario.
- Los apuntes **FACTURAR** producirán el gasto y, posteriormente, el ingreso correspondiente mediante la facturación.

No se ha creado por ahora una tabla permanente de distribuciones. El reparto podrá calcularse al generar cada informe, salvo que una necesidad real demuestre que conviene conservarlo.

## Datos catastrales
--------------------

Los futuros informes para el IRPF podrán necesitar:

- referencia catastral;
- valor catastral;
- valor del suelo;
- valor de la construcción;
- año de revisión catastral.

Estos datos pertenecen al inmueble. El usuario los rellenará cuando los conozca y deberá revisarlos cuando prepare la declaración correspondiente.

Que un valor no esté informado no debe impedir registrar la actividad ordinaria del inmueble.

## Controles y revisión
-----------------------

Los informes deben ayudar al usuario a detectar:

- trimestres sin los ingresos o gastos esperados;
- importes o clasificaciones anómalos;
- apuntes asignados al inmueble equivocado;
- diferencias entre los totales contables y fiscales;
- información necesaria que todavía no se haya registrado.

La revisión en hoja de cálculo sigue siendo útil como control visual y como solución rápida ante una exigencia fiscal nueva.

## Alcance actual
-----------------

Actualmente están disponibles:

- la pantalla índice de informes;
- el CSV anual de apuntes para un inmueble;
- la generación conjunta de los CSV de todos los inmuebles en un ZIP;
- el informe **IVA. Resumen anual**;
- la selección del año;
- el porcentaje configurable para la estimación de IRPF o IRNR.

## Evolución prevista
---------------------

Los siguientes informes se decidirán a partir de necesidades fiscales reales. Las prioridades previsibles son:

1. Informes básicos para la declaración trimestral del IVA.
2. Informes anuales orientados al IRPF o IRNR.
3. Distribución proporcional de gastos comunes de inmuebles subdivididos cuando el informe lo requiera.
4. Nuevas agrupaciones cuando cambien los formularios de Hacienda.

El criterio rector es conservar datos suficientemente detallados y generar sólo los informes que aporten utilidad comprobada, manteniendo el código y la interfaz lo más sencillos posible.
