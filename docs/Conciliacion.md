# \# Conciliación de movimientos

## \## Finalidad

La conciliación bancaria es uno de los dos objetivos principales de
Contab, junto con la obtención de información contable adaptable a las
necesidades fiscales.

Su finalidad es reducir el tiempo que el usuario dedica a revisar los
movimientos bancarios, relacionarlos con los ingresos y gastos de cada
inmueble y localizar las excepciones que requieren investigación.

Contab debe proponer y facilitar el trabajo, pero el usuario conserva
siempre el control y confirma el resultado final.

La conciliación no tiene que forzar todos los casos reales a una
correspondencia individual entre un movimiento bancario y un movimiento
previsto. El objetivo es que cada situación quede resuelta de una forma
comprensible y trazable, especialmente cuando años después sea necesario
justificarla.

## \## Situación real

El usuario revisa periódicamente los movimientos del banco y trata de
relacionarlos con:

-   los alquileres y otros importes cobrados;
-   las facturas y recibos pagados;
-   los gastos previstos, como comunidad, suministros, seguros o
    tributos;
-   los movimientos personales o ajenos a los inmuebles.

Cuando encuentra un cargo sin factura recibida por correo electrónico,
accede al banco para descargar su justificante. Los movimientos que no
consigue identificar deben investigarse individualmente.

La información bancaria no es uniforme. Un ingreso puede contener el
nombre del inquilino, el de otra persona que realiza el pago, un NIF,
una dirección o sólo un texto genérico. En recibos de suministros y
seguros suele aparecer el proveedor, pero no siempre el inmueble al que
corresponde.

La experiencia con los casos reales del cliente ha mostrado además
varias excepciones importantes:

-   los recibos domiciliados de gastos suelen coincidir exactamente con
    el apunte contable; una diferencia de importe normalmente debe hacer
    revisar el apunte en vez de aceptarse automáticamente;
-   un pago grande realizado mediante transferencia puede dividirse en
    varias transferencias por los límites diarios del banco;
-   algunos tributos municipales, como IBI y TRU, se contabilizan por
    inmueble pero el Ayuntamiento puede cargarlos agrupados en varios
    cobros globales;
-   algunos gastos se pagan en efectivo o con tarjeta y nunca aparecen
    en la cuenta bancaria;
-   los alquileres suelen poder conciliarse individualmente, pero un
    inquilino con atrasos puede realizar pagos parciales e irregulares
    que el cliente controla por saldo total y no asignando
    artificialmente cada pago a cada mensualidad;
-   algunos ingresos excepcionales, como una fianza o la primera
    mensualidad entregadas al firmar un contrato, pueden cobrarse en
    efectivo y no aparecer en el banco.

Estas excepciones son poco frecuentes y el número de inmuebles es
pequeño. Contab no necesita automatizarlas todas. Sí debe permitir dejar
constancia clara de cómo se resolvieron.

## \## Operativa con Contab

El proceso habitual es:

1.  El usuario descarga el CSV de su banco y lo importa en Contab.
2.  Contab incorpora únicamente los movimientos nuevos y evita duplicar
    los ya importados.
3.  La revisión considera los movimientos bancarios y previstos que
    continúan pendientes.
4.  Contab calcula propuestas automáticas a partir de importe, fechas y
    textos identificativos.
5.  Las propuestas se muestran al usuario antes de modificar ningún
    movimiento.
6.  El usuario puede rechazar una propuesta mediante **Dejar
    pendiente**. El rechazo se conserva durante la sesión de revisión,
    pero no se convierte en un dato permanente.
7.  Las propuestas automáticas con importe coincidente pueden
    confirmarse conjuntamente mediante **Confirmar propuestas**.
8.  Las propuestas con importes diferentes se muestran separadamente y
    nunca se confirman mediante el proceso automático normal.
9.  Los movimientos personales o ajenos a Contab pueden marcarse como
    descartados.
10. Las situaciones que no encajen en la conciliación automática deberán
    poder resolverse manualmente, dejando constancia suficiente para
    entender posteriormente la decisión.

Una propuesta automática nunca se considera conciliada sin la
confirmación del usuario.

La confirmación vuelve a calcular las propuestas en el servidor. No
depende de que el navegador envíe las parejas a conciliar. Se respetan
los movimientos que el usuario haya dejado pendientes y sólo se
confirman automáticamente las correspondencias de importe exacto.

## \## Bases de datos y bancos

El cliente mantiene dos contabilidades independientes, cada una en su
propia base de datos. Cada base se concilia contra una sola cuenta
bancaria.

Los bancos utilizados inicialmente son Ibercaja y CaixaBank. El banco se
asocia a la base de datos para que el usuario no tenga que indicarlo en
cada importación.

Contab no pretende sustituir la consulta de movimientos que ofrece la
banca electrónica. Sólo conserva la información necesaria para importar,
identificar, conciliar y justificar el resultado.

## \## Movimientos bancarios

De cada movimiento interesa conservar:

-   la fecha de la operación;
-   si es un ingreso o un gasto;
-   el importe;
-   el tipo y la descripción originales facilitados por el banco;
-   la referencia bancaria, cuando exista;
-   su situación dentro del proceso de conciliación.

No se necesitan el saldo, la fecha de valor ni repetir el banco y la
cuenta en cada movimiento.

Un movimiento bancario puede estar:

-   **Pendiente:** todavía no está resuelto.
-   **Conciliado:** ha sido resuelto y confirmado.
-   **Descartado:** es personal o ajeno a Contab.

Descartar es una acción reversible. El usuario puede restaurar el
movimiento y devolverlo a pendiente.

La importación debe impedir que un mismo movimiento se cargue otra vez
al importar períodos solapados, sin confundirlo con dos operaciones
reales que tengan la misma fecha e importe.

## \## Movimientos previstos

Un movimiento previsto representa un cobro o pago que Contab espera
encontrar o resolver dentro del proceso de conciliación.

Puede proceder de:

-   una factura emitida por Contab;
-   un apunte contable introducido al recibir una factura o
    justificante;
-   una previsión periódica de un inmueble;
-   una entrada manual excepcional.

Cuando procede de una factura o de un apunte real, el importe esperado
es normalmente exacto. Cuando procede de una regla periódica, tanto el
importe como las fechas pueden ser orientativos.

Las fechas previstas pueden quedar vacías, indicar sólo una fecha
inicial o formar un intervalo. Sirven para valorar una coincidencia.
Actualmente se admite como compatible un movimiento producido hasta
siete días antes de la fecha inicial; un movimiento posterior al
intervalo sigue pudiendo ser candidato, aunque ya no recibe la
puntuación correspondiente a la fecha.

Un movimiento previsto puede estar:

-   **Pendiente.**
-   **Parcialmente conciliado.**
-   **Conciliado.**
-   **Cancelado.**

La cancelación es reversible. Los movimientos conciliados no deben
eliminarse directamente.

## \## Previsiones periódicas

En el futuro podrán definirse reglas sencillas por inmueble, por
ejemplo:

-   cuota de comunidad mensual durante los primeros días del mes;
-   recibo de agua cada dos meses;
-   seguro anual en un período aproximado;
-   tributo anual;
-   alquiler mensual por un importe conocido.

El usuario disparará un proceso para generar las previsiones
correspondientes al período elegido.

Si una previsión creada por una regla se corresponde después con una
factura o apunte real, ambos deben relacionarse sin duplicar el
movimiento esperado.

Una previsión conciliada que no tenga apunte contable asociado puede
indicar que falta registrar o archivar el justificante. Contab debe
advertirlo, pero no crear automáticamente el apunte porque puede
desconocer su clasificación, período, impuestos o documento soporte.

## \## Criterios actuales de propuesta

Las propuestas automáticas actuales usan reglas sencillas y explícitas.
Para que un movimiento previsto pueda ser candidato debe:

-   estar pendiente;
-   tener la misma naturaleza, ingreso o gasto, que el movimiento
    bancario;
-   no encontrarse excesivamente en el futuro respecto a la fecha
    bancaria.

Sobre los candidatos compatibles se aplican estas señales:

-   importe exacto: **+100**;
-   contraparte encontrada en el texto bancario: **+50**;
-   alias configurado del inmueble y tipo de movimiento: **+40**;
-   fecha dentro del intervalo previsto: **+20**.

Los textos se comparan normalizados, ignorando mayúsculas, minúsculas,
acentos y espacios redundantes.

La propuesta sólo se presenta cuando el mejor candidato obtiene más de
20 puntos y no existe empate con otro candidato en la mejor puntuación.

Los alias de conciliación se configuran explícitamente por base de
datos, tipo de movimiento e inmueble. Permiten reconocer textos reales
del banco sin introducir reglas difusas o difíciles de justificar.

No se utiliza por ahora coincidencia aproximada de textos, aprendizaje
automático ni comportamiento histórico. El algoritmo debe mejorarse sólo
cuando los casos reales demuestren que aporta valor.

Una diferencia de importe no impide necesariamente mostrar una propuesta
si existen otras señales suficientemente fuertes. Sin embargo, esa
propuesta se separa visualmente y no puede entrar en la confirmación
automática normal.

## \## Conciliación individual 1:1

La conciliación automática actualmente implementada resuelve el caso
normal de una correspondencia completa entre:

-   un movimiento bancario pendiente; y
-   un movimiento previsto pendiente.

Para confirmarla automáticamente deben:

-   tener la misma naturaleza;
-   tener exactamente el mismo importe.

Al confirmarla se crea una entidad `Conciliacion` que relaciona ambos
movimientos y conserva el `importe_asociado`. El movimiento bancario y
el movimiento previsto pasan a estado **Conciliado**.

Si el movimiento previsto procede de un apunte contable, la relación
queda por tanto:

    MovimientoBancario
        ↓
    Conciliacion
        ↓
    MovimientoPrevisto
        ↓
    ApunteContable

La confirmación de las propuestas exactas se realiza en una única
transacción. Si una conciliación no puede confirmarse, no debe quedar
guardado parcialmente el lote.

Las propuestas rechazadas por el usuario, las propuestas con importes
diferentes y los movimientos que continúan pendientes no se modifican.

## \## Estado y método de resolución

El estado de un movimiento debe expresar si la situación está resuelta,
no el procedimiento utilizado para resolverla.

Por ello no se introducirán estados como `MANUAL` o `CONTABILIZADO` para
representar formas distintas de conciliación.

Conceptualmente deben mantenerse separadas dos preguntas:

-   **Estado:** ¿está resuelto el movimiento?
-   **Método:** ¿cómo se sabe o se ha decidido que está resuelto?

Un movimiento resuelto manualmente seguirá siendo un movimiento
**Conciliado**. La información de que fue resuelto manualmente, junto
con sus observaciones, deberá conservarse como parte de la resolución de
conciliación.

Inicialmente sólo es necesario distinguir el proceso individual normal y
la resolución manual. No se añadirá un método específico de conciliación
por saldo mientras los casos reales no demuestren que sea necesario.

## \## Conciliación manual

La conciliación manual será el siguiente paso funcional.

Debe servir para resolver de forma explícita situaciones que el proceso
automático no puede representar adecuadamente, por ejemplo:

-   gastos o ingresos pagados en efectivo;
-   gastos pagados con tarjeta y ausentes de la cuenta bancaria
    importada;
-   tributos municipales contabilizados por inmueble pero cobrados de
    forma agrupada;
-   situaciones de atrasos de alquiler controladas externamente por
    saldo;
-   otras excepciones verificadas por el usuario.

La resolución manual debe permitir introducir una observación que
explique qué ocurrió y cómo se comprobó. Esa observación pertenece a la
conciliación, no al `ApunteContable`, porque describe la forma de
resolver la correspondencia bancaria y no el hecho contable original.

Ejemplo:

    Movimiento previsto:
    IBI Piso Moncada
    250,00 €
    CONCILIADO
    Método: MANUAL

    Observaciones:
    "Pago incluido en los cargos agrupados del Ayuntamiento
    de junio, noviembre y regularización de diciembre 2026."

La prioridad no es automatizar estas excepciones, sino que queden
comprensibles y justificables años después.

## \## Correspondencias complejas

El modelo `Conciliacion`, mediante su `importe_asociado`, permite
evolucionar cuando sea necesario hacia:

-   un movimiento bancario relacionado con varios movimientos previstos;
-   varios movimientos bancarios relacionados con una única previsión;
-   conciliaciones parciales.

Esto puede cubrir pagos agrupados, pagos fraccionados y otras
diferencias reales.

Por ejemplo, un gasto previsto de 4.000 € podría pagarse mediante dos
transferencias de 2.500 € y 1.500 €. Cada transferencia podría quedar
conciliada y el movimiento previsto pasar primero a **Parcialmente
conciliado** y después a **Conciliado**.

Sin embargo, esta funcionalidad no se implementará por anticipado. El
modelo de datos la admite, pero el siguiente objetivo es la conciliación
manual sencilla.

Tampoco se añadirá por ahora un modo `1:1` o `m:n` al contrato. Los
atrasos de un inquilino son una situación temporal y no una propiedad
permanente del contrato. Si en el futuro fuese necesario gestionar
sistemáticamente esos episodios por saldo, se diseñará entonces una
solución específica a partir de casos reales.

## \## Control y conservación

El resultado debe permitir distinguir con claridad:

-   movimientos conciliados y confirmados;
-   propuestas pendientes de revisión;
-   propuestas con discrepancias que requieren intervención;
-   movimientos sin correspondencia;
-   previsiones que todavía no se han cobrado o pagado;
-   movimientos descartados;
-   posibles documentos o apuntes contables pendientes de registrar.

Debe conservarse información suficiente para reconstruir por qué se
consideró resuelta una situación. Esta trazabilidad es especialmente
importante para poder explicar años después un ingreso, gasto o
agrupación excepcional ante una revisión fiscal o contable.

Inicialmente se conservarán los movimientos porque su volumen es pequeño
y aportan trazabilidad al proceso. En el futuro podrá definirse una
limpieza por antigüedad, pero nunca se eliminarán movimientos pendientes
y no se desarrollará ese proceso hasta que exista una necesidad real.

## \## Alcance actual

Actualmente están disponibles:

-   la importación de CSV de Ibercaja y CaixaBank;
-   la detección de movimientos ya importados;
-   el listado, filtrado y paginación de movimientos bancarios;
-   el descarte y la restauración de movimientos bancarios;
-   el modelo de movimientos previstos, con fechas orientativas y
    estados;
-   el listado de movimientos previstos;
-   la cancelación y restauración de movimientos previstos;
-   la configuración de alias de conciliación por base de datos, tipo e
    inmueble;
-   la puntuación y propuesta automática de candidatos;
-   la revisión de propuestas sin modificar los datos;
-   la posibilidad de dejar una propuesta pendiente durante la sesión de
    revisión;
-   la separación entre propuestas de importe exacto y propuestas con
    importes diferentes;
-   la confirmación conjunta de las propuestas automáticas exactas;
-   la persistencia de la relación mediante `Conciliacion`;
-   la protección mediante tests de los flujos principales de
    conciliación automática 1:1.

La conciliación automática 1:1 puede considerarse funcionalmente cerrada
para el alcance actual.

## \## Trabajo pendiente

Los siguientes pasos son:

1.  Implementar una conciliación manual sencilla, con trazabilidad y
    observaciones.
2.  Probarla con los casos reales de efectivo, tarjeta, tributos
    agrupados y otras excepciones.
3.  Generar un informe claro de resultados y excepciones cuando la
    información almacenada permita hacerlo de forma útil.
4.  Añadir las reglas periódicas por inmueble cuando el proceso básico
    ya sea útil y exista una necesidad concreta.
5.  Mejorar progresivamente el algoritmo de propuestas únicamente a
    partir de casos reales del cliente.
6.  Implementar correspondencias parciales o múltiples sólo si la
    operativa real demuestra que la conciliación manual no es
    suficiente.

El criterio rector seguirá siendo aportar ahorro de tiempo con el mínimo
código e interfaz necesarios, conservar el control del usuario y dejar
una trazabilidad suficiente, sin convertir Contab en una aplicación de
banca electrónica ni en un sistema completo de gestión de cobros y
deudas.
