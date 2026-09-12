# Importación bancaria
======================

## Finalidad
------------

La importación bancaria incorpora en Contab los movimientos descargados desde la banca electrónica para utilizarlos posteriormente en la conciliación.

Su objetivo no es reproducir la consulta de movimientos del banco, sino evitar la introducción manual de datos y proporcionar una base fiable para localizar cobros, pagos y operaciones ajenas a la contabilidad de los inmuebles.

## Alcance
----------

Contab admite inicialmente archivos CSV de:

- Ibercaja;
- CaixaBank.

Cada contabilidad se mantiene en una base de datos independiente y se corresponde con una sola cuenta bancaria. Por ello, el banco se asocia a la base de datos y el usuario no tiene que seleccionarlo cada vez que importa un archivo.

No se contempla mezclar en una misma base de datos movimientos procedentes de varias cuentas.

## Operativa del usuario
------------------------

El proceso habitual es:

1. El usuario accede a la banca electrónica.
2. Descarga en formato CSV los movimientos del período que quiere revisar.
3. En Contab, abre la opción de importación bancaria.
4. Selecciona el archivo descargado.
5. Contab utiliza el formato correspondiente al banco configurado para esa base de datos.
6. Se incorporan únicamente los movimientos que todavía no estaban registrados.
7. Contab informa del resultado de la importación.

El usuario puede importar períodos solapados o repetir accidentalmente un archivo sin que ello duplique los movimientos ya incorporados.

## Información conservada
-------------------------

De cada movimiento se conserva solamente la información útil para la conciliación:

- fecha de la operación;
- naturaleza: ingreso o gasto;
- importe;
- tipo de movimiento proporcionado por el banco;
- descripción original completa;
- referencia bancaria, cuando exista;
- estado dentro del proceso de conciliación.

Los textos originales se conservan porque contienen las pistas necesarias para identificar inquilinos, proveedores, direcciones, conceptos y otras referencias.

No se conservan:

- el saldo de la cuenta;
- la fecha de valor;
- el banco y la cuenta repetidos en cada movimiento.

Estos datos no aportan utilidad al proceso previsto en Contab.

## Normalización
----------------

Ibercaja y CaixaBank entregan archivos con columnas, literales y formatos diferentes. Durante la importación, Contab transforma ambos formatos en una representación común.

Esta normalización permite que el resto del proceso de conciliación sea independiente del banco de origen.

Contab debe respetar siempre los datos originales relevantes. La normalización facilita su tratamiento, pero no debe eliminar textos que puedan servir posteriormente para identificar una operación.

## Ingresos y gastos
--------------------

Los bancos pueden representar los importes de formas distintas. Contab los transforma en:

- una naturaleza, **INGRESO** o **GASTO**;
- un importe siempre positivo.

La naturaleza indica el sentido del movimiento. De esta manera, el signo utilizado por cada banco no se propaga al resto de la aplicación.

## Prevención de duplicados
---------------------------

Cada movimiento importado recibe una identificación calculada a partir de sus datos bancarios relevantes.

Esta identificación permite:

- volver a importar el mismo archivo sin duplicar datos;
- importar períodos que se solapen;
- conservar como operaciones distintas dos movimientos reales aunque compartan fecha e importe.

La detección no debe basarse únicamente en fecha e importe, porque es frecuente que existan varios cargos o abonos iguales el mismo día.

## Diferencias entre bancos
---------------------------

### Ibercaja
-------------

El archivo diferencia habitualmente el tipo de operación mediante conceptos como transferencias, recibos de comunidad, energía, gas o seguros.

La descripción puede contener nombres de inquilinos o pagadores, NIF, proveedores y fragmentos de direcciones. La referencia bancaria suele ser interna y, por sí sola, normalmente no permite identificar un inmueble.

### CaixaBank
--------------

El tipo y la descripción de la operación se obtienen principalmente de las columnas de movimiento y datos adicionales.

Los ingresos suelen incluir el nombre del ordenante o alguna referencia al alquiler. Los recibos pueden identificar una comunidad o proveedor, aunque no siempre permiten conocer directamente el inmueble afectado.

Las diferencias de formato quedan limitadas al proceso de lectura. Una vez importados, los movimientos de ambos bancos se tratan igual.

## Textos bancarios
-------------------

Los conceptos bancarios son irregulares y no deben interpretarse como identificadores exactos.

Entre los casos observados se encuentran:

- alquileres pagados por el propio inquilino;
- alquileres pagados por su pareja u otra persona;
- textos con el NIF o parte de la dirección del inmueble;
- recibos de comunidad identificables por la dirección;
- suministros que sólo muestran el nombre del proveedor;
- seguros sin número de póliza ni inmueble;
- operaciones personales sin relación con Contab.

La importación no intenta resolver estas correspondencias. Su función es conservar correctamente la información para que el proceso de conciliación pueda analizarla después.

## Estados posteriores a la importación
----------------------------------------

Todo movimiento nuevo comienza como **Pendiente**.

Posteriormente puede pasar a:

- **Conciliado**, cuando el usuario confirma su correspondencia;
- **Descartado**, cuando es personal o ajeno a Contab.

El descarte es reversible y permite restaurar el movimiento a pendiente.

## Controles importantes
------------------------

La importación debe:

- rechazar archivos que no correspondan al formato esperado;
- detectar datos esenciales ausentes o inválidos;
- evitar importaciones parciales que puedan dejar un resultado confuso;
- conservar correctamente caracteres acentuados y otros textos del archivo;
- informar de cuántos movimientos se han incorporado y cuántos ya existían.

Los errores deben explicarse de forma comprensible para que el usuario pueda comprobar el archivo o descargarlo nuevamente.

## Conservación de movimientos
------------------------------

Por ahora se conservan todos los movimientos importados. Su volumen es pequeño y mantenerlos ayuda a justificar y revisar la conciliación.

En el futuro podrá incorporarse una limpieza por antigüedad. En ese caso:

- nunca se eliminarán movimientos pendientes;
- se conservará un margen temporal prudente;
- sólo se borrarán datos que ya no sean necesarios para justificar apuntes o conciliaciones.

No se implementará este mantenimiento hasta que exista una necesidad real.

## Fuera de alcance
-------------------

La importación bancaria no pretende:

- mostrar saldos o posiciones bancarias;
- sustituir la banca electrónica;
- descargar movimientos directamente desde el banco;
- modificar operaciones bancarias;
- decidir automáticamente a qué inmueble corresponde cada movimiento;
- crear apuntes contables sin información suficiente.

Estas limitaciones mantienen el proceso sencillo y centran el desarrollo en el ahorro real de trabajo.

## Evolución prevista
---------------------

La incorporación de nuevos bancos deberá limitarse, en lo posible, a crear un nuevo lector para su formato CSV. El resto de la conciliación debe seguir funcionando sin cambios.

Las mejoras futuras se decidirán a partir de archivos reales y necesidades comprobadas, evitando añadir opciones bancarias o datos que el usuario no vaya a utilizar.
