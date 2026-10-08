# Agentic Tree Search trong Workbench

## Yêu cầu đã chốt

Người dùng chọn đủ bốn giai đoạn của repo gốc: implementation → baseline
tuning → creative research → ablation. Một lần bấm Working mở một phiên Kaggle;
mọi node chạy tuần tự qua kết nối SSH đó. Proposal vẫn phải được duyệt trước.

## Thiết kế

- Dùng trực tiếp `treesearch.agent_manager.AgentManager.run`, `Stage`,
  `StageTransition`, chính sách chọn nhánh của `ParallelAgent`, `Journal`/`Node`
  và bộ xuất cây HTML của repo. Không viết bộ điều phối bốn giai đoạn thứ hai.
- Thêm điểm nối nhỏ cho provider Codex và agent thực thi SSH. Provider API và
  process pool/GPU local của launcher gốc tiếp tục là mặc định của launcher đó.
- Mục tiêu từng giai đoạn phải nằm trong phạm vi proposal. Không tự bổ sung
  dataset HuggingFace, kéo dài training hoặc tạo paper ngoài phạm vi đã duyệt.
- Người dùng chọn số bước tối đa cho mỗi giai đoạn khi bắt đầu Working. Đây là
  ngân sách tìm kiếm của phiên, không phải giới hạn tổng số lượt của người dùng.
- Node lỗi trở thành nhánh debug; node tốt làm baseline cho tuning/research/
  ablation. Lưu từng bản code, outputs, feedback và quan hệ cha/con trước khi
  chọn bước tiếp. Không ghi đè bằng chứng của node cũ.
- Dừng/restart giữ dữ liệu đã lưu và chỉ đối soát/dừng phiên cũ, không replay.
- Nguồn Library tiếp tục được stage và đọc qua đường dẫn.

## Dữ liệu

Các lượt mới dùng `experiments/YYYY-MM-DD_<idea_title>_attempt_N/` (N tăng để
tránh trùng tên), chứa `idea.md`, `idea.json`, `logs/0-run/`,
`token_tracker.json`, report và bằng chứng dừng. Bốn cây nằm trong các thư mục
stage của `logs/0-run/`, kèm `unified_tree_viz.html` theo cách repo gốc.
SQLite giữ liên kết project/run → experiment; run cũ vẫn mở từ đường dẫn đã lưu.
Review/PDF chỉ xuất hiện khi thật sự được tạo, không tạo file giả. Token chưa
được runtime cung cấp được ghi là chưa biết; không báo số 0 như số đo thực tế.

## Trình tự

1. Refactor điểm nối provider/agent và phân giải đường dẫn artifact; chạy tập
   regression hiện có rồi commit riêng, giữ nguyên hành vi.
2. Tích hợp executor SSH/Codex, bốn giai đoạn, layout experiment và giao diện.
3. Kiểm thử browser bằng provider/SSH local có đo số lần gọi; không tạo phiên
   Kaggle mới trong phạm vi kiểm thử này. Bàn giao rõ phần chưa kiểm chứng thật.

## Checklist nghiệm thu

- [ ] Launcher gốc tiếp tục dùng provider/process pool mặc định.
- [ ] Một Working đi qua đủ bốn stage của AgentManager gốc.
- [ ] Có nhánh draft/debug/improve và parent ID khôi phục đúng.
- [ ] Mỗi stage có thể dừng theo ngân sách; không có vòng substage vô hạn.
- [ ] Một SSH/bootstrap cho cả cây; dừng và chứng minh dừng trước COMPLETED.
- [ ] Artifact từng node bất biến; kết quả được hash khi thu qua SSH.
- [ ] Layout experiment có idea, journal, cây HTML và token tracking thật.
- [ ] GUI mở được cây và artifacts; refresh/restart vẫn xem được kết quả.
- [ ] Run cũ, retry, variant và project isolation tiếp tục hoạt động.
- [ ] Không gọi preflight/contract notebook cũ hoặc in toàn bộ Library vào prompt.

Ngoài phạm vi: tự động viết/review PDF không được yêu cầu trong proposal;
điều phối nhiều phiên Kaggle song song; chạy Kaggle thật để nghiệm thu.
