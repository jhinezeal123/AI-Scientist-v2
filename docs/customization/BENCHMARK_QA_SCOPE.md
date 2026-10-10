# Scope nghiệm thu benchmark trên Kaggle thật

Trạng thái: **đã hoàn tất QA bổ sung 2026-10-10**, benchmark mới và research 10
bước tự động, gate train với Codex thật đạt. Đợt đầu có audit khôi phục
benchmark và telemetry 10 bước tại [báo cáo QA](BENCHMARK_QA.md). Scope MVP3 trước chỉ có ba run hồi quy,
không gồm xuất bản dataset.

Phiên benchmark đầu tiên (`6e89a981d041476d9136345eadd16a0b`) bị gián
đoạn khi backend dừng; đã xác nhận notebook Kaggle dừng và chưa có yêu cầu tạo
dataset. Người dùng duyệt thêm **tối đa một phiên CPU 600 giây**, nâng trần QA
từ 3 phiên/30 phút lên **4 phiên/40 phút**. Phiên benchmark thứ hai là
`afa3900e44df43efa5a62d5c8c0ae4b3`; hai research run giữ scope ban đầu.
Hai research run hoàn tất là `c30f107afd3846d98229b3038859c4d9` (10 bước)
và `18fe361cac134ed382e0f83e4f17c74f` (100 bước). Đã dùng đủ bốn phiên;
không còn phiên dự phòng trong scope này.

## Giới hạn

### Phần QA bổ sung đã duyệt 2026-10-10

Người dùng yêu cầu “tôi duyệt thêm đấy, QA đầy đủ đi” sau khi báo cáo còn thiếu
nghiệm thu benchmark tự động và gate hỏi dữ liệu train bằng Codex thật.
Phần bổ sung gồm gate planner không mở session, **ba phiên CPU tối đa 600
giây/phiên**: một benchmark mới xuất bản một dataset public tổng hợp và một
research 10 bước tải benchmark mới. Dùng hai accounts trong bundle như dưới,
workload ≤60 giây, artifacts ≤5 MB. Phiên đầu của đợt bổ sung
`9f594b8a4d5247a38fb4f1db4dd4243b` hết thời gian sau khi shell bị đóng bởi
`set -e` kế thừa; đã xác nhận dừng và không có publication intent/dataset.
Trong yêu cầu QA đầy đủ đã duyệt, dành đúng **một phiên retry có giới hạn** sau
khi tái hiện và sửa lỗi transport này. Không retry khi publication chưa rõ,
không thêm retry nếu lại thất bại.
Tổng trần cả hai đợt là **7 phiên/70 phút session time**. Giữ dataset public.
Evidence riêng: `.workbench/acceptance/benchmark-followup-2026-10-10/`.

Đã dùng đủ ba phiên bổ sung: phiên lỗi nêu trên, benchmark retry
`55102af922304bba8e70b2246e327a8b` và research
`b1688d907cb649a994cc9b3b8ac7b7be`. Hai phiên sau COMPLETED tự động và cả
ba có stop receipt; chỉ một dataset public mới được tạo trong đợt bổ sung.

### Giới hạn đợt đầu

- Bốn phiên CPU tối đa (gồm một phiên bị gián đoạn), tối đa 600 giây/phiên,
  tổng 40 phút; workload ≤60 giây/run,
  artifacts ≤5 MB/run. Không mở rộng số phiên hoặc đổi accounts khi gặp lỗi.
- Accounts từ bundle: `jhin_access_token.txt`, `25520221_access_token.txt`.
- 32 mẫu test NumPy tổng hợp cố định, seed 42; không có train, không tải dữ liệu ngoài.
- Metric `mse_test`, minimize: mean squared error giữa prediction và nhãn của test
  dataset. Evaluator kiểm tra đầy đủ số mẫu/ID trước tính.
- Tái sử dụng cách sinh dữ liệu/evaluator hồi quy hiện có. Hai workload inference
  dùng tham số tuyến tính khác nhau, 10 và 100 bước đánh giá đo/log metric thật.

## Ba run

1. Benchmark tạo test CSV/evaluator/manifest; KaggleHub upload, API tạo **một
   dataset public mới** trên account `jhin_access_token.txt`. Title/slug dùng
   naming gate mặc định. Dataset chỉ chứa dữ liệu tổng hợp và evaluator/manifest.
2. Research A, `jhin_access_token.txt`: tải đúng dataset/version benchmark,
   chạy baseline inference và 10 bước đánh giá.
3. Research B, `25520221_access_token.txt`: cùng dataset/version/evaluator,
   inference với tham số khác và 100 bước đánh giá; run độc lập, không cần cha/con.

## Nghiệm thu

- Dataset READY/public/version hợp lệ; files tải về khớp hash đã xuất bản.
- Hai research dùng dataset/evaluator benchmark, không tạo test riêng.
- Có output/metric/stop receipt thật; MLflow gom hai run vào cùng experiment,
  chart/ranking khớp phép đo cuối.
- Không bật PDF/review/web search. Không retry nếu submission/create không rõ;
  đối soát trạng thái, không tạo version để ghi đè dataset.
- Giữ dataset public sau nghiệm thu; không tự xóa dataset/account.
