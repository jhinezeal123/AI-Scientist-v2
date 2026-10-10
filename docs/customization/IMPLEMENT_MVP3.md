# MVP 3 — triển khai theo task

Nguồn yêu cầu: [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), mục 7. Mỗi task dưới đây
có thể review riêng; trạng thái chỉ chuyển sang **đạt** khi có bằng chứng tương ứng.
Demo mới đã được người dùng duyệt theo [scope](MVP3_DEMO_SCOPE.md), tổng ba phiên CPU tối đa 30 phút.

| Task | Phạm vi và phần tái sử dụng | Nghiệm thu nhỏ | Trạng thái |
| --- | --- | --- | --- |
| M3-01 · Đóng gói pool 7 account | Lấy registry/token/cookie profile cần thiết từ `D:\Documents\kaggle_token\profiles` vào `kaggle mcp/profiles`; dùng `account_store`, proxy và CLI đã đóng gói; API chỉ trả metadata/readiness, không trả secret. | 7 account có token trong bundle, Git ignore hoạt động; readiness phân biệt token local và account đã kiểm chứng từ Kaggle. | Đạt: 7 local, 7 verified_idle sau auto_login; demo chạy thật trên 2 account |
| M3-02 · Run board | Dùng `WorkingStore`, `RunView.history`, proposal snapshot và cây run; thêm danh sách/filter purpose, state, account, session, error, artifact. | Baseline và hai biến thể hiện đúng project, account và trạng thái; refresh/restart không mất. | Đạt trên 3 run thật |
| M3-03 · Admission, queue và account pin | Mỗi Working có account ghim bền vững và RuntimeWorker riêng; tối đa 2 session/account, tính cả session ngoài Workbench và chỗ đã giữ; queue không submit khi chưa có chỗ/readiness. | Run cùng/khác account chạy đồng thời; run vượt giới hạn chờ tự động; dừng một run không dừng run khác; giữ account qua restart. | Cập nhật song song: nghiệm thu local qua worker/terminal thật, provider Kaggle dùng fixture; demo Kaggle trước đó chạy tuần tự |
| M3-04 · Recovery/control | Giữ logic stop/reconcile/explicit retry hiện có; mở rộng cho account của từng run và queue. | UNKNOWN không bị submit lại; cancel/stop có receipt; retry tạo run/attempt mới có parent. | Đạt; restart terminal thật, active/unknown/cancel dùng fixture |
| M3-05 · Collector chung và đo đường log | Dùng log SQLite, `WorkingStore.logs`, `MonitorStore` và log window hiện có; một collector/session; ghi requests, bytes, latency; định danh generation/cursor và gap. | Hai subscriber đọc cùng collector; cùng cursor không có log mới trả 0 entries; có số đo upstream/client trước/sau trên case tương đương. | Đạt; benchmark live + cursor sau restart, giới hạn đo bên dưới |
| M3-06 · Metrics/ETA | Trích metric có bằng chứng từ log/metrics artifact hiện có; tận dụng `RunMonitorPanel` và curve cũ; ETA chỉ khi có total step/tốc độ. | Curves là dữ liệu thật; thiếu dữ liệu hiện “chưa đủ dữ liệu”. | Đạt: 30 mẫu/run thật; ETA có regression test |
| M3-07 · Batch/ablation và compare | Dùng variant lineage, proposal approval, tags, journal hiện có; batch có giới hạn, từng variant vẫn cần approved scope; compare kiểm protocol split/data/metric. | Baseline + hai variant; khác protocol có cảnh báo và không rank chung. | Đạt: 3 run, cùng data/split, rank B → baseline → A |
| M3-08 · Demo và bàn giao | Chạy integration qua ít nhất hai account khi readiness/quota cho phép; lưu số đo collector, artifacts, ảnh board/compare và hướng dẫn sử dụng. | P3-01…P3-08 được đối chiếu bằng run thật; phần nào chưa kiểm chứng ghi rõ. | Đạt hành trình demo; giới hạn/test nền được ghi rõ |

## Ranh giới kỹ thuật

- `kaggle mcp` là snapshot đóng gói. Không import module hay dùng đường dẫn runtime
  từ `D:\Documents\kaggle_token`.
- `profiles`, `.runtime` và log chứa secret/trạng thái phiên và vẫn Git ignored.
  Không copy Chromium profile, cache, password registry hay toàn bộ donor checkout.
- Token hiện diện **không** đồng nghĩa đã xác minh đăng nhập/quota hoặc quyền
  với dataset cụ thể. Cả 7 account đã được kiểm tra cookie/idle sau đăng nhập bổ sung;
  readiness này không chứng minh quota hay quyền với mọi dataset.
- Mỗi run tái sử dụng một `RuntimeWorker` riêng (một slot/worker), lưu trạng thái
  dưới `working-agent/runtime-state.json`. Worker lập proposal vẫn độc lập.
  Run và phần tạo report/research dùng cùng worker riêng của run đó.
- Upstream `proxy.py` có HTTPS connection pool và token routing đã đóng gói.
  Request của phiên Kaggle phải giữ token/account được chọn, không fallback sang
  identity khác. Không copy nguyên `interface_old/kaggle_pool.py` hay MCP server.

## Bằng chứng hiện tại (2026-10-10)

- Đã copy 6 profile còn thiếu; tổng cộng 7 token và 7 registry entry nằm trong
  `kaggle mcp/profiles` (Git ignored). Chỉ copy `token.txt` và `web-session.json`;
  không copy browser profile/cache hoặc `credentials.json`. ACL của 15 file
  registry/token/cookie được thu hẹp bằng `protect_acl` đã đóng gói.
- CLI `idle` chỉ đọc đã trả `idle=true`, `active_session_count=0`, đúng username
  cho `jhin_access_token.txt` và `25520221_access_token.txt`. Năm account còn
  lại ban đầu có cookie local hết hạn; đã làm mới theo cập nhật bên dưới.
- Test liên quan Working/account/compare/log/queue chạy qua; UI `npm run build`
  chạy qua. Bộ `tests/workbench` rộng: 208 pass, 12 fail ở các kiểm thử cũ
  thuộc ingestion/library/source/system prompt/tree search/variant. Phần lỗi FK
  do bảng collector mới đã sửa bằng cleanup khi xóa run; hai test xóa còn fail
  ở kỳ vọng cũ về restore/legacy snapshot.
- Người dùng đã duyệt [scope demo](MVP3_DEMO_SCOPE.md). Baseline đã hoàn tất
  trên jhin, có 30 mẫu metric thật; final `mse_validation=0.01990025951573262`.
  Batch trả variant A STARTING trên cng và variant B QUEUED trên jhin; cả hai
  đã COMPLETED, mỗi run 30 mẫu metric, cùng dataset/split, có stop receipt.
  Đối chiếu độc lập từng bước khớp gradient descent của code MVP2 với sai số <1e-12.
  Kết quả: B `0.0018004327585372992`, baseline `0.01990025951573262`,
  A `0.13359086016887964` (MSE thấp hơn tốt hơn; đây là QA nhỏ).
  [Evidence đầy đủ](evidence/mvp3-live-acceptance.json),
  [cursor không đổi sau restart](evidence/mvp3-restart-cursor.json),
  [ảnh màn hình so sánh](evidence/mvp3-compare.jpg). GUI đã kiểm cả ba trạng thái
  COMPLETED, cùng protocol, thứ hạng và 30 mẫu/curve; bảng cuộn ngang trên cửa sổ hẹp.
- Hai QA với scope cũ đã hoàn tất thật qua hai account, có artifact SHA256 và
  stop receipt. Một QA Library cũ bị từ chối vì idea không còn trong project;
  backend không submit notebook cho yêu cầu đó.
- Tập cuối store/approval/Working/account/compare/provider/log/cursor: **51 passed**;
  UI production build qua. Bản MVP2 HEAD `c4781e1` cũng có đúng 12 test lỗi của
  suite rộng nêu trên; đã đối chiếu trong checkout tạm, không bỏ/nới test.
  Sau chỉnh guard cuối và instrumentation status: **15 passed** ở Working/provider;
  build cuối sau chỉnh bảng cửa sổ hẹp cũng qua.
- [Benchmark baseline khi đang WORKING](evidence/mvp3-baseline-live-log-benchmark.json):
  20 full-page đọc 35.280 byte; 20 delta đọc 5.500 byte, 0 entries mới, 0 request
  upstream thêm. [QA cng](evidence/mvp3-cng-log-benchmark.json) và
  [QA jhin](evidence/mvp3-jhin-log-benchmark.json) có phép đo bổ sung trên run đã dừng.
  Đây là hai mẫu đọc cache cùng run, không chứng minh tốc độ upstream của MVP2.

### Cập nhật đăng nhập bổ sung — 2026-10-10, 08:22 Asia/Saigon

Theo yêu cầu của người dùng sau commit MVP3, đã copy `profiles/credentials.json`
vào bundle, thu hẹp ACL và xác nhận Git ignore. Dùng `auto_login_core` có sẵn,
không đưa mật khẩu vào tham số dòng lệnh, để làm mới cookie cho `iyppmx`,
`turmii`, `bbucxi`, `vybxkd`, `ynvcii`; cả 5 đăng nhập thành công.
Kiểm tra lại qua Workbench API: **7/7 verified_idle**, đúng username,
`active_session_count=0`. Không mở thêm phiên compute. Báo cáo local không chứa
secret nằm tại `kaggle mcp/.runtime/login-renewal-20261010.json` (Git ignored).

## Đối chiếu checkpoint

| ID | Bằng chứng và giới hạn |
| --- | --- |
| P3-01 | Board thật có ba run, purpose/account/state; batch A STARTING, B QUEUED; queue bị chặn có reason trong fixture. |
| P3-02 | GUI và benchmark đọc cache của cùng baseline đang chạy; không tạo thêm collector/upstream request. Collector dùng chung được kiểm bằng test log/cursor. |
| P3-03 | Restart thật giữ generation/cursor/hash log và trả delta rỗng; repeated-line/gap kiểm bằng fixture. |
| P3-04 | Benchmark full-page/delta cùng run và counters upstream/client đã lưu; baseline API status đo chưa đầy đủ, không suy ra mức cải thiện upstream so với MVP2. |
| P3-05 | 90 mẫu metric thật, đối chiếu độc lập với code/dataset; ETA đo và thiếu dữ liệu kiểm bằng fixture. |
| P3-06 | GUI/API rank B → baseline → A cùng protocol; khác/thiếu protocol không rank trong test compare. |
| P3-07 | Ba stop receipt thật; cancel queued, unknown, retry/không replay kiểm bằng fixture; explicit retry QA có run cha. |
| P3-08 | 7 profile đóng gói; demo chạy thật qua hai account; sau auto_login bổ sung cả 7 verified_idle, đúng identity và không có active session. |

## Cách dùng

1. Khởi động backend như MVP2; bản nghiệm thu mở ở `http://127.0.0.1:8011/`.
2. Trong **Run**, chọn account, **Kiểm tra account**, chọn phần cứng/thời hạn,
   rồi **Bắt đầu Working**. Account đủ 2 session/chỗ giữ thì run vào hàng chờ.
3. Chọn 2–8 run đã duyệt, chưa mở Working trong board; bấm **Batch Working**,
   gán account từng run và bấm **Chạy batch song song**. Không tự tạo thêm biến thể hoặc retry.
4. Hủy item chờ không submit. Item bị chặn hiển thị nguyên nhân; sửa điều kiện
   rồi **Tiếp tục hàng chờ**. Queue tối đa 16 item; lỗi login/quota không retry vô hạn.
5. Chọn 2–8 run để **So sánh**. Chỉ rank run hoàn tất, metric hữu hạn và đúng
   contract, cùng data version/hash + split + metric. Thiếu/khác protocol có cảnh báo.

Các run chạy **song song**, tối đa **2 session/account** cho mọi project trong
instance. Hai account đủ chỗ có thể chạy 4 run đồng thời. Các run cùng account
chờ theo thứ tự; account hết chỗ không chặn account khác. Chỗ đang mở phiên,
STOPPING hoặc UNKNOWN còn được giữ đến khi có stop receipt đúng notebook/run.

Gate đọc lại session Kaggle khi nhận yêu cầu, khi dispatch queue và ngay trước
submit; cộng chỗ giữ local chưa thấy trên Kaggle, đối chiếu notebook reference
để không đếm trùng. Thiếu danh tính session thì tính dư để giữ an toàn; lỗi đọc
Kaggle chặn submit. Session mở bên ngoài sau lần kiểm tra cuối nằm ngoài quyền
điều phối của Workbench. Hủy/dừng chỉ gửi tín hiệu đến worker/SSH của run chọn.

Readiness chỉ quan sát. Khi bấm **Bắt đầu Working**, gate tự dùng credential local
và `auto_login_core` trong bundle để lấy cookie mới nếu hết hạn/không hợp lệ, rồi
xác minh đúng account và còn chỗ trước khi tiếp tục. Hàng chờ kiểm tra lại lúc đến lượt.
Kaggle yêu cầu xác minh bổ sung thì hoàn tất đăng nhập thủ công theo
[hướng dẫn](../../kaggle%20mcp/README.md), rồi thử lại.
Account lưu theo run; stop, inspect và recovery giữ nguyên identity đó.

### Nghiệm thu cập nhật chạy song song

- 68 test Working, parallel Working, account, Settings, generic output và restart
  đã qua; thêm 6 test về report đồng thời, API batch và CLI account boundary đã qua.
- Hai worker cùng account giữ hai terminal/gateway độc lập; run thứ ba chờ rồi
  tự chạy đúng một lần khi có stop receipt. Hai account chạy được bốn run đồng thời.
- Có ca concurrent admission khi provider chưa hiện session, session ngoài
  Workbench, STOPPING chưa xác nhận, UNKNOWN qua restart và chỗ giữ ở hai project.
- Test report dùng worker riêng của run; hủy report của một run không hủy run kia.
  API batch trả `STARTING, STARTING, QUEUED, STARTING` cho ba run account A và một run B.
- Worker, gateway HTTP, SQLite và lifecycle là code thật; runtime Codex và provider
  Kaggle trong các ca trên dùng fixture local. Không tạo notebook Kaggle mới.
- Build frontend đã qua. Bốn test tree-search cũ đã được cập nhật theo hợp đồng
  một run/`mvp0_working`: không tự chạy thêm stage/debug/retry; retry riêng tạo
  attempt mới và giữ nguyên file run trước. Test tiếp tục kiểm pinned approval,
  journal, xóa bản sao Library, dừng đúng worker/session và giữ file có SHA256
  khi kết quả thất bại hoặc timeout. Test token usage hiện có được giữ lại.
  Các file JSON được đọc UTF-8 để kiểm đúng thông báo tiếng Việt trên Windows.
- Chạy lại `test_tree_search`, `test_working`, `test_parallel_working`,
  `test_generic_working` và `test_session_recovery`: **59 passed**, gồm **5/5**
  test trong file từng có bốn test đỏ. Các ca này dùng fixture local, không
  tiêu thụ quota Kaggle.
- Hai tiến trình CLI `prepare` thật trên jhin/iyppmx tạo thành công hai bộ SSH
  độc lập, cùng metadata shared được lưu nguyên vẹn; đọc Kaggle thật xác nhận
  cả hai account vẫn idle. Không gọi `push`/`start` trong ca chuẩn bị này.
- Số đo API vẫn là tổng account trong cửa sổ thời gian run, có thể gồm run khác
  đang chạy đồng thời; GUI ghi rõ phạm vi này. Log/metric/artifact riêng từng run.

## Collector và giới hạn phép đo

- Mỗi Working có một SSH collector; GUI/API chỉ đọc cache SQLite với cursor riêng.
  Cursor `1:seq` bền vững; dòng trùng nội dung vẫn giữ. Log cap 2 triệu ký tự báo gap.
- Frame/byte SSH tách khỏi API upstream. API đo payload, attempts/errors và latency
  theo cửa sổ account, từ SDK proxy, cookie API và notebook status; không tính
  headers/TLS, SSH, browser/login. Readiness cùng account có thể góp vào tổng.
  Instrumentation notebook-status được bổ sung trong lúc nghiệm thu: tổng API
  của baseline chưa đầy đủ; hai variant đã ghi cả status (5 request/run).
- Client API không phát request Kaggle. Byte client là JSON UTF-8; latency server
  và client có định nghĩa riêng. Không dùng byte SSH làm tổng upstream.
- Tái đo bằng `scripts/workbench_benchmark_logs.py --project ID --run ID`.
  Script chỉ đọc. Hai mẫu full-page/delta đọc tuần tự; nếu workload tiến lên,
  subscriber có thể nhận thêm log thật trong cửa sổ đo.
- Telemetry tùy chọn dùng prefix `AILAB_METRIC ` và JSON `step`, `total_steps`,
  `elapsed_seconds`, `metrics`. Tên metric/direction lấy từ proposal. Không có
  total-step/tốc độ thì không dựng ETA; stream lỗi/gap không tạo final metric.
- Restart giữ log/cursor và queue. Phiên active được recovery chủ động dừng/
  đối soát, không tự chạy lại agent. Active recovery được kiểm bằng fixture;
  nghiệm thu restart live ở trạng thái đã dừng.
