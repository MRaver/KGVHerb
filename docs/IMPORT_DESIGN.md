# Thiết kế importer RDF/OWL → Neo4j cho Vietherb

> Cập nhật Phase 2B (2026-11-15): phần thiết kế gốc bên dưới được giữ để audit. Implementation hiện dùng byte-backed ImportPlan và writer chỉ cho database explicit `vietherb-test`, không còn mặc định `neo4j` hoặc API loose graph+manifest. Xem [báo cáo Phase 2B](PHASE2B_IMPLEMENTATION.md) và [HANDOFF](HANDOFF.md) cho gates/lifecycle/coverage hiện tại. Chưa thực hiện integration testing thực tế.

Ngày: 2026-11-15. Trạng thái: **đề xuất, chưa triển khai importer, chưa chạy Cypher**.

## 1. Phạm vi và bằng chứng

Chỉ phân tích và thiết kế. Không kết nối hoặc ghi Neo4j, không sửa ontology, không commit/push. Đã đọc [hướng dẫn](../AGENTS.md), [bối cảnh](PROJECT_CONTEXT.md), [bàn giao](HANDOFF.md), [inventory hiện tại](../src/vietherb_ontology/inventory.py) và [tests](../tests/test_inventory.py).

Môi trường thực đo: Windows, Python 3.15.2, RDFLib 7.6.0, neo4j driver 6.4.1. Người dùng cung cấp Neo4j Desktop 2026.10.2 Enterprise, database `neo4j`, URI `bolt://127.0.0.1:7687`. Phiên bản Desktop không phải phiên bản Neo4j server; phiên bản server, quyền schema và kết nối chưa được xác minh.

Git lúc kiểm tra: `main...origin/main`, HEAD `ea3201e4009f83420bf522e3a9f323ce3d89cfed`; `AGENTS.md`, `VHO.owl`, `docs/`, `src/`, `tests/` chưa được theo dõi. HEAD không đủ để tái lập mã chưa commit; cần manifest hash mã nguồn ở lần thí nghiệm sau.

Nguồn: [VHO.owl](../VHO.owl), SHA-256:

```text
2f7083f9fc1758edfadd45bf3b721661c585f1c2d3c750d509d94af78976aa73
```

Đã parse bytes bằng `Graph.parse(data=raw, format="xml", publicID=source.as_uri())`, với `rdflib.NORMALIZE_LITERALS=False`, không reasoning và không tải ontology imports. Hash tính trên cùng bytes được parse.

| Chỉ số trực tiếp từ graph | Kết quả |
| --- | ---: |
| RDF triples duy nhất | 2646 |
| `rdf:type owl:Class` | 1262 |
| `rdfs:subClassOf` | 1256 |
| `rdfs:subPropertyOf` | 2 |
| `rdf:type owl:AnnotationProperty` | 18 |
| `rdf:type owl:NamedIndividual` | 6 |
| `rdf:type owl:ObjectProperty` | 0 |
| `rdf:type owl:DatatypeProperty` | 0 |
| Blank nodes ở mọi vị trí | 0 |
| Chu trình trong đồ thị subclass | 0 |
| Class có hơn một superclass trực tiếp | 0 |
| Class không có superclass trực tiếp | 6 |
| Predicate khác nhau | 15 |
| IRI terms khác nhau trong cả ba vị trí | 1288 |
| Lượt literal ở object / literal duy nhất | 100 / 97 |
| Language tag theo lượt literal | `en`: 80; `vn`: 20 |
| Literal có `Literal.datatype` khác `None` | 0 |

Các dòng “18/6/0/0 owl declarations” trong baseline được xác định rõ ở bảng trên. “1256 rdfs edges” chỉ là subclass, không bao gồm hai subproperty triples.

Sáu roots có namespace `http://www.semanticweb.org/metruoi/ontologies/2017/2/VHO#` và local name `distribution`, `effect`, `fungi_kingdom`, `metabolite`, `morphology`, `plantae_family`.

Sáu named individuals đồng thời được khai báo là class: `alpha-amyrin`, `beta-amyrin`, `ellagic_acid`, `euphorbianin`, `rutin`, `taraxerol`. Không tách thành hai danh tính và không suy diễn quan hệ instance từ `subClassOf`.

| Predicate (prefix VHO giữ nguyên namespace trên) | Triples |
| --- | ---: |
| `rdf:type` | 1287 |
| `rdfs:subClassOf` | 1256 |
| `rdfs:label` | 33 |
| `rdfs:subPropertyOf` | 2 |
| `VHO:meta:other_name` | 27 |
| `VHO:meta:formula`, `VHO:meta:CAS_ID`, `VHO:meta:C_ID`, `VHO:meta:com_name` | 6 mỗi predicate |
| `VHO:meta:MW` | 5 |
| `VHO:meta:iupac_name`, `VHO:distri:province/state/city_name` | 4 mỗi predicate |
| `VHO:distri:nation_name` | 2 |
| `VHO:distri:geo_coordinate`, `VHO:has_herb` | 1 mỗi predicate |

`rdf:type`, `rdfs:label`, `rdfs:subClassOf`, `rdfs:subPropertyOf` được sử dụng nhưng không được khai báo property ngay trong file. Đây là vocabulary chuẩn, không phải lỗi cần “sửa”. Importer không được yêu cầu predicate có declaration mới chấp nhận triple.

### Hạn chế inventory hiện tại

- `class_roots` bị sai: chuyển class thành `str` rồi truyền vào `graph.objects`; phép kiểm tra độc lập bằng `URIRef` cho 6, trong khi `build_inventory` trả 1262. Không dùng trường roots trong [JSON cũ](ontology_inventory.json) làm ground truth.
- Test tên `test_parser_preserves_original_iri_and_literal` dùng `URIRef` ở object, không kiểm tra `Literal` thật.
- Parser chưa chủ động tắt literal normalization; test hash hiện tính lại từ cùng file nên không khóa baseline vào hash đã duyệt.
- Bộ test hiện hữu chạy ngày này: **3 tests passed, 0.240s**, exit code 0. Đây không phải chứng minh importer lossless. Chưa sửa code theo giới hạn nhiệm vụ.

## 2. Quyết định kiến trúc

Chọn **canonical triple store trên Property Graph**, cộng projection tùy chọn cho truy vấn GraphRAG. Không chọn cách chỉ chuyển class thành label, predicate thành relationship type và literal thành property: cách đó dễ mất đa trị, language, datatype, declaration và provenance.

```text
bytes nguồn + SHA-256
  → RDFLib (asserted graph, không inference)
  → term codec + triple codec có phiên bản
  → ImportSnapshot → ASSERTS → RdfTriple
                              ├─ SUBJECT   → RdfTerm
                              ├─ PREDICATE → RdfTerm
                              └─ OBJECT    → RdfTerm
  → export + so sánh đầy đủ → snapshot VALIDATED
  → projection truy vấn tùy chọn, có thể tái tạo
```

Các label/relationship ở sơ đồ là **cấu trúc lưu trữ nội bộ**, không phải entity/quan hệ y học mới và không được xuất thành RDF ontology. Một RdfTriple cũng không tự tạo các assertion `rdf:Statement` trong ontology.

### Mapping chuẩn

| RDF / metadata | Property Graph | Quy tắc bảo toàn |
| --- | --- | --- |
| IRI ở subject/predicate/object | `RdfTerm {key, kind:'iri', iri}` | Chuỗi IRI đầy đủ, không lowercase, decode URL, rút gọn hoặc thay ký tự |
| Literal | `RdfTerm {key, kind:'literal', lexical, datatypePresent, datatype, languagePresent, language}` | `lexical=str(term)`, không dùng `toPython()` |
| Blank node | `RdfTerm {key, kind:'bnode', scope, canonicalId}` | Scope theo snapshot; xem chính sách bnode bên dưới |
| Một triple asserted | `RdfTriple {key, subjectKey, predicateKey, objectKey}` + 3 liên kết term | Không phụ thuộc declaration; một triple không mất đi khi có projection |
| Thuộc nguồn nào | `(ImportSnapshot)-[:ASSERTS]->(RdfTriple)` | Một triple có thể thuộc nhiều snapshot |
| Bytes nguồn | `SourceArtifact {sha256, byteCount}` | Tách danh tính nội dung khỏi đường dẫn |
| Snapshot | `{key, sourceSha256, mappingVersion, parserPolicy, state}` | Bất biến khi VALIDATED |
| Lần thực thi | `ImportRun {id, status, settingsJson, versionsJson, ...}` | Mỗi lần có ID mới, liên kết `TARGETS` snapshot |

`datatypePresent=false` → lưu `datatype=''`; `languagePresent=false` → `language=''`. Flags phân biệt missing với dữ liệu; không dựa vào property null vì Neo4j không lưu null. Literal có language giữ tag nguyên gốc, kể cả `vn`, không tự sửa thành `vi`. Trong RDF 1.1 language literal có datatype ngữ nghĩa `rdf:langString`; RDFLib hiện báo `.datatype=None` cho dữ liệu này. Export phải dùng `Literal(lexical, lang=language, normalize=False)`, không thêm datatype cùng language. Typed literal dùng `datatype=URIRef(datatype)`, literal không language/datatype giữ đúng representation parser. Có thể thêm `effectiveDatatype` dẫn xuất nhưng tuyệt đối không dùng nó thay payload khi export.

### Khóa ổn định

Định nghĩa codec `term-v1` với JSON array UTF-8: `ensure_ascii=False`, `separators=(',', ':')`, không Unicode normalization. Ví dụ payload IRI `["iri", iri]`; literal `["literal", lexical, datatype-or-null, language-or-null]`. Key là SHA-256 của bytes có prefix phiên bản. Triple key = SHA-256 codec `["triple-v1", subjectKey, predicateKey, objectKey]`; không nối bằng delimiter tự chọn.

Khi key đã tồn tại, **đối chiếu toàn bộ payload**, khác biệt phải fail/rollback, không ghi đè. Đây là kiểm tra collision hoặc sai codec. IRI cùng chuỗi luôn cùng term, dù vừa class vừa individual. Không dùng Neo4j internal ID làm định danh lâu dài.

Snapshot key hash bộ `(sourceSha256, parserPolicyVersion, mappingVersion, effectiveBaseIRI, graphScope)`. Đường dẫn Windows lưu ở run, không là identity của source; base IRI phải ghi rõ vì relative IRI có thể resolve khác khi di chuyển file. Với VHO, `xml:base` hiện có xác định namespace.

Baseline không có blank nodes. MVP phải **fail closed nếu gặp bnode** cho đến khi triển khai canonicalization đã chọn và test; không dùng ID ngẫu nhiên RDFLib để hứa idempotency. Extension dùng canonical label trong source-scoped graph, pin thuật toán/version, kiểm tra graph isomorphism cho graph đối xứng; không trộn bnodes của hai source. RDF dataset/named graphs ngoài phạm vi RDF/XML một graph hiện tại; cần codec quad/graph name riêng trước khi hỗ trợ.

## 3. RDF types, annotation và projection

Mọi `rdf:type`, kể cả khai báo ontology/property, được lưu như triple bình thường. Không ép mỗi IRI vào đúng một loại node. Các labels `OwlClass`, `NamedIndividual` nếu thêm chỉ là cache của asserted types và phải truy ngược triple nguồn.

Annotation literal đa trị được giữ thành từng triple. Không suy luận `has_herb`, `meta:has_effect` thành quan hệ điều trị. Không tự thêm property declaration, domain/range hoặc suy luận một chất chữa bệnh từ tên class.

Projection tùy chọn chỉ sau validation:

- `SUBCLASS_OF`: đúng chiều subject → object của các triple `rdfs:subClassOf` asserted.
- `RDF_TYPE`: đúng các triple `rdf:type` asserted.
- Label search index: mỗi label kèm language và triple key; không thay canonical store.
- Mỗi projection edge mang `snapshotKey`, `tripleKey`, `projectionVersion`; chỉ đọc snapshot VALIDATED. Không export projection thành triple lần nữa.
- Suy luận tương lai nằm riêng, có `ruleId`, engine/version và premise triple keys; không trộn với asserted graph, không tính vào 2646 triples.

## 4. Constraints và Cypher dự kiến

**Các lệnh sau chỉ là thiết kế, chưa thực thi hoặc kiểm chứng trên server.** Cần kiểm tra server bằng `CALL dbms.components()` trong giai đoạn triển khai, xác minh database và schema hiện có. Không drop constraint hoặc reset database để làm import chạy được.

```cypher
CREATE CONSTRAINT rdf_term_key IF NOT EXISTS
FOR (n:RdfTerm) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT rdf_triple_key IF NOT EXISTS
FOR (n:RdfTriple) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT rdf_source_hash IF NOT EXISTS
FOR (n:SourceArtifact) REQUIRE n.sha256 IS UNIQUE;
CREATE CONSTRAINT rdf_snapshot_key IF NOT EXISTS
FOR (n:ImportSnapshot) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT rdf_run_id IF NOT EXISTS
FOR (n:ImportRun) REQUIRE n.id IS UNIQUE;
```

Uniqueness không bảo đảm existence: Enterprise có thể thêm `REQUIRE n.key IS NOT NULL` tương ứng, và existence cho kind, triple endpoint keys, source hash. Validate conditional payload theo kind trong Python. `SHOW CONSTRAINTS` phải xác nhận đúng schema, không chỉ tên hoặc thành công của `IF NOT EXISTS`. Không constraint nào ở đây bảo đảm mỗi triple có chính xác một SUBJECT/PREDICATE/OBJECT; validator phải kiểm tra riêng. Constraints tạo trước dữ liệu; không cần index trùng với unique index. [Neo4j constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/), [cú pháp](https://neo4j.com/docs/cypher-manual/current/schema/syntax/).

Batch terms, `$rows` đã qua codec/validation, properties chỉ gồm trường payload đã quy định:

```cypher
UNWIND $rows AS row
MERGE (n:RdfTerm {key: row.key})
ON CREATE SET n += row.properties
RETURN n.key AS key, properties(n) AS stored;
```

Batch triples, chỉ chạy khi snapshot đang LOADING do writer hiện tại sở hữu:

```cypher
MATCH (snap:ImportSnapshot {key: $snapshotKey})
WHERE snap.state = 'LOADING'
UNWIND $rows AS row
MATCH (s:RdfTerm {key: row.subjectKey})
MATCH (p:RdfTerm {key: row.predicateKey})
MATCH (o:RdfTerm {key: row.objectKey})
MERGE (t:RdfTriple {key: row.key})
ON CREATE SET t.subjectKey = row.subjectKey,
              t.predicateKey = row.predicateKey,
              t.objectKey = row.objectKey
MERGE (t)-[:SUBJECT]->(s)
MERGE (t)-[:PREDICATE]->(p)
MERGE (t)-[:OBJECT]->(o)
MERGE (snap)-[:ASSERTS]->(t)
RETURN t.key AS key, t.subjectKey AS subjectKey,
       t.predicateKey AS predicateKey, t.objectKey AS objectKey;
```

Managed transaction callback phải consume kết quả, so sánh **số rows và payload** trước commit; `MATCH` thiếu endpoint có thể làm mất row âm thầm. Nếu khác, raise để rollback toàn batch kể cả edges vừa thêm. Predicate phải là IRI; subject không được literal. Không dùng `ON MATCH SET` để ghi đè nội dung canonical. `MERGE` đi cùng uniqueness constraints; không tự bảo đảm uniqueness dưới mọi concurrent pattern. [Neo4j MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/).

Export theo snapshot, không export cả database:

```cypher
MATCH (snap:ImportSnapshot {key: $snapshotKey})-[:ASSERTS]->(t:RdfTriple)
MATCH (t)-[:SUBJECT]->(s:RdfTerm)
MATCH (t)-[:PREDICATE]->(p:RdfTerm)
MATCH (t)-[:OBJECT]->(o:RdfTerm)
RETURN t.key AS tripleKey, properties(s) AS subject,
       properties(p) AS predicate, properties(o) AS object
ORDER BY tripleKey;
```

Không dùng `DISTINCT` che duplicate structural edges. Validator được đọc LOADING snapshot của lần import để kiểm chứng; truy vấn phục vụ người dùng bắt buộc state VALIDATED.

## 5. Pipeline, batching và idempotency

Các module dự kiến (chưa tạo): source manifest → parser → term/triple codec → batch planner → Neo4j writer → exporter → validator → research report. Parser/codec không phụ thuộc database; writer chỉ nhận record đã validate.

1. Đọc bytes một lần, SHA-256 và parse chính bytes đó; kiểm tra hash baseline. Process parser riêng đặt `NORMALIZE_LITERALS=False` trước parse; không đổi global setting giữa các thread. Không tự fetch `owl:imports`; bảo toàn triple imports nếu có. Với XML bên ngoài, bổ sung kiểm soát external entities/network và giới hạn tài nguyên.
2. Dry-run xuất manifest và thống kê, không cần password. Kiểm tra payload/key/role, không sanitize IRI.
3. Khi được triển khai, dùng database explicit `neo4j`, URI cấu hình; secret từ môi trường hoặc secret store, không ghi password/URI chứa secret vào report/log.
4. Một writer tuần tự cho mỗi database ở MVP; không chạy hai importer đồng thời. Nếu cần đa writer phải bổ sung khóa/lease server-side trước, không coi trường owner tự nó là khóa. Tạo run và snapshot LOADING; liên kết snapshot với SourceArtifact bằng `FROM_SOURCE`.
5. Sắp xếp theo stable key; nhập terms trước triples. Batch mặc định đề xuất 500 rows, kèm giới hạn tổng bytes (ví dụ 4 MiB), ghi vào settings; chưa tuyên bố đây là giá trị tối ưu. Dùng `session.execute_write` và `UNWIND $rows`, không nối Cypher từ dữ liệu.
6. Callback retry-safe: UUID run và input tính ngoài callback, không ghi report/checkpoint filesystem trong callback. Neo4j batch commit là atomic; checkpoint lưu cùng transaction hoặc replay toàn bộ batch bằng MERGE sau crash. Không dựa vào thứ tự kết quả UNWIND.
7. Validation đầy đủ; nếu pass mới chuyển snapshot VALIDATED trong transaction cuối. Nếu fail, ghi run FAILED, giữ snapshot không phục vụ retrieval. Chưa có policy xóa tự động; cleanup là nhiệm vụ riêng cần chấp thuận.
8. Reimport cùng snapshot VALIDATED: kiểm tra manifest và validation rồi no-op đối với canonical graph; tạo run audit mới là chủ ý, không phải lỗi idempotency. Resume LOADING/FAILED chỉ sau xác nhận không còn writer sống và replay idempotent.
9. Bytes nguồn hoặc mapping policy đổi → snapshot mới. Không xóa triples nguồn cũ, không union nguồn mới/cũ khi trả lời; application chọn snapshot rõ ràng. Shared terms/triples vẫn dùng được giữa snapshots.

Tính atomic cho toàn source là **logical visibility**, không phải một transaction duy nhất: batch đã commit có thể còn trong database nhưng chưa được query phục vụ người dùng. Snapshot validated không được tiếp tục thêm ASSERTS.

## 6. Validation lossless bắt buộc

Mục tiêu: tái dựng **cùng tập RDF terms/triples**, không phải cùng bytes XML. Prefix, XML whitespace, comment, thứ tự và assertion trùng trong serialization không thuộc RDF graph set; bytes gốc + hash vẫn phải giữ làm provenance.

### So sánh đầy đủ

1. Tạo `expected` từ parse nguồn độc lập với writer, dùng tuple từng term: IRI `(iri, value)`; literal `(literal, lexical, datatype-or-null, language-or-null)`. Không dùng so sánh numeric values để thay lexical equality.
2. Export mọi assertion trong snapshot, kiểm tra cardinality raw rows = 2646, 2646 triple keys duy nhất; mỗi triple đúng một link từng role và endpoint khớp stored keys; mỗi predicate là IRI, không dangling endpoint.
3. Recompute term/triple keys từ payload; reconstruct `URIRef` hoặc `Literal(..., normalize=False)`. So sánh strict tuple sets: `missing=expected-exported`, `extra=exported-expected`, cả hai rỗng, lexical/datatype/language mismatch = 0. Đếm tổng bằng nhau là chưa đủ.
4. Baseline không bnode: kiểm tra equality toàn tập và fingerprint SHA-256 của sorted canonical JSON records. Khi hỗ trợ bnode phải thêm isomorphism, không so ID parser trực tiếp.
5. Reparse bản RDF export để kiểm tra compatibility; với serializer có thể đổi biểu diễn plain/xsd:string, strict payload comparison ở bước 3 vẫn là chuẩn chính, đồng thời báo riêng RDF-semantic equality.
6. So predicate histogram, declarations, overlap class/individual, language histogram, roots, cycles và multiple inheritance với baseline. Không xem cycle hoặc multiple inheritance là RDF lỗi ở nguồn tương lai.

Kỳ vọng thiết kế cho database sạch, một snapshot, canonical layer không projection: **1288 IRI terms + 97 literal terms = 1385 RdfTerm**, **2646 RdfTriple**, **7938 role links**, **2646 ASSERTS**. Đây là kỳ vọng từ graph nguồn, **chưa phải số liệu import đo được**; không dùng tổng node database khi có nguồn khác.

Acceptance: 2646 triples khôi phục; missing/extra/mismatch = 0; 100 literal occurrences giữ language `en:80`, `vn:20`; 97 literals duy nhất; mọi hash hợp lệ; reimport không tăng terms/triples/ASSERTS/projection trong snapshot. Một lỗi bất kỳ chặn VALIDATED.

## 7. Thiết kế kiểm thử tự động

Không thêm parser/mapping code trong nhiệm vụ này; dưới đây là test plan cho giai đoạn triển khai.

| Nhóm | Trường hợp | Điều kiện pass |
| --- | --- | --- |
| Parser/codec unit | IRI có `:`, `/`, `#`, Unicode; hai IRI cùng local name | Không đổi IRI, không collision |
| Literal unit | `"01"^^xsd:integer` khác `"1"^^xsd:integer`; decimal, boolean, datetime, invalid lexical | Không coercion hoặc mất lexical; invalid lexical giữ nguyên và báo riêng |
| Literal unit | `@en`, `@vn`, plain, typed string, empty string, newline, quote, backslash | Round-trip tuple giữ datatype/language và escaping |
| Graph unit | Đa trị, predicate chưa khai báo, resource vừa class vừa individual | Đủ triples, không tự thêm declaration |
| Taxonomy unit | 6 roots thật; fixture cycle, multiple inheritance | URIRef lookup đúng; report rõ, không sửa graph |
| Bnode boundary | Bnode/restriction/list | MVP reject rõ trước ghi; extension có test isomorphism và scope |
| Regression nguồn | Hash cố định đã duyệt + mọi baseline trong mục 1 | Phát hiện ontology thay đổi; không tự cập nhật expected |
| Integration | Database test riêng, constraints và import/export | Strict equality 2646, cardinality links đúng |
| Idempotency | Import hai lần; crash giữa batches; retry callback | Canonical counts không tăng, run audit tách biệt |
| Provenance | Hai sources cùng triple, source mới bỏ triple | Truy vấn snapshot không lẫn nguồn, source cũ không bị xóa |
| Negative validation | Xóa/mutate một link, language, datatype; payload cùng key khác nội dung | Validator fail, không publish |
| Isolation | Run fail giữa chừng; cố import đồng thời | Snapshot chưa validated không xuất hiện; concurrency bị chặn |

Fixtures tổng hợp chỉ là dữ liệu kỹ thuật, đặt namespace test và ghi rõ không phải bằng chứng y học. Integration chỉ chạy sau khi có database test được cấp; không reset database `neo4j` của người dùng. Temp files/reports đặt trên D. Chạy tests hiện tại bằng PowerShell:

```powershell
$env:PYTHONPATH='src'
$env:TEMP='D:\vietherb_rag'
$env:TMP='D:\vietherb_rag'
.\venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

## 8. Provenance và báo cáo nghiên cứu

Mỗi run ghi: source SHA-256/byte size/path; ontology IRI; effective base; parser format, normalization/imports/reasoning policy; Python/RDFLib/driver/server/OS versions; mapping/codec version; Git HEAD + dirty flag + source-code hashes; database name; batch row/byte limits; timestamps UTC; retry count; counts/differences/fingerprint; validation outcome. Không có credentials. Lưu raw manifest JSON và Markdown tóm tắt, không chỉ log terminal.

Đo riêng parse, encode, DB write, validation, tổng wall time, peak memory và storage nếu đo được; `not_measured` khi chưa có phép đo. Ghi CPU/RAM, server config, warm/cold cache và kích thước data. Với 2646 triples không suy rộng thành benchmark quy mô lớn.

Thí nghiệm đề xuất: canonical-only so với canonical+projection; batch 100/500/1000; first import so với idempotent rerun. Giữ source/settings/phần cứng cố định ngoài biến độc lập; định trước số lần lặp (ví dụ 5), lưu từng run và median/range. Các giá trị batch/lặp là kế hoạch, chưa là kết quả. Nếu so lossless với mapping lossy, báo thiếu triples/literal metadata như trade-off, không gọi chúng tương đương ngữ nghĩa.

Ontology assertions chỉ là nội dung nguồn, không mặc nhiên là bằng chứng lâm sàng. Retrieval/generation cần trích dẫn snapshot + triple keys; đánh giá chất lượng câu trả lời là thí nghiệm riêng, không suy ra từ import thành công.

## 9. Rủi ro và điểm cần xác nhận khi triển khai

- Inventory roots/test literal hiện thiếu coverage: sửa và bổ sung regression trước reuse.
- Literal normalization có thể làm mất lexical trước khi mapping; dùng process parser policy cố định và synthetic tests vì VHO hiện không có typed literals để kiểm chứng nhánh này.
- Language tag `vn` phải giữ như nguồn; không sửa ontology nhân danh chuẩn hóa.
- Hash collision/payload bug, partial import, silent MATCH row loss và duplicate role links cần fail-fast; uniqueness constraint không thay validator.
- Canonical triple nodes tốn nhiều hops/storage; projection tối ưu retrieval chỉ sau đo, không bỏ canonical truth.
- Chưa xác minh phiên bản Neo4j server/permissions/driver compatibility runtime. Cypher ở đây là candidate cần integration test trên server thật; không suy từ số phiên bản Desktop.
- RDF/XML graph không bao trùm named graphs, RDF-star hoặc bnode canonicalization. Input ngoài contract phải bị chặn rõ, không bỏ qua âm thầm.
- Bảo toàn graph không đồng nghĩa OWL reasoning hoặc kiểm chứng consistency/clinical evidence. Những việc đó ngoài importer asserted-only.

## 10. Tài liệu kỹ thuật đối chiếu

- [Neo4j MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/): patterns/constraints.
- [Neo4j constraint syntax](https://neo4j.com/docs/cypher-manual/current/schema/syntax/): DDL đề xuất.
- [Neo4j constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/): uniqueness/existence khác nhau.
- [Neo4j UNWIND](https://neo4j.com/docs/cypher-manual/current/clauses/unwind/): batch rows không bảo đảm thứ tự.
- RDFLib 7.6.0 cài tại máy: `rdflib/term.py`, constructor Literal dùng `rdflib.NORMALIZE_LITERALS` khi không truyền normalize; kiểm tra source local ngày 2026-11-15. Thiết kế codec/provenance/validation là đề xuất của dự án, chưa là implementation đã chạy.
