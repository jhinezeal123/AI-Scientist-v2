# MVP1 — workbench cá nhân qua nhiều phiên

Ngày bắt đầu: 2026-10-08, Asia/Saigon. Mốc MVP0: `mvp0-2026-10-08`.
Roadmap: [PRODUCT_ROADMAP.md, mục 5](PRODUCT_ROADMAP.md#5-mvp-1--workbench-cá-nhân-dùng-lại-qua-nhiều-phiên).

## Luồng và tiêu chí

Người dùng tạo project paper/workshop, import tài liệu, chọn nguồn để trao đổi và
duyệt proposal; sau khi đóng/mở app vẫn tiếp tục được; từ kết quả cũ tạo biến thể,
duyệt phạm vi mới rồi chạy Working và lưu report đúng project.

Giữ Library dạng file theo tên, context chứa đường dẫn, Run chứa lịch sử, và
Working qua SSH. Các nguồn/version đã duyệt giữ nguyên đến khi người dùng chủ
động xóa nguồn vĩnh viễn. Người dùng quyết định
từng lượt Working. OCR, RAG, nhiều agent/harness và điều phối đồng thời thuộc các
mốc sau, không thêm vào MVP1.

| Task | Bàn giao | Nghiệm thu | Trạng thái |
| --- | --- | --- | --- |
| M1-01 / CP1-A | Import PDF/file, bản gốc + text theo trang, ingestion status/version | Hai project riêng; chọn file vừa import làm context; agent đọc qua đường dẫn | Đã bàn giao local, 2026-10-08 |
| M1-02 / CP1-B | Trao đổi/approval/artifacts tiếp tục qua restart, UI khôi phục/lỗi | Restart không replay agent/notebook; source mới làm proposal chờ duyệt cần xem lại | Đã bàn giao local, 2026-10-08 |
| M1-03 / CP1-C | Tạo biến thể idea từ run, purpose/parent/thay đổi, proposal mới | Giữ dữ liệu cũ; duyệt mới trước Working; report gắn đúng project/run | Đã nghiệm thu local, 2026-10-08 |
| M1-04 | Demo và bàn giao P1-01…P1-06 | Competition + paper, PDF, restart giữa phiên, chạy biến thể thật có xác nhận dừng | Chưa nghiệm thu |

## M1-01

- Upload PDF có text hoặc file vào Library; lưu bytes bản gốc đúng version/hash.
- PDF trích text theo trang; trang không đọc được và file mã hóa/lỗi có trạng thái
  rõ. File không có text không bị ghi là đã đọc.
- Text/file gốc đều được tham chiếu trong context; không chèn toàn bộ vào prompt.
- Thay file tạo version mới của cùng nguồn, giữ nguyên bản đã ghim trong proposal.
- Backend/UI dùng được ngay trên localhost; kiểm thử local không tạo phiên Kaggle.

### Đã bàn giao

- GUI Library có “Nhập PDF / file”, “Thay file”, tải bản gốc và đọc text từng
  trang ngay trong Library. Thay file tạo version mới; đổi tiêu đề cũng đổi tên
  thư mục, đường dẫn của snapshot cũ tiếp tục được giải quyết đúng nguồn.
- Mỗi version có `source.md`, `original.<extension>`, `ingestion.json` và
  `pages/page-NNNN.md` đối với PDF; file text có `text.md`. SQLite giữ metadata
  trích xuất/hash để kiểm tra bản gốc, text và provenance trước khi cấp cho agent.
- Trạng thái: `extracted`, `partial`, `no_text`, `locked`, `error`,
  `file_reference`. Trích text thành công chưa có nghĩa agent đã đọc tài liệu.
- Planner được cấp bản sao Library riêng; Working chuyển cả tài liệu/page đã
  chọn qua cùng terminal SSH. File lớn hơn giới hạn 1 MB của donor được chia phần
  và kiểm tra size/SHA256 sau khi ghép. Donor không cần thay giao thức.
- Giới hạn xử lý tài liệu: 25 MiB/file, tối đa 500 trang và 2 MB text đã trích.
  PDF scan không OCR; tài liệu quá giới hạn text được ghi `partial` và bản gốc
  vẫn nguyên vẹn. Dataset lớn dùng reference.

### Bằng chứng và phạm vi kiểm chứng

- Bộ kiểm thử local gồm các trường hợp PDF text/khóa/không có text/lỗi, encoding,
  API multipart, giữ version, stale approval, hash, cô lập project, rollback lỗi
  ghi file/DB, planner đọc trang và Working gửi tài liệu qua terminal giả lập.
  Kết quả: **164 passed**; build frontend thành công.
- Browser trên localhost: tạo project “MVP1 Paper — kiểm tra nhập tài liệu”,
  nhập PDF hai trang, đọc trang 2, chọn nguồn làm context, thay file v2 và đổi
  tiêu đề. Restart backend rồi đọc v2 và tải lại bản gốc; project Soil giữ năm
  nguồn cũ. Text không xuất hiện trong context.
- Bằng chứng local: `.workbench/acceptance/mvp1-imports-2026-10-08/`.
  Bản sao SQLite trước migration: `.workbench/backups/mvp1-imports-2026-10-08/`.
- Kiểm thử planner/Working dùng fixture; chưa chạy Codex/Kaggle thật với PDF.
  Nghiệm thu toàn MVP1 và chạy biến thể thật thuộc M1-04.
- Tiến độ hiện tại nằm ở bảng task và các mục bàn giao bên dưới.

### Tinh chỉnh Library theo yêu cầu

- Nguồn hiển thị bằng card tiêu đề; chọn card để mở chi tiết. Bỏ nút nhập T01 và
  ô URL riêng: dán URL vào nội dung/mô tả, kể cả nhiều URL. URL vẫn được đưa vào
  reference để Working nhận diện Kaggle dataset/competition đã chọn. Chỉ lưu URL
  không có nghĩa app đã đọc trang.
- Xóa nguồn là xóa vĩnh viễn file gốc, text đã trích, tất cả version và bản sao
  Library của nguồn trong thư mục planner/Working của project. Không có thùng rác
  hay khôi phục nguồn. Nếu file đang mở khiến xóa thất bại, app báo chưa xóa hết
  và cho thử lại; backend tiếp tục phần đang xóa khi khởi động lại.
- Chặn xóa trong lúc agent làm việc. Proposal chưa duyệt dùng nguồn bị xóa cần
  lập lại. Lịch sử/report của run giữ nguyên; chạy lại với nguồn bị xóa bị chặn
  trước khi mở phiên Kaggle và cần nhập nguồn/lập proposal mới.

## M1-02 — Tiếp tục phiên đã lưu

### Luồng sử dụng

- GUI nhớ tab, idea, nguồn đang chọn và run đang mở riêng cho mỗi project trong
  browser đang dùng. Đổi project rồi quay lại hoặc tải lại trang sẽ mở đúng lựa
  chọn đó. Dữ liệu trao đổi, approval và artifacts vẫn do backend/SQLite lưu;
  browser chỉ lưu lựa chọn màn hình.
- Mất kết nối hiển thị thông báo và nút “Kết nối lại”, giữ dữ liệu đã tải để xem.
  App thử đọc lại sau 4 giây và tiếp tục theo dõi khi backend trở lại. Các thao
  tác làm việc đang mất kết nối bị khóa; app không tự gửi lại POST hoặc gọi agent.
- Câu trả lời đã bấm “Lưu câu trả lời” vẫn còn sau restart. Nút “Tiếp tục lập
  proposal vN” yêu cầu một lượt Codex mới với trao đổi đã lưu. Proposal bị gián
  đoạn có lỗi và nút “Tiếp tục lập proposal”; không tự chạy lại khi backend mở.
- Thay hoặc xóa nguồn chỉ làm cũ proposal chưa duyệt có dùng nguồn đó. Card idea
  hiện “Cần xem lại nguồn”, proposal nêu nguồn đã đổi và có nút lập lại từ các
  nguồn hiện đang chọn. Thêm một nguồn chưa chọn không làm cũ proposal khác.
  Proposal đã duyệt và nguồn đã ghim cho run giữ nguyên phiên bản.
- Run Working đang chạy khi backend dừng được khôi phục bằng kiểm tra/dừng
  phiên Kaggle cũ. Không tự mở SSH để chạy lại agent, không gửi notebook mới.
  Chỉ kết thúc run sau khi có xác nhận Kaggle dừng. Kết quả đã thu đủ được giữ;
  lượt bị ngắt chưa thu đủ được đánh dấu thất bại, có report/log và thao tác tạo
  lượt Working mới do người dùng quyết định.
- Form chưa bấm lưu không thuộc dữ liệu trao đổi đã lưu; cần bấm lưu trước khi
  đóng trang. Lựa chọn màn hình được nhớ theo browser, không đồng bộ giữa máy.

### Kiểm chứng

- **185 kiểm thử Workbench passed**, build frontend thành công. Sáu trường hợp
  M1-02 mới chạy toàn bộ lifespan app qua nhiều restart: câu hỏi/câu trả lời,
  duyệt lại không trùng run, đọc artifacts, source/version/project isolation,
  planning gián đoạn và Working bị ngắt ở ba giai đoạn. Runtime/MCP/SSH giả lập
  ghi số lần gọi để chứng minh restart không phát sinh agent/notebook mới.
- Browser trên backend thật `8011`: tải lại giữ idea/proposal/ba nguồn; chuyển
  Paper ↔ Soil giữ lựa chọn riêng; dừng/mở backend hiển thị mất kết nối rồi tự
  khôi phục đúng run, report và artifacts.
- Browser trên môi trường local giả lập `8012`: lưu câu trả lời, restart, tiếp
  tục tạo v2; duyệt rồi đổi nguồn v2; proposal đã duyệt giữ v1, proposal chờ
  duyệt cần xem lại và có thao tác lập bản mới. Không gọi Codex/Kaggle thật.
- Bằng chứng local: `.workbench/acceptance/m1-02-recovery-2026-10-08/`.
  Nghiệm thu với phiên Kaggle mới và biến thể thật vẫn thuộc M1-04.

## M1-03 — Tạo idea biến thể từ kết quả đã lưu

### Luồng sử dụng

- Từ run đã kết thúc, người dùng nhập tiêu đề, mục đích và thay đổi để tạo một
  idea DRAFT mới. Việc này không gọi planner, không duyệt proposal và không mở
  run/Working. Run chưa dừng hoặc không đủ điều kiện bị chặn.
- Idea/proposal/context/run mới lưu lineage về đúng project và run cha. Proposal
  và approval là lượt mới; approval tạo run mới, Working vẫn cần người dùng bấm
  riêng. Nút tạo lượt Working mới tiếp tục dùng retry với cùng proposal; quan hệ
  đó không thay parent/lineage của variant.
- Baseline lấy từ proposal/source refs và report/code/manifest được phép đọc.
  Snapshot ghim đường dẫn/hash; planner và Working nhận file tham khảo đã kiểm
  tra/stage cùng Library, không nhồi toàn bộ code/log vào prompt. File cha và
  artifact không bị ghi đè. Baseline thiếu vẫn tạo được variant từ metadata.
- Dùng chung `LibraryFiles.stage`, approved context snapshot/hash, `RunView`,
  Working manifest, proposal approval và xác nhận dừng. Journal `Node` chỉ liên
  kết code/thử nghiệm sau Working; `run.parent_run_id` đang biểu diễn retry. Vì
  lineage/purpose phải tồn tại từ DRAFT trước run và retry vẫn riêng, M1-03 thêm
  metadata SQLite `variant_ideas` thay vì đổi ý nghĩa hai cơ chế cũ. Không cần
  structural refactor trước behavior.
- Correction sau review: code tham khảo tổng quát lấy từ các đường dẫn `source/...`
  trong working manifest đã lưu và xác minh; UTF-8, tối đa 32 file và 1 MiB.
  `source/workload.py` legacy vẫn dùng hash code hiện có; file code khác dùng
  hash manifest. File không phù hợp/oversize được bỏ qua có cảnh báo, không scan
  thư mục run tùy ý. `LibraryFiles.stage` giữ iterator streaming theo từng file;
  Working xác minh snapshot/baseline trước khi trả phí rồi chỉ stage Library một
  lần trong request, không stage cả Library trước SSH rồi stage lại.
- Form biến thể reset khi đổi run; quay lại DRAFT variant chưa có proposal chỉ
  chọn lại các nguồn parent còn tồn tại, không mượn lựa chọn của idea khác.

### Kiểm chứng và bằng chứng

- Targeted backend sau correction: `pytest -q tests/workbench/test_variants.py tests/workbench/test_library_files.py tests/workbench/test_working.py tests/workbench/test_generic_working.py tests/workbench/test_planning.py`
  **34 passed**. Assertion hiện có xác minh `source/generate_data.py` được đọc
  từ working manifest đã lưu, stage đúng nội dung/hash và không đổi dữ liệu cha.
  Các kiểm tra khác bao gồm replay/conflict, ownership, stop confirmation,
  baseline hash, fallback khi thiếu code/report và chặn Working trước approval.
- Frontend build `npm run build` đạt (`tsc -b && vite build`).
- Browser fixture local `8012` đi hết draft → source version cần review →
  clarification/restart → proposal mới → approval/run mới → Working qua fake
  SSH/terminal/MCP → report, retry riêng, ẩn/khôi phục parent và đổi project.
  Planner/Working fixture thực đọc baseline files. DRAFT ban đầu không phát sinh
  planner/run/Working; API approval lặp trả cùng run. Parent report/code/output,
  proposal context hash và source snapshot v1 đều giữ nguyên sau khi nguồn hiện
  hành đổi lên v2. Project thứ hai không thấy dữ liệu project đầu.
- Evidence: `.workbench/acceptance/m1-03-variants-2026-10-08/` chứa counters,
  fixture và JSON hash trước/sau. Counters ghi `codex_real_calls=0`,
  `kaggle_real_sessions=0`; sau cả hai journeys fake planner=4, Working=1,
  SSH=1, terminal stop=1. Screenshot full-flow cũ hiển thị inline; source-
  deletion screenshots được lưu thành các file local ở phần dưới.
- Nhánh source đã xóa đã được nghiệm thu trong browser fixture `8012` ở task
  chính sau khi user mở tab: từ parent run `8077a3b8…`, tạo variant DRAFT
  `1f9a3c51…`; xóa duy nhất nguồn giả `5c51b0b2…` qua Library GUI (6 file,
  khoảng 1.3 KB). UI ghi rõ “Fixture source document: đã bị xóa; không tự khôi
  phục” và khóa planner trước khi review. Sau khi thêm/chọn “Fixture replacement
  document” v1, review mở khóa planner; proposal v2 `cf9c64ae…` dừng ở
  `AWAITING_APPROVAL`. Context hash `842782e0…` và `data_refs` chỉ chứa nguồn
  thay thế `eea0aa48…`; ID nguồn đã xóa không có trong snapshot, nhưng còn trong
  baseline lineage bất biến của variant. Không approve hoặc tạo Working mới cho
  journey này; luồng fake Working/report/stop đã được kiểm ở journey trước.
- Evidence JSON `.workbench/acceptance/m1-03-variants-2026-10-08/source-deleted-acceptance.json`
  xác nhận parent run/report/code/output/proposal context/hash không đổi và
  counters `codex_real_calls=0`, `kaggle_real_sessions=0` (fake planner=4,
  Working=1, SSH=1, stop=1). Browser evidence: [source-deleted-warning.png](../../.workbench/acceptance/m1-03-variants-2026-10-08/source-deleted-warning.png),
  [replacement-proposal.png](../../.workbench/acceptance/m1-03-variants-2026-10-08/replacement-proposal.png),
  [source-deleted-proposal-dom.txt](../../.workbench/acceptance/m1-03-variants-2026-10-08/source-deleted-proposal-dom.txt).
- Inventory CUA của worker vẫn trống; browser journey trên do root task thực
  hiện sau khi user mở tab. Counters và hash evidence chỉ thuộc fixture local.
- Backend thật `8011` được kiểm tra health; smoke test chỉ đọc dữ liệu đang có.
  Luồng Working toàn browser dùng fixture giả lập, chưa xác minh với Codex/Kaggle
  thật. Chạy biến thể thật và nghiệm thu trọn MVP1 vẫn thuộc M1-04.
