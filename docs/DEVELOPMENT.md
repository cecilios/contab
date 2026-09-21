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

Billing has been implemented to the minimum level required for the October 2026 parallel run.

The monthly screen is:

```text
/facturacion/
```

It receives:

```text
periodo       mm-aaaa
fecha_emision dd-mm-aaaa
```

Initial values propose the next calendar month and its first day.

The screen has two sections:

```text
Locales
Otros
```

Preparation is transient. Do not create `Factura` objects merely to display the monthly preparation.

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

Historical recipient/address snapshots are deliberately not stored in `Factura`. The archived physical document is the definitive historical representation.

## Billing: invoice preparation

`FacturaPreparada` is transient and contains the calculated monthly row.

If no invoice exists for contract/period:

* amounts are calculated from the current applicable rent and tax percentages;
* `siguiente_numero_factura()` predicts the number for display;
* no `Factura` is persisted.

If an invoice already exists:

* `FacturaPreparada.factura` references it;
* its persisted invoice number and economic amounts are displayed;
* the row shows `Emitida`.

The predicted number is only operational guidance for preparing the physical invoice. The definitive number is assigned when emission is confirmed.

Invoice numbering is per property and year, across all contracts belonging to the property:

```text
NN/YYYY<codigo_facturacion>
```

The sequence resets each year.

There is deliberately no database unique constraint on `(contrato_id, periodo)` because future extraordinary invoices may legitimately share a period.

Ordinary `emitir_factura()` nevertheless rejects a second invoice for the same contract/period, including when the existing invoice is annulled. Replacement after annulment requires a future explicit workflow.

## Billing: emission

`emitir_factura()` prepares:

```text
Factura
FacturaLinea(s)
ApunteContable
MovimientoPrevisto
```

The POST route owns the transaction and persists all of them atomically.

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

After emission the route redirects to the same monthly preparation and the row becomes `Emitida`.

Physical invoice creation remains manual for now. Automatic ODS/PDF generation is postponed.

## Billing: rent revision notices

`situacion_revision()` currently recognizes pending revisions:

```text
revision scheduled next month → AVISO
revision scheduled this month → ESPERANDO_INDICE
otherwise                     → none
```

The monthly screen shows:

```text
Aviso
En espera del índice
```

`emitir_factura()` recalculates the situation server-side rather than trusting the browser and stores the revision/notice on the emitted invoice.

Actual revision calculation, new rent creation and arrears remain postponed until required by a real case.

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

Each row is confirmed individually. This was chosen deliberately during initial parallel use because explicit confirmation gives the client confidence and there are very few rows.

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

Do not implement without a real requirement:

* editable draft invoices;
* a separate single-invoice workflow merely to prepare ordinary invoices;
* manual `OTRO` lines;
* extraordinary invoice UI;
* replacement after annulment;
* rectifying invoices;
* automatic ODS/PDF generation;
* full rent-revision calculation.

`Factura` should be created only when the user confirms emission.

If manual extra lines become necessary, prefer transient preparation data rather than persisting draft invoices.

## September 2026 invoice bootstrap

Before preparing the first real October 2026 invoices, import the real September 2026 invoices.

Purpose:

* establish the actual last 2026 invoice sequence for each property;
* preserve genuine invoice history instead of creating fake sequence records.

Keep this as a deliberately simple one-off script.

Expected approach:

```text
load real contracts
call crear_factura() for each actual September invoice
persist the resulting Factura and FacturaLinea records
```

Do **not** create September:

```text
ApunteContable
MovimientoPrevisto
```

September remains historical billing bootstrap only.

Do not build elaborate import infrastructure, dry-run systems or generic validation unless a concrete need appears. The user and client will review the imported result, and exceptional incorrect values can be corrected directly with DB Browser for SQLite.

Before writing the script, inspect the repository for existing script conventions and reuse the normal database/configuration infrastructure.

## Current stopping point

The minimum functional block required to start real parallel use on 1 October 2026 is complete.

Implemented and tested end-to-end:

```text
monthly preparation
    ↓
facturable contract
    → review calculated data/revision notice
    → Emitir
    → Factura + ApunteContable + MovimientoPrevisto
    → return to same month
    → Emitida

monthly preparation
    ↓
non-invoice contract
    → review rent
    → Contabilizar
    → ApunteContable + MovimientoPrevisto
    → return to same month
    → Contabilizado
```

The full pytest suite is green, and both monthly actions have been manually checked in the browser.

The latest completed functional block is:

```text
Contabilizar ingresos sin factura desde la preparación mensual
```

## Next change

The immediate priority is preparing the September bootstrap and starting the October parallel run. Further billing work should be driven primarily by issues and needs found during real use.

Immediate sequence:

1. update `Facturacion.md` and this handoff;
2. create the one-off September 2026 invoice bootstrap script;
3. run it against a copy of the future real database;
4. review the imported September invoices and resulting numbering;
5. begin October parallel use.

After real use begins, prioritize observed operational problems.

Likely later work, only as needed:

1. expenses, repercussion and analytical allocation, especially for grouped IBI work expected later in the year;
2. accounting completeness/integrity controls;
3. fiscal/accounting reports needed for year-end and January;
4. rent-revision completion when a real case reaches that stage;
5. invoice document generation if it proves worthwhile.

Do not let these anticipated areas delay the September bootstrap or the October parallel test.
