# MVP2 — bản chốt 2026-10-09

User nghiệm thu sau QA live và cho commit/push, đóng MVP2.
Nhánh: `codex/personal-implementation-agent`; mốc: `mvp2-2026-10-09`.
Nền MVP1: `mvp1-2026-10-08`.

## Đã bàn giao

- Hai mode Training/Research và Etc dùng chung Library trong một project;
  mode, đầu ra và các lựa chọn được ghim cùng proposal/approval.
- Một cây chung cho project, kéo để di chuyển và cuộn để zoom. Mỗi node
  là một run độc lập với phiên SSH riêng. Draft từ proposal; Improve/Etc con
  do user chủ động tạo. Agent sửa lỗi trong run, không tự tạo debug/stage con.
- Run con nhận code, memory_journal đã ghim và artifact cha qua link tải khi
  cần. Tags research/tuning/ablation chỉ phục vụ ghi nhớ.
- Summary, Report, Plots, PDF, Review là checkbox độc lập, mặc định tắt.
  Tận dụng các module gốc, không tự tái tạo pipeline viết bài/review.
- Etc có đầu ra mong muốn bắt buộc, thực thi trực tiếp, Output trong project;
  copy file kết quả sang Library thành bản sao riêng có provenance/hash.
- Xóa node lá đã dừng sẽ xóa các file riêng của run. Node có con không được
  xóa. Backend xác nhận Kaggle dừng trước khi công bố kết thúc.
- Library, experiment và output nằm chung trong thư mục project.

## Nghiệm thu live

Browser tạo idea/proposal, gọi Codex CLI và mở Kaggle CPU trên
`huynhtrungcuong`. Project: `QA Project Tree — live 09-10 (2)`.

- Draft/Improve thực thi thật; đọc code/journal và lazy fetch artifact cha,
  đối chiếu SHA256. Recompute local xác nhận split và MSE từ CSV thực tế.
- Summary/Report, Plots không Summary/Report, PDF/Review không
  Summary/Report/Plots; run tắt toàn bộ finishing cũng hoàn tất.
- PDF ICBINB cuối 2 trang được render và đọc cả hai trang. Review trả feedback
  hợp lệ, quyết định Reject đối với nội dung QA nhỏ; không coi đó là lỗi hệ thống.
- Etc tạo ba file, copy metrics-note vào Library, xóa populated leaf qua GUI
  sau xác nhận; thư mục run/output bị xóa và bản copy Library giữ nguyên hash.
- Marker log xuất hiện lúc foreground còn đang chờ; Stop đưa run về CANCELLED
  và biên nhận xác nhận Kaggle dừng. Không tự replay hoặc sinh debug node.
- Restart backend cấu hình thường trên 8011 giữ bảy node còn lại và trạng thái;
  health ok, không còn run QA đang hoạt động. Ba node lỗi lịch sử được giữ làm
  bằng chứng, không relabel thành thành công.

Chi tiết, run IDs, hashes, lỗi và screenshots:
[PROJECT_RUN_TREE.md](PROJECT_RUN_TREE.md#live-codex--kaggle-qa--2026-10-09).

## Các bản sửa trong nghiệm thu

AI Scientist commit `70bb6b5`: SQLite row factory, Windows extended path tại
biên Node gốc, dependency finishing/PDF/review, TeX chỉ khi chọn PDF,
summary success khi backend lỗi, responsive tree fit và prompt shell quoting.
Kaggle donor commit `9bf4c85`: streaming log ngắn không chờ lệnh kết thúc;
kiểm tra các vị trí chia gói và xác minh live Stop.

## Phạm vi chưa nghiệm thu live trong lượt này

GPU/TPU, template ICML, mọi tổ hợp checkbox và abrupt crash khi đang Working.
Đã xác minh cancellation thông thường và restart khi idle; không tuyên bố
khả năng recovery cho mọi kiểu crash. Các chi phí/token giá tiền không được
ước lượng giả từ các lần gọi Codex.

## Mở bản đã bàn giao

```powershell
.\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --port 8011
```

Mở http://127.0.0.1:8011/, chọn project rồi Run. Repo Kaggle donor cần bản
`9bf4c85` hoặc mới hơn để streaming log ngắn hoạt động đúng.
