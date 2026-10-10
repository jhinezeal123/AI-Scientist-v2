# Scope QA: pipeline research theo stage

## Ủy quyền cập nhật của user

Sau khi duyệt phiên thứ năm, user đã cho phép tự chủ động chạy thêm phiên CPU
để hoàn tất QA và không hỏi lại cho từng phiên. Ủy quyền này thay giới hạn số phiên
cũ. Vẫn giữ account huynhtrungcuong, benchmark public hiện có, CPU, TTL 600s/work
480s/output 5MB cho từng phiên. Chỉ mở lần tiếp theo khi lần trước đã dừng xác nhận;
giữ evidence FAILED, không replay run cũ. Không đổi provider, dataset hay remote scope.
Deadline 01:39 cũ đã được thay bằng cửa sổ QA tiếp đến 02:09 (19:09 UTC)
theo quyền chạy tiếp của user; giữ 60 lượt agent đã đặt. Nếu cần lượt tiếp,
operator tự ghi bổ sung hữu hạn theo ủy quyền mới trước khi mở phiên.

Phiên thứ sáu đã dừng xác nhận sau Draft đo thật: lỗi adapter gọi `asdict`
trên class ý tưởng Tuning/Ablation gốc, vốn không phải dataclass. Bản sửa giữ
đúng hai thuộc tính `name`/`description` và kiểm tra cả hai loại gốc trước retry.

Scope ban đầu được user duyệt ngày 2026-10-11. Bắt đầu 17:39 UTC ngày
2026-10-10, deadline 18:09 UTC (01:09 giờ Việt Nam). Tổng 60 lượt agent.

Scope MVP5 cũ đã dùng cho coding team bốn seat. QA này kiểm tra hướng sửa mới:
một actor cho từng stage, Human/Agent tùy chọn và agent được ủy quyền duyệt proposal.

## Hạn mức xin duyệt

- Dùng harness/model đã cài và đã có quyền: native Codex + DSH ACP của sản phẩm.
  Không giao việc triển khai cho DSH subagent, không mua dịch vụ hay đổi provider.
- Tối đa **60 lượt agent** tổng cộng, dừng QA sau **30 phút** wall clock.
- Tối đa **1 phiên Kaggle CPU**, account **huynhtrungcuong**, TTL **10 phút**;
  thực thi/thu output trong 8 phút, giữ 2 phút cho dừng và đối soát.
- Tái sử dụng benchmark dữ liệu tổng hợp đã public từ lần QA benchmark trước.
  Không tạo dataset mới, không đổi visibility, không GPU/TPU.
- Một project QA local riêng; output tối đa 5MB. Lưu journal/report/receipt thật.

## Hành trình

1. Human viết idea; proposal agent thực hiện; dừng trước approval human, kiểm tra
   pause/resume giữ nguyên proposal. Từ chối để kết thúc, không mở Kaggle.
2. Full auto: ideation → proposal → approval agent trong grant hữu hạn; một run CPU
   dùng experiment manager gốc qua Draft/Tuning/Research/Ablation, thu metric có
   evidence và summary/report. Chọn hai harness ở các stage khác nhau.
3. Kiểm tra GUI activity, actor approval/version/hash, task/session/handoff, run link,
   output, scope remote đã có và không mở lại session sau restart/reconciliation.

## Tiêu chí

- Actor đúng theo cấu hình, agent không vượt grant và không giả danh human.
- Gate chờ người không mở Kaggle trước câu trả lời.
- Chỉ một admission CPU, metric từ output thật, session được xác nhận dừng.
- Cả hai harness có task DONE với receipt và nguồn dữ liệu được pin.
- Không mở thêm phiên để chữa demo lỗi nếu chưa được duyệt bổ sung.
- Khi một gate không đạt, ghi lỗi/giới hạn thật; không thay evidence bằng fixture.

## Bổ sung xin duyệt sau phiên đầu

Bổ sung này đã được user duyệt; phiên thứ hai đã dùng.

- Phiên CPU đầu, run `033333960c424b109ab8e1ad8225233a`, đã dừng và xác nhận
  `stop_confirmed=true`; lỗi Windows reader giữ file khi backend atomically
  thay `research/pipeline.json`, chưa chạy node Draft.
- Đã tái hiện đúng Windows `winerror=5`; bản sửa retry atomically tối đa 200ms
  đã vượt kiểm tra reader thật và test hồi quy. Lỗi quyền kéo dài vẫn được báo.
- Xin thêm tối đa **1 phiên CPU**, cùng account/benchmark/TTL 600s và work 480s.
  Tổng tối đa 2 phiên; không tăng 60 lượt agent và không tăng deadline 18:09 UTC.
- Dùng workflow/run mới có grant riêng; giữ nguyên evidence FAILED của run đầu,
  không replay nó. Không mở phiên thứ ba nếu phiên bổ sung lỗi.

## Bổ sung lần hai (đã duyệt)

User đã duyệt phiên thứ ba và deadline 01:24 giờ Việt Nam.

- Phiên thứ hai `e9f779be99654084bdcf84957caf0b80` đã xác nhận dừng; pipeline
  ghi FAILED đúng. Windows console cp1252 không in được proposal tiếng Việt;
  backend hiện cấu hình stdout/stderr UTF-8. 5 test search/Windows đã đạt,
  gồm experiment manager thật chạy đủ bốn stage với result tiếng Việt.
- Xin thêm tối đa **1 phiên CPU**, cùng account/benchmark, TTL 600s/work 480s.
  Tổng tối đa 3 phiên. Giữ nguyên tổng 60 lượt agent (đã dùng 8 lượt),
  kéo deadline thêm 15 phút tới **18:24 UTC / 01:24 giờ Việt Nam**.
- Giữ hai run FAILED làm evidence; tạo workflow mới. Không tự mở phiên thứ tư.

## Bổ sung lần ba (đã duyệt)

User đã duyệt phiên thứ tư và deadline 01:39 giờ Việt Nam.

- Phiên thứ ba `da30982f865b4cdbaed7317e5bfdaec1` đã FAILED và xác nhận
  `stop_confirmed=true`. Agent Draft trả `finish` không thực thi vì lời dẫn
  native harness cấm “submit research”, mâu thuẫn với action JSON cho backend.
- Đã sửa lời dẫn để cho phép trả action JSON cho phiên backend đã được duyệt.
  CLI vẫn tắt local tools, giữ sandbox read-only và không nhận credentials.
  27 test harness/workflow đã đạt, gồm kiểm tra action contract và flags isolation.
- Xin thêm tối đa **1 phiên CPU**, cùng account/benchmark, TTL 600s/work 480s.
  Tổng tối đa 4 phiên; giữ 60 lượt agent (đã dùng 16 lượt), deadline
  **18:39 UTC / 01:39 giờ Việt Nam**. Không mở phiên trước khi user duyệt.
- Giữ cả ba run FAILED và hai workflow bị gate chặn trước admission làm evidence.
  Không replay run cũ, không tạo dataset mới và không tự mở phiên thứ năm.

## Bổ sung lần bốn (đã duyệt)

User đã duyệt phiên thứ năm, giữ deadline 01:39 giờ Việt Nam.

- Phiên thứ tư `56e2448e18704df58fbde8d09b2bd322` đã FAILED, có
  `stop_confirmed=true`. Backend đã thực thi action, nhưng source do agent tạo
  có lỗi cú pháp; agent trả prose thay vì action JSON khi báo lỗi. Không có metric.
- Đã chuẩn bị workload bằng cách tái sử dụng source đã chạy thành công ở QA
  benchmark cũ, chỉ đổi predictor/one-step/output names cho scope này. Local QA
  xác minh hash cả ba file public và chạy đủ bốn biến thể bằng evaluator thật:
  baseline/repeat MSE 0.0013851734605946817; ablation MSE 1.002662336883973.
  Resolver download được mô phỏng trong local QA; đây chưa phải nghiệm thu Kaggle.
- Source được chọn và pin trong Library; agent vẫn phải thực thi nó qua action
  backend và trả evidence thật. Native seats dùng gpt-6.1-sol đã có trong catalog;
  approval vẫn dùng DSH ACP. Không dùng code/metric fixture thay thế kết quả live.
- Xin thêm tối đa **1 phiên CPU 10 phút**, tổng tối đa 5 phiên. Không tăng
  deadline **18:39 UTC / 01:39 giờ Việt Nam**, không tăng tổng **60 lượt agent**
  (đã dùng 22 lượt). Giữ account/benchmark/output/TTL/work như scope hiện có.
- Không mở phiên thứ năm trước khi được user duyệt; không replay bốn run FAILED.
