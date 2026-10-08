# MVP1 — bản chốt 2026-10-08

Đạt P1-01…P1-06 qua demo browser và Codex/Kaggle thật. Mốc Git:
`mvp1-2026-10-08`, nhánh `codex/personal-implementation-agent`.

## Đã bàn giao

- Library theo project: PDF/file gốc, text theo trang, status/version/hash;
  context chứa đường dẫn để agent tìm và đọc phần cần thiết.
- Discussion, proposal, approval và artifacts bền vững qua restart. Nguồn
  thay đổi làm proposal chờ duyệt cần xem lại; nguồn đã duyệt giữ đúng version.
- Idea biến thể từ run cũ có purpose/parent/change_summary và proposal mới;
  dữ liệu cha không bị ghi đè. Nhiều run APPROVED chưa chạy có thể cùng tồn tại;
  chỉ một Working/session được hoạt động tại một thời điểm.
- Agentic Tree Search dùng AgentManager/Journal/Node/chọn nhánh/exporter của
  repo gốc, đủ bốn stage trên một terminal SSH. Experiment nằm cạnh Library
  trong project, mỗi lượt có attempt riêng.
- Lỗi timeout giữ FAILED, thu file có SHA256 khi SSH rảnh rồi dừng Kaggle.
  COMPLETED đòi kết quả agent được xác minh và backend xác nhận phiên dừng.

## Demo đã nghiệm thu

Project **tree search make moons**, idea **M1-04 — paper, RBF và test holdout**,
run **f7a637498ab54bb8853dda5fcd432590**. Paper là Scikit-learn JMLR 2011,
đọc trang 3–4; model selection trên split make_moons 1200/400/400, seed 42.

- COMPLETED, đủ bốn node/ba cạnh, một phiên Kaggle CPU đã dừng.
- SVC RBF C=1/gamma=scale không scaler thắng bằng validation **94,75%**.
- Test **93,25%**, 373/400 dự đoán đúng; CSV/metrics được đối chiếu độc lập.
- 19 file source/output, 57.272 bytes, 135 artifact công khai có hash giữ nguyên
  qua restart. 125 artifact run cha và project competition cũ không đổi.

Mở `http://127.0.0.1:8011/` → chọn project trên → Run → **Run f7a63749**.
“Mở cây thí nghiệm” hiển thị một cây và chi tiết node bên dưới; node Ablation
hiện delta validation 0.0025. “Artifacts đã lưu” mở trang file, gồm
`output/test_predictions.csv`, `output/metrics.json`, `output/paper_notes.md`
và `report.md`. Xem [M1_04_ACCEPTANCE.md](M1_04_ACCEPTANCE.md) để đối chiếu bằng chứng.

Kết quả nằm tại:

```text
.workbench/projects/tree search make moons/experiment/
  2026-10-08_M1-04_—_paper,_RBF_và_test_holdout_attempt_1/
```

## Thử một idea khác

1. Nhập tài liệu vào Library, kiểm tra trạng thái/trang đã trích.
2. Tạo idea có tiêu đề, chọn nguồn, lập proposal, trả lời nếu agent hỏi rồi duyệt.
3. Chọn CPU/GPU/TPU, TTL và số bước mỗi stage; bấm Working.
4. Chờ report và xác nhận dừng. Từ run đã kết thúc có thể tạo idea biến thể hoặc
   lượt Working mới; từng lượt do người dùng quyết định.
5. Restart backend rồi mở lại đúng project/run để xem dữ liệu đã lưu.

Khởi động từ root repo:

```powershell
.\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --port 8011
```

`working_seconds` trong `.workbench/config.local.json` giới hạn toàn bộ thời
gian agent và tìm kiếm, mặc định 900 giây; TTL trên GUI giới hạn phiên Kaggle.
Demo xác minh được user duyệt riêng 1.500 giây Working/1.800 giây TTL; sau demo
đã trả lại thiết lập cũ. Tác vụ dài cần cấu hình Working phù hợp trước khi mở
backend, tối đa trong TTL. Không có quota tổng số lượt của người dùng.

## Phạm vi kiểm chứng

Local: planning/working 15 passed sau sửa admission; variants/library/tree/
recovery 16 passed; tree/working 13 passed sau sửa timeout, kiểm tra timeout
riêng sau review cuối 1 passed. Các tập có phần giao nhau, không cộng tổng.
Frontend build đạt. Demo thật kiểm tra source lỗi/thay file, v1/v2/stale,
project isolation, approval, variant, bốn stage, report/stop và ba lần restart.

Đây là workbench có phiên bền vững và biến thể dùng được; phép đo trên một split
cố định không tái lập benchmark paper hoặc chứng minh ý nghĩa thống kê của
ablation. OCR/RAG, fidelity general implementation, nhiều session đồng thời và
launcher GPU local vẫn thuộc mốc sau. Dữ liệu/config/evidence thực trong
`.workbench/` và donor ngoài repo được giữ local, không đưa vào Git.
