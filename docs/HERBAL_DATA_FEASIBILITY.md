# KGVHerb C1 — Medicinal Plant Data Feasibility Audit

Ngày kiểm tra: **2026-11-23**. Kết luận: **CONDITIONAL** cho một pilot KG lấy cây thuốc làm trung tâm, có truy nguyên nguồn. Có thể bắt đầu từ định danh thực vật và các ghi nhận thành phần hóa học; chưa đủ cơ sở coi các nguồn này là một benchmark hỏi đáp công dụng thuốc tiếng Việt đã mở và có chứng cứ đầy đủ.

**Nhãn chứng cứ:** VERIFIED = quan sát trực tiếp metadata, giấy phép, source hoặc HTTP HEAD; DOCUMENTED = mô tả của tác giả; UNKNOWN = chưa thể xác minh; BLOCKED = chưa thể sử dụng trong phạm vi truy cập hiện tại. “Có nguồn trích dẫn” không đồng nghĩa với chứng minh hiệu quả điều trị.

Phạm vi: đọc trang công khai, metadata API, danh mục tệp và source notebook; không đọc các archive dữ liệu, không tải CSV/TSV payload, ảnh, mô hình, hoặc kiểm tra toàn bộ bản ghi. Không crawling, scraping hàng loạt, chạy notebook, cài đặt, import Neo4j hay thực nghiệm. Chỉ tạo báo cáo này; giữ nguyên các tệp có sẵn, kể cả HANDOFF và các thay đổi Git đã tồn tại.

## 1. So sánh nguồn

| Nguồn | Khả dụng và định dạng xác minh được | Định danh / loại dữ liệu | Provenance và giới hạn | Vai trò pilot |
|---|---|---|---|---|
| [LOTUS](https://lotus.naturalproducts.net/) | VERIFIED: các endpoint SDF, Mongo và SMILES trả HEAD 200. Giao diện ghi phiên bản February 2021. Zenodo công khai các CSV.gz/TSV.gz có phiên bản; không tải payload. | Compound: LOTUS ID, InChI/InChIKey, SMILES; organism: tên khoa học và định danh taxonomy tùy bản xuất. | DOCUMENTED: liên kết structure–organism–reference; Wikidata hỗ trợ statement và reference. Không bảo đảm mọi hàng đều có trích dẫn đầy đủ hoặc có full text. Không phải nguồn công dụng truyền thống mặc định. | Nguồn chính cho ghi nhận compound–taxon có tài liệu gốc. |
| [Enveda ethnobotany](https://github.com/enveda/ethnobotany) | VERIFIED: gói association TSV.gz và TSV.zip hiện diện, HEAD 200; còn TSV, JSON và ZIP mapping trong cây repository. Không tải/decompress các gói. | Source notebook dùng plant_curie, plant_name, disease_curie, chemical_curie, database; taxonomy utility dùng NCBITaxon. | Notebook đọc trường trích dẫn vào biến pmid; mức điền và tính hợp lệ chưa kiểm tra. Có cả association từ database và từ khai thác văn bản bằng mô hình. README liệt kê VietHerb, nhưng các hàng VietHerb cụ thể chưa xác minh. | Nguồn ứng viên cho association và chuẩn hóa, chưa được coi là tập công dụng đã kiểm chứng. |
| [ScienceDB: Viet Medi Species 2026](https://www.scidb.cn/en/detail?dataSetId=d2e66ca3d73540739a39789d9b1cf989) | VERIFIED: trang PUBLIC, metadata mở và giấy phép phân tầng đọc được. Trang công bố một gói; mục lục được lập chỉ mục nêu Archive.zip, 21.67 GB. Bảng tệp tải trong trình duyệt hiện trống: tải trực tiếp/authentication **UNKNOWN**, không thử tải ZIP. | DOCUMENTED: CSV metadata; speciesKey của GBIF, scientificName, canonicalName, vietnameseName, taxonomicStatus, phân loại; ảnh đa giới sinh vật. | Taxonomy và nguồn ảnh GBIF có đường truy nguyên được mô tả. Citation cho từng tên Việt, nguồn catalogue và nội dung từng CSV chưa xác minh. Không cung cấp chứng cứ công dụng chỉ vì một loài được gắn nhãn medicinal. | Lớp tên Việt–taxon; bỏ ảnh khỏi MVP. |
| [ViHerbQA](https://github.com/queenley/ViHerbQA) | VERIFIED: repository công khai nhưng dataset chỉ có .gitignore; download.sh rỗng. README yêu cầu liên hệ tác giả qua email. Benchmark **BLOCKED** cho sử dụng ngay; không gửi email. | Code mong đợi train.csv, val.csv, test.csv với question, final_answer, context. Đây là schema mong đợi, không phải payload đã xác minh. | README mô tả QA sinh bằng LLM từ bài viết; citation/source ID cho từng câu, chất lượng gold và tách tập chưa xác minh. | Tham khảo phương pháp; không làm điều kiện bắt buộc để bắt đầu pilot. |

Không có số lượng thực vật chung, số hàng VietHerb, độ đầy đủ citation hoặc thống kê overlap nào được đo trong audit này. Các con số xuất hiện trong mô tả dataset của tác giả không được xem là thống kê đã tái kiểm chứng.

### Bằng chứng tệp và đường tải

**LOTUS — HEAD, không GET dữ liệu:**

| Endpoint | HTTP / header quan sát | Điều chưa xác minh |
|---|---|---|
| [/download/sdf](https://lotus.naturalproducts.net/download/sdf) | 200; Content-Type chemical/x-mdl-sdfile; Content-Disposition LOTUS_DB_LATEST.zip; 105,371,084 bytes công bố trong header | MIME và đuôi ZIP không thống nhất; chưa kiểm tra magic bytes hay thành viên trong archive. |
| [/download/mongo](https://lotus.naturalproducts.net/download/mongo) | 200; application/zip; LOTUSlatest.zip; 766,883,885 bytes | Định dạng MongoDB dump được giao diện mô tả; layout/BSON bên trong chưa kiểm tra. |
| [/download/smiles](https://lotus.naturalproducts.net/download/smiles) | 200; text/plain; LOTUS_DB.smi; 25,345,417 bytes | Chưa kiểm tra cột, encoding hay khả năng giữ reference của từng dòng. |

[Trang tải](https://lotus.naturalproducts.net/download) và [documentation](https://lotus.naturalproducts.net/documentation) được đọc qua giao diện trình duyệt vì trình trích xuất web trả trang rỗng. HEAD 200 chứng minh endpoint phản hồi tại thời điểm kiểm tra, không chứng minh tải hoàn chỉnh hay dữ liệu đúng.

[Zenodo 5794106](https://zenodo.org/records/5794106), qua [metadata API](https://zenodo.org/api/records/5794106), hiện liệt kê **260413_frozen.csv.gz**, **260413_frozen_metadata.csv.gz**, tệp changes report và source exporter; nhãn access=open, license=cc-by-4.0. Không đồng nhất bản đang được API trả về với snapshot 2021 được bài báo nhắc tới. [Zenodo 7534077](https://zenodo.org/records/7534077) có **organism_metadata.tsv.gz**, **reference_metadata.tsv.gz**, **structure_metadata.tsv.gz**; metadata API cũng ghi CC BY 4.0. Ba bảng metadata riêng không thay thế bảng liên kết occurrence; schema join cần kiểm tra khi được phép lấy mẫu sau này.

**Enveda — commit 07d0a6b27ea572465305dcafc82e260756b011c2:** [cây data](https://github.com/enveda/ethnobotany/tree/07d0a6b27ea572465305dcafc82e260756b011c2/data) có:

- processed/plant_disease_associations.tsv.gz — HEAD 200; 1,168,762 bytes.
- processed/plant_chemical_associations.tsv.zip — HEAD 200; 6,052,431 bytes.
- processed/plant_disease_collapsed.tsv.gz, các bảng correlation TSV.gz và bảng non_binary TSV.
- mapping/country_codes.tsv, mondo_upper_level_mapping.tsv, smiles.tsv.zip và trefle_grounding.json.

Định dạng TSV và cách nén được xác nhận thêm bằng lời gọi read_csv với sep='\t' trong [notebook 2_1](https://github.com/enveda/ethnobotany/blob/07d0a6b27ea572465305dcafc82e260756b011c2/notebooks/2_1_data_processing.ipynb). Kích thước trên là metadata tệp, không phải số bản ghi. Không suy ra schema đầy đủ của file collapsed/correlation từ tên tệp.

**ScienceDB:** DOI [10.57760/sciencedb.013q9](https://doi.org/10.57760/sciencedb.013q9), V1. ZIP chỉ được xác nhận ở mức mục lục được lập chỉ mục; CSV bên trong và đuôi định dạng ảnh **UNKNOWN**. Một đường bổ sung do tác giả công bố là [VietMediSpecies, nhánh feature/update](https://github.com/trientran/VietMediSpecies/tree/4e64ae324d2b2f3fbff099e8c7bd841f80741ef6): danh mục Git có **merged_species_with_gbif_metadata.csv**, **csv/species_metadata.csv**, **csv/gbif_species_match_results.csv** và các CSV khác. Chỉ đọc cây tệp; không tải CSV. Sự tương đương với metadata trong ZIP và phạm vi áp dụng giấy phép ScienceDB cho từng CSV trên GitHub vẫn cần xác nhận.

**ViHerbQA — commit 32e412f285d6bcf4a2112e7c6008ed862a47f854:** [dataset/](https://github.com/queenley/ViHerbQA/tree/32e412f285d6bcf4a2112e7c6008ed862a47f854/dataset) không chứa tập QA theo cây Git. [Dataloader](https://github.com/queenley/ViHerbQA/blob/32e412f285d6bcf4a2112e7c6008ed862a47f854/src/model/dataloader.py) xác nhận schema CSV mong đợi. Có script split không chứng minh các split thực tế đã được phát hành.

## 2. Giấy phép: code, metadata và dữ liệu tách riêng

| Nguồn / artifact | Code | Metadata / dataset | Quyết định tái sử dụng |
|---|---|---|---|
| LOTUS website và công cụ | Footer website ghi web application MIT, code LOTUS GPLv3; [lotus-processor hiện tại](https://github.com/lotusnprod/lotus-processor/blob/main/LICENSE) là AGPLv3. Đây là các thành phần/phiên bản khác nhau. | Các deposit Zenodo đã kiểm tra ghi **CC BY 4.0**. [Structured Wikidata](https://www.wikidata.org/wiki/Wikidata:Licensing) là **CC0**; phần văn bản ngoài structured namespaces có điều khoản khác. | Gắn license theo đúng artifact, không gắn “LOTUS=CC0” cho mọi dump. License paper/full text không được suy ra từ license metadata. |
| Enveda | [LICENSE tại commit đã ghim](https://github.com/enveda/ethnobotany/blob/07d0a6b27ea572465305dcafc82e260756b011c2/LICENSE): MIT, copyright Enveda 2026; đã đọc trực tiếp. | Không tìm thấy giấy phép dữ liệu chuyên biệt trong cây tệp đã kiểm tra. MIT của software không tự xác nhận quyền đối với nội dung VietHerb, COCONUT, nguồn literature hay các database bên thứ ba. | Code có grant rõ; quyền tái phân phối từng lớp dữ liệu upstream **UNKNOWN**. Giữ nguồn riêng, chưa hợp nhất thành một dataset tuyên bố mở hoàn toàn. |
| ScienceDB | Bản ghi không cấp giấy phép code. Không thấy LICENSE trong cây repository tác giả bổ sung đã kiểm tra: **UNKNOWN** cho code đó. | Trang ghi rõ curated CSV metadata/annotations CC BY 4.0. Ảnh giữ license của publisher GBIF, có thể CC0, CC BY hoặc CC BY-NC; không được tác giả tái cấp phép. | Metadata là ứng viên tốt sau khi xác nhận artifact; MVP không cần ảnh. Không áp dụng CC BY của metadata lên ảnh. |
| ViHerbQA | [LICENSE đã ghim](https://github.com/queenley/ViHerbQA/blob/32e412f285d6bcf4a2112e7c6008ed862a47f854/LICENSE): MIT. | Tập QA qua email, điều khoản dataset và quyền của bài viết gốc **UNKNOWN**. | Chưa dùng benchmark/data chỉ dựa vào MIT của repository. Cần artifact, grant dữ liệu, nguồn bài viết và quy tắc chia tập. |

Đây là kiểm kê điều khoản quan sát được, không phải kết luận rằng tác giả sở hữu mọi quyền upstream. Tính công khai của một URL không thay thế license. Một kết quả cache raw-main của Enveda trả GPLv2 trái với phiên bản hiện tại; báo cáo dùng LICENSE MIT đã đọc tại commit cụ thể, không dùng cache làm nguồn quyết định.

## 3. Enveda có dữ liệu hoặc mapping VietHERB tái sử dụng được không?

**Có bằng chứng ở mức nguồn đầu vào:** [README](https://github.com/enveda/ethnobotany/blob/07d0a6b27ea572465305dcafc82e260756b011c2/README.md) liệt kê VietHerb và dẫn bài VIETHERB. Có các gói association đã chuẩn hóa, nhưng **chưa xác minh** trong payload rằng có hàng được gắn database=VietHerb, giá trị chính xác của nhãn đó, số lượng hay ID bản ghi gốc.

[Notebook 2_1](https://github.com/enveda/ethnobotany/blob/07d0a6b27ea572465305dcafc82e260756b011c2/notebooks/2_1_data_processing.ipynb) sử dụng plant_curie, disease_curie, chemical_curie, database; vòng lặp đọc năm giá trị cho plant–disease và sáu cho plant–chemical, trong đó một giá trị được đặt tên pmid. Điều này chứng minh mô hình xử lý có chỗ cho nguồn/citation, **không chứng minh mỗi hàng có PMID hợp lệ** hoặc PMID đó hỗ trợ đúng association.

Cây Git hiện tại có processed và mapping nhưng không có thư mục raw hay mapping riêng được đặt tên VietHerb, dù README mô tả raw/intermediary data. **Kết luận: có ứng viên dữ liệu dẫn xuất; chưa có gói VietHERB độc lập, có license rõ và lineage row-level đã xác minh để dùng ngay.** Các mapping MONDO/Trefle không được coi là mapping VietHERB nếu chưa kiểm tra.

[Notebook relation extraction](https://github.com/enveda/ethnobotany/blob/07d0a6b27ea572465305dcafc82e260756b011c2/notebooks/1_data_processing_relation_extraction_t0pp-bern2.ipynb) mô tả đầu vào PubMed/sentence/MeSH/NCBITaxon và dùng mô hình đánh giá association. Nhãn high confidence trong pipeline không phải thẩm định lâm sàng. Không chạy pipeline và không chuyển association thành khẳng định chữa bệnh.

## 4. Liên kết giữa nguồn và KG có provenance

### Định danh

- **Thực vật:** ScienceDB công bố speciesKey, scientificName, canonicalName, taxonomicStatus và tên Việt phân tách bằng dấu chấm phẩy. Enveda utility dùng ncbitaxon:; LOTUS/Wikidata có taxon identifiers tùy record. **Có khả năng liên kết**, nhưng cần crosswalk GBIF–NCBITaxon–Wikidata hoặc đối sánh tên khoa học có tác giả, bậc phân loại, synonym và phiên bản backbone. Không có overlap nào được đo.
- **Tên Việt:** là alias có ngôn ngữ/vùng miền, không phải canonical ID. Tên giống nhau chưa đủ gộp loài; tên khoa học cũ cũng có thể trỏ tới taxon concept khác.
- **Hợp chất:** giữ InChIKey đầy đủ, cấu trúc/stereochemistry và ID gốc. chemical_curie trong Enveda là trường có thật trong source; namespace và mức mapping đầy đủ còn UNKNOWN. Không gộp chất theo tên thường hoặc chỉ connectivity block khi cần phân biệt stereoisomer.
- **Chỉ định/công dụng:** giữ nguyên disease_curie, câu nguồn và loại assertion. Mapping lên bệnh/nhóm bệnh tổng quát có thể mất ngữ cảnh, không tự tạo một quan hệ điều trị.

### Các quan hệ đề xuất — không phải triple đã đo hoặc property của ontology hiện có

| Quan hệ khái niệm | Nguồn ứng viên | Provenance tối thiểu / điều kiện |
|---|---|---|
| Taxon — has_scientific_name / has_vernacular_name → Name | ScienceDB metadata | Taxon ID, bản ghi/row, snapshot, nguồn và ngôn ngữ; nguồn chứng thực riêng cho từng alias nếu có. |
| Compound — reported_in_taxon → Taxon | LOTUS | Statement/occurrence ID, taxon và compound ID, reference DOI/PMID/Wikidata item, source version. |
| TraditionalUseAssertion — concerns_taxon → Taxon; — reported_for → Use/Indication | Enveda/VietHerb hoặc tài liệu gốc được phép | Database/source-record ID và văn bản/đoạn trích; phân loại traditional report, model-extracted, experimental hoặc clinical theo nguồn thực tế. Thiếu nguồn thì quarantine. |
| Assertion — supported_by → Reference/SourceSpan | LOTUS; Enveda khi reference hợp lệ | Đối chiếu đúng quan hệ, chủ thể, chiều và qualifier; có DOI không tự chứng minh một claim. |
| Taxon — mapped_to → ExternalTaxon | Crosswalk được kiểm tra | Hệ định danh, mapping method, confidence, reviewer, backbone version; phân biệt exact match với candidate match. |
| Image — depicts → Taxon | GBIF/ScienceDB, ngoài MVP | Occurrence ID, publisher, ảnh/URL, license và attribution từng ảnh; không suy ra công dụng. |

LOTUS là nguồn có thiết kế provenance ở cấp occurrence rõ nhất: [bài của nhóm LOTUS](https://lotus.nprod.net/lotus-manuscript/v/627e395814966f5ff4cd1beeb4b5ee9b39a8773f/) mô tả compound “found in taxon” với reference “stated in”. Cần giữ statement/reference node, không chỉ lấy direct edge làm mất reference. Bài báo và documentation chứng minh thiết kế; độ đầy đủ từng hàng trong dump chưa kiểm tra.

Trong pilot, mỗi assertion nên giữ: ID ổn định, subject/predicate/object gốc, source dataset/version/URI, file hash và row/statement locator khi có artifact, reference, đoạn nguồn được phép lưu, qualifiers, loại evidence, license và trạng thái review. Giữ IRI/RDF/OWL hiện có; lớp enrichment và assertion dẫn xuất tách khỏi ontology gốc. Không suy ra citation còn thiếu từ tên cây.

## 5. Khoảng trống và rủi ro nghiên cứu

1. **Chưa có corpus công dụng Việt đã đủ quyền và provenance:** ScienceDB chủ yếu là taxonomy/ảnh; LOTUS là occurrence hóa học; Enveda có association tổng hợp; ViHerbQA chưa được cấp payload.
2. **Citation không đồng nghĩa entailment:** DOI/PMID có thể thiếu, sai, dẫn review hoặc không nói đúng plant part/preparation/dose/population. Cần đọc nguồn và giữ cùng assertion; không ghép bằng tên chung.
3. **Chất có trong loài không chứng minh tác dụng hay an toàn:** không suy từ compound–taxon sang loài–chữa bệnh; không chuyển model-extracted association thành bằng chứng lâm sàng.
4. **Không độc lập nguồn:** Enveda dùng LOTUS và VietHerb theo README. Trùng lineage không phải xác nhận độc lập. Overlap và leakage chưa đo; chưa tạo split.
5. **Taxonomy/version:** synonym, homonym, bậc genus/species và tên địa phương có thể gây false join; snapshot website cũ khác Wikidata sống. Metadata ScienceDB bao gồm cả các giới ngoài Plantae, nên phải lọc phạm vi pilot.
6. **License nhiều lớp:** cần phân biệt code, factual metadata, bài viết, ảnh và nội dung upstream; không phân phối lại một gói hỗn hợp với một license giả định.
7. **Benchmark:** ViHerbQA access BLOCKED; exact gold, source IDs, article-level splitting, duplicate/paraphrase overlap và expert adjudication UNKNOWN. Không báo cáo điểm benchmark hay tuyên bố chất lượng gold.
8. **Giới hạn audit:** không kiểm tra payload, magic bytes của ZIP/SDF, checksum, schema đầy đủ, tỷ lệ citation, tài nguyên đã tải được hoàn chỉnh hay số hàng hợp lệ. HTTP/metadata không thay thế audit bản ghi.

[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) và [HANDOFF.md](HANDOFF.md) đã được đọc. Các kết quả ontology/import offline trong handoff là bối cảnh đã ghi nhận trước, không được chạy lại hoặc dùng làm bằng chứng về dữ liệu công dụng trong audit này. [AtlasKV review trước đó](../../VietMedKG/docs/literatureReview.md) củng cố yêu cầu giữ assertion ID/citation bên ngoài vector; chưa cần AtlasKV để xây dựng MVP dữ liệu.

## 6. Minimum viable dataset và điều kiện GO

**Đề xuất quy mô, không phải thống kê dataset:** 10–20 taxon thuộc Plantae có tên Việt đã đối chiếu; 30–60 assertion occurrence có reference có thể kiểm tra; khoảng 20 câu hỏi được người đọc nguồn gán chứng cứ. Không hứa rằng giao của các nguồn sẽ đạt các mục tiêu này.

### Lõi nên ưu tiên

1. **Taxon/name layer:** metadata CSV CC BY của ScienceDB, ưu tiên xin/bảo đảm một bản metadata-only có phiên bản thay vì tải ZIP ảnh lớn. CSV công khai trong repository tác giả là đường ứng viên, nhưng phải xác nhận đúng bản phát hành và quyền áp dụng trước khi tái phân phối.
2. **Compound/reference layer:** một bản LOTUS có license và version rõ, giữ đầy đủ quan hệ occurrence–taxon–reference; hoặc các statement Wikidata CC0 có reference, được chọn có giới hạn trong một bước thu thập được phê duyệt sau này. Audit hiện tại không thực hiện bước lấy dữ liệu.
3. **Evidence subset:** chỉ nhận assertion nếu định danh, license và reference round-trip được. Khi full text không được phép lưu, giữ citation/locator và đánh dấu mức truy cập; không dùng citation-only làm claim đã xác minh nội dung.
4. **Traditional-use extension:** chỉ bổ sung sau khi quyền Enveda/VietHerb và lineage được làm rõ hoặc có nguồn công dụng cấp phép rõ. Không có điều kiện này thì giới hạn pilot vào định danh và occurrence; chưa đánh giá câu hỏi khuyến nghị điều trị.
5. **Evaluation nhỏ độc lập:** câu hỏi dựa trên nguồn, có câu đa giá trị, alias mơ hồ, nguồn thiếu và khả năng abstain. Ghi source span/statement và nhãn ambiguity; tách việc gold hỗ trợ đối chiếu khỏi retrieval chỉ dựa vào câu hỏi. ViHerbQA chỉ là track bổ sung khi được cấp quyền và audit.

### Verdict

- **GO có giới hạn:** thiết kế dữ liệu và pilot taxonomy–compound–reference, sau khi có artifact metadata nhỏ và kiểm tra từng assertion.
- **CONDITIONAL cho mục tiêu KGVHerb đầy đủ:** cần nguồn công dụng tiếng Việt có quyền tái sử dụng, nhận dạng taxon chắc chắn và bằng chứng ở mức claim.
- **NO-GO ở thời điểm này:** công bố benchmark công dụng/hiệu quả điều trị được “xác minh”, tái phân phối bản VietHERB tổng hợp chưa rõ quyền, hoặc coi ViHerbQA là benchmark đã tải công khai.

Điều kiện chuyển sang GO đầy đủ: xác nhận license đúng artifact; lấy được subset nhỏ có version/hash trong tác vụ khác; chứng minh liên kết taxon và provenance round-trip; kiểm chứng nội dung claim theo nguồn; có bộ QA evidence-annotated với quy tắc chống leakage. Không có kết quả lâm sàng hoặc overlap thực nghiệm nào được suy ra từ báo cáo này.

