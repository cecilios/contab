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
    + optional FACTURAR ImputacionContrato(s)
    + ApunteContable
    + MovimientoPrevisto

invoice deletion
    → delete MovimientoPrevisto
    + FACTURAR ImputacionContrato(s)
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
    + optional MovimientoPrevisto INGRESO/GASTO

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

## Negative accounting entries

`ApunteContable.importe_negativo` is a boolean indicating the sign
of an accounting entry.

Monetary values (`base`, `iva_importe`, `retencion_importe`, `total`)
are stored as non-negative magnitudes.

The sign belongs to the accounting entry as a whole.

Manual forms accept a negative base and normalize the stored magnitude
while setting `importe_negativo=True`.

Displayed amounts recover the sign, including the accounting list,
editing form and applicable reports.

A negative entry retains its accounting `naturaleza` and category.
Reports subtract its amounts from the original income or expense
category rather than moving them to the opposite category.

The expected bank movement uses the opposite nature when the entry
is negative:

```text
GASTO positive    → MovimientoPrevisto GASTO
GASTO negative    → MovimientoPrevisto INGRESO
INGRESO positive  → MovimientoPrevisto INGRESO
INGRESO negative  → MovimientoPrevisto GASTO
```

The expected bank amount remains positive.

The shared helper naturaleza_prevista_apunte() centralizes this rule.

Changes to the sign of an accounting entry must respect the same
historical protections as changes to its amount.

The implemented treatments are CONTABILIZAR and REPERCUTIR.

Negative FACTURAR entries and rectifying invoices remain outside
the implemented scope.


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
optional MovimientoPrevisto
```

Positive and negative REPERCUTIR entries may be included in the
same reimbursement request.

The prepared request calculates a signed balance:
- Positive balance: the tenant owes money. Create a
  MovimientoPrevisto INGRESO.
- Negative balance: the tenant has a credit. Create a
  MovimientoPrevisto GASTO for the absolute balance.
- Zero balance: no expected bank movement is created.
The request and its imputations are persisted even when the balance
is zero. This records that the selected entries have been compensated
and prevents them from reappearing as pending.

`SolicitudReembolsoLinea.importe` and `ImputacionContrato.importe`
retain positive magnitudes. Their accounting sign comes from the
original ApunteContable.

The request total uses the signed amounts of its lines.
`SolicitudReembolsoLinea` preserves which accounting origin was included in the request.

That origin is either:

```text
ApunteContable
```

or:

```text
DistribucionApunte
```

The expected movement represents the resulting payment or collection
between the tenant and the owner. No movement exists for a zero balance.

The original supplier payment remains a separate accounting/banking fact.

### Reimbursement request states

The request normally derives its operational state from its associated
expected movement.

A zero-balance request has no expected movement and is displayed as
`Sin movimiento`, with a total of `0,00`.

Such requests may be deleted while no other historical constraints
prevent the operation. Deletion also removes their imputations,
making the original entries pending for reimbursement again.

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


## Bank import and reconciliation

See `docs/Conciliacion.md` for the end-user behavior.

### Import and state model

Bank import is implemented in
`src/contab/conciliacion/importacion.py`.

Original bank dates, descriptions, amounts in cents, nature,
and import fingerprints are preserved. Supported banks:
IBERCAJA and CAIXABANK.

Bank movement states:

- `PENDIENTE`
- `PARCIAL`
- `CONCILIADO`
- `DESCARTADO`

Expected movement states:

- `PENDIENTE`
- `PARCIAL`
- `CONCILIADO`
- `CANCELADO`

`Conciliacion` associates one bank movement with one expected
movement through a positive `importe_asociado`.

Associations are unique by bank/expected pair. There is no
independent reconciliation-group entity.

`saldo_movimiento_bancario()` and `saldo_movimiento_previsto()`
return `(associated, pending)` calculated from recorded amounts.

`PARCIAL` is an implemented and supported state.

### Exact, progressive, and accepted-difference reconciliation

Supported cardinalities:

- 1:1
- 1:n
- m:1

An independent m:n operation is not supported.

**Exact reconciliation** exhausts the available balances on both
sides.

**Progressive reconciliation** associates only the amount that
can actually be applied. Any residual balance remains available
for later associations, and the movement state reflects that.

**Accepted differences** explicitly close review even when
the original amount has not been fully associated.

`Conciliacion.cierra_bancario` and
`Conciliacion.cierra_previsto` record the side whose review
was closed despite a remaining arithmetic balance.

The state-update services derive `CONCILIADO` from either a fully
applied balance or the corresponding explicit closure flag.

These flags do not alter the original amount, create a fictional
payment, or waive the economic difference.

Removing an association removes its closure flags and recalculates
the affected movement states. Other associations remain intact.

Services do not commit transactions; routes own transaction
boundaries.

### Chronological allocation and grouped differences

`preparar_asociaciones_cronologicas()` computes associations
without persisting or changing movements.

It uses available balances, including balances of movements
already partially reconciled.

Expected movements are processed by `fecha_prevista_desde`,
oldest first, with ID as a stable tie-breaker.
Movements without a planned date sort last.

Bank movements are processed by date, oldest first, with ID
as a stable tie-breaker.

The function rejects:

- Empty selections.
- m:n selections.
- Repeated movements.
- Unavailable or fully exhausted movements.
- Mixed bank/expected natures.
- Selections that leave any selected movement without an association.

`confirmar_grupo_conciliacion(..., cerrar_diferencia=True)`
confirms associations and marks the movement retaining the
arithmetic difference.

It rejects a closure unless exactly one movement retains an
unassociated balance after the proposed associations.

For grouped m:1 accepted differences, all selected expected
movements must have the same non-null `contrato_id`.

Different contracts, mixed known/unknown contracts, and all-unknown
contracts are rejected.

This contract restriction applies specifically to accepted
differences involving multiple expected movements. Progressive
reconciliation without accepted closure remains possible between
different contracts.

Existing associations and balances must never be overwritten
to make totals match.

### Automatic proposals

`buscar_propuestas_conciliacion()` prioritizes exact matches
before considering discrepancies.

Implemented automatic proposals:

- Exact 1:1.
- Exact grouped 1:2 and 2:1.
- Unequal 1:1 with a clearly identified counterpart.

Automatic 1:1 discrepancies are considered only when:

- The difference does not exceed 5% of the expected remaining balance.
- Bank and expected movements have the same nature.
- Their dates are compatible.
- The bank movement identifies the expected counterpart
  through the available matching rules or configured aliases.
- The match is unambiguous on both sides.

The 5% threshold applies only to automatic suggestions.
It does not restrict user-confirmed progressive associations
or manual acceptance of differences.

Automatic discovery of 1:3 and 3:1 remains postponed.

### Review screen and routes

`GET /conciliacion/revisar` shows automatic proposals and
manual reconciliation forms.

`_obtener_revision_conciliacion(db_session)` is shared by
GET and POST handlers and recomputes current proposals.

Manual reconciliation is divided into independent **Ingresos**
and **Gastos** forms. Each has its own expected/bank selection,
totals, difference, and action buttons.

`revision_conciliacion.js` initializes each form independently
and enables the appropriate action for the selected cardinality
and balances.

For equal amounts, the exact-confirmation button is available.

For different amounts, the user can choose:

- `parcial`: associate available amounts and preserve residuals.
- `aceptar_diferencia`: associate available amounts and
  explicitly close the remaining difference.

`exacta` remains the action for exact reconciliation.

The backend validates movement nature and supported cardinality
independently of the browser.

Relevant POST endpoints:

- `/conciliacion/revisar/propuestas/aceptar`
- `/conciliacion/revisar/propuestas/rechazar`
- `/conciliacion/revisar/manual/confirmar`

Automatic proposals are recomputed before acceptance.
Rejecting a proposal releases its movements for manual selection
within the current session without changing the database.

The review screen also retains bank discard actions
and access to manual reconciliation without a bank movement.

### Manual reconciliation without bank

`conciliar_movimiento_previsto_manualmente(movimiento, notas)`
marks an expected movement `CONCILIADO` with
`metodo_conciliacion="MANUAL"`.

It requires a nonblank explanation and creates no
`MovimientoBancario` or `Conciliacion` record.

The action is accessible through **Conciliar sin banco**
in the review screen.

`deshacer_conciliacion_manual()` reverses the operation.

Cash payments, settlements through another account, and
other verified resolutions are possible use cases.

Contract reporting must handle these operations explicitly,
without treating their absence of a bank association as proof
that no payment occurred.

### Contract economic balance (planned)

The future contract statement must show, at a selected date:

- Obligations due.
- Actual receipts attributable to the contract.
- Their difference.

`balance = total_due - actual_receipts`

A positive balance indicates tenant debt.
A negative balance indicates tenant credit.

This calculation must be independent of reconciliation review
status, including accepted-difference closures.

Differences accumulate across periods, including cents.

Receipt attribution must avoid double counting bank movements
associated with multiple expected movements.

Cash collections, payments on account, and movements without
a specific expected obligation require explicit attribution
rules before implementing this statement.

No invoice alteration, artificial accounting adjustment,
or automatic forgiveness is implied by reconciliation.

### Remaining work

- Implement the contract economic statement and payment
  attribution rules.
- Optionally extend automatic grouped-proposal detection
  to 1:3 and 3:1.

Do not replace `PARCIAL`, introduce reconciliation groups,
or implement an independent m:n reconciliation operation.

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

`REPERCUTIR` and `FACTURAR` are implemented as distinct workflows.

```text
REPERCUTIR
    → independent reimbursement request
    → attributed amount is not ordinary fiscal income

FACTURAR
    → original expense remains fully owner's expense
    → attributed amount is included in an ordinary invoice
    → invoice produces separate accounting income
```

Do not route `REPERCUTIR` through ordinary invoice emission.

### FACTURAR preparation

`buscar_gastos_facturables_pendientes(session, contrato=...)` obtains eligible expenses not yet invoiced for the contract.

Reuse the existing spatial and temporal attribution logic:

```text
ordinary property
    ApunteContable
        → ImputacionContrato

type-T property
    ApunteContable
        → DistribucionApunte
        → ImputacionContrato
```

Invoice preparation adds pending expenses to `FacturaPreparada.lineas`.

Automatic expense lines carry:

```text
referencia_facturable = "apunte:<id>"
```

or:

```text
referencia_facturable = "distribucion:<id>"
```

This reference identifies the source allocation across preparation, editing, preview and final accounting.

### Editing and validation

The user may:

- change the expense line concept;
- remove the expense line before emission.

The user may not:

- change its automatically calculated amount;
- duplicate an expense reference;
- introduce an invalid expense reference.

An omitted expense creates no persisted `ImputacionContrato` and remains pending.

`preparar_datos_documento_factura()` must copy `referencia_facturable` from `LineaFacturaEditada` into the document lines.

The external HTML invoice template must submit one hidden `linea_referencia_facturable` field per line, including an empty value for ordinary lines. Otherwise the final accounting form cannot reconstruct the invoice correctly.

### Persistence

`emitir_factura()` accepts the prepared lines and associates every retained FACTURAR expense with the corresponding `FacturaLinea`.

Persist:

```text
ImputacionContrato.factura_linea_id
```

The field is nullable and unique, with a foreign key to `FacturaLinea`.

The imputations preserve their accounting components and reference exactly one source:

```text
ApunteContable
```

or:

```text
DistribucionApunte
```

The route persists the entire invoice operation atomically.

After emission, the invoiced allocation is no longer pending for its contract. For type-T expenses, invoicing one child's allocation must not consume another child's allocation.

### Reversible deletion

When an emitted invoice can be deleted, its FACTURAR imputations must be explicitly deleted before the invoice lines.

Keep the deletion in the route's existing transaction.

The original source expense, its spatial distributions and the supplier's expected payment must not be deleted.

Afterward, those allocations become pending for invoicing again.

An invoice with a `PARCIAL` or `CONCILIADO` expected collection cannot be deleted, and its imputations must remain untouched.

### Migration and verification

The schema includes the nullable unique foreign key:

```text
ImputacionContrato.factura_linea_id
    → FacturaLinea.id
    → ON DELETE RESTRICT
```

The incremental Alembic migration uses `batch_alter_table` for SQLite and explicitly named foreign-key and unique constraints.

The migration has been applied and verified on the demo database and the production databases.

Automated tests cover direct expenses, type-T distributions, pending-expense selection, preview reference preservation, changed concepts, immutable amounts, omitted expenses, duplicate references, persistence, reversible deletion and rejection of deletion when collection is reconciled.

The complete pytest suite and the operational visual flow have passed.
## Billing: intentionally postponed scope

Do not implement merely because the model could support it:

* persistent editable draft invoices;
* separate ordinary single-invoice preparation subsystem;
* generalized extraordinary invoice workflow;
* invoice annulment workflow;
* replacement after annulment;
* rectifying invoices;
* generalized rent-revision behavior for hypothetical contracts;
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

Support for negative accounting entries is implemented.

The implementation covers:

- The `ApunteContable.importe_negativo` field and its database migration.
- Manual creation, editing and display of signed accounting amounts.
- Historical protections when changing an entry's sign.
- Expected bank movements with the appropriate banking nature.
- Signed amounts in accounting reports and summaries.
- Positive and negative `REPERCUTIR` entries.
- Reimbursement requests with positive, negative or zero balances.
- Zero-balance requests without expected movements, including deletion.
- Signed amounts in reimbursement preparation and email text.
- Correct wording and signs for prorated refunds.

The database migration has been applied and checked.

The complete test suite and the relevant manual visual checks passed
at the end of this implementation block.

## Next change

No immediate implementation work is required for negative entries.

Continue development according to the next real operational need,
using small changes protected by tests.

Known deferred items:

- Negative `FACTURAR` entries.
- Rectifying invoices.
- Replacing `criterio_periodo` with `dia_hasta_incluido`.
- Creating accounting entries prefilled from bank movements.

Do not implement these items merely because they are listed here.
