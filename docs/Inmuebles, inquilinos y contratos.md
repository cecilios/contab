# Inmuebles, inquilinos y contratos
====================================

## Finalidad
------------

Inmuebles, inquilinos y contratos forman la base de Contab. Su función es conservar los datos estables necesarios para:

- conocer a qué propiedad corresponde cada ingreso o gasto;
- determinar quién ocupa cada unidad alquilable;
- calcular la renta vigente;
- preparar la facturación y los ingresos previstos;
- clasificar y agrupar correctamente la información contable.

El sistema está pensado para una cartera personal de menos de diez inmuebles. Debe ser robusto y claro, pero sin procesos complejos propios de una aplicación comercial de gestión inmobiliaria.

## Conceptos principales
------------------------

Se utiliza la siguiente terminología:

- **Inmueble:** propiedad física o jurídica a la que se imputan ingresos y gastos.
- **Local:** unidad susceptible de alquiler, con independencia de que sea un local comercial, un piso o una plaza de garaje.
- **Inquilino:** persona física o jurídica que figura como titular de un contrato.
- **Contrato:** relación entre una unidad alquilable y uno o varios inquilinos durante un período determinado.

En el caso habitual, un inmueble coincide con una única unidad alquilable. Cuando una propiedad está subdividida, se distingue entre el inmueble completo y cada una de sus partes alquilables.

## Inmuebles individuales
-------------------------

Un piso, un local comercial o una plaza de garaje que no estén subdivididos se registran directamente como inmuebles independientes.

Cada inmueble contiene los datos necesarios para identificarlo y utilizarlo en contratos, contabilidad e informes, entre ellos:

- referencia interna;
- tipo;
- código utilizado en facturación;
- descripción y dirección;
- participación;
- datos catastrales;
- ruta base para sus documentos;
- estado activo o inactivo.

La referencia debe ser breve, estable y fácilmente reconocible por el usuario, porque se utiliza en listados, documentos e informes.

## Inmuebles subdivididos
-------------------------

Algunas propiedades, normalmente locales comerciales, están divididas en varias unidades alquilables. La estructura conceptual es:

> Inmueble subdividido → Local A, Local B, Local C

Para representarla de forma sencilla:

- se crea un inmueble de tipo **T** para la propiedad completa;
- se crea un inmueble independiente para cada parte alquilable;
- cada parte selecciona como padre el inmueble subdividido;
- cada parte indica su porcentaje de participación.

El inmueble de tipo **T** representa la propiedad común y tiene una participación del 100 %. No puede tener contrato porque no es una unidad alquilable.

Los contratos y sus ingresos se asignan a los locales hijo. Los gastos comunes, como el IBI, el seguro o la comunidad, pueden asignarse al inmueble subdividido.

La jerarquía se muestra claramente en el listado para distinguir la propiedad completa de sus partes.

## Participación
----------------

La participación representa el porcentaje que corresponde a cada parte dentro de un inmueble subdividido.

Servirá para repartir gastos comunes en los informes que lo necesiten, especialmente los orientados al IRPF. No todos los informes deben aplicar ese reparto de la misma forma.

El reparto se calculará cuando sea necesario. No se mantiene por ahora un histórico permanente de distribuciones, porque no aporta utilidad suficiente.

## Estado del inmueble
----------------------

Un inmueble puede estar activo o inactivo.

Un inmueble inactivo se conserva para mantener la coherencia de contratos y apuntes anteriores, pero no debe ofrecerse para nuevas operaciones ordinarias.

Los informes de un ejercicio pueden incluir inmuebles inactivos cuando tengan apuntes contabilizables durante ese año.

## Datos catastrales y documentales
-----------------------------------

Los datos catastrales pertenecen al inmueble y pueden ser necesarios para futuros informes fiscales:

- referencia catastral;
- valor catastral;
- valor del suelo;
- valor de la construcción;
- año de revisión catastral.

No son obligatorios para empezar a utilizar Contab. El usuario los rellenará cuando los conozca y los revisará al preparar las declaraciones correspondientes.

La ruta de documentos también pertenece al inmueble. En el futuro permitirá generar y archivar facturas y otros documentos dentro de la organización de carpetas que ya utiliza el cliente.

Contab no pretende sustituir el sistema de archivos como archivo documental.

## Inquilinos
-------------

Un inquilino puede ser una persona física o una entidad. Su NIF es el principal dato para identificarlo y evitar duplicados.

Si al crear un contrato se introduce un NIF ya registrado, Contab reutiliza el inquilino existente. El nombre indicado debe coincidir con el guardado.

Cuando un mismo NIF aparece con un nombre diferente, Contab muestra el conflicto y no guarda el contrato. Esto evita que una errata cree identidades contradictorias.

El usuario debe decidir si:

- corrige el nombre introducido en el contrato; o
- modifica previamente los datos del inquilino cuando el nombre almacenado sea el incorrecto.

No se normalizan automáticamente diferencias relevantes de escritura porque podrían ocultar un error real.

## Titulares del contrato
-------------------------

Un contrato debe tener al menos un titular y puede tener varios.

Los titulares se mantienen ordenados. Todos se relacionan con registros de inquilinos, lo que permite reutilizar sus datos sin duplicarlos.

El contrato conserva la relación con sus titulares, mientras que los datos personales generales se mantienen en el registro del inquilino.

## Contratos
------------

Un contrato sólo puede asignarse a una unidad alquilable activa.

No puede crearse para:

- un inmueble subdividido de tipo **T**;
- un inmueble inactivo;
- un período que se solape con otro contrato del mismo inmueble.

El contrato recoge:

- fechas de inicio y vencimiento;
- fecha de finalización, cuando exista;
- fecha desde la que comienza la facturación o previsión de ingresos;
- titulares;
- fianza;
- renta;
- revisiones previstas;
- datos necesarios para facturar;
- destino del local, cuando resulte útil para identificar su actividad.

La finalización de un contrato no elimina su información. Permite conservar la relación histórica mínima necesaria para contabilidad e informes.

## Fechas del contrato
----------------------

Las fechas deben mantener una secuencia coherente:

- el vencimiento no puede ser anterior al inicio;
- la facturación no puede comenzar antes del contrato;
- la fecha de inicio de facturación debe ser el primer día de un mes;
- la finalización no puede ser anterior al inicio;
- una revisión no puede ser anterior al comienzo del contrato.

Al editar un contrato con movimientos históricos, no deben permitirse cambios que hagan incoherentes las rentas o revisiones ya registradas.

## Contratos con y sin factura
------------------------------

Cada contrato indica si genera factura.

Cuando genera factura:

- se exigen los datos necesarios para emitirla;
- se utilizan IVA y retención;
- se mantiene una dirección y un concepto de facturación.

Cuando no genera factura:

- esos datos son opcionales;
- pueden dejarse vacíos;
- también pueden rellenarse anticipadamente por si fueran necesarios en el futuro;
- el contrato sigue generando ingresos contables y movimientos previstos para conciliación.

En edición, los datos de facturación siempre pueden modificarse, aunque el contrato no genere factura.

## Concepto y destino
---------------------

El concepto de factura describe el alquiler y se completará posteriormente con el período facturado.

El destino identifica el uso o negocio desarrollado en el local, por ejemplo, ferretería. Es un dato diferente del concepto de factura y puede resultar útil en documentos e informes.

## Rentas
---------

La renta se mantiene separada del contrato para poder conservar sus cambios a lo largo del tiempo.

Cada renta tiene una fecha de efecto. La renta vigente en una fecha es la última cuyo inicio no sea posterior a dicha fecha.

El contrato comienza con una renta inicial y las revisiones o anexos posteriores pueden generar nuevas rentas.

Los importes se manejan siempre como cantidades monetarias positivas.

## Revisiones de renta
----------------------

Cada contrato contiene la fecha de su próxima revisión y el método que debe utilizarse.

Los métodos previstos incluyen:

- IPC nacional;
- IPC autonómico;
- IRAV;
- actualización fija.

Los tres índices externos tienen el mismo tratamiento en Contab. Su nombre sólo ayuda al usuario a saber qué porcentaje debe buscar e introducir. La aplicación no descarga índices automáticamente.

La revisión detallada se integrará con la facturación cuando exista un caso real de uso. Debe actualizar la renta contractual y, cuando corresponda, calcular atrasos.

## Carga inicial de contratos antiguos
---------------------------------------

Contab no pretende reconstruir la historia completa de contratos anteriores a su implantación.

Para la carga inicial se adopta una solución práctica:

- si no hay anexos relevantes, la renta inicial registrada puede ser la renta vigente;
- si existen anexos, el último puede reflejar la renta vigente;
- una nota puede aclarar la renta que figuraba realmente en el documento y que el importe introducido corresponde a la situación actual;
- la próxima revisión se registra con su fecha futura real.

No se crean anexos ficticios, estados especiales de carga ni procesos de reconstrucción histórica.

La trazabilidad completa se mantendrá para los contratos y cambios realizados a partir del uso efectivo de Contab.

## Corrección de datos
----------------------

Los datos maestros deben corregirse en su lugar de origen:

- los datos personales, en el inquilino;
- los datos físicos y fiscales, en el inmueble;
- las condiciones del alquiler, en el contrato;
- los cambios económicos, mediante rentas, revisiones o anexos.

Así, facturación, contabilidad, conciliación e informes utilizan una fuente común y no necesitan pantallas específicas para corregir copias de los mismos datos.

## Alcance actual
-----------------

Actualmente Contab permite:

- crear y modificar inmuebles;
- representar inmuebles subdivididos y sus partes;
- mostrar su jerarquía en el listado;
- crear y reutilizar inquilinos;
- detectar conflictos entre NIF y nombre;
- crear y editar contratos con varios titulares;
- impedir contratos incompatibles o solapados;
- distinguir contratos con y sin factura;
- mantener rentas y revisiones previstas;
- utilizar estos datos en contabilidad e informes.

## Evolución prevista
---------------------

Las ampliaciones se harán únicamente cuando sean necesarias para facturación, conciliación o informes.

Entre las necesidades previsibles están:

- completar el tratamiento automático de revisiones de renta;
- utilizar el destino del local en documentos e informes;
- incorporar los valores catastrales a informes fiscales;
- emplear las rutas documentales al generar facturas;
- distribuir gastos comunes en los informes que lo exijan.

El criterio rector es mantener un modelo suficientemente previsor, pero desarrollar sólo la interfaz y los procesos que aporten utilidad real al cliente.
