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

The user is an experienced C++ developer but knows little Python/Flask.

Instructions should therefore be precise and concrete. Identify exact files, functions and changes instead of asking the user to search the repository.

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

Automated pytest/integration tests are preferred over time-consuming artificial browser setup.

Manual end-to-end tests are most valuable with real client data or when a UI interaction is being finalized.

When providing a complete replacement for a function or file, provide genuinely complete code. Never use placeholders such as:

```text
# ...
```

inside code the user is expected to paste.

Before relying on a function signature, inspect the current implementation.

When a test receives a pytest fixture as a parameter, its dependencies should also be expressed as fixture parameters rather than referring directly to decorated fixture functions.

Shared fixtures should remain minimal. Prefer local setup in focused tests when enriching a shared fixture could alter assumptions elsewhere.

At commit time:

* do not explain Git commands;
* propose only one or more commit messages;
* use Spanish infinitive phrases.

Documentation is a state/handoff mechanism, not a changelog.

Update it after meaningful functional blocks or before a significant pause.

## Product context

Contab is a small personal application for managing the economic activity of fewer than ten rented properties.

Its two primary goals are:

1. **Bank reconciliation**: reduce the work required to identify and reconcile real bank movements with expected income and expenses.
2. **Flexible accounting/reporting**: record economic facts once and retain enough stable detail to regroup them later for changing fiscal and reporting requirements.

Billing, contracts and other modules are auxiliary to these goals.

The application entered real parallel use with the existing manual accounting process in October 2026.

The purpose of the parallel period is to discover operational problems from real data before adding further complexity.

Prefer real client value over feature count.

## Permanent design principles

### Keep the application small

Prefer direct code, explicit services, simple Flask routes, understandable models and deterministic rules.

Avoid abstractions, screens and workflows for hypothetical cases.

A forward-looking database field is acceptable when the future need is stable, obvious and cheap to prepare.

Operational functionality should wait for a real requirement.

### User control

Automation assists the user but does not make doubtful decisions on their behalf.

In reconciliation:

```text
Contab proposes
User reviews
User confirms
```

The same principle applies to billing, reimbursement and corrections.

Contab may determine whether an operation is valid, but the user decides whether to perform it.

Exceptional cases must remain manually resolvable.

### Enter data once

A real economic fact should be entered once and then reused for:

```text
accounting
reconciliation
reporting
billing
reimbursement
```

where appropriate.

Do not require re-entering an expense merely because it later participates in another process.

### Preserve source evidence

Do not destroy information needed for later verification.

Examples:

* bank movements retain original bank text;
* accounting entries retain document references;
* emitted invoices preserve historical invoice data;
* distributions preserve the property shares used at the time;
* contract imputations preserve the accounting components attributed at the time;
* physical invoices and supporting documents remain in the filesystem.

### Preserve historical decisions

Once a derived accounting decision has been persisted, future configuration changes must not silently recalculate history.

Important examples:

```text
DistribucionApunte
    → preserves spatial allocation

ImputacionContrato
    → preserves temporal/contract allocation

Factura
    → preserves emitted invoice data
```

Reports must use those persisted decisions instead of reconstructing them from current property shares or current contracts.

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

expense reimbursement request
    → ImputacionContrato(s)
    + SolicitudReembolso
    + SolicitudReembolsoLinea(s)
    + MovimientoPrevisto INGRESO

expense reimbursement undo
    → delete MovimientoPrevisto
    + SolicitudReembolsoLinea(s)
    + ImputacionContrato(s)
    + SolicitudReembolso
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
Deshacer solicitud de reembolso
```

When effects can no longer be safely removed, do not weaken validation rules.

A future explicit compensating or rectifying workflow must handle the case.

### Tests are intentional complexity

Protect:

* domain rules;
* complete form flows;
* error handling;
* multi-record operations;
* migrations;
* historical persistence rules;
* important module boundaries.

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

Use SQLAlchemy:

```python
select()
```

not legacy:

```python
Session.query()
```

Money is stored as integer cents.

Nature determines direction:

```text
INGRESO
GASTO
```

Percentage values requiring two decimal places use hundredths of a percentage point.

For SQLite constraint changes, Alembic `batch_alter_table` is normally required.

Back up real databases before schema migrations.

## Multiple databases and banks

Each logical database represents one accounting context and corresponds to one bank account for reconciliation.

Currently supported bank importers:

```text
IBERCAJA
CAIXABANK
```

`config.py` validates that every logical database has one supported bank.

Application-context helpers resolve the selected database and bank.

## Implemented property and contract scope

Implemented:

* properties and rentable units;
* subdivided type-`T` parent properties;
* tenants;
* contracts with multiple ordered holders;
* rents;
* rent revisions;
* contract annexes;
* extensions;
* rent changes;
* contractual grace periods.

### Contract annexes

`AnexoContrato` represents a formal contractual modification.

Current types:

```text
PRORROGA
CAMBIO_RENTA
CARENCIA
```

A `CARENCIA` stores:

```text
fecha_desde
fecha_hasta
```

Database and domain validation ensure:

```text
CARENCIA
    → fecha_desde and fecha_hasta required

other annex types
    → fecha_desde and fecha_hasta absent

fecha_hasta >= fecha_desde

CARENCIA dates use whole months

CARENCIA periods for the same contract do not overlap
```

Multiple separated grace periods are allowed.

The helper:

```text
carencia_vigente(contrato, periodo)
```

returns the applicable annex or `None`.

A contractual grace period is deliberately not represented as:

```text
RentaContrato = 0
```

or as an `AjusteRenta`.

Its meaning is that no ordinary invoice should be prepared during the covered period.

## Accounting scope

Implemented:

* accounting categories/subcategories from `contab.ini`;
* accounting-entry CRUD and validation;
* accounting periods;
* accounting treatments;
* document metadata;
* optional expected movements for manual entries;
* type-`T` spatial distribution;
* contract temporal attribution;
* reimbursement workflow for `REPERCUTIR`;
* accounting CSV reports;
* annual VAT summary;
* report integration of persistent distributions and imputations.

Important treatments:

```text
CONTABILIZAR
REPERCUTIR
FACTURAR
```

Their accounting meaning is:

```text
CONTABILIZAR
    → full income/expense belongs to the owner

REPERCUTIR
    → part attributed to a tenant is excluded from owner's expense
    → tenant reimbursement is not fiscal income
    → any residual not attributed to contracts remains owner's expense

FACTURAR
    → original expense remains fully owner's expense
    → later invoice creates ordinary accounting income separately
```

Do not confuse:

```text
distribuir
```

with:

```text
repercutir
```

Terminology:

```text
distribuir
    = spatial allocation of a type-T expense among child properties

imputar
    = temporal attribution of an expense/distribution to contracts

repercutir
    = request reimbursement from the tenant

facturar
    = later include an expense in an invoice while preserving the original expense
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

`MovimientoPrevisto.apunte_id` remains nullable because independent expected movements are allowed.

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

For linked movements in:

```text
PENDIENTE
CANCELADO
```

the movement itself imposes no additional edit restriction.

For linked movements in:

```text
CONCILIADO
PARCIAL
```

protect changes to:

```text
inmueble
naturaleza
total
```

The amount protection compares accounting total, not only its internal composition.

Deleting an accounting entry is likewise forbidden if any linked expected movement is:

```text
CONCILIADO
PARCIAL
```

## Type-T expense distribution

An `Inmueble` of type `T` represents a common property container whose expenses belong analytically to its child properties.

A common expense is entered once on the `T`.

Creation generates persistent:

```text
DistribucionApunte
```

records for the child properties.

Each distribution stores:

```text
participacion
base
iva_importe
retencion_importe
total
```

The components are distributed independently and the final total is:

```text
total = base + iva_importe - retencion_importe
```

The persisted values are historical.

If property participation percentages change later, previous accounting reports must continue using the stored distribution.

A type-`T` container is not accounting output by itself.

Reports show its expenses through the corresponding child properties.

## Contract imputations

`ImputacionContrato` represents the portion of an expense attributed to one contract.

It may originate from exactly one of:

```text
ApunteContable
```

or:

```text
DistribucionApunte
```

For normal properties:

```text
ApunteContable
    ↓
ImputacionContrato
```

For type-`T` properties:

```text
ApunteContable
    ↓
DistribucionApunte
    ↓
ImputacionContrato
```

The model persists:

```text
base
iva_importe
retencion_importe
importe
```

with:

```text
importe = base + iva_importe - retencion_importe
```

Do not reconstruct those components later from only the total.

Accounting components are allocated independently to contracts so rounding remains coherent.

Temporal attribution uses:

```text
fecha
periodo_desde
periodo_hasta
criterio_periodo
contract dates
```

Possible period criteria are:

```text
EXCLUIR_HASTA
EXCLUIR_DESDE
INCLUIR_AMBOS
EXCLUIR_AMBOS
```

Days not covered by any applicable contract remain attributable to the owner.

Historical report calculations use persisted imputations.

## Protecting persisted imputations

A persisted `ImputacionContrato` represents a historical allocation decision and must not silently become inconsistent with its source entry.

If an entry has persisted contract imputations, directly or through one of its distributions, modifications are rejected when they change:

```text
inmueble
fecha
base
iva_importe
retencion_importe
periodo_desde
periodo_hasta
criterio_periodo
tratamiento
```

This protection applies both to:

```text
ApunteContable.imputaciones_contrato
```

and:

```text
DistribucionApunte.imputaciones_contrato
```

Descriptive changes that do not alter the historical allocation remain allowed.

For example:

```text
notas
```

may still be corrected.

An accounting entry with persisted imputations cannot be deleted.

The downstream operation that created those imputations must first be undone when still reversible.

This follows the general rule:

```text
historical derived effect exists
    → protect source fields

fully reversible downstream operation
    → undo downstream operation first
    → correct source
    → perform operation again
```

## Expense reimbursement workflow

`REPERCUTIR` is implemented as a reimbursement workflow independent from ordinary invoice emission.

Pending expenses are calculated for a contract from accounting data and current unprocessed allocation candidates.

The user flow is:

```text
pending repercutible expenses
    ↓
select expenses
    ↓
review temporary calculation
    ↓
communicate externally
    ↓
Marcar como enviado
```

Confirmation persists atomically:

```text
ImputacionContrato(s)
SolicitudReembolso
SolicitudReembolsoLinea(s)
MovimientoPrevisto INGRESO
```

`SolicitudReembolsoLinea` preserves which accounting origin was included in the request.

That origin is either:

```text
ApunteContable
```

or:

```text
DistribucionApunte
```

The expected movement represents the tenant reimbursement.

The original supplier payment remains a separate accounting/banking fact.

### Reimbursement request states

The request itself derives its useful operational state from its associated expected movement.

Current relevant states:

```text
PENDIENTE
PARCIAL
CONCILIADO
CANCELADO
```

The reimbursement listing shows active requests.

Deletion/undo rules:

```text
PENDIENTE
    → may be undone

CANCELADO
    → may be undone

PARCIAL
    → cannot be undone

CONCILIADO
    → cannot be undone
```

Undo removes atomically:

```text
MovimientoPrevisto
SolicitudReembolsoLinea(s)
ImputacionContrato(s)
SolicitudReembolso
```

Afterward, the original expense becomes pending for reimbursement again.

Do not add a generic independent editor for reimbursement lines or imputations.

The current lifecycle deliberately keeps those records tied to the reimbursement operation that created them.

## Accounting reports

Current implemented reports include:

```text
annual CSV per property
ZIP containing one CSV per applicable property
IVA annual summary
```

Reports consider:

```text
CONTABILIZAR
FACTURAR
REPERCUTIR
```

Accounting semantics:

```text
CONTABILIZAR
    → full owner's amount

FACTURAR
    → full original expense remains owner's expense

REPERCUTIR
    → owner amount = source base - persisted contract-attributed base
```

For type-`T` entries:

```text
ApunteContable
    ↓
DistribucionApunte for requested child property
    ↓
optional ImputacionContrato residual calculation
```

Reports do not show the type-`T` container as separate accounting.

They show the child properties.

When `REPERCUTIR` is only partially attributed to contracts, the residual remains expense of the owner.

When fully attributed, owner expense may be zero.

Reports use persisted:

```text
DistribucionApunte
ImputacionContrato
```

rather than recomputing historical allocation from current configuration.

The IVA-oriented CSV continues to show:

```text
income base
expense base
IVA on income
retention on income
```

It deliberately does not move supported expense IVA into the existing control sheet because the report reproduces the user's established workflow.

## Selecting properties for reports

Applicable properties for annual export are selected using the following rules:

```text
active non-T property
    → included

inactive non-T property with applicable entries in year
    → included

type-T property
    → never included as its own accounting output

type-T entry
    → child properties from its persisted DistribucionApunte records are applicable
```

Applicable treatments are:

```text
CONTABILIZAR
FACTURAR
REPERCUTIR
```

This also ensures that historical activity from an inactive child property can still appear for the relevant year.

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

Each exact-amount proposal has an **Aceptar** button.

Pressing it immediately confirms only the selected bank/expected movement pair.

There is no bulk confirmation and no temporary proposal rejection mechanism.

Unaccepted proposals simply remain pending.

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

A successful acceptance creates a persistent `Conciliacion`, marks both movements reconciled and sets the expected movement method to:

```text
INDIVIDUAL
```

The user is redirected to the review screen, where proposals are recalculated.

### Discarding bank movements during review

The **Pendientes** section offers a **Descartar** button for each bank movement.

It reuses:

```text
POST /conciliacion/movimientos/<movimiento_id>/descartar
```

The review form includes:

```text
origen = revision
```

so the endpoint returns to the review screen.

Discarding is immediate and changes the bank movement to:

```text
DESCARTADO
```

Discarded movements no longer appear in review because that screen queries only pending movements.

They remain accessible and reversible from the bank-movement listing.

## Manual reconciliation

An expected movement can be reconciled manually when the real situation is not represented by normal bank 1:1 correspondence.

Manual reconciliation requires nonblank notes explaining the resolution.

It sets:

```text
estado = CONCILIADO
metodo_conciliacion = MANUAL
```

Manual reconciliation is reversible.

Normal `INDIVIDUAL` reconciliation cannot be undone through the manual-reversal action because it also involves a bank movement and persistent reconciliation relation.

Do not implement general 1:n, n:1 or partial reconciliation until real use shows that the current individual/manual combination is insufficient.

## Billing: current operational scope

Billing contains the ordinary workflow required for current real use together with the reversible correction workflows already needed operationally.

The monthly screen is:

```text
/facturacion/
```

It receives:

```text
periodo
fecha_emision
```

The screen has:

```text
Locales
Otros
```

Preparation is transient.

Do not create `Factura` objects merely to display monthly preparation.

A `Factura` is persisted only when the user confirms final accounting.

A separate revision overview exists at:

```text
/facturacion/revisiones
```

## Billing: contract selection and grace periods

A contract is included when active at any point in the month:

```text
fecha_inicio <= last day of month
and
fecha_fin is None or fecha_fin >= first day of month
```

For rent lookup:

```python
fecha_renta = max(periodo, contrato.fecha_inicio)
```

For `genera_factura=True`, ordinary invoice preparation is skipped before:

```text
fecha_inicio_facturacion
```

The contract remains visible as being in grace period.

After that check, invoice preparation evaluates:

```text
carencia_vigente(contrato, periodo)
```

If a contractual `CARENCIA` applies, the contract also remains visible but no invoice is prepared.

The order is:

```text
contract active in month?
    ↓
initial billing grace?
    ↓
contractual CARENCIA?
    ↓
rent revision
    ↓
rent
    ↓
ordinary invoice preparation
```

Do not move rent calculation before grace-period checks.

The non-invoice `Otros` path deliberately has not generalized contractual grace-period handling.

Only extend it if a real non-invoice contract requires it.

## Billing: grace-period presentation

Initial billing grace and `CARENCIA` annexes use:

```text
LocalEnCarenciaPreparado
```

The monthly Locales table keeps the contract visible and shows:

```text
En carencia. Próximo mes a facturar mm/aaaa
```

No Preview, Modify or accounting action is offered.

For initial grace:

```text
proximo_periodo_facturacion
    = contrato.fecha_inicio_facturacion
```

For contractual `CARENCIA`:

```text
proximo_periodo_facturacion
    = first day of month after anexo.fecha_hasta
```

## Billing: rent revisions

Current revision workflow covers:

```text
AVISO
ESPERANDO_INDICE
PENDIENTE
APLICADA
NO_APLICADA
```

Typical sequence:

```text
month before revision
    → AVISO

scheduled month while index unavailable
    → ESPERANDO_INDICE
    → old rent

following month with unresolved revision
    → PENDIENTE
    → Resolver revisión
```

Applying a revision creates:

```text
new RentaContrato
RevisionRenta = APLICADA
next annual RevisionRenta = PENDIENTE
```

The first applicable later invoice may contain:

```text
revised rent
+ arrears for scheduled revision month
```

Choosing:

```text
No aplicar este año
```

sets:

```text
current revision = NO_APLICADA
next annual revision = PENDIENTE
```

No new rent is created.

The dedicated revisions dashboard shows:

```text
Locales / Otros
last resolved revision
next pending revision
display situation
actions
```

Available actions include:

```text
No aplicar este año
Corregir revisión
```

## Billing: correcting an applied rent revision

User-facing action:

```text
Corregir revisión
```

Internal concept:

```text
reabrir revisión
```

This is not an in-place edit of the applied percentage.

The purpose is to undo a mistaken revision while all downstream effects remain reversible and then reuse the normal resolution workflow.

Typical sequence:

```text
wrong applied percentage
    ↓
delete affected invoice/accounting first
    ↓
Corregir revisión
    ↓
RevisionRenta → PENDIENTE
delete generated RentaContrato
delete automatically generated next RevisionRenta
    ↓
prepare affected month again
    ↓
resolve with correct value
    ↓
emit again
```

`preparar_reapertura_revision()` is the central validator.

A revision is reopenable only when:

```text
estado == APLICADA
generated RentaContrato exists
next annual RevisionRenta exists
next annual revision is still PENDIENTE
no affected/later invoice exists
no affected/later rental accounting entry exists
```

The route owns the transaction and performs the deletion of generated objects.

Do not create a special edit-percentage path.

## Billing: final accounting

The definitive action from Preview is:

```text
Contabilizar
```

The POST parses the exact transient edited invoice represented by Preview and verifies the recalculated values.

`emitir_factura()` prepares:

```text
Factura
FacturaLinea(s)
FacturaDestinatario(s)
ApunteContable
MovimientoPrevisto
```

The route persists all records atomically.

Generated accounting data uses:

```text
naturaleza = INGRESO
categoria = ING_ALQUILERES
period = invoice month
base / IVA / retención / total = invoice values
referencia_documento = numero_factura
```

The expected collection interval covers the invoice month deliberately.

After persistence, the monthly row becomes:

```text
Emitida
```

## Billing: deleting an emitted invoice

`Eliminar` is intended for genuinely reversible invoice mistakes.

Semantics:

```text
Eliminar
    → invoice disappears completely
    → invoice number becomes reusable
```

This differs deliberately from future:

```text
Anular
Rectificar
```

An invoice may be deleted only when domain validation confirms that downstream effects remain reversible.

The route removes atomically, as applicable:

```text
MovimientoPrevisto
FacturaLinea(s)
FacturaDestinatario(s)
Factura
ApunteContable
```

Expected movements in:

```text
PARCIAL
CONCILIADO
```

block deletion.

Do not weaken this operation to solve historical rectification.

## Billing: non-invoice rents

Contracts with:

```text
genera_factura=False
```

appear under:

```text
Otros
```

The user confirms each row individually with:

```text
Contabilizar
```

The result is:

```text
ApunteContable
MovimientoPrevisto
```

with no emitted invoice.

Already-accounted monthly rents are recognized through the contract's expected movements and linked accounting entries.

Do not use amount or reconciliation state as period identity.

## Billing: FacturaLinea.tipo technical debt

`FacturaLinea.tipo` currently supports:

```text
RENTA
DIFERENCIA_REVISION
REPERCUSION_GASTO
OTRO
```

Its practical value is limited.

Do not refactor it merely for cleanliness.

Removing it would require a migration and should wait for a real operational reason.

## Billing: expense billing

`REPERCUTIR` is now implemented as an independent reimbursement workflow.

Do not route `REPERCUTIR` through ordinary invoice preparation.

`FACTURAR` remains the treatment intended for an expense that:

```text
remains fully owner's expense
+
may later be added to a tenant invoice
```

Integration of real `FACTURAR` expenses with invoice preparation is still pending and should be implemented only when a concrete real case requires it.

When that happens, reuse:

```text
ApunteContable
DistribucionApunte
ImputacionContrato
```

as appropriate.

Do not enter the economic fact again.

## Billing: intentionally postponed scope

Do not implement merely because the model could support it:

* persistent editable draft invoices;
* separate ordinary single-invoice preparation subsystem;
* generalized extraordinary invoice workflow;
* invoice annulment workflow;
* replacement after annulment;
* rectifying invoices;
* generalized rent-revision behavior for hypothetical contracts;
* `FACTURAR` expense integration before a real case requires it;
* contractual grace periods for `Otros` before a real contract requires them.

Transient editing already handles simple exceptional invoice lines.

`Eliminar factura`, `Corregir revisión` and reimbursement undo solve cases that are still fully reversible.

Do not stretch them to cases requiring preserved historical effects.

## Known later work

The following items are known but are not current blockers.

### Accounting integrity controls

Continue adding controls only where real use exposes ambiguity or risk.

Likely areas include:

```text
missing expected recurring entries
period gaps
period overlaps
probable duplicates without strong document identity
year-end completeness checks
```

Avoid building a generic audit subsystem prematurely.

### Fiscal reports

Current IVA-oriented reports are implemented.

Future annual reports should be driven by actual IRPF/IRNR preparation requirements.

Preserve detailed accounting data so new groupings can be produced without changing historical entries.

### FACTURAR integration

When a real case appears, integrate eligible accounting expenses with invoice preparation.

Preserve the distinction:

```text
FACTURAR
    → original expense remains owner's expense
    → invoice later creates normal income
```

Do not reuse `REPERCUTIR` semantics.

### Invoice annulment and rectification

Future operations need explicit semantics.

#### Anular

Expected direction:

```text
original invoice remains historical
invoice number remains consumed
state becomes ANULADA
```

Exact accounting and reconciliation effects remain to be designed.

#### Rectificar

Expected direction:

```text
original invoice remains
rectifying invoice is created
relationship between both is preserved
```

This is also the likely mechanism for corrections after later accounting effects can no longer be safely removed.

### More complex rent revisions

Current revision behavior covers the known real contracts.

Only generalize it if another contract requires different timing, index handling or arrears behavior.

### Invoice document improvements

The current HTML/printing workflow is sufficient.

Further document-generation work should be driven by real use.

## Current stopping point

The latest completed functional block is the accounting distribution, reimbursement and reporting integration.

Implemented and tested:

```text
ApunteContable
    ↓
normal property
    → accounting components remain on entry

type-T property
    ↓
DistribucionApunte per child property
    → persisted participation
    → persisted base
    → persisted IVA
    → persisted retention
    → persisted total
```

Temporal attribution is:

```text
ApunteContable / DistribucionApunte
    ↓
period + applicable contracts
    ↓
ImputacionContrato
    → persisted base
    → persisted IVA
    → persisted retention
    → persisted total
```

`REPERCUTIR` workflow is complete for the known cases:

```text
pending expense
    ↓
select for contract
    ↓
review calculated allocation
    ↓
communicate externally
    ↓
Marcar como enviado
    ↓
persist atomically:
        ImputacionContrato(s)
        SolicitudReembolso
        SolicitudReembolsoLinea(s)
        MovimientoPrevisto INGRESO
```

Undo behavior is:

```text
PENDIENTE / CANCELADO
    → undo allowed

PARCIAL / CONCILIADO
    → undo rejected
```

Undo restores the original expense to pending reimbursement state.

Accounting reports now apply:

```text
CONTABILIZAR
    → full owner's amount

FACTURAR
    → full original expense remains owner's expense

REPERCUTIR
    → only non-imputed residual remains owner's expense
```

For type-`T` properties:

```text
source ApunteContable
    ↓
persisted DistribucionApunte
    ↓
persisted ImputacionContrato when applicable
    ↓
child-property accounting output
```

The type-`T` container itself is not shown as separate accounting.

Historical decisions are protected.

If persisted contract imputations exist, source accounting fields that determine the allocation cannot be modified.

Protected fields are:

```text
inmueble
fecha
base
iva_importe
retencion_importe
periodo_desde
periodo_hasta
criterio_periodo
tratamiento
```

The same rule applies when the persisted imputation belongs to a distribution of a type-`T` entry.

Descriptive fields such as notes remain editable.

An accounting entry with persisted contract imputations cannot be deleted until the reversible downstream reimbursement operation has been undone.

The full pytest suite was green at completion of this block.

## Next change

Do not extend the reimbursement/distribution subsystem merely because the current block is complete.

The implemented `REPERCUTIR` workflow, type-`T` allocation and IVA-report integration are sufficient for the currently known cases.

The immediate priority remains real operational use.

Choose the next work from concrete needs discovered while using:

```text
accounting
bank import
reconciliation
invoice preparation
invoice review
rent revisions
contract annexes
reimbursements
fiscal reports
```

Likely next areas are:

1. accounting completeness and integrity controls;
2. year-end / IRPF / IRNR reporting required by real fiscal preparation;
3. `FACTURAR` integration with invoice preparation when the first concrete case appears;
4. invoice annulment or rectification when first required;
5. operational problems discovered during bank reconciliation or parallel accounting use.

Preserve the general correction rule:

```text
still fully reversible
    → undo downstream effects
    → correct source
    → perform operation again

persistent historical effect must remain
    → do not silently recalculate or overwrite it
    → use an explicit rectification workflow when needed
```

Prefer fixing real operational friction over adding anticipated functionality.