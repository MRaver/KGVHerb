# Phase 2 — Read-only preflight và review Phase 1

Ngày: 2026-11-15. Phạm vi đã làm: bước 1–4; không database writes, không DDL, không tạo/xóa/reset database, không commit/push. Chưa triển khai hoặc chạy integration tests có ghi. Chỉ thêm báo cáo và cập nhật bàn giao; mã nguồn Phase 1 giữ nguyên.

## 1. Connectivity và trạng thái kiểm chứng

| Hạng mục | Bằng chứng hiện tại |
| --- | --- |
| TCP `127.0.0.1:7687` | Kết nối socket thành công, cổng OPEN |
| Bolt authentication | Driver 6.4.1, thử `auth=None` một lần: `AuthError`, `Neo.ClientError.Security.Unauthorized` |
| `RETURN 1` hiện tại | Không hoàn thành do auth failure; không xác nhận lại thành công trước đây |
| Server version / edition | Chưa truy vấn được; người dùng cung cấp Enterprise 2026.10.2 |
| Desktop / instance | Người dùng cung cấp Desktop 2.3.1, instance VietherbDB; chưa kiểm chứng qua server |
| Database `neo4j` ONLINE | Người dùng cung cấp; chưa xác minh lại |
| Existing databases | Chưa xác minh, không được hiểu là danh sách rỗng |
| Constraints / indexes | Chưa xác minh, không được hiểu là không có schema |
| User / effective privileges | Chưa xác minh |
| Data directory | Người dùng cung cấp `D:\Neo4jData`; không thay đổi cấu hình hoặc dữ liệu |

Phiên terminal chỉ thấy tên biến liên quan Neo4j `NEO4J_DESKTOP_DATA_PATH`, không có username/password Neo4j trong môi trường; không thấy `.env*` ở root. Không đọc credential stores, không thử password mặc định hoặc đoán password. Không ghi credentials vào file/log. Authentication failure không phải bằng chứng database OFFLINE.

Các read-only queries đã chuẩn bị nhưng bị chặn bởi authentication trước khi chạy:

```cypher
// database neo4j, session READ_ACCESS
RETURN 1 AS ok;
CALL dbms.components();
SHOW CURRENT USER;
SHOW CONSTRAINTS;
SHOW INDEXES;

// database system, session READ_ACCESS
SHOW DATABASES;
SHOW CURRENT USER PRIVILEGES;
```

Khi có credentials trong môi trường của process agent, chạy lại bằng driver READ_ACCESS, không gọi writer. Dùng `NEO4J_USERNAME` và `NEO4J_PASSWORD` hoặc secret mechanism do người dùng chọn, không gửi mật khẩu qua chat. Nếu SHOW bị từ chối, ghi riêng lỗi quyền; không suy ra quyền ghi bằng một write thử. `SHOW DATABASES` có thể chỉ liệt kê databases người dùng được phép thấy, không luôn là inventory toàn DBMS. [Neo4j: Show databases](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/listing-databases/), [quyền truy cập](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-privileges/).

## 2. Kết quả review implementation

### Các điểm cần sửa trước database integration writes

**P1 — Không có guard bảo vệ database `neo4j`.** [Neo4jWriter constructor](../src/vietherb_ontology/neo4j_io.py) mặc định `database='neo4j'`. Bật `enabled=True` mà quên database sẽ ghi vào database bị cấm trong Phase 2. Yêu cầu database explicit, allowlist duy nhất database test đã phê duyệt, từ chối `neo4j`/`system` trước mở session; kiểm tra target không phải alias trỏ về database bảo vệ. Thêm test guard và target identity, không chỉ test enabled=False.

**P1 — Chưa kiểm tra schema trước lần INIT đầu tiên.** `import_graph` chạy INIT ngay sau preflight offline, không kiểm tra năm unique constraints hoặc index ONLINE. MERGE không thay schema contract. Cần read-only schema preflight kiểm tra label/property/type của constraints và target, fail-closed khi thiếu/sai; tuyệt đối không tự tạo constraints. MVP vẫn phải yêu cầu exclusive single writer, không xem owner property là distributed lock.

**P1 — Run ID không được ràng buộc duy nhất với snapshot/manifest.** INIT dùng `MERGE (r:ImportRun {id:$owner})` và `ON CREATE SET` rồi MERGE TARGETS mà không so payload của run đã tồn tại. Dùng lại run ID cho snapshot khác có thể tạo thêm TARGETS và ghi sai trạng thái audit. Cần reject run ID conflict ngay trong initialization transaction; cùng ID chỉ được replay đúng cùng run identity. Kiểm tra cardinality TARGETS và FROM_SOURCE, không chỉ payload snapshot. Guard FINISH/FAILED cũng phải gắn run với đúng snapshot.

**P1 — Writer tin manifest do caller truyền, không xác minh identity/content.** Chỉ so graph với encoded plan; không recompute snapshotKey từ các trường identity hoặc ràng buộc content fingerprint của graph/plan với manifest nguồn. Graph khác có thể được gắn manifest/hash cũ nếu caller truyền sai. Cần validated import-plan object tạo từ cùng source bytes, fingerprint và identity kiểm tra lại trước mở session; reject modified SHA/key/base/policy. SHA bytes không thể suy ngược từ graph: phải giữ provenance chain từ parse_source, không chỉ hash lại graph rồi gọi đó là source SHA.

### Các vấn đề khác cần bổ sung

**P2 — Run provenance chưa đủ.** Writer chỉ lưu stable manifestJson, bỏ thời gian, software versions, code hashes, batch settings ở run; không lưu started/finished timestamps hoặc failure reason. Tách immutable snapshot identity và đầy đủ run metadata có allowlist không chứa secrets. Stable identity vẫn phải không phụ thuộc timestamp để giữ idempotency.

**P2 — Failure handling chưa hoàn chỉnh.** `initialize` nằm ngoài try; nếu validation của snapshot VALIDATED rerun fail thì FAILED query chỉ MATCH LOADING nên run có thể còn LOADING. Lỗi ghi failure audit có thể che lỗi gốc. Cần trạng thái run riêng khỏi snapshot, failure recording có kiểm tra row count, bảo toàn original exception; không chuyển snapshot VALIDATED sang FAILED chỉ vì một run bị lỗi khi chưa có policy rõ.

**P2 — Input payload types chưa strict.** Probe offline thực tế: đổi `languagePresent=True` thành integer `1` vẫn được decode_term chấp nhận do equality Python coi `True == 1`. Cần kiểm tra `type(flag) is bool`, string fields và key shape; tương tự assertionCount phải integer đúng contract, không boolean. Không ảnh hưởng baseline đã kiểm tra nhưng không đáp ứng strict malformed-input validation.

**P2 — Preflight plan chưa xác minh toàn bộ terms.** export_rows tạo dictionary nên duplicate term keys bị gộp; terms không được tham chiếu trong triple không được graph validation kiểm tra. Planner có thể phát hiện duplicate sau INIT đã commit. Validate mọi term/key, uniqueness, đúng tập terms được dùng và toàn bộ batch plan trước bất kỳ write nào; không để lỗi thuần offline tạo snapshot dở dang.

**P2 — Test doubles không chứng minh Cypher/rollback.** Session double không parse Cypher, không enforce constraints, không hoàn tác mutation khi callback throw. Test rerun hiện chứng minh Python bỏ qua batch writes, không chứng minh Neo4j MERGE idempotency hoặc transaction rollback. Cần test thật trên database test, kiểm tra state trước/sau bằng read transaction độc lập.

Exporter dùng OPTIONAL MATCH và collect không DISTINCT để giữ role cardinality; đây là hướng phù hợp. `CALL (t)` là variable-scope subquery trong tài liệu hiện tại; chưa có bằng chứng syntax error, nhưng phải compile/execute trên server đã xác thực, không tuyên bố tương thích chỉ từ mock pass. [Neo4j CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/index.html).

## 3. Kiểm tra offline được chạy lại

```powershell
$env:PYTHONPATH='src'
$env:TEMP='D:\vietherb_rag'
$env:TMP='D:\vietherb_rag'
.\venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Kết quả: **25 tests passed, 0 failures/errors, 2.191s, exit code 0**. Không viết test mới hoặc sửa code ở bước review này. Không chạy lại writer trên DB thật.

SHA-256 nguồn đo lại:

```text
2f7083f9fc1758edfadd45bf3b721661c585f1c2d3c750d509d94af78976aa73
```

[Báo cáo offline Phase 1](phase1_offline/validation_report.json) vẫn là bằng chứng 2646 triples, 6 roots, 1288 IRI terms, 97 unique literal terms, missing/extra/mismatch=0. Đó chưa phải kết quả tái dựng từ Neo4j.

## 4. Kế hoạch đề nghị phê duyệt (chưa thực thi)

### Gate A — Hoàn thành read-only inventory

Cấp credentials qua môi trường process, xác minh version, database statuses, actual privileges, constraints/indexes trên `neo4j` bằng các queries ở mục 1. Báo cáo schema theo từng database; constraints không có phạm vi toàn DBMS. Không tự thay quyền hay tạo user/role.

### Gate B — Sửa implementation offline

Sửa các P1/P2 trên và thêm unit regressions; chạy lại offline acceptance. Định nghĩa integration runner fail-closed, database explicit, không autoprovision/reset/cleanup, không discovery chạy tests ghi ngoài opt-in. Chỉ bắt đầu code/test changes sau review này theo yêu cầu bước 1–4.

### Gate C — Database thử nghiệm riêng

Đề xuất **`vietherb-test`**, nếu chưa tồn tại. Nếu đã tồn tại, không dùng lại hoặc reset tự động: cần kiểm tra read-only và xác nhận ownership/phạm vi, hoặc đề xuất tên mới để review. Không dùng database alias chưa resolve. Database test trên cùng DBMS dùng data root hiện tại; xác nhận cấu hình lưu trên D trước tạo.

DDL đề xuất để người dùng review, **chưa chạy**:

```cypher
// Run only after separate approval, on system.
CREATE DATABASE `vietherb-test` WAIT 30 SECONDS;
```

Không dùng `OR REPLACE`, `DROP`, `IF NOT EXISTS` che việc target đã tồn tại. Tên có dấu gạch ngang dùng backticks. [Neo4j: database naming](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/naming-databases/), [create databases](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/create-databases/).

Chỉ sau database được xác nhận và constraint DDL được duyệt riêng, tạo đúng năm unique constraints trong **vietherb-test**:

```cypher
CREATE CONSTRAINT rdf_term_key FOR (n:RdfTerm) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT rdf_triple_key FOR (n:RdfTriple) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT rdf_source_hash FOR (n:SourceArtifact) REQUIRE n.sha256 IS UNIQUE;
CREATE CONSTRAINT rdf_snapshot_key FOR (n:ImportSnapshot) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT rdf_run_id FOR (n:ImportRun) REQUIRE n.id IS UNIQUE;
```

Xác minh schema/index ONLINE sau DDL; không bỏ qua lỗi schema hoặc tạo constraints ở neo4j. Existence/type constraints nếu thêm phải liệt kê để duyệt trước, không tự mở rộng DDL.

### Gate D — Integration test matrix

| Nhóm | Thao tác chỉ trên database test đã duyệt | Kiểm chứng |
| --- | --- | --- |
| Routing/safety | Target allowlist và alias resolution | Không mở write session cho neo4j/system |
| Constraints | Tạo duplicate key trong explicit tx rồi rollback | Lỗi constraint; không để lại node/triple |
| Transactions | Tạo sentinel trong explicit tx, raise/rollback | Read transaction sau đó không thấy sentinel |
| Payload mismatch | Fixture riêng, conflicting term cùng key | Batch rollback, payload cũ không đổi |
| Missing MATCH | Endpoint thiếu trong synthetic batch | Callback raise; không có partial triple/ASSERTS commit |
| Structural corruption | Thêm duplicate link hoặc sửa payload fixture trong explicit tx | Validator fail; tx rollback; graph baseline không đổi |
| Snapshot lifecycle | Fixture LOADING/FAILED/VALIDATED | Visibility đúng; không publish failure; audit trạng thái nhất quán |
| Full VHO import/export | Terms rồi triples; export theo snapshot | Strict lexical/datatype/language round-trip 2646 triples |
| Idempotency | Reimport source/identity đúng, run ID mới | Terms/triples/role links/ASSERTS không tăng; run audit tăng có chủ ý |
| Run identity | Dùng lại run ID với source khác | Reject/rollback, không thêm TARGETS |
| Recovery | Inject failure giữa batches trong fixture riêng | Committed prefix không phục vụ retrieval, không reset/xóa dữ liệu |

Không dùng teardown xóa/reset database. Negative fixtures/corruption ưu tiên explicit transaction rollback; fixtures cần commit dùng namespace và snapshot riêng, giữ lại để audit. Không sửa ontology gốc hoặc xóa graph baseline. Chưa khẳng định concurrency safety; chỉ chạy single writer.

Kỳ vọng cho snapshot VHO sau import: 1385 RdfTerm (1288 IRI + 97 literals), 2646 RdfTriple, 7938 SUBJECT/PREDICATE/OBJECT links, 2646 ASSERTS; roots=6; literal occurrence languages en=80/vn=20. missing/extra/mismatch=0, source SHA đúng. Đếm scope snapshot, không dựa tổng database nếu có fixtures.

Mỗi run báo server/driver version, schema, database identity, source hash, codec/mapping version, code hashes, batch settings, fingerprint, raw validation và transaction outcomes; không credentials. Artifacts/temp giữ trên D. Thất bại bất kỳ → không publish, không sửa ontology hoặc tự reset database.

## 5. Điểm dừng

Chưa có đủ authentication để hoàn thành server inventory. Cần cơ chế credentials không qua chat để chạy lại read-only queries. Database test, constraints và integration writes **chưa được phê duyệt và chưa chạy**. Báo cáo này không yêu cầu bật writer ngay: sửa blockers và hoàn thành inventory trước, rồi mới xin phê duyệt DDL/test target cụ thể.
