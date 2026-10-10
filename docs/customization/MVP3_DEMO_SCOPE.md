# Scope demo nghiệm thu MVP3

Demo này cần người dùng duyệt trước khi tạo phiên Kaggle mới. Những run QA đã
được duyệt từ trước chỉ được dùng để kiểm tra routing, queue, collector và stop;
chúng không thay thế demo baseline + hai biến thể bên dưới.

## Ba run đề xuất

| Run | Account | Thay đổi duy nhất | Đầu ra |
| --- | --- | --- | --- |
| Baseline | `jhin_access_token.txt` | Learning rate 0.1 | Code, metrics JSON, prediction CSV, curve stdout |
| Variant A, con của baseline | `25520221_access_token.txt` | Learning rate 0.05 | Cùng loại đầu ra |
| Variant B, con của baseline | `jhin_access_token.txt` | Learning rate 0.2 | Cùng loại đầu ra |

- Tái sử dụng `source/train.py` của run `c3ea17bb7a314f429e24467a63b45723`,
  project `QA Project Tree — live 09-10 (2)`, đã thực thi thành công ở MVP2.
- Hồi quy tuyến tính NumPy trên 96 điểm tổng hợp với seed 42; split cố định
  index 0–63 / 64–79 / 80–95; khởi tạo w=b=0; đúng 30 bước.
- Chỉ thêm tham số learning rate và log `AILAB_METRIC` từ phép đo thật.
- Metric so sánh: `mse_validation`, minimize, sau bước cuối; metric test chỉ
  báo cáo, không dùng để chọn phương án. Cùng một phiên bản nguồn/spec dữ liệu
  trong Library, cùng split và metric cho cả ba proposal.
- CPU; mỗi phiên tối đa 600 giây, mỗi workload tối đa 60 giây, đầu ra ≤5 MB/run.
  Tổng giới hạn thời gian phiên: 30 phút. Chạy tuần tự theo slot agent hiện có.
- Không tải dữ liệu ngoài, không bật PDF/review/web search hoặc nghiên cứu bổ sung.

## Cách nghiệm thu

1. Duyệt scope; tạo proposal baseline, chạy và xác nhận stop receipt.
2. Tạo hai idea con từ baseline, duyệt đúng thay đổi ở bảng, gửi batch.
3. Quan sát account/queue/session, curves/ETA, artifact và parent lineage.
4. Dùng hai subscriber với cursor riêng trên một collector; so sánh payload
   full snapshot với delta cùng cửa sổ, ghi byte/latency/request upstream.
5. So sánh ba run, sau đó kiểm tra khác protocol không có hạng chung.

Không tự mở rộng số run khi quota, đăng nhập hoặc workload gặp lỗi. Retry cần
thao tác rõ ràng của người dùng; trạng thái không xác định phải đối soát trước.
