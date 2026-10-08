# MVP0 — bản chốt 2026-10-08

MVP0 đã được người dùng duyệt. Mốc Git: `mvp0-2026-10-08`, trên nhánh
`codex/personal-implementation-agent`.

## Luồng đang dùng

Library theo project → idea có tiêu đề → trao đổi/proposal → duyệt → Working
qua SSH Kaggle → thu source/output, log và report → xác nhận phiên Kaggle đã dừng.

- Codex chạy local, thao tác trong Kaggle qua một terminal SSH giữ kết nối.
- Code và submit nằm trong thao tác Working; proposal mô tả nhiệm vụ tổng quát.
- Người dùng quyết định từng lượt, không có quota tổng coder/submit.
- Run và idea là card có chi tiết; lịch sử nằm trong Run. Không có tab History riêng
  hoặc biểu đồ loss bắt buộc.
- Nguồn được lưu theo tên project/tiêu đề nguồn trong Library, có version/hash.
  Context chứa đường dẫn; agent tìm/đọc file khi cần.
- Xóa idea/run có thể khôi phục; run chưa xác nhận dừng không được xóa.
- Hai prompt Working cấu hình bằng alias tại `ai_scientist/workbench/system_prompt/`.

## Bằng chứng và giới hạn

- Training notebook của T09 được nghiệm thu trong [MVP0_RUN_GUIDE.md](MVP0_RUN_GUIDE.md).
- Working qua SSH đã đi hết trên Kaggle CPU với CSV synthetic 1.000 dòng,
  source/output/report đã thu và `stop_confirmed=true`; xem
  [WORKING_ACCEPTANCE.md](WORKING_ACCEPTANCE.md).
- Lượt kiểm tra lại sau gộp prompt: `2261d9907a9a46bdbf73d4f007fc1715`,
  COMPLETED; 4 source/output files, 67.114 bytes, 11 log records. Dữ liệu 1.000 dòng
  được đối chiếu độc lập với seed/công thức; kết quả vẫn đọc được sau reload.
- Bản cuối có 149 kiểm thử workbench local đạt và frontend build đạt.
  Chuyển tên thư mục đối chiếu 223 file cũ và 10 snapshot; dữ liệu giữ nguyên.
- Dữ liệu thực, config, token, bằng chứng local và artifacts nằm trong `.workbench/`
  hoặc donor ngoài repo, không được đưa vào Git.
- Chưa nghiệm thu training/GPU/TPU trên luồng Working hiện hành; không khẳng định
  đạt mục tiêu triển khai dưới tám giờ.

## Dùng và mở rộng

[WORKING_SSH.md](WORKING_SSH.md) là hướng dẫn luồng chạy hiện hành.
[PROJECT_LIBRARY.md](PROJECT_LIBRARY.md) mô tả thư mục và phiên bản nguồn.
Các phần notebook/preflight cũ chỉ phục vụ dữ liệu lịch sử.

MVP1 tiếp tục trên cùng workbench, ưu tiên import PDF/file và khả năng tiếp tục
qua nhiều phiên; lịch sử dùng tab Run, thực thi dùng Working qua SSH.
