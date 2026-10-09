# CONTAB DEVELOPMENT HANDOFF

## Purpose

This is the technical handoff for resuming Contab development in a new conversation.

It is written primarily for the development assistant. It should contain enough current context to avoid reconstructing previous design decisions from commit history.

Before proposing changes or code:

1. inspect the latest `develop` branch;
2. read completely:

   * `docs/PROJECT.md`
   * `docs/DEVELOPMENT.md`
   * `docs/Inmuebles, inquilinos y contratos.md`
   * `docs/Apuntes-contables.md`
   * `docs/Informes-contables.md`
   * `docs/Importacion-bancaria.md`
   * `docs/Conciliacion.md`
   * `docs/Facturacion.md`

3. inspect the current project structure and the code relevant to the next change;
4. briefly summarize:

   * project purpose and principles;
   * implemented state;
   * exact stopping point;
   * next proposed small change.

Repository:

```text
cecilios/contab
branch: develop
```

The user's local tree may be ahead of GitHub between commits. Once the user says changes have been committed and pushed, `develop` can again be treated as current.

## Development workflow

The user is an experienced C++ developer but knows little Python/Flask. Instructions should be precise and concrete and should identify exact files, functions and changes instead of asking the user to search the repository.

Preferred workflow:

```text
agree on behavior
    ↓
write or adjust focused tests
    ↓
make the smallest production change
    ↓
run focused tests
    ↓
run full pytest suite
    ↓
perform a manual/visual test only when useful
    ↓
update docs after a meaningful block
    ↓
commit
```

TDD-style development is preferred when practical, but strict test-first work is not required.

Long integration tests should contain short comments explaining the user actions being simulated.

Automated pytest/integration tests are preferred over time-consuming artificial browser setup. Manual end-to-end tests are most valuable with real client data or when a UI interaction is being finalized.

When providing a complete replacement for a function or file, provide genuinely complete code. Never use placeholders such as `# ...` inside code the user is expected to paste.

Before relying on a function signature, inspect the current implementation.

When a test receives a pytest fixture as a parameter, its dependencies should also be expressed as fixture parameters rather than referring directly to decorated fixture functions.

Shared fixtures should remain minimal. Prefer adding local setup to a focused test rather than enriching a widely used fixture when that could change assumptions in existing tests.

At commit time:

* do not explain Git commands;
* propose only one or more commit messages;
* use Spanish infinitive phrases.

Documentation is a state/handoff mechanism, not a changelog. Update it after meaningful functional blocks or before a significant pause.

## Product context

Contab is a small personal application for managing the economic activity of fewer than ten rented properties.

Its two primary goals are:

1. **Bank reconciliation**: reduce the work required to identify and reconcile real bank movements with expected income and expenses.
2. **Flexible accounting/reporting**: record economic facts once and retain enough stable detail to regroup them later for changing fiscal and reporting requirements.

Billing, contracts and other modules are auxiliary to these goals.

The application begins real parallel use with the existing manual accounting process in October 2026. The purpose of the parallel period is to discover operational problems from real data before adding further complexity.

Prefer real client value over feature count.

## Permanent design principles

### Keep the application small

Prefer direct code, explicit services, simple Flask routes, understandable models and deterministic rules.

Avoid abstractions, screens and workflows for hypothetical cases.

A forward-looking database field is acceptable when the future need is stable, obvious and cheap to prepare. Operational functionality should wait for a real requirement.

### User control

Automation assists the user but does not make doubtful decisions on their behalf.

In reconciliation:

```text
Contab proposes
User reviews
User confirms
```

The same principle applies to billing and corrections: Contab may determine whether an operation is valid, but the user decides whether to perform it.

Exceptional cases must remain manually resolvable.

### Enter data once

A real economic fact should be entered once and then reused for accounting, reconciliation, reporting and billing where appropriate.

### Preserve source evidence

Do not destroy information needed for later verification.

Examples:

* bank movements retain original bank text;
* accounting entries retain document references;
* emitted invoices preserve historical invoice data;
* physical invoices and supporting documents remain in the filesystem.

### Atomic operations

Operations that create or remove several related records must succeed or fail together.

Current important examples:

```text
manual accounting entry
    → ApunteContable
    + optional MovimientoPrevisto

invoice emission
    → Factura
    + FacturaLinea(s)
    + FacturaDestinatario(s)
    + ApunteContable
    + MovimientoPrevisto

invoice deletion
    → delete MovimientoPrevisto
    + FacturaLinea(s)
    + FacturaDestinatario(s)
    + Factura
    + ApunteContable

non-invoice monthly rent
    → ApunteContable
    + MovimientoPrevisto

rent-revision reopening
    → RevisionRenta back to PENDIENTE
    + delete generated RentaContrato
    + delete automatically generated next RevisionRenta
```

Routes own database transactions.

Services implement business rules, calculate values, validate state and prepare or mutate domain objects, but do not commit.

Explicit `session.delete()` operations are normally owned by routes together with the transaction.

### Reversibility before rectification

Contab distinguishes between errors whose effects are still fully reversible and operations that have already produced historical/accounting effects that must be preserved.

When all subsequent effects can be safely removed, prefer:

```text
undo
→ return to prior coherent state
→ perform operation correctly again
```

Examples:

```text
Eliminar factura
Corregir revisión
```

When effects can no longer be safely removed, do not weaken validation rules. A future explicit compensating or rectifying workflow must handle the case.

### Tests are intentional complexity

Protect domain rules, complete form flows, error handling, multi-record operations, migrations and important module boundaries.

Do not reduce test coverage merely to keep production code small.

When a service already exhaustively tests a validation matrix, higher-level route/UI tests should verify delegation and visible behavior rather than duplicate every lower-level case.

## Technical architecture

Current stack:

```text
Python 3.13
Flask
SQLAlchemy
Alembic
SQLite
Jinja2
pytest
Waitress
LMDE 7
```

Architecture:

```text
Flask modular monolith

routes
  ↓ HTTP / forms / sessions / transactions
services
  ↓ business rules / domain preparation
SQLAlchemy models
  ↓
SQLite
```

Use SQLAlchemy `select()`, not legacy `Session.query()`.

Money is stored as positive integer cents. Nature determines direction:

```text
INGRESO
GASTO
```

Percentage values requiring two decimal places use hundredths of a percentage point.

For SQLite constraint changes, Alembic `batch_alter_table` is normally required. Back up real databases before schema migrations.

## Multiple databases and banks

Each logical database represents one accounting context and corresponds to one bank account for reconciliation.

Currently supported bank importers:

```text
IBERCAJA
CAIXABANK
```

`config.py` validates that every logical database has one supported bank. Application context helpers resolve the selected database and bank.

## Implemented property and accounting scope

Implemented:

* properties and rentable units;
* subdivided type-T parent properties;
* tenants;
* contracts with multiple ordered holders;
* rents and rent revisions;
* contract annexes for extensions and rent changes;
* contractual grace-period annexes;
* accounting categories/subcategories from `contab.ini`;
* accounting-entry CRUD and validation;
* accounting periods and treatments;
* document metadata;
* accounting CSV reports;
* annual VAT summary;
* demo database generation.

### Contract annexes

`AnexoContrato` represents a formal contractual modification.

Current types are:

```text
PRORROGA
CAMBIO_RENTA
CARENCIA
```

A grace-period annex stores:

```text
fecha_desde
fecha_hasta
```

Both fields are nullable at model level because other annex types do not use them, but a `CARENCIA` annex requires both.

Database constraints ensure:

```text
CARENCIA
    → fecha_desde and fecha_hasta are not NULL

other annex types
    → fecha_desde and fecha_hasta are NULL

fecha_hasta >= fecha_desde
```

The domain service:

```text
crear_anexo_carencia()
```

also validates:

```text
annex date >= contract start
fecha_desde is first day of month
fecha_hasta is last day of month
fecha_desde >= contract start
periods do not overlap another CARENCIA annex
```

Multiple non-overlapping grace periods are allowed.

The helper:

```text
carencia_vigente(contrato, periodo)
```

returns the applicable `AnexoContrato` or `None`.

The interval is inclusive at both ends.

A contractual grace period is deliberately not represented as:

```text
RentaContrato = 0
```

or as an `AjusteRenta`.

Its meaning is that no ordinary invoice should be prepared during that period.

The contract UI supports:

```text
Añadir anexo
    → Período de carencia
```

and the annex history displays the grace-period dates and optional description.

Important accounting treatments:

```text
CONTABILIZAR
REPERCUTIR
FACTURAR
```

`CONTABILIZAR` participates in accounting reports.

`REPERCUTIR` means charging a cost to a tenant. It is different from analytical allocation among properties.

Terminology:

```text
distribuir = analytical allocation among properties for reporting
repercutir = charge a cost to the tenant
```

## Accounting form validation

The accounting form follows:

```text
Validar
   ↓
Guardar
```

Validation computes automatic fields and a signature representing the validated state.

If protected form data changes afterward, saving fails and the user must validate again.

Blocking business validation should happen during `Validar`, not only during `Guardar`.

If validation is blocking:

```text
no firma_validacion
no Guardar button
```

The save path still rechecks domain rules defensively.

## Accounting entry and expected movement

Manual accounting-entry creation offers:

```text
☑ Generar movimiento previsto para conciliación
```

Default: checked.

When enabled, the expected movement is created in the same transaction.

Derived movement fields come from the accounting entry:

```text
inmueble
naturaleza
concepto
importe_esperado = apunte.total
contraparte = apunte.tercero_nombre
```

Expected dates are independent reconciliation data.

Rules:

```text
both empty       → valid
desde only       → valid
hasta only       → invalid
hasta < desde    → invalid
```

Never invent the expected bank date from `ApunteContable.fecha`.

`MovimientoPrevisto.apunte_id` remains nullable because independent expected movements are still allowed.

## Editing entries linked to expected movements

The accounting entry remains the source for derived economic/descriptive fields.

After an allowed edit, synchronize:

```text
inmueble
naturaleza
concepto
importe_esperado
contraparte
```

Do not overwrite:

```text
fecha_prevista_desde
fecha_prevista_hasta
estado
metodo_conciliacion
notas
```

For linked movements in `PENDIENTE` or `CANCELADO`, all accounting fields may be changed.

For linked movements in `CONCILIADO` or `PARCIAL`, protect changes to:

```text
inmueble
naturaleza
total
```

The amount protection compares accounting total, not its internal composition.

Deleting an accounting entry is likewise forbidden if any linked expected movement is `CONCILIADO` or `PARCIAL`.

## Bank import

Bank-file parsing belongs to:

```text
src/contab/conciliacion/importacion.py
```

Current behavior:

* uses operation date, not value date;
* parses Spanish monetary formats;
* stores positive cents;
* derives nature from source sign;
* preserves original type and description;
* preserves optional bank reference;
* rejects zero or malformed values;
* creates stable SHA-256 import fingerprints;
* uses an occurrence counter to distinguish legitimate identical rows in the same CSV.

`preparar_movimientos_bancarios()` returns new model objects and does not add or commit them.

Do not add bank/account/value-date/balance/accounting-entry fields without a real requirement.

Bank movement states:

```text
PENDIENTE
CONCILIADO
DESCARTADO
```

Expected movement states:

```text
PENDIENTE
PARCIAL
CONCILIADO
CANCELADO
```

Cancellation/discard is reversible.

## Automatic reconciliation

Automatic reconciliation currently handles the normal 1:1 case.

Normalization:

* removes accents;
* converts to uppercase;
* collapses whitespace.

Candidate scoring:

```text
exact amount                 +100
counterparty match            +50
property/type alias match     +40
date proximity                +20
```

Same nature is mandatory.

A bank movement more than seven days before the beginning of the expected interval is incompatible.

A movement later than the expected interval may remain a candidate but receives no date score.

A proposal is produced only when:

```text
best score > 20
and
no tie for best score
```


Mismatched amounts are shown separately and cannot be accepted through normal automatic reconciliation.

The review screen is:

```text
/conciliacion/revisar
```

Reconciliation proposals are accepted individually.

Each exact-amount proposal has an **Aceptar** button. Pressing it immediately confirms only the selected bank/expected movement pair.

There is no bulk confirmation and no temporary proposal rejection mechanism. Unaccepted proposals simply remain pending.

The individual acceptance endpoint is:

```text
POST /conciliacion/revisar/<movimiento_id>/aceptar
```

The form submits:

```text
previsto_id
```

Before accepting, the server:

1. verifies that the bank movement is pending;
2. recalculates its proposal using current pending expected movements and configured aliases;
3. verifies that the proposed expected movement matches `previsto_id`;
4. delegates domain validation and state changes to `confirmar_conciliacion()`.

The operation runs in a database transaction.

A successful acceptance creates a persistent `Conciliacion`, marks both movements reconciled and sets the expected movement method to `INDIVIDUAL`.

The user is redirected to the review screen, where proposals are recalculated.

### Discarding bank movements during review

The **Pendientes** section of the review screen offers a **Descartar** button for each bank movement.

It reuses the existing endpoint:

```text
POST /conciliacion/movimientos/<movimiento_id>/descartar
```

The review form includes:

```text
origen = revision
```

This makes the endpoint redirect back to the review screen after a successful discard.

Discarding is immediate, requires no additional confirmation, and changes the bank movement state to `DESCARTADO`.

Discarded movements no longer appear in reconciliation review because that screen queries only `PENDIENTE` bank movements.

They remain accessible and reversible from the **Movimientos bancarios** listing.

The existing bank movement state filter is sufficient for the user's current needs. No additional discarded/non-discarded filter or special row coloring is required.

The acceptance and discard workflows are covered by route integration tests, including validation failures and persistence.

## Manual reconciliation

An expected movement can also be reconciled manually when the real situation is not represented by a normal bank 1:1 correspondence.

Manual reconciliation requires nonblank notes explaining the resolution.

It sets:

```text
estado = CONCILIADO
metodo_conciliacion = MANUAL
```

Manual reconciliation is reversible.

Normal `INDIVIDUAL` reconciliation cannot be undone through the manual-reversal action because it also involves a bank movement and persistent reconciliation relation.

Do not implement general 1:n, n:1 or partial reconciliation until real use shows that the current individual/manual combination is insufficient.

Discard proposals remain postponed because they currently offer little value.

## Billing: current operational scope

Billing contains the complete ordinary workflow required for the October 2026 parallel run together with the first reversible correction workflows needed during real operation.

The monthly screen is:

```text
/facturacion/
```

It receives:

```text
periodo
fecha_emision
```

Initial values propose the next calendar month and its first day.

The screen has two sections:

```text
Locales
Otros
```

Preparation is transient. Do not create `Factura` objects merely to display the monthly preparation.

A `Factura` is persisted only when the user confirms the final accounting operation.

A separate revision overview is available at:

```text
/facturacion/revisiones
```

## Billing: contract selection

A contract is included when it is active at any point in the month:

```text
fecha_inicio <= last day of month
and
fecha_fin is None or fecha_fin >= first day of month
```

For rent lookup:

```python
fecha_renta = max(periodo, contrato.fecha_inicio)
```

This selects the applicable rent but does not imply proration.

For a contract with `genera_factura=True`, normal invoice preparation is skipped when the requested period is before:

```text
fecha_inicio_facturacion
```

Such contracts remain visible under **Locales** as being in grace period.

After the initial billing-date check, invoice preparation also checks:

```text
carencia_vigente(contrato, periodo)
```

If a contractual grace period applies, the contract likewise remains visible under **Locales** but no invoice is prepared.

The order is therefore:

```text
contract active in month?
    ↓
initial billing grace period?
    ↓
contractual CARENCIA annex active?
    ↓
rent revision
    ↓
rent
    ↓
ordinary invoice preparation
```

Do not move rent calculation before the grace-period checks. A contract in grace period must not require a currently available rent merely to appear in the monthly control list.

The non-invoice path under **Otros** has deliberately not been changed. Initial and contractual grace-period behavior for `genera_factura=False` must not be generalized without a real requirement.

## Billing: grace-period presentation

Both initial billing grace and `CARENCIA` annexes use:

```text
LocalEnCarenciaPreparado
```

It contains:

```text
contrato
inmueble
destinatario_nombre
proximo_periodo_facturacion
```

The monthly Locales table interleaves ordinary prepared invoices and grace-period rows ordered by property reference.

A grace-period row keeps the normal first columns:

```text
Inmueble
Nº factura = blank
Destinatario
```

The remaining economic/action columns are merged and display:

```text
En carencia. Próximo mes a facturar mm/aaaa
```

No Preview, Modify or accounting action is offered.

For initial grace:

```text
proximo_periodo_facturacion
    = contrato.fecha_inicio_facturacion
```

For a `CARENCIA` annex:

```text
proximo_periodo_facturacion
    = first day of month after anexo.fecha_hasta
```

Example:

```text
CARENCIA
01/11/2026 → 31/01/2027

October 2026
    → normal invoice

November 2026
December 2026
January 2027
    → En carencia. Próximo mes a facturar 02/2027

February 2027
    → normal invoice
```

No invoice number, rent, revision state, prepared lines or invoice actions are produced for a grace-period month.

## Billing: recipient and invoice snapshots

All contract holders are recipients, ordered by `ContratoInquilino.orden`.

Scalar accounting fields join them with `" / "`:

```text
tercero_nombre = "Ana Pérez / Juan Pérez"
tercero_nif    = "11111111A / 22222222B"
```

During preparation, recipient and billing-address data come from the current contract and holders.

When an invoice is persisted, historical invoice data is snapshotted so later contract changes do not alter the meaning of an already issued invoice.

Relevant historical data include:

```text
referencia_inmueble
descripcion_inmueble
direccion_facturacion
codigo_postal_facturacion
poblacion_facturacion
provincia_facturacion
FacturaDestinatario(s)
```

`Factura.apunte_contable_id` links the invoice to the accounting entry generated by its emission.

Do not replace these snapshots with live contract data when displaying an already emitted invoice.

## Billing: invoice preparation

`FacturaPreparada` is transient and represents the calculated invoice for the requested period.

It contains, among other data:

```text
contract
property
recipient
billing address
definitive prepared lines
automatic notes
base
VAT
withholding
total
predicted invoice number
rent revision and state
existing Factura, if already emitted
```

A key design rule is:

```text
FacturaPreparada.lineas
    = definitive lines that consumers should display
```

Routes and templates must not independently reconstruct invoice concepts already prepared by the service.

In particular, the ordinary rent concept already includes the invoiced period, for example:

```text
Alquiler local. Octubre de 2026
```

This avoids differences between the monthly list, Modify and Preview paths.

If no invoice exists for contract/period:

* lines and amounts are calculated from current contract data;
* automatic notes are prepared;
* revision effects are incorporated when applicable;
* `siguiente_numero_factura()` predicts the number for display;
* no `Factura` is persisted.

If an invoice already exists:

* `FacturaPreparada.factura` references it;
* persisted invoice lines and economic amounts are used;
* current contract data must not recalculate the economic content;
* the row shows `Emitida`.

The predicted number is only operational guidance. The definitive number is assigned when the invoice is persisted.

Invoice numbering is per property and year, across all contracts belonging to the property:

```text
NN/YYYY<codigo_facturacion>
```

The sequence resets each year.

There is deliberately no database unique constraint on `(contrato_id, periodo)` because future extraordinary invoices may legitimately share a period.

Ordinary `emitir_factura()` nevertheless rejects a second invoice for the same contract/period.

## Billing: automatic notes

Automatic invoice notes are prepared centrally and included in `FacturaPreparada.notas`.

Current automatic cases include:

```text
24 % withholding
rent revision AVISO
rent revision ESPERANDO_INDICE
rent revision APLICADA
```

These notes must survive all paths:

```text
monthly list → Preview

monthly list → Modify → Preview
```

Modify therefore starts from `factura.notas`.

User-entered notes can be added during transient editing.

The final notes are persisted with the invoice when accounting is confirmed.

Do not reconstruct automatic notes independently in individual templates or routes.

## Billing: transient modification

An unissued prepared invoice can be opened through `Modificar`.

The form receives the lines already contained in `FacturaPreparada`.

It allows transient editing of:

```text
concepts
amounts
VAT percentage
withholding percentage
notes
```

No draft `Factura` is persisted.

Empty form lines are discarded.

The form deliberately exposes only a small fixed number of line/note inputs because real invoices are compact and the physical document is intended to occupy approximately half an A4 page.

A revision in state `PENDIENTE` that must be resolved before billing blocks modification and final accounting.

The result is represented by `FacturaEditada`, which is then used by Preview and final accounting.

## Billing: preview and invoice document

Invoices can be previewed directly from the monthly list or after passing through Modify.

The preview renders the configured HTML invoice template.

The rendered invoice uses prepared data for:

```text
issuer
recipient
property
period
lines
notes
base
VAT
withholding
total
invoice number
issue date
```

The same prepared invoice must produce equivalent economic/document data regardless of the path used to reach Preview.

The current HTML invoice is printable and is sufficient for the real workflow.

The preview also contains a hidden accounting form carrying the exact edited lines, percentages, notes and previsualized totals.

The server does not trust those totals blindly.

Before persistence:

```text
parse submitted edited invoice
recalculate base / VAT / withholding / total
compare with previewed totals
```

If they differ, accounting is rejected and the user must preview again.

This protects the transition between Preview and Contabilizar.

## Billing: rent revisions

Rent revisions are integrated with invoice preparation and also have a dedicated overview panel.

`situacion_revision()` provides the state relevant to a requested billing period.

Current visible monthly states are:

```text
AVISO
ESPERANDO_INDICE
PENDIENTE
APLICADA
```

### AVISO

A pending revision scheduled for the following month produces:

```text
AVISO
```

The monthly list displays:

```text
Aviso
```

and the prepared invoice includes an explanatory automatic note.

### ESPERANDO_INDICE

A pending revision scheduled for the current month whose index is not yet available produces:

```text
ESPERANDO_INDICE
```

The monthly list displays:

```text
Esperando índice
```

The previous rent remains applicable for that invoice.

An automatic note explains that the index is unavailable and that the difference will be charged once it becomes known.

The general revisions panel does not resolve the percentage from this state. Percentage resolution remains tied to the monthly billing context.

### PENDIENTE

When a previous revision requires resolution before billing can continue:

```text
PENDIENTE
```

Modify/accounting is blocked.

The monthly preparation offers:

```text
Resolver revisión
```

The user must resolve the revision before continuing.

### APLICADA

After the revision has been resolved and its effects belong in the current billing period:

```text
APLICADA
```

The monthly list displays:

```text
Aplicada
```

This is a period-specific billing state. It must not continue appearing indefinitely in later months.

The revised `RentaContrato` supplies the new ordinary monthly rent.

When the scheduled revision month was previously invoiced using the old rent while waiting for the index, the applicable following invoice also contains an arrears line for that month.

Prepared lines therefore become, conceptually:

```text
revised current monthly rent
+ arrears for scheduled revision month
```

The same preparation also produces two automatic notes:

```text
index / percentage applied and resulting rent increase
arrears explanation referring to the previous invoice
```

The applied revision, arrears line and notes have been tested through:

```text
monthly Preview
Modify
Preview after Modify
final Contabilizar
```

The final persisted invoice retains both lines and the recalculated totals.

Index descriptions include the currently required methods, including IRAV.

Month-name formatting is centralized in the formatting utilities rather than maintaining repeated month tables in billing code.

## Billing: revision resolution domain logic

The core resolution operation currently belongs to:

```text
contab.contratos.services.resolver_revision_renta()
```

Signature:

```python
resolver_revision_renta(
    revision,
    fecha_resolucion,
    aplicar,
    porcentaje_aplicado,
)
```

For application:

```text
revision must be PENDIENTE
percentage is required
current rent at revision.fecha_prevista is found
new rent is calculated
new RentaContrato begins at revision.fecha_prevista
revision → APLICADA
percentage and resolution date are recorded
next yearly RevisionRenta is created as PENDIENTE
```

For non-application:

```text
revision must be PENDIENTE
percentage must be None
no RentaContrato is created
revision → NO_APLICADA
resolution date is recorded
next yearly RevisionRenta is created as PENDIENTE
```

The next revision uses the same method and the same month/day in the following year.

Routes persist the returned objects inside their transaction.

## Billing: revisions overview

The revisions dashboard is:

```text
/facturacion/revisiones
```

It shows active contracts divided into:

```text
Locales
Otros
```

Rows are ordered by property reference.

For each contract `preparar_revisiones_renta()` exposes:

```text
contrato
ultima_revision
proxima_revision
situacion_proxima
ultima_revision_reabrible
```

`ultima_revision` is the most recent resolved revision:

```text
APLICADA
or
NO_APLICADA
```

`proxima_revision` is the earliest pending revision.

The dashboard situation for the next pending revision is display-oriented and can be:

```text
ESPERANDO_INDICE
AVISO
RESOLVER
PENDIENTE
```

Important distinction:

```text
monthly billing
    → actual percentage resolution

revisions dashboard
    → overview
    → No aplicar este año
    → Corregir revisión when safe
```

Do not reintroduce `Resolver revisión` as a dashboard action. Resolution belongs to the billing month where its economic effect is being prepared.

The dashboard uses a single Jinja macro for Locales/Otros tables.

Its action column uses the same compact `<details>` / `⋮` menu pattern as invoice actions.

The menu closes when another menu opens or when the user clicks outside.

The active row remains visually highlighted while its action menu is open.

## Billing: No aplicar este año

A pending revision can be deliberately skipped for the current year from the revisions dashboard.

Action:

```text
No aplicar este año
```

The route calls `resolver_revision_renta()` with:

```text
aplicar = False
porcentaje_aplicado = None
```

Result:

```text
current revision
    → NO_APLICADA
    → fecha_resolucion = today
    → no new RentaContrato

next yearly revision
    → PENDIENTE
    → same method
```

Any still-pending next revision shown in the panel may be marked as not applied; the action is not restricted to a particular display cycle.

Already resolved revisions are rejected.

## Billing: correcting an applied rent revision

User-facing action:

```text
Corregir revisión
```

Internal concept:

```text
reabrir revisión
```

This is not an in-place edit of `porcentaje_aplicado`.

The purpose is to undo a mistaken revision resolution while all later effects are still reversible, then reuse the normal `Resolver revisión` workflow.

Typical real scenario:

```text
revision due in April
April invoice
    → old rent
    → ESPERANDO_INDICE

May
    → resolve April revision
    → May invoice uses revised rent
    + April arrears

wrong percentage discovered
    ↓
Eliminar May invoice
    ↓
Corregir revisión
    ↓
April revision returns to PENDIENTE
    ↓
prepare May again
    ↓
Resolver revisión with correct percentage
    ↓
reissue May invoice correctly
```

### Preparation/validation

`facturacion.services.preparar_reapertura_revision()` is the central validator.

It returns:

```python
@dataclass(frozen=True)
class ReaperturaRevision:
    revision: RevisionRenta
    renta: RentaContrato
    siguiente_revision: RevisionRenta
```

The function does not mutate database state.

A revision is re-openable only when:

```text
revision.estado == APLICADA
```

and all required generated objects still exist in the expected state.

Specifically:

1. the generated `RentaContrato` exists at:

```text
renta.fecha_desde == revision.fecha_prevista
```

2. the automatically created next annual revision exists at:

```text
revision.fecha_prevista with year + 1
```

3. that next revision is still:

```text
PENDIENTE
```

4. no invoice exists for the same contract in the application month or later;

5. no rental accounting entry exists for the same contract in the application month or later.

The application month is the month immediately after `revision.fecha_prevista`.

Example:

```text
revision.fecha_prevista = 2026-04-01
periodo_aplicacion      = 2026-05-01
```

Therefore:

```text
April invoice
    → allowed to remain

May invoice or later
    → blocks reopening
```

### Identifying later accounting effects

`ApunteContable` has no `contrato_id`.

Therefore accounting effects are identified through:

```text
Contrato.movimientos_previstos
    → MovimientoPrevisto.apunte
```

A movement blocks reopening when its linked entry satisfies:

```text
apunte exists
apunte.naturaleza == INGRESO
apunte.categoria == ING_ALQUILERES
apunte.periodo_desde is not None
apunte.periodo_desde >= periodo_aplicacion
```

Do not inspect `MovimientoPrevisto.estado` for this decision.

If the accounting effect exists, reopening is blocked regardless of whether the movement is:

```text
PENDIENTE
CANCELADO
PARCIAL
CONCILIADO
```

`Corregir revisión` does not undo accounting records.

The appropriate invoice/accounting undo workflow must be used first.

### Mutation

After validation, `reabrir_revision_renta()` restores the revision itself:

```text
estado = PENDIENTE
porcentaje_aplicado = None
fecha_resolucion = None
```

The route owns the transaction and deletes:

```text
generated RentaContrato
automatically generated next RevisionRenta
```

The operation is atomic.

The POST route is:

```text
/facturacion/revisiones/<revision_id>/reabrir
```

After reopening, normal monthly preparation is reused. No special "edit percentage" path exists.

### Dashboard availability

`RevisionContratoPreparada.ultima_revision_reabrible` exposes the decision to the UI.

The dashboard does not duplicate the rules.

Conceptually:

```text
if ultima_revision is APLICADA:
    try preparar_reapertura_revision()
        → reabrible = True
    FacturacionError
        → reabrible = False
```

The menu displays **Corregir revisión** only when this value is true.

## Billing: final accounting

The definitive action from Preview is:

```text
Contabilizar
```

The accounting POST parses the exact `FacturaEditada` represented by the preview.

It verifies that its recalculated amounts match the previsualized amounts before persistence.

`emitir_factura()` then prepares:

```text
Factura
FacturaLinea(s)
FacturaDestinatario(s)
ApunteContable
MovimientoPrevisto
```

The POST route owns the transaction and persists all of them atomically.

When `FacturaEditada` is supplied, `crear_factura()` persists its lines rather than reconstructing a single rent line from the contract.

This is important for invoices containing revision arrears or manually edited extra lines.

Generated accounting data:

```text
naturaleza = INGRESO
categoria = ING_ALQUILERES
periodo_desde = first day of invoice month
periodo_hasta = last day of invoice month
referencia_documento = numero_factura
base / IVA / retención / total = invoice values
```

The expected movement:

```text
importe_esperado = factura.total
fecha_prevista_desde = first day of month
fecha_prevista_hasta = last day of month
```

The deliberately broad expected interval avoids making reconciliation harder when a tenant pays late.

After persistence the route redirects to the same monthly preparation and the row becomes `Emitida`.

## Billing: deleting an emitted invoice

`Eliminar` is implemented for genuinely reversible invoice mistakes.

Semantics:

```text
Eliminar
    → invoice disappears completely
    → invoice number becomes reusable
```

This is intentionally different from future:

```text
Anular
    → invoice remains historical
    → number remains consumed
```

and:

```text
Rectificar
    → original remains
    → rectifying invoice is created
```

### Validation

`preparar_eliminacion_factura()` validates the operation and returns the objects that the route must remove.

An invoice can be deleted only when:

```text
estado == EMITIDA
```

and it is the last invoice number for that property/year.

The accounting entry is normally required.

A limited exception exists for historical bootstrap invoices that predate the current accounting linkage.

At most one expected movement may be associated with the invoice accounting entry.

If present, the movement may only be:

```text
PENDIENTE
CANCELADO
```

Deletion is rejected for:

```text
PARCIAL
CONCILIADO
```

### Atomic deletion

The route deletes, as applicable:

```text
MovimientoPrevisto
FacturaLinea(s)
FacturaDestinatario(s)
Factura
ApunteContable
```

and flushes as needed before deleting the accounting entry.

The whole operation is performed inside one transaction.

After deletion, the number can be predicted and reused by normal invoice preparation.

This operation is an important prerequisite for `Corregir revisión` when an affected invoice has already been emitted.

## Billing: FacturaLinea.type technical debt

`FacturaLinea` currently has a constrained `tipo` field:

```text
RENTA
DIFERENCIA_REVISION
REPERCUSION_GASTO
OTRO
```

This classification currently provides little useful behavior.

It is especially questionable now that prepared invoice lines can be edited transiently before persistence: `crear_factura()` may classify edited lines according to position rather than preserving the semantic origin of every prepared line.

Do not refactor this immediately.

Removing or simplifying `FacturaLinea.tipo` requires a database migration, and there is no current operational reason to prioritize that change.

Likely direction:

```text
verify whether any real behavior depends on FacturaLinea.tipo
    ↓
if not
    → remove field and CheckConstraint
    → create Alembic migration
    → simplify creation code/tests
```

Only undertake this when real use justifies the cleanup.

## Billing: non-invoice rents

Contracts with `genera_factura=False` appear under `Otros`.

The row contains:

```text
Inmueble
Destinatario
Importe
Estado/Acción
```

Only holder names are displayed as recipient information; NIF/address would add noise to this control list.

Each row is confirmed individually.

Action:

```text
Contabilizar
```

After registration:

```text
Contabilizado
```

`contabilizar_ingreso_sin_factura()` prepares:

```text
ApunteContable
MovimientoPrevisto
```

with:

```text
naturaleza = INGRESO
categoria = ING_ALQUILERES
base = total = applicable rent
IVA = 0
retención = 0
period = whole month
expected collection interval = whole month
referencia_documento = ""
```

Holder names and NIFs are preserved in the accounting entry even though only names are shown in the monthly UI.

The route persists both records atomically.

Contractual `CARENCIA` annexes are deliberately not applied to this path yet.

If a real non-invoice contract later requires a grace period, both monthly preparation and `contabilizar_ingreso_sin_factura()` must be reviewed so the domain rule cannot be bypassed by calling the accounting service directly.

### Recognizing an already-accounted non-invoice rent

`ApunteContable` has no `contrato_id`; `MovimientoPrevisto` does.

Therefore monthly preparation recognizes an already-accounted rent through `Contrato.movimientos_previstos` and its linked accounting entry.

Identity is:

```text
same contract
linked apunte exists
apunte.naturaleza == INGRESO
apunte.categoria == ING_ALQUILERES
apunte.periodo_desde == first day of requested month
apunte.periodo_hasta == last day of requested month
```

Do not use these fields as identity:

```text
amount
concept
movement state
expected collection dates
```

Amount may later be corrected legitimately. Reconciliation state answers a different question. Expected dates describe payment timing rather than accounting period.

The service also rejects a second accounting operation for the same contract/period.

The same movement-to-entry traversal is reused when deciding whether a rent revision can be reopened.

## Billing: intentionally postponed scope

The ordinary billing workflow and the currently required reversible correction workflows are complete.

Do not implement the following merely because the model could support them:

* persistent editable draft invoices;
* a separate ordinary single-invoice preparation subsystem;
* extraordinary invoice workflow;
* invoice annulment workflow;
* replacement after annulment;
* rectifying invoices;
* generalized rent-revision workflows for hypothetical contracts;
* generic expense repercussion before a real use case requires it;
* contractual grace periods for `Otros` before a real non-invoice contract requires them.

Transient editing already handles simple exceptional invoice lines without creating persistent drafts.

`Eliminar factura` and `Corregir revisión` solve errors that can still be completely undone.

Do not stretch them to solve cases requiring historical rectification.

## Billing: pending work

The following items are known but are not current blockers.

### Expense repercussion

Integrate real repercutible expenses with invoice preparation when the first concrete cases appear.

Keep the distinction:

```text
distribuir = analytical allocation
repercutir = charge to tenant
```

Reuse accounting data rather than entering the same economic fact again.

### Annulment and rectification

`Eliminar` is implemented only for fully reversible mistakes.

Future operations need different semantics.

#### Anular

Expected semantics:

```text
original invoice remains historical
invoice number remains consumed
state becomes ANULADA
```

Its exact accounting and reconciliation effects still need to be designed.

#### Rectificar

Expected semantics:

```text
original invoice remains
rectifying invoice is created
relationship between both is preserved
```

This is also the likely path for correcting a rent revision after later accounting/invoice effects can no longer be safely removed.

Design these flows explicitly when required.

Do not relax `Eliminar factura` or `Corregir revisión` as shortcuts.

### More complex rent revisions

The current revision workflow covers the known real cases:

```text
AVISO
ESPERANDO_INDICE
PENDIENTE
APLICADA
NO_APLICADA
Corregir revisión while reversible
```

Only generalize it if a contract requires different timing, index handling or arrears behavior.

### Revision indices

Current index descriptions include the methods required now, including IRAV.

Add further index/territorial behavior only when real contracts require it.

### Extraordinary lines

Transient Modify already permits additional lines.

Do not create a separate persistent draft/extra-line subsystem without a real operational requirement.

### Invoice document improvements

The current HTML template and printing workflow are sufficient.

Further layout, format or document-generation work should be driven by real use.

## Current stopping point

The ordinary billing workflow, the first required correction workflows and contractual invoice grace periods are complete for the currently known real cases.

Implemented and tested end-to-end:

```text
monthly preparation
    ↓
facturable contract
    → initial billing grace?
       → visible Locales row
       → no invoice
       → next billable month shown
    → CARENCIA annex active?
       → visible Locales row
       → no invoice
       → next billable month shown
    → otherwise
       → prepared definitive invoice lines
       → automatic notes
       → revision state/effects when applicable
       → Preview directly
          or
         Modify → Preview
       → printable invoice
       → Contabilizar
       → validate previewed totals
       → Factura
       + FacturaLinea(s)
       + FacturaDestinatario(s)
       + ApunteContable
       + MovimientoPrevisto
       → return to same month
       → Emitida
```

Contractual grace-period support currently covers:

```text
AnexoContrato.tipo = CARENCIA
fecha_desde = first day of first grace month
fecha_hasta = last day of last grace month
non-overlapping periods
multiple separated grace periods allowed

contract annex UI
    → create CARENCIA annex
    → validate domain rules
    → persist
    → show in annex history

monthly invoice preparation
    → detect active CARENCIA
    → skip rent/invoice preparation
    → keep contract visible
    → show first month after carencia as next billable period
```

Example:

```text
CARENCIA 01/11/2026 → 31/01/2027

10/2026 → invoice
11/2026 → no invoice
12/2026 → no invoice
01/2027 → no invoice
02/2027 → invoice
```

This behavior currently applies only to `genera_factura=True`.

`Otros` remains deliberately unchanged.

Revision workflow currently covers:

```text
month before revision
    → AVISO
    → automatic notice

scheduled revision month while index unavailable
    → ESPERANDO_INDICE
    → old rent
    → automatic explanation

following month with unresolved revision
    → PENDIENTE
    → Resolver revisión

apply revision
    → new RentaContrato
    → RevisionRenta = APLICADA
    → next annual RevisionRenta = PENDIENTE

applicable following invoice
    → APLICADA
    → revised monthly rent
    + arrears for scheduled revision month
    + automatic revision notes

choose not to apply
    → NO_APLICADA
    → no new rent
    → next annual RevisionRenta = PENDIENTE
```

The dedicated revisions dashboard provides:

```text
Locales / Otros
last resolved revision
next pending revision
display situation
action menu
```

Available actions include:

```text
No aplicar este año
Corregir revisión
```

The `APLICADA` state and arrears are period-specific and do not continue into later ordinary invoices.

The non-invoice path remains:

```text
monthly preparation
    ↓
non-invoice contract
    → review rent
    → Contabilizar
    → ApunteContable + MovimientoPrevisto
    → return to same month
    → Contabilizado
```

Reversible invoice correction is implemented:

```text
wrong emitted invoice
    ↓
Eliminar factura
    ↓
remove invoice + accounting + expected movement atomically
    ↓
reuse invoice number
    ↓
prepare and emit correctly again
```

Reversible revision correction is implemented:

```text
wrong applied percentage
    ↓
remove affected invoice/accounting first if present
    ↓
Corregir revisión
    ↓
RevisionRenta → PENDIENTE
delete generated RentaContrato
delete next annual RevisionRenta
    ↓
prepare affected month again
    ↓
Resolver revisión with correct percentage
    ↓
emit/account again
```

The reopening validator defensively rejects corrections when:

```text
revision is not APLICADA
generated rent is missing
next annual revision is missing
next annual revision is already resolved
affected/later invoice exists
affected/later rental accounting entry exists
```

The full pytest suite is green.

Manual browser testing has covered the relevant billing paths, including:

```text
ordinary preview
Modify
Preview after Modify
initial billing grace
CARENCIA annex creation
CARENCIA annex history
CARENCIA monthly preparation
resuming billing after CARENCIA
AVISO
ESPERANDO_INDICE
PENDIENTE resolution
APLICADA
NO_APLICADA
revised rent
arrears line
automatic notes
final accounting with multiple lines
invoice deletion
reusable invoice numbering
revisions dashboard
action menu behavior
Corregir revisión
re-resolving with a corrected index
reissuing the affected invoice
```

The latest completed functional block is:

```text
Incorporar carencias contractuales en la facturación
```

It includes:

```text
database migration
AnexoContrato CARENCIA type
fecha_desde / fecha_hasta
creation service and validation
web form and route
annex selection/history UI
carencia_vigente()
monthly invoice-preparation integration
visible grace-period row
resume ordinary billing after the grace period
```

The implementation deliberately treats carencia as absence of an ordinary invoice rather than as a zero rent or temporary rent adjustment.

## Next change

Do not start another speculative billing refactor merely because the current block is complete.

The immediate priority remains real operational use.

Use the current system and prioritize problems that actually appear during:

```text
invoice preparation
invoice review and printing
accounting
bank import
reconciliation
rent-revision handling
contract-annex handling
```

Known later areas include:

1. expense repercussion and analytical allocation, especially grouped property expenses;
2. accounting completeness/integrity controls;
3. fiscal/accounting reports needed for year-end and January;
4. invoice annulment and rectification when first required;
5. rent-revision generalization only if another real contract needs it;
6. invoice document/layout improvements if real use shows a need;
7. extending grace-period handling to `Otros` only if a real non-invoice contract requires it.

For billing corrections, preserve the current principle:

```text
fully reversible
    → undo and perform again

historical effects must remain
    → explicit annulment / rectification workflow
```

Prefer fixing real operational friction over adding anticipated functionality.
