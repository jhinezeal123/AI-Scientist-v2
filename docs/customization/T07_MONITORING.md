# T07 — Theo dõi Kaggle trong GUI

Ngày triển khai: 2026-10-06.

**Bổ sung T09:** run `f45680b33f3d40c0bdfaa6275e6869d2`, exact session355795064,
đã xác minh live session_stream khi RUNNING:22records/cursor1:22. Terminal REST đối soát
21records/cursor2:21/gap=false với runner.log; restart giữ log/counter, không push lại.
Lỗi đọc đầu hồi phục tự động. Các giới hạn “chưa kiểm live” bên dưới là trạng thái lịch sử
tại lúc bàn giao T07; xem [bằng chứng T09](MVP0_RUN_GUIDE.md#t09--bằng-chứng-hiện-tại-2026-10-06).

**Điều chỉnh theo user (2026-10-06):** Khôi phục hiển thị loss/metric trong chi tiết run:
biểu đồ, chọn metric và bảng số liệu từng step; mặc định chọn `training_loss` khi có.
Phần này chỉ xuất hiện khi notebook phát telemetry hợp lệ. Tác vụ không có metric vẫn xem
trạng thái và log; thẻ run nhỏ gọn giữ nguyên. ETA chưa hiển thị trong GUI.

## Tính năng

- Một observer cho mỗi run có đầy đủ account/ref/version/kernel/script-version/session đã pin.
- Đọc qua MCP ở nền, cadence 4 giây khi RUNNING, backoff tối đa 30 giây; GUI đọc SQLite mỗi 2 giây.
- Persist log theo vị trí, generation và cursor; không loại dòng chỉ vì nội dung giống nhau.
- Replay ngắn giữ log cũ. Nguồn thay đổi tạo generation/gap; terminal replay đầy đủ đối soát runner.log.
- GUI không yêu cầu tác vụ có metric/epoch. Khi có telemetry, hiển thị loss/metric từ cache
  và giữ nguyên nội dung trong log; chuyển metric không gọi lại Kaggle.
- Quan sát không xác minh được hiển thị UNKNOWN/lỗi đọc, giữ identity và log cũ, thử đọc lại.
- Restart tự tiếp tục observer cho run chưa có terminal log đầy đủ; không gọi coder hoặc push.
- Kaggle success chuyển COLLECTING, failure chuyển FAILED. Outputs/report và COMPLETED thuộc T08.

## Kiểm thử bằng GUI

1. Mở `http://127.0.0.1:8011/`, chọn **Soil Grain Size MVP0 → Run**.
2. Click card **Run e2545599**. Phần **Theo dõi Kaggle** có trạng thái COMPLETE, loss/metric
   và log thật. Chọn metric trong **Metric hiển thị**, mở **Số liệu từng step** để xem giá trị.
3. Reload trang, mở lại card: vẫn đúng 21 records, generation 1.
4. Click **Run 787afc70**: terminal ERROR, không có metric training; log có traceback
   `Runtime contract must provide exactly one input mount.`
5. Với một run mới được duyệt qua pipeline, sau submit mở card: log tự cập nhật, không cần bấm
   cập nhật trạng thái. Có thể chuyển Library/Idea khi collector vẫn chạy nền.
6. Mất kết nối hiện lỗi đọc; nguồn log bị cắt hiện gap rõ ràng. Không coi các trạng thái này
   là tác vụ thành công.

Run cũ UNKNOWN từ HTTP499 không có đầy đủ session nên không tự suy đoán hoặc gửi lại.

## Bằng chứng và giới hạn

- MCP thật: run e2545599, version1, kernel137301710, script_version216981117, session355701890.
  21 records; EMD 194.1037389025 → 105.2035872820 → 82.4352012492; terminal runner.log khớp
  telemetry và completion marker. Không có gap, state COLLECTING.
- Run 787afc70: exact session355718475, 77 records terminal ERROR, state FAILED.
- Backend restart thực tế giữ cursor `1:21`, generation1, 21 records, 3 metric points;
  request cùng cursor trả zero entries. Submit counter vẫn 1/1.
- Local evidence: `.workbench/readiness/t07-terminal-delta.json`, `t07-restart-proof.json`,
  `t07-monitor-ui.png`.
- Fixtures: repeated lines/prefix/short replay, paging/bad cursor, source reset/terminal reconciliation,
  measured ETA/invalid telemetry, restart resume, one observer/run và identity mismatch.
- Chưa kiểm live SSE của một session đang training bằng collector mới. Terminal REST/runner.log
  đã kiểm thật; endpoint SSE đã đọc đúng 21 records của exact session đã kết thúc qua MCP mới.
  Observer active/restart/no-overlap đã kiểm bằng fixtures. P0-05 live còn cần lượt GUI tiếp theo/T09.
- Upstream có thể replay toàn bộ log; MVP0 chỉ giảm payload từ backend tới GUI bằng delta cache.
  Chưa tối ưu incremental bytes từ Kaggle; T08 chưa thu outputs/report vào workflow hoàn chỉnh.

## API và mã nguồn

`GET /api/projects/{project_id}/runs/{run_id}/logs?cursor=1:21&limit=100`

Response có generation, entries(seq/text/stream), next_cursor, has_more, reset, gap,
run_state, observation, metric points, eta_seconds và lỗi đọc/telemetry.

Collector: `ai_scientist/workbench/monitor.py`; cache: `monitor_store.py`;
GUI: `workbench-ui/src/RunMonitorPanel.tsx`; donor MCP additive tool: `workbench_monitor_snapshot`.
SDK giữ pin 0.1.37; không sửa chữ ký các MCP tools cũ.

## Review trước T08

Đã sửa và kiểm tra hồi quy:

- Discovery tạo lại observer đã chết; vẫn chỉ có một task đang chạy cho mỗi run.
- Read-only monitor/reconcile không hạ COMPLETED về COLLECTING/UNKNOWN/RUNNING hoặc làm mất report_path.
  GUI dùng trạng thái COMPLETED của app trực tiếp, không hiểu nhầm thành provider COMPLETE.
- Danh sách run/history cập nhật từ SQLite mỗi 2 giây, không chờ người dùng mở card; không gọi MCP từ GUI.
  History mới thay trạng thái cũ đã quan sát. Paging giữ từng response riêng khi React cập nhật log.
- Telemetry có số nguyên quá lớn chỉ tạo warning; không ngăn lưu log hoặc làm sai trạng thái tác vụ.
- 59 backend tests, 9 donor/MCP/Windows-worker tests pass; frontend build đạt.
- Fresh MCP thật: terminal snapshot 21 records, COMPLETE/complete=true/truncated=false (8.454s);
  session log stream 21 records và completion marker (2.140s), exact session355701890.
- Sau restart backend, API paging 7 records/page trả đúng 3 pages/21 records, cursor1:21;
  request lặp trả zero entries, gap=false, submit counter1/1, invalid cursor bị reject HTTP422.

Evidence: `.workbench/readiness/t07-review-provider.json`, `t07-review-api.json`, `t07-reviewed-ui.png`.
Không còn lỗi đã biết chặn T08. Phần chưa xác nhận là live update/reconnect lúc một notebook vẫn đang training;
ghi nhận riêng cho lượt GUI tiếp theo/T09, không coi terminal replay là bằng chứng hoàn tất P0-05.
