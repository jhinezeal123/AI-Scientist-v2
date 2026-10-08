# MVP1 — workbench cá nhân qua nhiều phiên

Ngày bắt đầu: 2026-10-08, Asia/Saigon. Mốc MVP0: `mvp0-2026-10-08`.
Roadmap: [PRODUCT_ROADMAP.md, mục 5](PRODUCT_ROADMAP.md#5-mvp-1--workbench-cá-nhân-dùng-lại-qua-nhiều-phiên).

## Luồng và tiêu chí

Người dùng tạo project paper/workshop, import tài liệu, chọn nguồn để trao đổi và
duyệt proposal; sau khi đóng/mở app vẫn tiếp tục được; từ kết quả cũ tạo biến thể,
duyệt phạm vi mới rồi chạy Working và lưu report đúng project.

Giữ Library dạng file theo tên, context chứa đường dẫn, Run chứa lịch sử, và
Working qua SSH. Các nguồn/version đã duyệt giữ nguyên. Người dùng quyết định
từng lượt Working. OCR, RAG, nhiều agent/harness và điều phối đồng thời thuộc các
mốc sau, không thêm vào MVP1.

| Task | Bàn giao | Nghiệm thu | Trạng thái |
| --- | --- | --- | --- |
| M1-01 / CP1-A | Import PDF/file, bản gốc + text theo trang, ingestion status/version | Hai project riêng; chọn file vừa import làm context; agent đọc qua đường dẫn | Đã bàn giao local, 2026-10-08 |
| M1-02 / CP1-B | Trao đổi/approval/artifacts tiếp tục qua restart, UI khôi phục/lỗi | Restart không replay agent/notebook; source mới làm proposal chờ duyệt cần xem lại | Chưa bắt đầu |
| M1-03 / CP1-C | Tạo biến thể idea từ run, purpose/parent/thay đổi, proposal mới | Giữ dữ liệu cũ; duyệt mới trước Working; report gắn đúng project/run | Chưa bắt đầu |
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
- M1-02 và M1-03 chưa triển khai trong checkpoint này.
