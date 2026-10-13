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

El tratamiento del apunte determina qué parte constituye realmente ingreso o gasto del propietario.

El criterio funcional es:

- **CONTABILIZAR:** el ingreso o gasto forma parte de la contabilidad del propietario.
- **REPERCUTIR:** la parte atribuida a un inquilino y posteriormente reembolsada no constituye gasto del propietario. La parte que no pueda atribuirse a ningún contrato permanece como gasto del propietario.
- **FACTURAR:** el gasto forma parte íntegramente de la contabilidad del propietario. Cuando posteriormente se facture al inquilino, la factura producirá además su correspondiente ingreso contable.

Por tanto, `FACTURAR` no elimina ni aplaza contablemente el gasto original.

En `REPERCUTIR`, la exclusión de los informes debe aplicarse únicamente a la parte efectivamente atribuida a contratos. Una parte sin contrato aplicable sigue correspondiendo al propietario.

Los informes utilizan las distribuciones e imputaciones persistidas para conservar las decisiones históricas de reparto y atribución. No recalculan esos repartos a partir de la configuración o los contratos actuales.

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

- los inmuebles activos que no sean contenedores de tipo `T`;
- los inmuebles inactivos que tengan apuntes aplicables durante el año solicitado;
- los locales de inmuebles `T` que tengan distribuciones persistidas correspondientes a apuntes aplicables.

Se consideran aplicables los tratamientos `CONTABILIZAR`, `FACTURAR` y `REPERCUTIR`.

Los inmuebles de tipo `T` no aparecen como contabilidad propia. Sus gastos se muestran en los locales hijo según las `DistribucionApunte` persistidas.

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

Un inmueble de tipo `T` representa la propiedad común de varios locales alquilables. Algunos gastos, como el IBI, el seguro o la comunidad, pertenecen al conjunto de la propiedad.

Los apuntes registrados en un inmueble `T` no constituyen contabilidad propia del contenedor. Al crearse se distribuyen entre sus locales hijo según la participación configurada.

La distribución se conserva persistentemente en `DistribucionApunte`, incluyendo la participación utilizada y los importes resultantes. De esta forma, un cambio posterior de participaciones no altera el reparto histórico.

A partir de cada distribución se aplica el tratamiento del apunte:

- **CONTABILIZAR:** toda la parte distribuida corresponde al propietario y debe aparecer en la contabilidad del local.
- **REPERCUTIR:** la parte atribuida temporalmente a contratos se excluye como gasto del propietario; los períodos sin contrato permanecen como gasto del propietario.
- **FACTURAR:** toda la parte distribuida continúa siendo gasto del propietario. La parte atribuida a contratos podrá incorporarse posteriormente a factura.

La distribución espacial y la atribución temporal son operaciones distintas:

- `DistribucionApunte` determina a qué local corresponde el gasto;
- `ImputacionContrato` determina qué parte de ese gasto corresponde a cada contrato.

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
- el porcentaje configurable para la estimación de IRPF o IRNR;
- la aplicación de los tratamientos `CONTABILIZAR`, `FACTURAR` y `REPERCUTIR`;
- la distribución de los gastos de inmuebles `T` entre sus locales mediante `DistribucionApunte`;
- la exclusión, en gastos `REPERCUTIR`, de la parte persistida en `ImputacionContrato` como atribuida a contratos.

Los informes utilizan las distribuciones e imputaciones persistidas y no reconstruyen históricamente los repartos a partir de los contratos o participaciones actuales.

## Evolución prevista
---------------------

Los siguientes informes se decidirán a partir de necesidades fiscales reales. Las prioridades previsibles son:

1. Informes básicos para la declaración trimestral del IVA.
2. Informes anuales orientados al IRPF o IRNR.
3. Nuevas agrupaciones cuando cambien los formularios de Hacienda.
4. Integración de distribuciones e imputaciones en cualquier nuevo informe fiscal que las necesite.

El criterio rector es conservar datos suficientemente detallados y generar sólo los informes que aporten utilidad comprobada, manteniendo el código y la interfaz lo más sencillos posible.
