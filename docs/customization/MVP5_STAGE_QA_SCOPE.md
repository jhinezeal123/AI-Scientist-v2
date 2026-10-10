# Scope QA: pipeline research theo stage (chờ duyệt)

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
