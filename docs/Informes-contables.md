# Informes contables
====================

## Finalidad
------------

Los informes de Contab permiten revisar los ingresos y gastos de los inmuebles y preparar las declaraciones fiscales sin reconstruir manualmente la contabilidad del ejercicio.

Los apuntes se registran una sola vez, con su clasificación contable. Los informes utilizan esos datos y las distribuciones e imputaciones ya guardadas.


## Funcionamiento general

Desde Informes se elige el informe, el ejercicio y las opciones correspondientes.

Los informes pueden consultarse en pantalla, imprimirse y exportarse a Excel (XLSX). La
pantalla y el Excel utilizan los mismos datos y criterios contables.

Los importes calculados por Contab se exportan como números. Excel puede utilizar fórmulas
para los totales, pero no se exportan las fórmulas que reproducen repartos o criterios contables.


## Apuntes incluidos
--------------------

El tratamiento del apunte determina qué parte constituye realmente ingreso o gasto del propietario.

El criterio funcional es:

- **CONTABILIZAR:** el ingreso o gasto forma parte de la contabilidad del propietario.
- **REPERCUTIR:** la parte atribuida a un inquilino y posteriormente reembolsada no
  constituye gasto del propietario. La parte que no pueda atribuirse a ningún contrato
  permanece como gasto del propietario.
- **FACTURAR:** el gasto forma parte íntegramente de la contabilidad del propietario. Cuando posteriormente se facture al inquilino, la factura producirá además su correspondiente ingreso contable.

Por tanto, `FACTURAR` no elimina ni aplaza contablemente el gasto original.

En `REPERCUTIR`, la exclusión de los informes debe aplicarse únicamente a la parte efectivamente atribuida a contratos. Una parte sin contrato aplicable sigue correspondiendo al propietario.

Los informes utilizan las distribuciones e imputaciones persistidas para conservar las decisiones históricas de reparto y atribución. No recalculan esos repartos a partir de la configuración o los contratos actuales.

### Tratamiento de importes negativos

Los apuntes negativos conservan su naturaleza y clasificación contable.

En los informes, sus importes se presentan con signo negativo y se restan
de la columna y categoría a las que pertenece el apunte original.

Por ejemplo:

- Un gasto de gas de `100,00 €` se incluye como gasto positivo.
- Una devolución de gas de `30,00 €`, registrada como gasto negativo,
  se incluye como `-30,00 €` en la misma categoría.
- El gasto neto resultante es `70,00 €`.

Una devolución de un gasto no se traslada a la columna de ingresos,
ni una devolución de un ingreso se traslada a la columna de gastos.

Esta regla se aplica tanto a las líneas de detalle como a los totales
y resúmenes contables.

En los apuntes `REPERCUTIR`, el signo también se tiene en cuenta al
determinar qué parte corresponde al propietario, utilizando las
imputaciones a contratos que estén persistidas.



## Informe: Ingresos y gastos del año

El informe **Ingresos y gastos del año** muestra los apuntes fiscalmente computables de un inmueble durante el ejercicio seleccionado.

Los movimientos aparecen ordenados por fecha y agrupados en cuatro trimestres.

Las columnas son:

- Fecha y concepto.
- Ingresos.
- Una columna por cada categoría de gastos definida en `contab.ini`.
- IVA y retención de los ingresos.

Las columnas de gastos se generan según el orden y la denominación de las categorías contables, incluidas las inactivas que puedan tener apuntes históricos. Las subcategorías se agrupan en su categoría principal.

Los importes corresponden a las bases contables. El IVA y las retenciones de los ingresos se muestran por separado.

Cada trimestre termina con los totales por categoría y un resumen de **Ingresos, Gastos, IVA y Retención**. Al final del informe aparecen los mismos totales para el conjunto del año.

No se muestra una columna de total de gastos en cada apunte; ese importe aparece únicamente en los resúmenes.

### Selección de inmuebles

Si se selecciona un inmueble concreto, Contab muestra su informe y permite imprimirlo o exportarlo a Excel.

Si se selecciona **Todos los inmuebles**, no se presenta un informe conjunto en pantalla. La opción **Exportar Excel** genera un único libro con una hoja independiente por inmueble.

Se incluyen todos los inmuebles, tanto activos como inactivos, incluidos los de tipo `T` y sus locales hijos. Los resultados de las hojas no se suman entre sí.

### Tratamiento de los apuntes

- **CONTABILIZAR:** se incluye el ingreso o gasto registrado.
- **FACTURAR:** se incluye el gasto original. La factura posterior, cuando genera su correspondiente apunte de ingreso, se refleja por separado.
- **REPERCUTIR:** solo se incluye la parte del gasto que corresponde al propietario y que no está atribuida a contratos. Si todo el gasto corresponde a los inquilinos, el apunte no aparece en el informe.

Los importes negativos se muestran con signo negativo y se restan de la categoría correspondiente.

### Inmuebles subdivididos

En el informe de un inmueble `T` aparecen completos sus apuntes propios, tanto ingresos como gastos.

En el informe de cada local hijo aparecen sus apuntes propios y las partes de los ingresos y gastos del inmueble `T` que tenga asignadas mediante distribuciones persistidas.

Para los gastos repercutibles también se consideran las imputaciones guardadas a los contratos, de modo que únicamente aparezca la parte correspondiente al propietario.

El informe no vuelve a calcular repartos espaciales ni temporales.



## Informe: IVA. Resumen anual
------------------------------

El informe **IVA. Resumen anual** reúne en una única hoja los totales trimestrales de
todos los inmuebles incluidos en el ejercicio.

Dentro de cada trimestre separa:

- locales comerciales y otros contratos que generan factura;
- pisos y demás inmuebles cuyos contratos no generan factura.

La separación se determina por el contrato y su indicador de generación de factura, no únicamente por el tipo del inmueble.

Para cada inmueble se muestran los totales necesarios para revisar ingresos, gastos, IVA, retenciones y una estimación del rendimiento neto.

El resumen incluye también los totales generales del trimestre y del año.

### Estimación del rendimiento neto
----------------------------------

La estimación pretende aproximar el importe que conserva el propietario después
de gastos e impuestos.

Para los locales comerciales utiliza las retenciones reales
registradas.

Para pisos y otros inmuebles permite indicar un porcentaje
estimado de IRPF o IRNR, inicialmente del 24 %.

Por defecto, el porcentaje se aplica a los ingresos menos
los gastos. El usuario puede elegir aplicarlo a los ingresos
brutos, sin descontar gastos.

Cuando la base de estimación es negativa, Hacienda se
estima en cero.

Se trata de una estimación orientativa, no de un cálculo
fiscal definitivo.

El neto se calcula restando a los ingresos brutos los gastos y la retención real
o Hacienda estimada. El IVA se muestra por separado y no se descuenta del neto.
