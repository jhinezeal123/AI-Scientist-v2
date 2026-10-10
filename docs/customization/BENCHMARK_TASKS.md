# Benchmark và MLflow

## Scope

Idea có ba loại: Training/Research, Etc, Tạo benchmark mới. Benchmark chạy trên
Kaggle, tạo dataset public bằng bộ upload KaggleHub và trả link dataset.
Metric (tên, chiều tối ưu, định nghĩa) và mô tả tập test bắt buộc; train tùy chọn.
Training/Research chọn benchmark đã tạo. Benchmark + phiên bản dataset cố định
là nhóm so sánh MLflow. Không kiểm tra công bằng hoặc giới hạn steps để so sánh.
Planner hỏi lại khi người dùng yêu cầu train nhưng chưa có tập train.

## Tasks

- [x] B1: Lưu định nghĩa benchmark, liên kết idea và đóng băng benchmark trong approval.
- [x] B2: Luồng Working tạo dữ liệu trên Kaggle, upload public, xác minh và lưu link/version.
- [x] B3: MLflow mặc định, không fallback; đồng bộ và so sánh theo benchmark.
- [x] B4: Form Idea, chọn benchmark, kết quả dataset và biểu đồ tất cả run của benchmark.
- [x] B5a: Kiểm thử local và tài liệu chạy.
- [x] B5b: Nghiệm thu public dataset và hai research run Kaggle thật; có audit
  khôi phục benchmark/telemetry 10 bước, chi tiết trong BENCHMARK_QA.md.
- [x] B5c: Benchmark và research 10 bước tự động sau sửa lỗi; gate train thiếu
  dữ liệu với Codex thật, download public không auth, hashes/telemetry/MLflow đều đạt.
- [x] B6: Gate đặt tên dataset trước phiên Kaggle và trước upload.

## Quy ước

Một benchmark là một phiên bản bất biến. Thay metric/test hoặc dữ liệu tạo
benchmark mới. Không tự gán benchmark cho run cũ thiếu bằng chứng.
Dataset chứa `benchmark.json`, `evaluate.py` và các file test; các file train
chỉ xuất hiện khi được yêu cầu. Evaluator có giao diện được mô tả trong manifest,
có thể đo accuracy, latency, memory, cache hay mục tiêu research khác.
Không giả định mọi Training/Research đều có training loop.

## Dùng trong GUI

1. Trong **Idea**, chọn **Tạo benchmark mới**. Nhập tên metric, chiều tối ưu,
   cách tính metric và mô tả tập test. Train có thể để trống.
2. Chọn Library cần dùng, trao đổi với planner và duyệt proposal.
3. Trong **Run**, chọn account/phần cứng/thời gian rồi bắt đầu Working.
   Agent tạo test/evaluator trên Kaggle. Backend thu file và dùng KaggleHub
   upload cùng SDK create `is_private=False`; chỉ hoàn tất khi đã xác minh public,
   phiên bản dataset READY và Kaggle session đã dừng.
4. Link dataset xuất hiện trong chi tiết run. Tạo Idea **Training/Research**,
   chọn benchmark này rồi lập/duyệt/chạy proposal.
5. Trong **Run → Biểu đồ MLflow theo benchmark**, chọn benchmark để xem mọi
   Training/Research đang dùng nó. Không cần có quan hệ cha/con hoặc cùng số steps.

Benchmark hiện có phạm vi project. Metric/test/evaluator/version được ghim trong
approval; đổi phép đo bằng cách tạo benchmark mới. Run cũ thiếu benchmark vẫn
đọc được; tạo Improve và chọn benchmark trước khi chạy phiên mới. Không xóa run
tạo benchmark khi còn idea/run đang tham chiếu nó. Xóa một benchmark chưa được
sử dụng chỉ xóa dữ liệu local; dataset public trên Kaggle không bị tự động xóa.

## Gate tên dataset

- Slug tự sinh `ais-benchmark-<run-id>`: dài 6–50 ký tự, chữ thường/số/gạch ngang,
  không dấu gạch ngang ở hai đầu hoặc lặp liên tiếp. UUID tránh trùng giữa các run.
- Title tự sinh từ objective đã duyệt: `Benchmark: <objective>`, chuẩn hóa
  khoảng trắng và giới hạn 50 ký tự. Title phải dài 6–50 ký tự, không chứa ký tự
  điều khiển hoặc khoảng trắng ở hai đầu. GUI hiển thị title/slug trước khi chạy.
- Kiểm tra tồn tại trên đúng account trước khi mở phiên và kiểm tra lại trước
  upload. HTTP 404 xác nhận tên còn trống. Nếu get trả 403, phải đọc hết danh
  sách MY của đúng owner (kể cả private) và xác nhận không trùng; 403 riêng lẻ,
  lỗi quyền/mạng hoặc pagination không đầy đủ đều chặn. Không ghi đè/tạo version.

## Chạy và lưu trữ

Dependencies bổ sung nằm trong `requirements-mvp0.txt` (MLflow bắt buộc) và
`kaggle mcp/requirements.txt` (KaggleHub 1.0.2, SDK giữ pin của bundle).
Môi trường `.venv-mvp0` đã cài các dependencies này. Build UI và khởi động lại
Workbench để tải backend/UI mới. Không dùng code hoặc profiles trực tiếp từ
repo `kaggle_token`; publication dùng bundle/account đã chọn trong repo này.

MLflow mặc định lưu tại `.workbench/mlflow/mlflow.db` bằng SQLite. Mỗi
project/benchmark có một experiment. Có thể đặt
`AI_SCIENTIST_MLFLOW_TRACKING_URI` để dùng MLflow server riêng. MLflow phải sẵn
sàng trước khi mở Training/Research session; lỗi đồng bộ không chuyển về nguồn
so sánh khác. Run đã chạy xong giữ kết quả Kaggle, còn biểu đồ báo lỗi và cho
đồng bộ/đọc lại MLflow. Điểm trên biểu đồ phải khớp các mẫu đo đã thu.

Package/receipt/hash nằm trong artifacts của run. Token chỉ có trong môi trường
subprocess publication, không gửi vào agent/SSH/dataset. Publication intent được
lưu trước create để tránh upload lặp khi kết quả không rõ; trường hợp gián đoạn
sau create cần đối soát dataset, không tự tạo version mới.

## Kiểm thử

Kiểm thử local dùng MLflow SQLite thật và provider Kaggle mô phỏng. Bao gồm
test-only benchmark, public visibility, dataset name/collision/network gate,
pinning/context/approval, chặn Training/Research thiếu benchmark trước submit,
so sánh 10/100 steps, nhóm trên 8 run, thiếu metric, MLflow lỗi/extra step và
khôi phục import dở dang. Frontend được kiểm tra bằng TypeScript/Vite build.
Kết quả kiểm tra cuối 2026-10-10: **298 test Workbench pass**, frontend
TypeScript/Vite build pass. Có một cảnh báo deprecation SQLAlchemy từ MLflow,
không có test lỗi.

QA GUI và Kaggle thật: [báo cáo ngày 2026-10-10](BENCHMARK_QA.md).
Đã xác minh dataset public v1, hai root research 10/100 bước trên hai accounts,
hash/evaluator/metric và cùng experiment/chart/ranking MLflow. Run 100 đi trọn
luồng tự động; benchmark và telemetry 10 bước của đợt đầu được khôi phục có audit.
Đợt QA bổ sung đã chạy benchmark mới và research 10 bước hoàn toàn tự động trên
hai accounts, không khôi phục thủ công. Gate hỏi nguồn train đã được Codex thật
xác nhận. Chi tiết phiên thất bại, lỗi sửa và giới hạn kiểm chứng có trong báo cáo QA.

Nguồn API: [KaggleHub upload/create](https://github.com/Kaggle/kagglehub/blob/main/src/kagglehub/datasets_helpers.py)
và [Kaggle CLI quy tắc title/slug](https://github.com/Kaggle/kaggle-cli/blob/main/src/kaggle/api/kaggle_api_extended.py).
