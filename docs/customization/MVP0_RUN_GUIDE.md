# MVP 0 — hướng dẫn và readiness note

## Trạng thái T01 — 2026-10-06

Đã bàn giao các artifact và probe của T01; môi trường local sẵn sàng cho T02. Account, cookie, API, quota, rules/evaluation và schema dữ liệu thật đã được xác minh. **Competition readiness còn điều kiện:** account đã tham gia và tải được dữ liệu, nhưng chưa có bằng chứng attach/mount source này trong notebook Kaggle. Không đánh dấu quyền mount đã xác minh chỉ từ việc tải CSV. Chưa tạo implementation/notebook, chưa submit và chưa chạy training.

### Môi trường đã kiểm chứng

- Fork đang ở `codex/personal-implementation-agent`, HEAD `96bd51617cfdbb494a9fc283af00fe090edfae48`. Donor Kaggle đang ở HEAD `b16597527ec0710862aa5a3cb2fc1a4f94d0edc1`. Các thay đổi tài liệu local ở cả hai checkout được giữ nguyên.
- Python `3.12.3`; `.venv-mvp0` được tạo riêng trong fork. `requirements-mvp0.txt` cài thành công; `requirements-mvp0.lock.txt` chốt 70 package đã resolve. `pip check` báo không có dependency hỏng.
- Import thành công `Journal`, `Node`, `MetricValue`, `ExecutionResult`, `CodexCliRuntime`, `AgentRuntime`, `RuntimeRequest`, `RuntimeResult` và `RuntimeProgress`. Import không nạp `torch`.
- Node `v24.15.0`, npm `11.12.1`. `npm ci` thành công trong `kaggle_token/agent_platform/frontend`; lock hiện resolve React/ReactDOM `18.3.1`, TypeScript `5.9.3`, Vite `8.3.1`, plugin React `6.1.1`. npm báo một advisory mức high cho dependency gián tiếp `source-map-js` `1.2.1`; T01 giữ nguyên lock donor như kế hoạch.
- Codex CLI native executable: `C:/Users/DELL/AppData/Local/OpenAI/Codex/bin/2ffcf3015ebd52b4/codex.exe`, version `0.160.0`. Cấu hình hiện tại `gpt-6-luna` / reasoning `max`. Smoke `codex exec --json --ephemeral --sandbox read-only` trả JSONL hợp lệ và envelope readiness; exit code `0`.
- Donor MCP Python `3.12.3`, MCP SDK `1.30.0`, `kagglesdk==0.1.37`. Stdio launch với cwd donor và `tools/list` thành công; thấy 12 tool cũ. Proxy cổng `127.0.0.1:80` đang nhận kết nối.
- Donor `.venv` ban đầu thiếu dependency mở trình duyệt. Đã cài `patchright==1.61.2` (cùng version global đang dùng), `pyee==13.0.1`, `greenlet==3.5.6`; không nâng SDK/global. Import browser helper và `pip check` donor thành công. Dùng browser profile hiện có, không tải browser mới.

### Account và quota đã kiểm chứng

Account được chọn là `huynhtrungcuong`, được user xác nhận lại ngày 2026-10-06, với alias MCP `jhin_access_token.txt`. Cookie mới hết hạn lúc 10:44:13 ngày 2026-10-20 (Asia/Saigon), `expired=false`, `server_invalid=false`. MCP `list_sessions` thành công với 0 session đang hoạt động; giới hạn concurrent GPU batch là 2, GPU interactive là 1.

Cookie API `GetAcceleratorQuotaStatistics` trả HTTP 200: GPU còn **30/30 giờ**, TPU còn **20/20 giờ**, đã dùng 0 giờ; mốc refresh `2026-10-10T00:00:00Z` (07:00 Asia/Saigon). Helper SDK donor `identity()` xác minh token có `username=huynhtrungcuong`, `active=true`. Chỉ probe account này.

### Rules, metric và dữ liệu thực tế

SDK pinned qua proxy, với Bearer token của account đã chọn, đọc thành công competition ID `139732`, `userHasEntered=true`, các trang description/evaluation/rules/data-description và toàn bộ danh sách file. Đã đọc rules; account đã tham gia từ trước, probe không thực hiện thao tác chấp nhận rules.

- Rules giới hạn một account, team tối đa 5, tối đa 5 leaderboard submissions/ngày. Dữ liệu dành cho competition và mục đích phi thương mại/nghiên cứu/học tập. External data/models/tools có điều kiện về khả năng tiếp cận và license; proposal phải ghi rõ nếu sử dụng. MVP này không gửi leaderboard submission.
- Công thức trong ảnh evaluation đã được mở và đọc: `EMD = sum(i=1..10, abs(F_i - prediction_i) * (log10(x_(i+1)) - log10(x_i)))`; score là mean theo mẫu đất, lower-is-better. Đây không phải phép tích phân hình thang. Public/private cuối cùng có trọng số 0.30/0.70.
- Danh sách thật gồm **165 file, 395,376,331 bytes**: 127 ảnh training, 35 ảnh test, 3 CSV. Không có `train.csv`/`test.csv` như trang mô tả; dùng tên file thực tế dưới đây.
- `Training_labels_updated.csv`: 24 dòng mẫu đất, header `sample_id,0.002,0.0063,0.02,0.063,0.2,0.63,2,6.3,20,63,200`. Cả 24 label đều numeric, không giảm, trong `[0,100]`, cột cuối bằng 100.
- `sample_submission.csv`: 10 test IDs và cùng 11 target columns. Placeholder toàn 0, kể cả cột cuối: **không phải prediction hợp lệ**. IDs test được lấy từ file này; không giả định có `test.csv`.
- `ppm_updated.csv`: 5 dòng camera, header `phone,camera,width,height,ppm`. Đây là thông tin calibration, không phải label.
- 127 ảnh training đều map được duy nhất vào 24 `sample_id` bằng filename; mỗi mẫu có 3–8 ảnh. Thư mục thật lồng hai lớp: `Training-All_Photos_updated/Training-All_Photos_updated/` và `Test_All_Photos/Test_All_Photos/`. Tên camera có nhiều biến thể underscore/space; parser phải dựa vào IDs thực và alias camera được kiểm tra.
- Split validation phải giữ toàn bộ ảnh của cùng `sample_id` trong cùng fold; score tổng hợp theo mẫu đất. Đây là ràng buộc tránh leakage; lựa chọn fold/model cụ thể vẫn thuộc proposal. Chưa chứng minh không có quan hệ địa chất giữa các sample IDs khác nhau.

Snapshot nguồn/CSV và ảnh công thức được giữ local trong `.workbench/readiness/` (ignore Git). Sau T03, import text/ref cùng provenance vào Library; không coi các URL chưa đọc là nguồn đã đọc.

### Read-only spike và phần còn cần xác minh

Helper donor `KaggleSdkAccountClient` import được với pin `0.1.37`. Đã kiểm notebook cũ `huynhtrungcuong/temporun-gpu-smoke`, private, kernel ID `126377394`, version **1**: `get_kernel` trả đúng owner/version, `status` trả `COMPLETE`, không có failure message. `output_page` trả 1 file và 5,930 bytes log, không có trang tiếp theo; shape gồm `files`, `log`, `log_truncated`, `next_page_token`. Không chạy lại notebook này.

`status`/`output_page` đọc current version; caller phải gọi `get_kernel` để kiểm version trước khi thu kết quả. `session_logs(session_id)` yêu cầu positive exact session ID; T01 đã kiểm signature/layout, chưa probe endpoint này vì spike không có session ID xác minh. T06/T08 phải pin session của run mới và kiểm log delta/output download thực tế.

**Blocker quyền mount:** việc đã tham gia và tải CSV chứng minh quyền đọc, là bằng chứng thuận lợi cho eligibility, nhưng chưa chứng minh Kaggle cho attach source competition vào notebook của account. Cần kiểm quyền attach trong editor hoặc response eligibility chỉ đọc trước submit ở T06; nếu bị chặn thì dừng submit và ghi lỗi cụ thể. `/kaggle/input/soil-grain-size-from-photos` là đường dự kiến, chưa quan sát runtime. Actual mount/training/output của bài này chỉ kiểm sau proposal approval. Vì vậy T01 chưa được ghi là competition-ready hoàn toàn.

Trang competition công khai mô tả mục tiêu là dự đoán cumulative grain-size distribution từ ảnh. Trang evaluation nêu 11 support diameters `0.002–200 mm`, metric log-weighted Earth Mover's Distance/Wasserstein-1 lấy trung bình trên samples, lower-is-better, cùng ràng buộc prediction không giảm trong `[0,100]` và giá trị tại `200 mm` là `100`. Đây chỉ là thông tin public; nó **không thay thế** xác minh rules, schema/files, group identifiers hay quyền mount bằng account đã chọn. Không chốt proposal/split/training từ tên competition hoặc summary này.

Nguồn đọc công khai:

- [Competition overview và evaluation](https://www.kaggle.com/competitions/soil-grain-size-from-photos/overview/evaluation)
- [Competition data page](https://www.kaggle.com/competitions/soil-grain-size-from-photos/data)
- [Competition rules](https://www.kaggle.com/competitions/soil-grain-size-from-photos/rules)

Các probe readiness không cấp quyền code idea/training. Nếu token hoặc profile cần thay đổi, cập nhật trong donor; không đưa token/password vào config hay tài liệu. Có thể tiếp tục T02/T03 với blocker mount ghi rõ; phải giải quyết trước submit.

## Config mẫu

`config-mvp0.example.json` chứa các đường dẫn/runtime đã kiểm tra và alias account được chọn; không chứa credential. Đường dẫn Codex CLI có mã thư mục version và có thể đổi sau khi cập nhật Codex. Chỉ tạo `.workbench/config.local.json` sau khi danh tính Kaggle được xác nhận.

## T02 — runtime và journal bootstrap

T02 đã triển khai tại `ai_scientist/workbench/`. `runtime.py` nạp module donor nguyên bản từ config, chọn đúng model/reasoning và generic role `mvp0_plan`, `mvp0_code`, `mvp0_report`. Payload được validate bằng Pydantic strict/extra-forbid, reject envelope có files. Chưa expose API gọi coder/report hoặc submit; approval/store thuộc task sau.

FastAPI lifespan tạo một worker `ThreadPoolExecutor(max_workers=1)` và giữ một MCP stdio session qua toàn bộ vòng đời app. Runtime blocking chạy ngoài event loop, không xếp thêm job khi worker bận. Shutdown gửi cancellation và chờ trong `shutdown_seconds` (mặc định 15 giây); dùng nguyên cơ chế timeout/kill/parser của donor. Nếu không xác nhận được child đã dừng, job ghi `unknown` và từ chối nhận job tiếp theo. Không coi timeout shutdown là bằng chứng process đã bị kill.

`.workbench/runtime-state.json` là marker job local tạm thời trước khi có project store T03. Restart chuyển `running` thành `interrupted`, không replay Codex. Marker `unknown` cần đối soát process trước khi reset; ở T02 chưa có GUI đối soát. Journal dùng `Node.to_dict/from_dict` và `Journal.append/get_node_by_id` upstream, deepcopy trước restore, nối lại parent/children qua IDs; không gọi best-node/provider summary.

### Chạy skeleton trên PowerShell

Từ `D:\Documents\AI-Scientist-v2`:

```powershell
& .\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --config config-mvp0.example.json
```

Đọc health tại `http://127.0.0.1:8000/health`; `Ctrl+C` shutdown app. Có thể đổi port bằng `--port 8001`. T02 bàn giao backend skeleton; GUI đã được bổ sung ở T03 bên dưới. Muốn dùng config riêng, copy example sang `.workbench/config.local.json`; sau đó có thể bỏ `--config`.

Smoke explicit chỉ kiểm JSON transport, không tạo workload:

```powershell
& .\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --config config-mvp0.example.json --smoke
```

### Bằng chứng nghiệm thu T02 — 2026-10-06

- Codex CLI thật qua adapter donor trả `RuntimeResult` và `PlanPayload` hợp lệ, files rỗng; smoke exit 0. Session `01a10f5a-a214-7d50-8f89-1e9e6ef451de`. MCP thật initialize/tools-list được 12 tool, đóng session khi smoke kết thúc.
- `tests/workbench/test_bootstrap.py`: 5 focused checks cho journal round-trip/input không bị sửa, role validation, health khi worker bận, cancellation/marker shutdown, restart không replay và unknown outcome không nhận thêm job.
- 3 focused checks donor tại `test_research.py` đạt: bounded CLI fixture/timeout, JSONL final-message/files parser, Codex native read-only argv/parser. Không chạy toàn bộ harness/provider suite.
- Import bootstrap runtime/journal không nạp Torch. Source stock và runtime donor không bị sửa.
- Uvicorn thật trên loopback port 8769 trả `/health` HTTP 200 với session MCP thật; graceful shutdown hoàn tất và không nạp Torch. Port kiểm tra đã được đóng sau probe.

T02 là nền tảng runtime/journal; chưa chứng minh notebook/training/report thật. Blocker attach/mount của T01 vẫn giữ nguyên.
