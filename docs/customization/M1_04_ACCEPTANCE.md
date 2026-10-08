# M1-04 — Nghiệm thu thật và đóng MVP1

Ngày: 2026-10-08. Trạng thái: đạt P1-01…P1-06; MVP1 đã nghiệm thu thật.

## Demo và phạm vi

- Dùng project competition `Soil Grain Size MVP0` và project nghiên cứu
  `tree search make moons`, không sửa dữ liệu/run competition cũ.
- Import PDF thật *Scikit-learn: Machine Learning in Python* (JMLR, 2011) qua
  Library GUI; agent đọc các trang liên quan từ file. Đây là thử nghiệm API/mô
  hình trên make_moons, không tuyên bố tái lập benchmark của paper.
- Dùng run cha `20070c8199274ba9ac6037906459cf68` đã dừng, tạo idea biến thể qua
  GUI, ghim baseline và duyệt proposal mới trước Working.
- Mỗi lượt mở một phiên Kaggle CPU của account `huynhtrungcuong`; ngân sách tìm kiếm một
  bước mỗi stage, đủ implementation/tuning/research/ablation. Dữ liệu 2.000
  mẫu, seed 42, noise 0.25, stratified 1.200/400/400; fit tối đa 30 giây;
  output tối đa 5 MB. Không mở phiên tiếp theo khi chưa được user yêu cầu.
- Thay đổi: đối chiếu LogisticRegression với SVC RBF; tuning C của baseline,
  nghiên cứu RBF, ablation scaler. Chọn cấu hình bằng validation; stage cuối
  đánh giá test đúng một lần sau lựa chọn, lưu CSV dự đoán và metrics thật.
- Tạo ghi chú protocol v1; thay v2 sau approval để kiểm tra provenance và
  source stale. Restart trước Working và sau kết quả; kiểm tra không replay.
- Kiểm tra nguồn không đọc được và thao tác thay nguồn qua GUI. Không xóa
  project hiện có, không sửa SQLite để hoàn thành demo.

## Checklist nghiệm thu

- [x] P1-01: chuyển competition ↔ paper; Library/context/history/run riêng.
- [x] P1-02: PDF gốc, hash và text theo trang; nguồn lỗi có trạng thái rõ.
- [x] P1-03: source v2 làm proposal chưa duyệt stale; approval v1 vẫn giữ
  đúng bytes/hash và nguồn ghim.
- [x] P1-04: restart giữ discussion, approval và artifacts, không tạo agent,
  run hoặc notebook mới; GUI tiếp tục đúng project/run.
- [x] P1-05: variant thật giữ parent/purpose/change_summary; thực thi đủ bốn
  stage, thu outputs/report và proof Kaggle dừng; code/artifacts cha bất biến.
- [x] P1-06: GUI hiển thị lỗi nguồn/runtime và thao tác sửa/tiếp tục; không
  chỉnh DB thủ công.
- [x] CSV test và metrics nhất quán; report phân biệt phép đo và giới hạn.
- [x] Cập nhật IMPLEMENT_MVP1/PRODUCT_ROADMAP và hướng dẫn demo.

## Bằng chứng

Evidence local: `.workbench/acceptance/m1-04-2026-10-08/`.
PDF chính thức: https://www.jmlr.org/papers/volume12/pedregosa11a/pedregosa11a.pdf

Chỉ đánh dấu đạt sau khi có bằng chứng thật tương ứng; không dùng fixture để
thay cho lần chạy Codex/Kaggle của demo này.

## Các bước đã quan sát

- PDF JMLR có sáu trang text; bản gốc SHA256
  `1c338a6b3c6c1dcafda3990a8098b8b50dd6c77616361396fb75f6822c6e0778`.
  Nguồn `52289031d4c9405eb4776d2aa5bfee13`, tiêu đề
  “Scikit-learn — JMLR 2011”. GUI mở được trang 4 về Pipeline/model selection.
- Project Soil giữ năm nguồn và sáu run cũ; chuyển GUI về project paper chỉ
  thấy Library và history của project paper.
- Idea biến thể `24625d82d3874faa8462fef91ca52284` tạo proposal mới
  `f2627516ff61415b87e190b3fd29ec5a`. User duyệt v1, context SHA256
  `9cb32ad6fd1ed6e076813006dd36ab811b1c05cee3959c1272e461ec4f97f9df`.
  Run mới `bdf6659726b64e7c9f3a65abbfc415a5` giữ lineage về run cha.
- Protocol v2 được lưu sau approval. Proposal đã duyệt giữ v1; proposal QA
  chưa duyệt `2076162159c04f67b66f01a56178b44b` chuyển STALE, GUI hiện thao tác
  lập lại từ nguồn đang chọn. Không Working cho idea QA này.
- File PDF lỗi được import qua GUI, hiện lỗi cấu trúc; “Thay file” bằng PDF
  thật tạo v2 trích đủ sáu trang. Nguồn test lỗi không thuộc context Working.
- Restart trước Working giữ nguyên ideas/proposals/history, request worker
  và SHA256 của 125 artifact công khai của run cha. Browser hiện mất kết nối,
  khóa thao tác ghi và có “Kết nối lại”; backend trở lại không replay POST.
- Run thật được bắt đầu bằng nút GUI “Bắt đầu Working”, CPU, TTL 30 phút và
  `[1,1,1,1]` bước. SSH nhận protocol v1 và PDF/page files đã ghim.

## Sửa lỗi phát hiện trong demo

Run APPROVED chưa từng gọi agent hoặc mở Kaggle ở project QA cũ đã khóa
approval/Working của project khác. Commit `a0d0737` bỏ khóa do run chuẩn bị
chưa chạy, dùng predicate lifecycle hiện có; identity từ phiên thật, worker
đang bận và session chưa đối soát vẫn chặn Working đồng thời.

Kiểm chứng local: planning/working 14 passed trước sửa, 15 passed sau sửa;
variants/library/tree-search/session-recovery 16 passed. Hai tập có phần giao
nhau nên không cộng thành tổng số test riêng biệt. Frontend `npm run build` đạt.

### Lượt thật đầu: hết thời gian trước JSON cuối

- Phiên `bdf66597…` dùng đúng một notebook CPU và một SSH. Implementation,
  tuning và research đã được xác minh/lưu thành ba node; stage Ablation đã
  thực thi nhưng Codex CLI chạm giới hạn toàn Working 900 giây trước khi trả
  payload cuối. Run FAILED, search failed, không sửa thành COMPLETED.
- Backend xác nhận Kaggle dừng lúc `2026-10-08T13:09:20Z`; kernel
  `137673454`, script version `217675512`, session `356409422`, notebook v1.
- Nhánh exception cũ không thu source/output hiện hành trước STOP. Bản sửa
  thu qua SSH sẵn có khi terminal rảnh, kiểm tra SHA256, giữ FAILED khi thiếu
  phản hồi cuối; không chờ terminal bận hoặc ghi đè manifest đã xác minh.
  Prompt search node chuyển sang đọc phần cần thiết và trả JSON ngay khi đủ
  bằng chứng (commit `09938d8`). Regression tree/working: 13 passed; kiểm tra timeout riêng sau
  review cuối: 1 passed.
- Đã tải lại đúng 18 file source/output của phiên COMPLETE, v1, bằng read-only
  exact-session view và SDK download. Files nằm trong evidence
  `recovered-stopped-output/`, không sửa DB/journal/report run cũ. CSV có
  400 sample_id khác nhau; accuracy tính trực tiếp từ y_true/y_pred = 0.9325,
  khớp metrics. Validation thắng 0.9475, SVC RBF C=1/gamma=scale không scaler.
  Bằng chứng này chứng minh kết quả tính toán; chưa chứng minh luồng cuối
  search/collection/report thành công của MVP1.
- Chỉ mở một phiên thật trong phạm vi approval đầu. Lượt xác minh tiếp theo
  cần user duyệt riêng, đề xuất giữ thuật toán/split/ngân sách fit/output và
  tăng thời gian Working lên 25 phút trong TTL 30 phút.

## Lượt xác minh đạt

User đã duyệt riêng lượt xác minh CPU, Working tối đa 1.500 giây/25 phút,
TTL 1.800 giây/30 phút, cùng proposal v1 và `[1,1,1,1]` bước. Tạo run bằng
“Tạo lượt Working mới” rồi “Bắt đầu Working” qua GUI:

- Run `f7a637498ab54bb8853dda5fcd432590`, COMPLETED, `stop_confirmed=true`.
- Notebook `huynhtrungcuong/ai-scientist-ssh-f7a637498ab5`.
- Bắt đầu `2026-10-08T13:22:29Z`; xác nhận dừng `2026-10-08T13:38:28Z`.
- Experiment `tree search make moons/experiment/2026-10-08_M1-04_—_paper,_RBF_và_test_holdout_attempt_1`.
- Một phiên Kaggle/SSH cho bốn node; 23 lệnh SSH. Token tracker ghi usage
  đầy đủ của bảy Codex calls: bốn node và ba query của AgentManager gốc.
- 19 file source/output, 57.272 bytes tổng, trong đó output 24.445 bytes;
  manifest và manifest của từng node đều khớp SHA256. Có 135 artifact công khai.

| Stage | Kết quả validation | Lựa chọn/phép đo |
| --- | --- | --- |
| Implementation | 0.8925 | StandardScaler + LogisticRegression C=1 |
| Tuning | 0.8925 | C=1 thắng C=0.1; hòa C=10 thì ưu tiên C nhỏ |
| Research | 0.945 | StandardScaler + SVC RBF C=1, gamma=scale |
| Ablation | 0.9475 | SVC RBF không scaler; chênh lệch +0.0025 |

Chọn cấu hình bằng validation rồi fit trên train, predict test đúng một lần.
CSV có 400 sample_id khác nhau, 373 dự đoán đúng; accuracy tính lại
**0.9325**, khớp metrics. IDs/nhãn holdout khớp lượt thật trước trên cùng
protocol. CSV comparison khớp tám bản ghi candidate của bốn stage; các phép
đo dùng lại đều ghi nguồn. Đọc code xác nhận preprocessing/estimator chỉ fit
train, validation dùng lựa chọn và test chỉ predict sau lựa chọn. Không chạy
lại training local để tạo số đo thay thế.

Viewer hiển thị một cây bốn node/ba cạnh; chọn node và về node cha qua browser
đạt, phần chi tiết nằm dưới cây. Metric của node Ablation là **delta validation
0.0025**, khác với final validation 0.9475 và test 0.9325 trong metrics/report.

Restart sau COMPLETED giữ nguyên SHA256 của 135 artifact run mới và 125
artifact run cha; ideas/proposals/history/worker request ID không đổi. GUI
khôi phục đúng project/run COMPLETED, đủ bốn stage và xác nhận Kaggle dừng.
Các project khác giữ nguyên resource/run IDs. Run FAILED ban đầu không bị sửa.
Thiết lập Working 25 phút chỉ dùng cho lượt được duyệt; sau demo khôi phục
config thời gian cũ và backend đã chạy lại tại port 8011.

Evidence chính: `completed-result-verification.json`,
`final-restart-verification.json`, `verified-before-final-restart.json`,
`verified-after-final-restart.json`, `completed-run.png`, `completed-tree.png`.

## Phạm vi bàn giao

MVP1 đạt khả năng Library/project/phiên làm việc bền vững và tạo biến thể từ
kết quả đã lưu. Đây là phép đo trên một split make_moons cố định, không chứng
minh tái lập benchmark paper hoặc ý nghĩa thống kê của chênh lệch 0.0025.
OCR, RAG, GPU/TPU cho demo này, nhiều phiên đồng thời và general implementation
fidelity vẫn thuộc các mốc sau. Demo không dùng unit fixture thay cho kết quả thật.

Hướng dẫn và mốc Git: [MVP1_RELEASE.md](MVP1_RELEASE.md).
