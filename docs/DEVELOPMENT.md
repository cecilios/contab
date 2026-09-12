CONTAB DEVELOPMENT HANDOFF
==========================

Purpose
-------

Internal technical checkpoint for resuming Contab development in a fresh
conversation. Read this file, inspect the current develop branch, and continue
from CURRENT INCOMPLETE STEP. The user's local tree can be ahead of GitHub
between commits.

Repository and workflow
-----------------------

- Repository: https://github.com/cecilios/contab
- Branch: develop
- Development version: 0.2.0
- Stack: LMDE 7, Python 3.13, Flask, SQLAlchemy, Alembic, SQLite,
  Jinja2, pytest and Waitress.
- The user edits locally following step-by-step guidance.
- Inspect current code before proposing exact edits. Use rg to find callers.
- Run focused tests and then the full suite.
- Explicit unit tests are preferred even when integration tests cover the same
  function indirectly.
- In long multi-step tests, add a short comment before each user action.
- Commit messages are Spanish infinitive phrases.

Product priorities
------------------

Contab is a small personal application for fewer than ten properties. Its two
primary goals are:

1. Reduce the work required to reconcile bank movements with expected income
   and expenses.
2. Preserve accounting detail so changing Spanish tax reports can be produced
   without rebuilding the year's accounting manually.

Everything else is secondary. Prefer the smallest understandable solution to a
real need. Keep code and UI minimal. Slightly forward-looking database fields
are acceptable only when clearly predictable and cheap. Avoid hypothetical
features. Tests are valuable, not unwanted code growth.

Architecture and conventions
----------------------------

- Modular Flask monolith.
- Business rules in services, testable without Flask.
- Routes own HTTP, sessions, transactions and templates.
- Use a render helper when the same form is returned through several GET/error
  paths. A listing with one render path does not need one.
- Use SQLAlchemy select(), not legacy Session.query().
- Money is positive integer cents; nature determines income or expense.
- Percentage values with two decimals use hundredths of a percentage point.
- Show human labels, not internal codes.
- Avoid JavaScript unless a small interaction clearly improves usability.
- Supporting PDFs live in the filesystem; do not build document-history UIs.
- Preserve data in migrations. SQLite constraint changes normally require
  Alembic batch_alter_table.
- Back up databases before schema changes.

Implemented functional scope
----------------------------

- Multiple logical SQLite databases selected at application entry.
- Properties, including type T subdivided parent properties and rentable child
  units linked through inmueble_padre_id. Type T cannot have contracts.
- Tenants and contracts with multiple holders, billing data, rents and rent
  revisions.
- Accounting categories/subcategories in contab.ini, including active states.
- Accounting-entry CRUD, validation and human-oriented forms.
- ApunteContable includes optional periodo_desde/periodo_hasta, tratamiento
  (CONTABILIZAR, REPERCUTIR, FACTURAR), document name and issuer data.
- Accounting CSV reports: individual annual VAT CSV, ZIP with all applicable
  property CSVs, and annual VAT summary.
- Demo database creation script.
- Initial invoice models exist, but ODS/PDF generation is postponed.
- Ibercaja and CaixaBank CSV importers.
- Persisted bank movements, duplicate prevention, listing, state filters and
  discard/restore operations.
- Expected-movement model and services.

Key business decisions
----------------------

Initial historical rent loading is intentionally simple: enter the current
valid rent on the contract or last annex. There is no opening-rent workflow,
historical closure flag or fictitious annex.

Automatic invoicing is postponed because accounting and reconciliation provide
more value.

Accounting treatments:

- CONTABILIZAR: included in accounting reports.
- REPERCUTIR: passed to the tenant, not treated as owner expense/income.
- FACTURAR: eventually included in a tenant invoice.

Common type-T expenses may later be distributed proportionally in IRPF reports.
No DistribucionApunte table is currently needed. "Distribute" means accounting
report allocation; "repercutir" means charging the tenant.

Configuration
-------------

contab.ini includes [app], [databases], [bancos],
[categorias_contables] and [subcategorias_contables]. Each logical database has
one bank:

    [databases]
    cliente = sqlite:///data/cliente.db
    hermana = sqlite:///data/hermana.db

    [bancos]
    cliente = IBERCAJA
    hermana = CAIXABANK

config.py has cargar_bancos(), which requires one supported bank per database
and rejects entries for nonexistent databases.

app.py stores app.extensions["contab_databases"] and
app.extensions["contab_bancos"]. context.py has explicitly tested helpers:
get_database_name(), get_session_factory() and get_bank_name(), including their
error cases.

Bank import
-----------

src/contab/conciliacion/importacion.py owns bank-file parsing.
src/contab/conciliacion/services.py owns reconciliation rules.

MovimientoBancarioImportado is a frozen, slotted dataclass containing fecha,
naturaleza, importe, tipo_original, descripcion_original,
referencia_bancaria and huella_importacion.

Readers leer_csv_ibercaja(), leer_csv_caixabank() and dispatcher
leer_csv_bancario():

- locate bank-specific headers after preambles;
- use operation date, never value date;
- parse Spanish amounts and store positive cents;
- derive INGRESO/GASTO from source sign;
- strip surrounding whitespace;
- preserve type, description and optional reference;
- reject zero values and malformed input;
- produce stable SHA-256 fingerprints.

An occurrence counter distinguishes legitimate identical rows in one CSV.
Full anonymized CSV fixtures provide regression coverage.

preparar_movimientos_bancarios() queries fingerprints and returns only new
models. It neither adds nor commits; the route controls the transaction.

MovimientoBancario fields: id, fecha, naturaleza, importe, tipo_original,
descripcion_original, referencia_bancaria, unique huella_importacion and estado
(PENDIENTE, CONCILIADO, DESCARTADO). Do not add bank, account, value date,
balance or apunte_id.

Bank UI
-------

- /conciliacion/ lists bank movements.
- /conciliacion/importar imports CSV via GET/POST.
- POST routes discard and restore bank movements.
- Main navigation has one Conciliacion link to the list.
- The list links to import and expected movements.
- Default filter: PENDIENTE. Other filters: TODOS, CONCILIADO, DESCARTADO.
- Order: fecha DESC, id DESC. Page size: 25.
- Pending can be discarded; discarded can be restored; reconciled has neither
  action. Filters survive pagination and actions.
- CSS classes include movimientos-bancarios, apuntes-contables and
  movimientos-previstos. .enlaces-acciones uses flex gap instead of separator
  characters.

Reconciliation design
---------------------

Expected movements originate from:

1. Invoice generation: accounting entry plus expected income.
2. Manual accounting entry: optional expected income/expense.
3. Later periodic generation from per-property rules.

An expectation linked to an accounting entry is documented and normally exact.
A periodic expectation without an entry is approximate. When the real entry is
created later, link or replace the periodic expectation; do not duplicate it.

Matching generates proposals and never silently confirms them. The user imports
CSV, runs matching over new and old pending bank movements, confirms/rejects
proposals, discards unrelated movements and can match unresolved items manually.

A confirmed association connects MovimientoBancario to MovimientoPrevisto and,
indirectly through apunte_id, to ApunteContable. A matched periodic expectation
without apunte_id must warn that the accounting entry/supporting document is
missing. Never auto-create that accounting entry because classification, period,
VAT and document information may be unknown.

Keep reconciled expected movements. States are PENDIENTE, PARCIAL, CONCILIADO
and CANCELADO. Do not add UTILIZADO.

Future associations must support one bank movement to several expectations,
several bank movements to one expectation, and partial matching. Therefore do
not put a single direct foreign key between MovimientoBancario and
MovimientoPrevisto. A later association table will contain importe_asociado.

Dates and approximate amounts are scoring signals, not hard exclusion rules. A
movement expected from day 15 may arrive on day 14. Do not ask the user for a
tolerance percentage; tolerance belongs to the algorithm.

MovimientoPrevisto
------------------

Fields: id, required inmueble_id, optional contrato_id, optional apunte_id,
optional fecha_prevista_desde, optional fecha_prevista_hasta, naturaleza,
concepto, strictly positive importe_esperado, contraparte, estado and notes.

Date rules:

- both dates may be empty;
- desde may exist without hasta;
- hasta cannot exist without desde;
- if both exist, hasta >= desde.

The former required fecha_prevista was migrated. Existing values were copied to
both new date columns. The migration used batch mode, updated amount/state/date
checks, and blocks incompatible downgrade rather than inventing dates.

No tolerance, expected bank text, recurring-rule reference or reconciled amount
is stored yet.

Expected-movement list and services completed locally
------------------------------------------------------

GET /conciliacion/previstos and template
conciliacion/movimientos_previstos.html exist locally. The list defaults to
PENDIENTE; filters TODOS/PENDIENTE/PARCIAL/CONCILIADO/CANCELADO; paginates; and
shows interval, property, nature, concept, counterparty, derived origin, amount
and state.

Interval display:

- no date: "Sin fecha prevista"
- from only: "Desde dd/mm/yyyy"
- equal dates: one date
- range: "dd/mm/yyyy a dd/mm/yyyy"

Origin is derived: apunte_id -> "Apunte contable"; otherwise contrato_id ->
"Contrato"; otherwise "Previsión independiente".

Services cancelar_movimiento_previsto() and
restaurar_movimiento_previsto() have direct passing tests:

- only PENDIENTE can become CANCELADO;
- PARCIAL/CONCILIADO cannot be cancelled;
- only CANCELADO can be restored to PENDIENTE;
- errors do not change the original state.

CURRENT INCOMPLETE STEP
-----------------------

A local route test named approximately
test_cancelar_movimiento_previsto_desde_interfaz POSTs to:

    /conciliacion/previstos/<movimiento_id>/cancelar

It currently fails with HTTP 404 because the route is not implemented. The full
suite was green before this deliberately failing test. Do not recreate the model,
list or service tests above.

Resume steps
------------

1. In conciliacion/routes.py import redirect/url_for and the expected-movement
   cancel/restore services plus ConciliacionError.

2. Add _estado_previsto_retorno(): read request.form["estado"] with PENDIENTE
   default; allow TODOS and keys of ESTADOS_MOVIMIENTO_PREVISTO; otherwise return
   PENDIENTE.

3. Implement POST /conciliacion/previstos/<int:id>/cancelar:

    open selected DB session and transaction
    session.get(MovimientoPrevisto, id)
    missing -> 404
    call cancelar_movimiento_previsto()
    ConciliacionError -> 400, never 500
    redirect to listar_movimientos_previstos preserving filter

4. Add one route test and route for:

    POST /conciliacion/previstos/<int:id>/restaurar

Use the same transaction/error/redirect pattern.

5. Add Acciones to movimientos_previstos.html:

- PENDIENTE -> POST "Cancelar"
- CANCELADO -> POST "Restaurar"
- PARCIAL/CONCILIADO -> blank
- hidden estado=estado_seleccionado preserves the filter.

6. Test persistence, missing id -> 404, invalid transition -> 400, and absence
   of buttons for PARCIAL/CONCILIADO. Run focused tests, full suite and visual
   checks.

After completing that block
---------------------------

Build the first pure matching-proposal algorithm before periodic rules:

- pending bank movements only;
- pending/partial expected movements only;
- nature compatibility mandatory;
- amount and date proximity contribute to scoring;
- dates are soft and cannot eliminate near candidates;
- return proposals without changing database state.

Do not create the many-to-many reconciliation table until confirmation and
partial-allocation behavior is concrete.

Documentation roles
-------------------

- docs/PROJECT.md: user-facing scope and principles.
- docs/Ajustes-contables.md: accounting-entry behavior.
- docs/Conciliacion.md: Reconciliation design and behavior.
- docs/Importacion-bancaria.md: Bank data import and behavior.
- docs/Informes-contables.md: accounting-reporting behavior and situation.
- docs/Inmuebles, inquilinos y contratos.md: Properties, tenants and contracts, principles and behaviour.
- docs/Facturacion.md: billing behavior and situation.
- docs/DEVELOPMENT.md: internal technical handoff.
