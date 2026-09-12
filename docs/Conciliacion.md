# Conciliación de movimientos
==============================

## Finalidad
------------

La conciliación bancaria es uno de los dos objetivos principales de Contab, junto con la obtención de información contable adaptable a las necesidades fiscales.

Su finalidad es reducir el tiempo que el usuario dedica a revisar los movimientos bancarios, relacionarlos con los ingresos y gastos de cada inmueble y localizar las excepciones que requieren investigación.

Contab debe proponer y facilitar el trabajo, pero el usuario conserva siempre el control y confirma el resultado final.

## Situación actual
-------------------

El usuario revisa periódicamente los movimientos del banco y trata de relacionarlos manualmente con:

- los alquileres y otros importes cobrados;
- las facturas y recibos pagados;
- los gastos previstos, como comunidad, suministros, seguros o tributos;
- los movimientos personales o ajenos a los inmuebles.

Cuando encuentra un cargo sin factura recibida por correo electrónico, accede al banco para descargar su justificante. Los movimientos que no consigue identificar deben investigarse individualmente.

La información bancaria no es uniforme. Un ingreso puede contener el nombre del inquilino, el de otra persona que realiza el pago, un NIF, una dirección o sólo un texto genérico. En recibos de suministros y seguros suele aparecer el proveedor, pero no siempre el inmueble al que corresponde.

## Operativa prevista con Contab
--------------------------------

El proceso habitual será:

1. El usuario descarga el CSV de su banco y lo importa en Contab.
2. Contab incorpora únicamente los movimientos nuevos y evita duplicar los ya importados.
3. El usuario solicita la conciliación de los movimientos recién importados y de los que continuasen pendientes.
4. Contab propone las correspondencias que considere probables.
5. El usuario revisa las propuestas y confirma o rechaza cada resultado.
6. Cuando sea necesario, puede relacionar movimientos manualmente.
7. Los movimientos personales o ajenos a Contab se marcan como descartados.
8. El usuario concentra su trabajo en las excepciones que no hayan podido resolverse automáticamente.

Una propuesta automática nunca se considera conciliada sin la confirmación del usuario.

## Bases de datos y bancos
--------------------------

El cliente mantiene dos contabilidades independientes, cada una en su propia base de datos. Cada base se concilia contra una sola cuenta bancaria.

Los bancos utilizados inicialmente son Ibercaja y CaixaBank. El banco se asocia a la base de datos para que el usuario no tenga que indicarlo en cada importación.

Contab no pretende sustituir la consulta de movimientos que ofrece la banca electrónica. Sólo conserva la información necesaria para importar, identificar, conciliar y justificar el resultado.

## Movimientos bancarios
------------------------

De cada movimiento interesa conservar:

- la fecha de la operación;
- si es un ingreso o un gasto;
- el importe;
- el tipo y la descripción originales facilitados por el banco;
- la referencia bancaria, cuando exista;
- su situación dentro del proceso de conciliación.

No se necesitan el saldo, la fecha de valor ni repetir el banco y la cuenta en cada movimiento.

Un movimiento bancario puede estar:

- **Pendiente:** todavía no está resuelto.
- **Conciliado:** ha sido relacionado y confirmado.
- **Descartado:** es personal o ajeno a Contab.

Descartar es una acción reversible. El usuario puede restaurar el movimiento y devolverlo a pendiente.

La importación debe impedir que un mismo movimiento se cargue otra vez al importar períodos solapados, sin confundirlo con dos operaciones reales que tengan la misma fecha e importe.

## Movimientos previstos
------------------------

Un movimiento previsto representa un cobro o pago que Contab espera encontrar en el banco.

Puede proceder de:

- una factura emitida por Contab;
- un apunte contable introducido al recibir una factura o justificante;
- una previsión periódica de un inmueble;
- una entrada manual excepcional.

Cuando procede de una factura o de un apunte real, el importe esperado es normalmente exacto. Cuando procede de una regla periódica, tanto el importe como las fechas son orientativos.

Las fechas previstas pueden quedar vacías, indicar sólo una fecha inicial o formar un intervalo. Sirven para valorar una coincidencia, pero no para rechazarla automáticamente: un recibo esperado a partir del día 15 puede llegar el día 14.

No se pedirá al usuario un porcentaje de tolerancia para cada previsión. Los márgenes formarán parte del futuro algoritmo de conciliación.

Un movimiento previsto puede estar:

- **Pendiente.**
- **Parcialmente conciliado.**
- **Conciliado.**
- **Cancelado.**

La cancelación será reversible. Los movimientos conciliados no deben eliminarse directamente.

## Previsiones periódicas
-------------------------

En el futuro podrán definirse reglas sencillas por inmueble, por ejemplo:

- cuota de comunidad mensual durante los primeros días del mes;
- recibo de agua cada dos meses;
- seguro anual en un período aproximado;
- tributo anual;
- alquiler mensual por un importe conocido.

El usuario disparará un proceso para generar las previsiones correspondientes al período elegido.

Si una previsión creada por una regla se corresponde después con una factura o apunte real, ambos deben relacionarse sin duplicar el movimiento esperado.

Una previsión conciliada que no tenga apunte contable asociado puede indicar que falta registrar o archivar el justificante. Contab debe advertirlo, pero no crear automáticamente el apunte porque puede desconocer su clasificación, período, impuestos o documento soporte.

## Criterios de conciliación
----------------------------

Las propuestas se basarán en la combinación de varias señales:

- coincidencia entre ingreso y gasto;
- igualdad o proximidad del importe;
- cercanía a las fechas previstas;
- nombres de inquilinos, pagadores o proveedores;
- NIF y otras referencias;
- direcciones o identificadores de inmuebles;
- palabras significativas del texto bancario;
- comportamiento observado en movimientos anteriores.

El texto no siempre será suficiente. En suministros o seguros, el proveedor puede ser común a varios inmuebles; en esos casos serán especialmente importantes el importe, la fecha y la existencia previa del apunte o previsión.

También debe admitirse que el pago del alquiler lo realice la pareja u otra persona distinta del titular del contrato.

## Correspondencias complejas
-----------------------------

El diseño debe permitir, cuando sea necesario:

- un movimiento bancario relacionado con varios movimientos previstos;
- varios movimientos bancarios relacionados con una única previsión;
- conciliaciones parciales.

Esto cubre pagos agrupados, pagos fraccionados y diferencias que se resuelvan posteriormente.

Al confirmar una conciliación, el movimiento bancario queda relacionado con el movimiento previsto y, a través de éste, con el apunte contable cuando exista.

## Control y conservación
-------------------------

El resultado debe permitir distinguir con claridad:

- movimientos conciliados y confirmados;
- propuestas pendientes de revisión;
- movimientos sin correspondencia;
- previsiones que todavía no se han cobrado o pagado;
- movimientos descartados;
- posibles documentos o apuntes contables pendientes de registrar.

Inicialmente se conservarán los movimientos porque su volumen es pequeño y aportan trazabilidad al proceso. En el futuro podrá definirse una limpieza por antigüedad, pero nunca se eliminarán movimientos pendientes y no se desarrollará ese proceso hasta que exista una necesidad real.

## Alcance actual
-----------------

Actualmente están disponibles:

- la importación de CSV de Ibercaja y CaixaBank;
- la detección de movimientos ya importados;
- el listado, filtrado y paginación de movimientos bancarios;
- el descarte y la restauración de movimientos;
- el modelo básico de movimientos previstos, con fechas orientativas y estados;
- el listado de movimientos previstos.

## Trabajo pendiente
--------------------

Los siguientes pasos son:

1. Completar la operativa de los movimientos previstos.
2. Implementar las propuestas automáticas de conciliación.
3. Permitir la revisión, confirmación y conciliación manual.
4. Generar un informe claro de resultados y excepciones.
5. Añadir las reglas periódicas por inmueble cuando el proceso básico ya sea útil.
6. Mejorar progresivamente el algoritmo con los casos reales del cliente.

El criterio rector seguirá siendo aportar ahorro de tiempo con el mínimo código e interfaz necesarios, sin convertir Contab en una aplicación de banca electrónica ni en un archivo histórico de movimientos.
