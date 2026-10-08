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
| M1-01 / CP1-A | Import PDF/file, bản gốc + text theo trang, ingestion status/version | Hai project riêng; chọn file vừa import làm context; agent đọc qua đường dẫn | Đang triển khai |
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
