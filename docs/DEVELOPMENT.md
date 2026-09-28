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

cecilios/contab
branch: develop

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

Automated pytest/integration tests are preferred over time-consuming artificial browser setup. Manual end-to-end tests are most valuable with real client data.

When providing a complete replacement for a function or file, provide genuinely complete code. Never use placeholders such as `# ...` inside code the user is expected to paste.

Before relying on a function signature, inspect the current implementation.

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

The application will begin real parallel use with the existing manual accounting process in October 2026. The purpose of the parallel period is to discover operational problems from real data before adding further complexity.

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

Exceptional cases must remain manually resolvable.

### Enter data once

A real economic fact should be entered once and then reused for accounting, reconciliation, reporting and billing where appropriate.

### Preserve source evidence

Do not destroy information needed for later verification.

Examples:

* bank movements retain original bank text;
* accounting entries retain document references;
* physical invoices and supporting documents remain in the filesystem.

### Atomic operations

Operations that create several related records must succeed or fail together.

Current important examples:

```text
manual accounting entry
    → ApunteContable
    + optional MovimientoPrevisto

invoice emission
    → Factura + FacturaLinea
    + ApunteContable
    + MovimientoPrevisto

non-invoice monthly rent
    → ApunteContable
    + MovimientoPrevisto
```

Routes own transactions. Services prepare and coordinate domain objects but do not commit.

### Tests are intentional complexity

Protect domain rules, complete form flows, error handling, multi-record operations, migrations and important module boundaries.

Do not reduce test coverage merely to keep production code small.

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
  ↓ business rules
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
* accounting categories/subcategories from `contab.ini`;
* accounting-entry CRUD and validation;
* accounting periods and treatments;
* document metadata;
* accounting CSV reports;
* annual VAT summary;
* demo database generation.

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

Mismatched amounts are shown separately and cannot be bulk-confirmed.

The review screen is:

```text
/conciliacion/revisar
```

Rejected proposals for the current review session are stored in:

```python
session["conciliacion_rechazados"]
```

Bulk confirmation recalculates proposals server-side and only confirms exact-amount matches.

A confirmed normal correspondence creates a persistent `Conciliacion` and marks both movements reconciled. The expected movement records method `INDIVIDUAL`.

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

Billing now contains the complete ordinary workflow required for the October 2026 parallel run.

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

### Contract selection

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

A facturable contract is excluded if the period is earlier than `fecha_inicio_facturacion`.

## Billing: recipient

All contract holders are recipients, ordered by `ContratoInquilino.orden`.

Scalar accounting fields join them with `" / "`:

```text
tercero_nombre = "Ana Pérez / Juan Pérez"
tercero_nif    = "11111111A / 22222222B"
```

For invoice rows the billing address comes from the current contract.

Historical recipient/address snapshots are deliberately not stored in `Factura`. The emitted document is the definitive historical representation.

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

Ordinary `emitir_factura()` nevertheless rejects a second invoice for the same contract/period, including when the existing invoice is annulled. Replacement after annulment requires a future explicit workflow.

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

A revision in state `PENDIENTE` blocks modification until the revision has been resolved.

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

The current HTML invoice is printable and is sufficient for the October real workflow.

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

Rent revisions are integrated with invoice preparation.

`situacion_revision()` provides the state relevant to the requested billing period.

Current visible states are:

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

### PENDIENTE

When the revision requires resolution before billing can continue:

```text
PENDIENTE
```

Modify/accounting is blocked.

The user must resolve the revision first.

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

Do not generalize the revision workflow until a real contract requires behavior outside the current rules.

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

## Billing: FacturaLinea.type technical debt

`FacturaLinea` currently has a constrained `tipo` field:

```text
RENTA
DIFERENCIA_REVISION
REPERCUSION_GASTO
OTRO
```

This classification currently provides little useful behavior.

It is especially questionable now that prepared invoice lines can be edited transiently before persistence: `crear_factura()` currently classifies the first edited line as `RENTA` and subsequent edited lines as `OTRO`, so the stored type does not necessarily preserve the semantic origin of a prepared line such as revision arrears.

Do not refactor this immediately.

Removing or simplifying `FacturaLinea.tipo` requires a database migration, and there is no operational reason to risk that change immediately before the October real run.

Revisit after real use begins.

Likely direction:

```text
verify whether any real behavior depends on FacturaLinea.tipo
    ↓
if not
    → remove field and CheckConstraint
    → create Alembic migration
    → simplify creation code/tests
```

Do not undertake this migration merely for aesthetic cleanup before real billing starts.

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

## Billing: intentionally postponed scope

The ordinary October workflow is complete.

Do not implement the following merely because the model could support them:

* persistent editable draft invoices;
* a separate ordinary single-invoice preparation subsystem;
* extraordinary invoice workflow;
* replacement after annulment;
* rectifying invoices;
* generalized rent-revision workflows for hypothetical contracts;
* generic expense repercussion before a real use case requires it.

Transient editing already handles simple exceptional invoice lines without creating persistent drafts.

## Billing: pending work

The following items are known but are not blockers for October billing.

### `FacturaLinea.tipo`

Review whether line types have any continuing functional value.

If not, remove/simplify them later with an explicit Alembic migration.

Do not perform this schema change immediately before real use.

### Expense repercussion

Integrate real repercutible expenses with invoice preparation when the first concrete cases appear.

Keep the distinction:

```text
distribuir = analytical allocation
repercutir = charge to tenant
```

Reuse accounting data rather than entering the same economic fact again.

### Annulment, replacement and rectification

The model supports invoice state, but there is no complete operational workflow for replacement or rectification.

Design this explicitly when required.

Do not relax the ordinary duplicate-invoice protection as a shortcut.

### More complex rent revisions

The current revision workflow covers the known real case.

Only generalize it if a contract requires different timing, index handling or arrears behavior.

### Revision indices

Current index descriptions include the methods required now, including IRAV.

Add further index/territorial behavior only when real contracts require it.

### Extraordinary lines

Transient Modify already permits additional lines.

Do not create a separate persistent draft/extra-line subsystem without a real operational requirement.

### Invoice document improvements

The current HTML template and printing workflow are sufficient for October.

Further layout, format or document-generation work should be driven by real client use.

## September 2026 invoice bootstrap

The real September 2026 invoices provide the historical billing antecedent needed for October numbering.

The bootstrap is billing history only.

It must not create September:

```text
ApunteContable
MovimientoPrevisto
```

The purpose is:

* preserve genuine September invoice history;
* establish the actual last 2026 invoice sequence for each property;
* allow October numbering to continue correctly.

Keep any bootstrap/import tooling deliberately simple.

## Current stopping point

The billing functionality required for the October 2026 real run is complete.

Implemented and tested end-to-end:

```text
monthly preparation
    ↓
facturable contract
    → prepared definitive invoice lines
    → automatic notes
    → revision state/effects when applicable
    → Preview directly
       or
      Modify → Preview
    → printable invoice
    → Contabilizar
    → validate previewed totals
    → Factura + FacturaLinea(s)
    + ApunteContable
    + MovimientoPrevisto
    → return to same month
    → Emitida
```

Revision workflow currently covers:

```text
month before revision
    → AVISO
    → automatic notice

scheduled revision month while index unavailable
    → ESPERANDO_INDICE
    → old rent
    → automatic explanation

revision resolution
    → new RentaContrato

applicable following invoice
    → APLICADA
    → revised monthly rent
    + arrears for scheduled revision month
    + automatic revision notes
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

The full pytest suite is green.

Manual browser testing has covered the relevant billing paths, including:

```text
ordinary preview
Modify
Preview after Modify
AVISO
ESPERANDO_INDICE
APLICADA
revised rent
arrears line
automatic notes
final accounting with multiple lines
correct persisted totals
```

No known billing change is required before using Contab for the October invoices.

The latest completed functional block is:

```text
Unificar los conceptos definitivos en FacturaPreparada.lineas
```

This removed the last known difference in interpretation between the monthly list and Modify/Preview paths.

## Next change

Do not start another speculative billing refactor before the October real run.

The immediate priority is operational use with real client data.

Use the current system and prioritize any problem that actually appears during:

```text
October invoice preparation
invoice review and printing
accounting
bank import
reconciliation
```

Further billing development should be driven primarily by observed needs.

Known later areas include:

1. expense repercussion and analytical allocation, especially grouped property expenses;
2. accounting completeness/integrity controls;
3. fiscal/accounting reports needed for year-end and January;
4. `FacturaLinea.tipo` cleanup if it remains unnecessary;
5. invoice annulment/replacement/rectification when first required;
6. rent-revision generalization only if another real contract needs it;
7. invoice document/layout improvements if real use shows a need.

Prefer fixing real operational friction over adding anticipated functionality.
