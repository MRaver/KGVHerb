
# Vietherb GraphRAG — Handoff

## Phase 2 preflight — current review gate

- Scope: steps 1–4 only. Read AGENTS, PROJECT_CONTEXT, IMPORT_DESIGN, HANDOFF, Phase 1 sources/tests and offline validation report. No source-code fixes or integration writes in this task.
- [PHASE2_PREFLIGHT.md](PHASE2_PREFLIGHT.md) records detailed findings, read-only query plan, database/constraint DDL proposals and integration test matrix; all DDL remains unexecuted.
- TCP 127.0.0.1:7687 OPEN. A single Bolt attempt with auth=None failed: AuthError / Neo.ClientError.Security.Unauthorized. No credential guessing. No Neo4j username/password available in the process environment or root .env files.
- Server version, existing databases, constraints/indexes and effective privileges remain **unverified due to authentication**, not empty/absent. User reports Desktop 2.3.1, Enterprise server 2026.10.2, VietherbDB, neo4j ONLINE; this supersedes older Desktop/server version wording below.
- Existing offline suite rerun: **25 passed, 0 failures/errors, 2.191s, exit 0**. Ontology SHA unchanged: 2f7083f9fc1758edfadd45bf3b721661c585f1c2d3c750d509d94af78976aa73.
- Review blockers: writer defaults to protected neo4j; no schema preflight; ImportRun ID collision not validated; caller-supplied manifest not content/identity-verified. Additional issues: incomplete run metadata/failure lifecycle, non-strict boolean payload fields and term-plan preflight gaps. Code intentionally not changed in this review-only gate.
- Proposed test DB: vietherb-test, only after authenticated read-only inventory, code fixes/review and explicit approval of target and constraints. Do not create/reset/drop any database; do not write neo4j. No commit/push.
- Next: provide credentials via process environment/secret mechanism (never chat/logs), finish read-only server/schema inventory, review proposed fixes and test setup. Await user approval before all database writes.

## Phase 1 offline implementation — 2026-11-15 (current)

This section supersedes the historical design-only status below. Awaiting review before integration testing. No Neo4j connection, writer against a real database, constraints/database creation/deletion, ontology modification, commit or push was performed.

### Implemented / changed files

- [pipeline.py](../src/vietherb_ontology/pipeline.py): read-once source hashing, no-normalization parser, blank-node/DTD rejection, versioned term/triple codec, deterministic row/byte-limited batches and strict structural/lexical validator.
- [inventory.py](../src/vietherb_ontology/inventory.py): root lookup fixed with URIRef and shared parser policy. [ontology_inventory.json](ontology_inventory.json) regenerated; now exactly six roots.
- [neo4j_io.py](../src/vietherb_ontology/neo4j_io.py): dependency-injected, default-disabled writer; snapshot/source/run provenance, transactional payload/MATCH checks, structural exporter, validation-gated publication and validated rerun no-op for canonical data. No connection factory or DDL.
- [dry_run.py](../src/vietherb_ontology/dry_run.py): offline-only CLI and manifest/report generation; never invokes the writer.
- [test_inventory.py](../tests/test_inventory.py) and [test_pipeline.py](../tests/test_pipeline.py): baseline SHA-256, exact roots, actual literals, typed lexical variants, Unicode, languages, multivalued/undeclared annotations, dual class/individual types, batch limits, malformed payloads/links, visibility, session-double writer/reimport tests.
- [phase1_offline/](phase1_offline/): source manifest, JSON/Markdown validation report and corrected inventory.
- This handoff updated; original ontology and design unchanged.

### Reproduction (PowerShell, project root)

```powershell
$env:PYTHONPATH='src'
$env:TEMP='D:\vietherb_rag'
$env:TMP='D:\vietherb_rag'
.\venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\venv\Scripts\python.exe -B -m vietherb_ontology.dry_run VHO.owl --output docs/phase1_offline
```

### Results and provenance

- Final test run: **25 tests passed in 2.220s, 0 failures/errors, exit code 0**. An intermediate run had one test-double setup error (`Mock` lacked `__enter__`); corrected to `MagicMock`, then rerun successfully. No database operations followed that failure or any other run.
- Offline dry-run: 2646 triples encode/decode losslessly; six exact roots; 1288 IRI terms; 97 unique literal terms; missing=extra=mismatch=0. N-Triples serialization/reparse strict round-trip also passes. No inference or clinical claims added.
- Source SHA-256 remains `2f7083f9fc1758edfadd45bf3b721661c585f1c2d3c750d509d94af78976aa73` (420694 bytes).
- [Source manifest](phase1_offline/source_manifest.json): snapshot key, source/base/parser settings, software versions, Git state, hashes of every Python source/test file; 3 term batches and 6 triple batches, 500 rows / 4 MiB maximum.
- [Validation report](phase1_offline/VALIDATION_REPORT.md) and [raw results](phase1_offline/validation_report.json): measured offline outcome. Database timing/server version and memory are explicitly not measured.

### Remaining risks / integration gate

- Cypher and real driver/server behavior remain unexecuted. Session/transaction doubles check Python control flow, not actual Neo4j rollback, constraints, query plans or isolation.
- Explicit enablement, existing reviewed uniqueness constraints and exclusive single-writer operation are prerequisites; no distributed lock/lease implemented. FAILED snapshot recovery requires a separate reviewed procedure; automatic cleanup/resume is intentionally absent.
- Parser serializes package calls while changing RDFLib global normalization; use a dedicated process, not arbitrary concurrent external RDFLib calls. Supported input is one RDF graph; bnodes/named graphs/RDF-star are not implemented. DTD/entity input rejected; no claim of a general hostile-input sandbox.
- Projection and inference layers are not implemented in Phase 1. No server compatibility/performance claims and no clinical validation claims.
- Core source/codec identity is compared separately from variable run metadata so timestamp changes do not break canonical idempotency. Full offline run metadata is in the manifest; future database audit reporting should persist complete run versions/settings as well.
- Stop here pending user review before integration testing. Preserve pre-existing untracked files, including Handoff_note.txt.

## Historical design-stage handoff (retained for audit)

## Last updated
2026-11-15

## Current milestone
RDF-faithful importer architecture proposed; implementation and database validation pending.

## Completed work
- Prepared [IMPORT_DESIGN.md](IMPORT_DESIGN.md): canonical RDF terms/triples, snapshot provenance, candidate Cypher, batching/idempotency, strict round-trip validation and research test plan. Documentation only; no Neo4j connection or writes in this task.
- Independently reverified source SHA-256 and baseline using RDFLib with literal normalization disabled: 2646 triples, 1262 classes, 1256 subclass edges, 18 annotation properties, 6 named individuals, 0 object/datatype properties, 0 blank nodes, 0 subclass cycles, 0 multiple inheritance, 6 roots.
- Verified 100 literal occurrences (97 unique): language tags en=80, vn=20; RDFLib datatype=None for these language literals.
- Development environment verified through `venv` (RDFLib 7.6.0 and Neo4j driver 6.4.1 import successfully).
- `VHO.owl` parsed as RDF/XML without OWL inference or IRI rewriting.
- Added `src/vietherb_ontology/inventory.py` for reproducible, provenance-aware ontology inventory.
- Added regression tests in `tests/test_inventory.py`.
- Generated `docs/ontology_inventory.json` from the current ontology.

## Files changed
Current task: only `docs/IMPORT_DESIGN.md` (new) and `docs/HANDOFF.md` (updated). Files below were created in the previous task and remain unchanged here.

- `src/vietherb_ontology/__init__.py`
- `src/vietherb_ontology/inventory.py`
- `tests/test_inventory.py`
- `docs/ontology_inventory.json`
- `docs/HANDOFF.md`

## Test results
- 2026-11-15: existing unittest suite rerun with virtualenv Python, PYTHONPATH=src, `-B`, TEMP/TMP on D: **3 tests passed in 0.240s**, exit code 0. No importer integration tests exist or were executed; Cypher is unexecuted design.
- `PYTHONPATH=src .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v`: 3 tests passed.
- Source SHA-256: `2f7083f9fc1758edfadd45bf3b721661c585f1c2d3c750d509d94af78976aa73`.
  This value is recorded as provenance, not as an experimental result.

## Git state
- `main...origin/main`
- New files are currently untracked; no commit or remote push was performed.

## Open issues
- User now reports Neo4j Desktop 2026.10.2 Enterprise, database `neo4j`, Bolt `bolt://127.0.0.1:7687`. Actual server version, connectivity and database-side mapping remain unverified; Desktop version is not server version.
- Existing inventory root calculation is wrong: it passes strings instead of URIRef to graph.objects and returns 1262 roots; independent typed-term inspection gives 6. Existing ontology_inventory.json is not authoritative for class_roots. Fix deferred because this task permits analysis/design only.
- Existing literal-preservation test uses a URIRef object, not a Literal. Add genuine lexical/datatype/language tests and explicit parser normalization policy before importer implementation. Current passing tests do not establish losslessness.
- The ontology declares 0 `owl:ObjectProperty` and 0 `owl:DatatypeProperty`; it has 18 `owl:AnnotationProperty`. Mapping must preserve that distinction.
- Six resources are both `owl:NamedIndividual` and `owl:Class`; this overlap must not be normalized away.
- RDF-to-Neo4j mapping integrity and performance are not yet measured.

## Decisions requiring review
Canonical triple-node storage plus optional derived projections proposed. MVP should reject blank-node sources until a tested source-scoped canonicalization policy exists. See IMPORT_DESIGN.md for details.

## Next recommended action
After implementation is requested: fix inventory/test gaps, implement isolated parser/codec and dry-run validation, then verify server version and execute integration tests in a designated test database before any production import. Do not infer clinical evidence from ontology assertions.
