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

The user's local tree can be ahead of GitHub between commits. When the user says a change has been committed and pushed, `develop` can be treated as current again.

Repository:

```text
cecilios/contab
branch: develop
```

## Development workflow

The user is an experienced C++ developer but knows little Python/Flask. Instructions should therefore be technically precise and concrete without assuming familiarity with Flask idioms.

Preferred workflow:

```text
agree on behavior
    ↓
write/adjust focused tests
    ↓
make smallest production change
    ↓
run focused tests
    ↓
run full pytest suite
    ↓
manual/visual test only when it adds real value
    ↓
update docs after a meaningful functional block
    ↓
commit
```

TDD-style work is preferred when practical, but strict test-first development is not required.

For long integration tests, add short comments describing the simulated user action.

Do not ask the user to search through the repository when the code can be inspected directly from GitHub.

At commit time, do not explain Git commands. Only propose one or more commit messages.

Commit messages are Spanish infinitive phrases, for example:

```text
Añadir conciliación manual de movimientos previstos
Generar movimientos previstos desde apuntes contables
Sincronizar apuntes con movimientos previstos
Proteger apuntes con movimientos parcialmente conciliados
```

Documentation is a state/handoff mechanism, not a changelog. Do not update it after every tiny change.

## Product context

Contab is a small personal application for managing the economic activity of fewer than ten rented properties.

It is not intended to become:

* a general accounting package;
* a commercial property-management platform;
* a banking application;
* a complex multi-user or multi-company system;
* a document-management system.

The two primary goals are:

1. **Bank reconciliation**: reduce the work required to identify and reconcile real bank movements with expected income and expenses.
2. **Flexible accounting/reporting**: record economic facts once and retain enough stable detail to regroup them later for changing fiscal/reporting requirements.

Billing, property management and other modules are auxiliary to those goals.

Prefer real client value over feature count.

## Permanent design principles

### Keep the application small

Prefer:

* direct code;
* explicit services;
* simple Flask routes;
* understandable data models;
* deterministic rules;
* incremental changes.

Avoid abstractions or workflows for hypothetical future cases.

A slightly forward-looking database field is acceptable when the future need is stable, obvious and cheap to prepare. UI and operational workflows should wait for real use cases.

### User control

Automation assists but does not make doubtful decisions for the user.

In reconciliation:

```text
Contab proposes
User reviews
User confirms
```

Exceptional situations must remain manually resolvable.

### Enter data once

A real economic fact should be entered once and reused for:

* accounting;
* reconciliation;
* reports;
* eventually billing when applicable.

### Preserve source evidence

Do not overwrite or normalize away source information needed for later verification.

Examples:

* bank movements retain original bank text;
* accounting entries retain document references;
* supporting documents remain in the filesystem.

### Atomic operations

Operations producing several related records should succeed or fail together.

Current important example:

```text
ApunteContable
      +
MovimientoPrevisto
```

They are created in the same transaction.

Future invoice generation should eventually coordinate:

```text
Factura
 + líneas
 + ApunteContable
 + MovimientoPrevisto
```

### Tests are intentional complexity

Test code is not considered unnecessary complexity.

Protect:

* domain rules;
* complete form flows;
* error presentation;
* multi-record operations;
* migrations;
* important module boundaries.

Automated integration tests are preferred over long artificial visual tests when they verify the same behavior.

Manual end-to-end testing should concentrate on real client data, where it can reveal workflow problems that synthetic browser tests cannot.

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

Business rules belong in services whenever practical.

Routes own:

* HTTP behavior;
* selected logical database;
* transactions;
* redirects;
* templates;
* user-facing validation/error handling.

Use SQLAlchemy `select()`, not legacy `Session.query()`.

Money is stored as positive integer cents. Nature determines direction:

```text
INGRESO
GASTO
```

Percentage values requiring two decimal places use hundredths of a percentage point.

Supporting PDFs and invoices remain in the filesystem. Do not build document-history interfaces without a real requirement.

For SQLite constraint changes, Alembic `batch_alter_table` is normally required.

Back up real databases before schema migrations.

## Multiple databases and banks

Each logical database represents one accounting context and corresponds to one bank account for reconciliation.

Example configuration:

```ini
[databases]
cliente = sqlite:///data/cliente.db
hermana = sqlite:///data/hermana.db

[bancos]
cliente = IBERCAJA
hermana = CAIXABANK
```

Currently supported importers:

```text
IBERCAJA
CAIXABANK
```

`config.py` validates that every logical database has one supported bank.

Application context helpers resolve the selected database and bank.

## Implemented property/accounting scope

Implemented:

* properties;
* subdivided type-T parent properties;
* rentable child units;
* tenants;
* contracts with multiple holders;
* rents and rent revisions;
* accounting categories/subcategories from `contab.ini`;
* accounting-entry CRUD;
* accounting validation forms;
* accounting periods;
* treatments;
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

`REPERCUTIR` means passing a cost to a tenant; it is not the same as allocating a common expense among child properties.

`FACTURAR` is intended for later inclusion in an invoice.

Terminology:

```text
distribuir = analytical allocation among properties for reporting
repercutir = charge a cost to the tenant
```

Do not confuse them.

## Accounting-entry form behavior

The form follows:

```text
Validar
   ↓
Guardar
```

Validation computes automatic fields and a signature representing the validated form state.

If any protected form data changes after validation, saving fails and the user must validate again.

Blocking business validation should happen on **Validar**, not only on **Guardar**.

If validation is blocking:

```text
no firma_validacion
no Guardar button
```

The save path must still recheck domain rules defensively.

This distinction is intentional: do not give the user the expectation that a form can be saved if a known blocking condition already exists.

## Accounting entry → expected movement

Manual accounting-entry creation currently offers:

```text
☑ Generar movimiento previsto para conciliación
```

Default: checked.

The user may explicitly uncheck it.

When checked, the expected movement is created from the accounting entry in the same transaction.

Derived fields:

```python
MovimientoPrevisto.inmueble = ApunteContable.inmueble
MovimientoPrevisto.naturaleza = ApunteContable.naturaleza
MovimientoPrevisto.concepto = ApunteContable.concepto
MovimientoPrevisto.importe_esperado = ApunteContable.total
MovimientoPrevisto.contraparte = ApunteContable.tercero_nombre
```

Expected dates are independent reconciliation data:

```text
fecha_prevista_desde: optional
fecha_prevista_hasta: optional
```

Rules:

```text
both empty       -> valid
desde only       -> valid
hasta only       -> invalid
hasta < desde    -> invalid
```

Never use `ApunteContable.fecha` as an invented expected bank date.

If expected-movement generation is unchecked, invalid text in the expected-date controls is irrelevant and must not block creation.

`MovimientoPrevisto.apunte_id` remains nullable for now. Do not make it required until real usage demonstrates that independent expectations are unnecessary.

## Editing accounting entries with linked expected movements

The accounting entry is the source for the derived economic/descriptive fields of its linked expected movements.

Whenever an entry is successfully edited, synchronize:

```text
inmueble
naturaleza
concepto
importe_esperado
contraparte
```

Do **not** synchronize or reset:

```text
fecha_prevista_desde
fecha_prevista_hasta
estado
metodo_conciliacion
notas
```

Protection depends on expected-movement state.

### PENDIENTE / CANCELADO

All accounting fields may be changed.

The linked expected movement is synchronized afterward.

### CONCILIADO / PARCIAL

The following accounting properties are protected:

```text
inmueble
naturaleza
total
```

The amount rule compares accounting **total**, not its internal composition.

Therefore an accounting composition change is conceptually allowed if the resulting total remains unchanged.

Descriptive changes remain allowed and are synchronized.

Current service rule is conceptually:

```python
protected = any(
    movimiento.estado in {"CONCILIADO", "PARCIAL"}
    for movimiento in apunte.movimientos_previstos
)

economic_change = (
    inmueble is not apunte.inmueble
    or naturaleza != apunte.naturaleza
    or total != apunte.total
)

if protected and economic_change:
    raise ContabilidadError(...)
```

The route invokes the same protection during `Validar` so a blocked edit never receives a validation signature.

## Deleting accounting entries

Deletion is forbidden if any linked expected movement is:

```text
CONCILIADO
PARCIAL
```

Deletion remains allowed when linked movements are:

```text
PENDIENTE
CANCELADO
```

Allowed linked expected movements are deleted together with the accounting entry.

This rule intentionally matches the economic protection used during editing.

## Bank import

`src/contab/conciliacion/importacion.py` owns bank-file parsing.

Bank movement parsing:

* uses operation date, not value date;
* parses Spanish monetary formats;
* stores positive cents;
* derives nature from source sign;
* preserves original type and description;
* preserves optional bank reference;
* rejects zero/malformed values;
* produces stable SHA-256 import fingerprints.

An occurrence counter distinguishes legitimate identical rows in the same CSV.

`preparar_movimientos_bancarios()` filters already imported fingerprints and returns new model objects. It does not add or commit them.

`MovimientoBancario` currently contains:

```text
id
fecha
naturaleza
importe
tipo_original
descripcion_original
referencia_bancaria
huella_importacion
estado
```

Do not add bank/account/value-date/balance/apunte foreign keys without a real requirement.

Bank movement states:

```text
PEN
```
