# Phase 2B — Integration blocker fixes (offline)

Ngày: 2026-11-15. Trạng thái: implementation và offline validation hoàn tất; **chờ review trước mọi integration testing thực tế**.

Đã đọc AGENTS, PROJECT_CONTEXT, IMPORT_DESIGN, PHASE2_PREFLIGHT và HANDOFF. Git trước sửa: `main...origin/main`, các file project hiện chưa được theo dõi. Giữ nguyên file không liên quan, ontology và artifacts Phase 1. Không kết nối Neo4j, không tạo/xóa database hoặc constraints, không commit/push.

Người dùng xác nhận thủ công: Neo4j Enterprise 2026.10.2; `neo4j`, `system`, `vietherb-test` ONLINE; database test ban đầu 0 nodes và năm unique constraints đã được tạo. Đây là thông tin người dùng cung cấp, **không phải phép đo của agent trong Phase 2B**.

Ghi nhận thay đổi Git đồng thời từ bên ngoài: lúc kiểm tra cuối repository đã ở branch `Phase2-Preflight`, HEAD `c9d528b94d5ddf9a0276fdeb24946923b24991c4` (`Add comprehensive test suite for vietherb_ontology`). Agent không chạy commit hoặc đổi branch. Manifest ghi đúng HEAD này và `gitDirty=false` tại thời điểm dry-run; sau đó các tài liệu bàn giao mới tạo/sửa làm worktree dirty. Đã kiểm tra lại toàn bộ codeHashes trong manifest: 0 mismatch. Không reset hoặc hoàn tác thay đổi Git bên ngoài.

## 1. Blocker → implementation → regression

| Finding trong preflight | Sửa đổi | Kiểm chứng offline |
| --- | --- | --- |
| Database mặc định neo4j | Constructor bắt buộc keyword `database`; chỉ nhận chính xác `vietherb-test`; `enabled` mặc định False, phải bool | Thiếu database, neo4j/system, case/whitespace/target khác bị chặn trước session |
| Target/alias chưa kiểm tra | Read-only SHOW DATABASES với fields explicit; yêu cầu standard/online/read-write; đối chiếu `db.info()` name + database ID; reject alias/missing metadata | Fake target sai ID, alias, offline/composite/read-only/missing bị chặn trước INIT |
| Chưa kiểm tra schema | Read-only SHOW CONSTRAINTS/INDEXES; đúng năm tên, node labels, properties, uniqueness type; backing RANGE index ONLINE đúng owningConstraint | Thiếu/sai constraint/index hoặc POPULATING fail trước INIT; không tự sửa schema |
| Tin manifest/plan caller | Immutable ImportPlan giữ source bytes và canonical JSON; trước session reparse bytes, tính lại SHA, snapshot key, fingerprint, encode và so toàn bộ records | Tamper SHA/key/base/policy/mapping/fingerprint/byteCount/source bytes/records bị reject |
| Run ID conflict | Run identity gắn snapshot, target DB ID và batch settings; kiểm tra payload + đúng một TARGETS; snapshot đúng một FROM_SOURCE | Cross-source run ID reuse, duplicate TARGETS/FROM_SOURCE, inconsistent lifecycle reject/rollback trong double |
| Run provenance thiếu | Lưu started/finished UTC, versions (bao gồm server components khi sau này preflight thật), code hashes, Git state, source path, DB ID, settings; snapshot identity tách timestamp | Kiểm tra metadata fields và same-run replay/new-run canonical idempotency |
| Failure lifecycle | INIT nằm trong try; init exception không giả nhận run đã commit. Failure audit riêng cho run; chỉ đổi snapshot LOADING đúng owner, giữ VALIDATED khi rerun lỗi | Test init rollback, failed batch, rerun validation fail, missing audit rows, audit unavailable; giữ original exception + safe note |
| Payload bool/int tương đương | Kiểm tra exact bool/string/key shape; payload comparison qua canonical JSON; assertionCount phải int không bool | `True`/`1`, `False`/`0`, extra fields, invalid language bị reject |
| Plan gộp duplicate/unused terms | Validate tất cả terms/triples, đúng role, key uniqueness, exact used-term set; precompute batch limits trước session | Duplicate/unused/missing/malformed terms và invalid batch settings không mở session |
| Doubles không chứng minh DB behavior | Chuẩn bị explicit integration suite riêng với server-side rollback/constraint probes, import/export, reimport, duplicate-role corruption trong rollback tx | Chỉ kiểm tra default/gates bằng doubles ở Phase 2B; **chưa chạy suite trên server** |

ImportPlan không thể chứng minh một manifest tùy ý bằng cách hash graph thay source SHA: implementation luôn xác minh lại chính bytes của source. Không inference, không tự tạo ontology entities/medical relations. Literal lexical value, datatype và language tag vẫn giữ nguyên.

## 2. Files thay đổi

- [pipeline.py](../src/vietherb_ontology/pipeline.py): strict payload types, SHA key shape, full record-set validation, cardinality int check và decode errors.
- [import_plan.py](../src/vietherb_ontology/import_plan.py) — mới: frozen byte-backed ImportPlan, build/verify, source/manifest/content identity và batch validation.
- [target.py](../src/vietherb_ontology/target.py) — mới: allowlist database, read-only catalog/schema/identity gates và server components.
- [writer.py](../src/vietherb_ontology/writer.py) — mới: guarded initialization, lifecycle, run/snapshot/source identities, audit metadata, failure preservation.
- [neo4j_io.py](../src/vietherb_ontology/neo4j_io.py): giữ low-level callbacks/exporter; guard run-state mạnh hơn; facade tới guarded writer; bỏ lifecycle queries cũ.
- [integration_runner.py](../src/vietherb_ontology/integration_runner.py) — mới: mặc định offline; read-only và write modes tách biệt; không DDL/cleanup/reset.
- [dry_run.py](../src/vietherb_ontology/dry_run.py): dùng verified ImportPlan và report title chung.
- [test_pipeline.py](../tests/test_pipeline.py): migrate writer tests sang API mới; giữ các test parser/codec/role corruption.
- [test_blockers.py](../tests/test_blockers.py) — mới: 29 regression tests bổ sung, target/schema/plan/run/lifecycle/failure/runner gates, fake transaction có backup/rollback trạng thái Python.
- [phase2b_offline/](phase2b_offline/) — mới: manifest, JSON/Markdown report và inventory riêng; không ghi đè báo cáo Phase 1.
- [HANDOFF.md](HANDOFF.md), [IMPORT_DESIGN.md](IMPORT_DESIGN.md), báo cáo này: cập nhật trạng thái/API và điểm dừng.

## 3. API mới và gate order

API cũ `import_graph(graph, manifest, terms, triples, ...)` bị loại bỏ vì cho phép ghép graph với provenance không liên quan. API được review mới:

```python
plan = build_plan(source, expected_sha256=BASELINE_SHA256)
# Only instantiate/use after integration review; this task did not do so on a real driver.
writer = Neo4jWriter(driver, database="vietherb-test", enabled=True)
report = writer.import_plan(plan, run_id="unique-non-secret-run-id")
```

Thứ tự bắt buộc: enabled/database/run ID → byte-backed plan, tất cả records và batches → read-only target/schema preflight → INIT transaction kiểm tra existing identities/edges trước MERGE và kiểm tra lại sau → batches → export/strict validation + publish transaction.

Reuse cùng run ID chỉ là replay cùng identity/settings; run VALIDATED không được ghi lại batch hoặc sửa terminal audit khi replay thành công. Run ID mới cho reimport tạo audit mới nhưng không đổi canonical terms/triples/assertions. Snapshot FAILED hoặc orphan LOADING không được tự resume; cần review recovery riêng.

Failure code lưu DB là `IMPORT_OR_VALIDATION_FAILED`, không lưu raw exception text chứa secrets. Nếu audit không ghi được, original exception được giữ với safe note; không báo audit thành công giả. Failure trong INIT có rollback/outcome-unknown note, không tự tạo failed run ở transaction khác khi identity chưa xác minh.

## 4. Runner và sử dụng

Mặc định **không connect, không khởi tạo driver**, kể cả môi trường đã có credentials:

```powershell
$env:PYTHONPATH='src'
$env:TEMP='D:\vietherb_rag'
$env:TMP='D:\vietherb_rag'
.\venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\venv\Scripts\python.exe -B -m vietherb_ontology.dry_run VHO.owl --output docs/phase2b_offline
.\venv\Scripts\python.exe -B -m vietherb_ontology.integration_runner --database vietherb-test
```

`--read-only` là explicit opt-in mở connection để inspect target/schema, không gọi write callback. Chế độ ghi tương lai bắt buộc đồng thời `--execute-writes`, `--confirm-database vietherb-test`, `--exclusive-writer` và database explicit. **Không chạy các mode có kết nối trong Phase 2B.** Flags là safety gates cho người thực thi sau review, không thay quyền phê duyệt.

Chỉ hai mode có connect mới đọc `NEO4J_USERNAME`/`NEO4J_PASSWORD`; không nhận password từ CLI, không hardcode auth, URI cố định local Bolt. CLI chỉ xuất safe error type khi thất bại, không traceback/raw driver message. Không có lệnh CREATE/DROP DATABASE, CREATE/DROP CONSTRAINT hoặc DELETE/RESET trong runner. Future write suite giữ lại import và audit thành công; negative probes rollback, không cleanup database.

Suite chuẩn bị: năm uniqueness probes trong explicit rollback tx, sentinel rollback, full baseline import, strict export validation, canonical counts và rerun idempotency, duplicate-role corruption detection trong rollback tx và validation sau rollback. Các regression Python khác (run conflicts, missing rows, failure audit, snapshot lifecycle) đã chạy bằng doubles; coverage server-side tương ứng vẫn cần xác nhận/mở rộng sau review, không coi doubles là server proof.

## 5. Kết quả thực đo offline

- **54 tests passed, 0 failures, 0 errors, 28.069s, exit code 0**.
- Diagnostics workspace cho source/tests: **No errors found**.
- Dry-run: **2646 triples**, **6 roots**, **1288 IRI terms**, **97 unique literal terms**.
- Strict missing/extra/mismatch = **0/0/0**; N-Triples serialization/reparse cũng pass.
- Runner default mode thực chạy: `connectionOpened=false`, `databaseOperations=false`, validation pass.
- Manifest: [source_manifest.json](phase2b_offline/source_manifest.json); raw report: [validation_report.json](phase2b_offline/validation_report.json); [Markdown report](phase2b_offline/VALIDATION_REPORT.md).
- Source SHA-256 đo lại:

```text
2f7083f9fc1758edfadd45bf3b721661c585f1c2d3c750d509d94af78976aa73
```

Fingerprint graph giữ nguyên `4b9cb2aad5a74deff593377b072804fd0faa78301cc0c1cdccbc8cc0b35375f4`. Manifest lưu hash mọi Python source/test file để kiểm chứng code thực chạy, kể cả worktree chưa commit. Batch mặc định vẫn 500 rows / 4 MiB, 3 term batches và 6 triple batches.

Skill `python-fact-grounded-coding` được dùng để biến từng finding thành regression/assertion runtime, đối chiếu caller API và kiểm tra diagnostics; không dùng nó để suy ra hành vi server chưa đo.

## 6. Những gì chưa được chứng minh và điểm dừng

- Chưa chạy bất kỳ Neo4j connection/queries nào trong đợt này. Catalog fields, Cypher syntax, actual constraints, permissions, rollback và driver/server interoperability phải được integration test thật sau review. Thông tin người dùng xác minh thủ công không được đổi thành kết quả test của agent.
- Các target/schema gates fail-closed nếu metadata thiếu/khác contract; không tự repair schema. Đã đối chiếu tài liệu chính thức về [SHOW DATABASES](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/listing-databases/), [db.info](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/) và [SHOW INDEXES](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/); vẫn cần kiểm tra trên server thực.
- Chỉ hỗ trợ exclusive single writer; không distributed lock. Không có tự động recovery/cleanup, đặc biệt với commit outcome unknown. Không biến exception thành claim rollback đã được chứng minh trên DB thật.
- Parser package lock không bảo vệ code bên ngoài tự đổi RDFLib global setting; dùng dedicated process. Blank nodes/named graphs/RDF-star, projection, reasoning và clinical validation ngoài scope.
- ImportPlan được reparse/re-encode để kiểm chứng, ưu tiên correctness cho baseline nhỏ; chưa benchmark hiệu năng quy mô lớn.

**Dừng sau implementation/offline validation. Chờ người dùng review trước read-only connection hoặc integration writes.**
