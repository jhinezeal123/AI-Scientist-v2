# MVP 0 — hướng dẫn sử dụng và bằng chứng nghiệm thu

## Khởi động từ checkout hiện có

Chạy PowerShell tại `D:\Documents\AI-Scientist-v2`:

```powershell
& .\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --port 8011
```

Mở **http://127.0.0.1:8011/**. Lệnh này khởi động backend, MCP Kaggle qua stdio và
serve GUI đã build. Chỉ chạy một backend cho workspace. Dừng bằng `Ctrl+C`, rồi dùng
cùng lệnh để mở lại. Project không nằm trong browser và không phụ thuộc port.

### Setup lần đầu

Checkout đang dùng Python 3.12, Node 24/npm 11, donor tại `D:\Documents\kaggle_token`
và hai virtualenv riêng. Donor phải có các dependencies, registry account, token và
browser profile đã cấu hình theo README của donor. Đăng nhập Codex CLI và Kaggle bằng
tài khoản của bạn trước khi dùng app; giữ credential trong donor, không đưa vào config/Git.

```powershell
# Từ thư mục repo, nếu chưa có virtualenv:
py -3.12 -m venv .venv-mvp0
& .\.venv-mvp0\Scripts\python.exe -m pip install -r requirements-mvp0.lock.txt

# Build frontend:
Push-Location workbench-ui
npm ci
npm run build
Pop-Location

# Chỉ tạo config nếu chưa tồn tại, giữ nguyên config hiện có:
New-Item -ItemType Directory -Path .workbench -Force | Out-Null
if (-not (Test-Path -LiteralPath .workbench/config.local.json)) {
    Copy-Item -LiteralPath config-mvp0.example.json -Destination .workbench/config.local.json
}
```

Sửa đường dẫn tuyệt đối trong `.workbench/config.local.json` cho máy của bạn:
`donor_root`, `donor_python`, `workspace_root`, `codex_executable`; chọn
`codex_model`, `codex_reasoning_effort`, `kaggle_account_alias` và `kaggle_username`.
Example hiện dùng `gpt-6-luna`/`max`, alias `jhin_access_token.txt`, username
`huynhtrungcuong`. Alias là tên account đã đăng ký trong donor, không phải token.
Executable hiện trỏ tới bản Codex npm trong đường dẫn vendor cố định, không dùng thư mục
version của desktop app. Nếu package layout thay đổi, cập nhật path rồi khởi động lại;
config validation từ chối path không tồn tại trước khi mở app.

### Đi hết pipeline bằng GUI

1. Chọn/tạo project. **Library:** lưu đề bài, evaluation/rules và data reference có schema,
   đường mount, provenance. URL không kèm nội dung được ghi “chưa đọc”; app không tự fetch.
   **Nhập nguồn T01** dùng snapshot đã đọc ngày 2026-10-06, không tự refresh.
2. **Idea:** nhập ý tưởng và **Lưu idea**, chọn idea và checkbox nguồn phù hợp, rồi lập
   proposal. Nếu agent hỏi lại, nhập câu trả lời trong conversation và tiếp tục lập proposal.
3. Đọc mục tiêu, split, metric, các bước, budget và outputs. Bấm **Duyệt proposal vN** của
   bản hiện hành. Sửa idea/nguồn trước approval sẽ làm proposal cũ `STALE`; cần lập bản mới.
   Approval tạo run, chưa tự chạy coder hoặc gửi Kaggle.
4. **Run:** bấm thẻ alias của run đã duyệt → **Tạo code và notebook bằng Codex**.
   Xem source/config/notebook và preflight. Nếu code bị từ chối, dùng lượt sửa còn lại trong
   budget; preflight là kiểm tra contract/static, không chứng minh thuật toán ML đúng toàn bộ.
5. Khi run hiện **Sẵn sàng gửi** (`PREFLIGHT` đạt), bấm **Gửi notebook và chạy trên Kaggle**
   một lần. App kiểm account/rules/data/quota, lưu submit
   intent và ghim owner/ref/kernel/version/script version/session. Không tự gửi leaderboard.
6. Giữ tab **Run** để xem status và log; các tab Library/History vẫn dùng được trong lúc chờ.
   Log dùng cursor được lưu ở backend. Sau exact-session success, app tải outputs, kiểm
   manifest/hash và kết quả, gọi Codex viết report, rồi mới ghi `COMPLETED`.
7. **History → Mở chi tiết run:** xem snapshot idea/proposal/source đã duyệt, report preview,
   notebook/source, facts và output links. Mở lại sau restart vẫn giữ cùng run và kết quả.

### Dữ liệu lưu ở đâu

| Đường dẫn trong workspace | Nội dung |
| --- | --- |
| `.workbench/config.local.json` | Config local, không chứa credential |
| `.workbench/projects/<project_id>/project.sqlite` | Library, idea/proposal, run, journal, log/cursor |
| `.workbench/projects/<project_id>/runs/<run_id>/` | Source, notebook, checks, submit/monitor/collection state, outputs, report/facts |
| `.workbench/runtime-state.json` | Marker worker; restart không replay job Codex |
| `.workbench/logs/` | Log backend/proxy để chẩn đoán |

Những thư mục runtime được ignore Git; commit task không sao lưu dataset hoặc kết quả local.
Muốn sao lưu project, dừng backend rồi sao chép cả thư mục project cùng artifacts.

### UNKNOWN, lỗi và giới hạn MVP0

- `UNKNOWN` nghĩa là chưa xác định được kết quả thao tác/identity; bấm **Đối soát lần gửi** để đọc
  lại trạng thái. Không gửi lại run đã dùng submit, kể cả run failed hoặc lỗi HTTP499.
- Một run active/unresolved khóa run mới. Cấu hình hiện tại cho phép tạo run mới sau khi
  kiểm account không còn session hoạt động; run UNKNOWN cũ vẫn được giữ và cấm gửi lại.
  Không sửa DB/counter để vượt gate. Đổi quy tắc bằng config rồi restart nếu cần.
- Codex job timeout/interrupted không tự replay. Report retry có counter bền vững, mặc định
  tối đa ba lần; outcome chưa biết cần đối soát. Khi user cho phép sửa report ngoài budget,
  lưu giới hạn mới riêng cho run cùng record authorization, giữ nguyên số lượt đã tiêu thụ.
  Report đã lưu và run `COMPLETED` không gọi lại.
- Budget mỗi run tối đa hai coder calls, một training/submit, 600 giây training và
  10,000,000 bytes outputs. Thời gian queue/setup/download/report nằm ngoài training timer.
- MVP0 hiện giữ contract training: metric hữu hạn, epoch telemetry và checkpoint artifact.
  General implement cho EDA/synthetic/PCA/đọc ảnh là phần mở rộng sau này. GUI chung chỉ
  hiện status/log/report; không yêu cầu chart hoặc ETA.
- Nghiệm thu Soil dùng 24 sample/127 ảnh, group split 20 train/4 validation, seed 42 và CNN
  nhỏ từ đầu. EMD validation cục bộ không phải leaderboard score hay bằng chứng chất lượng
  nghiên cứu. Phải đọc và duyệt proposal cho idea mới, không dùng số đo của run cũ.
- Một worker Codex và một account demo; chưa có quản lý nhiều session/account hay compare.
  Log SSE có cửa sổ đọc hữu hạn; app đối soát với log terminal trước khi hoàn tất collection.

## T09 — Bằng chứng hiện tại, 2026-10-06

**MVP0 đã đạt tám tiêu chí chức năng P0 và CP0-A…D trong scope prototype.** Run mới đi qua
Library/idea/approval/Codex/code/submit/status/outputs/report/History bằng GUI, Kaggle success
và app `COMPLETED`. Trong nghiệm thu đã sửa blocker schema của report; user cho phép sửa
tiếp và lượt report thứ tư thành công. Source workload/data giữ nguyên, coder1/2 và submit1/1.

| Bằng chứng | Kết quả |
| --- | --- |
| Proposal được user duyệt | `93d367ebf0d143f6b9fa1b0de54cb812` v1, context SHA `107a43587eeefdbbb1c6a62e2ac896dccafdb342e7a1a402588b64a54f50fdca` |
| Run mới qua GUI | `f45680b33f3d40c0bdfaa6275e6869d2`; coder1/2, native session `01a111c3-3d01-7291-902a-e4c2d76c6a0f`; preflight PASS |
| Source do Codex tạo | SHA `d316d0b31a0b2928f0f88aed3a804a3addf468a5159e96ec6e9d3db2945c4100`; không sửa workload/data thủ công |
| MCP/Kaggle thật | `huynhtrungcuong/ailab-f45680b33f3d40c0bdfaa6275e6869d2`, version1, kernel137345547/script217065827/session355795064; remote COMPLETE, submit1/1 |
| Dữ liệu/training thật | Mount165files; 24 groups/127 ảnh, train20/108 ảnh, validation4/19 ảnh; seed42/CNN[16,32,64]/3epoch |
| Measurements | EMD `184.78710864267654 → 109.24989188610095 → 70.26776872201779`; runner elapsed `30.892590729000005` giây |
| Log live → terminal | RUNNING/session_stream:22 records/cursor1:22; COMPLETE/terminal_rest:21 records/cursor2:21/gap=false. Nguồn replay khác tạo generation mới; terminal được đối soát với runner.log |
| Outputs | metrics656B, checkpoint100939B, result4587B, runner.log835B; bốn file khớp manifest size/hash |
| Report | Ba lần ValidationError trước sửa; sau approval bổ sung, lượt4 tạo report đúng schema/facts; `report_attempts=4`, `report_limit=4`, phase COMPLETED/report.md |
| Restart cuối sau COMPLETED | Toàn bộ snapshot run mới giữ nguyên:28 links HTTP200/hash đúng, report/context/history/cursor/collection state/counters; không replay report/coder/push |
| Restart khi report bị chặn | Trước approval sửa,27 links/counters/report phase3 giữ nguyên; app không tự vượt giới hạn |
| Restart với report đã lưu | Run cũ `e2545599…` giữ 24 links HTTP200/hash đúng,21 records/cursor1:21, report/context/history; không replay |
| Focused checks | 78 backend tests,12 donor/MCP/Windows-worker tests,5 donor runtime fixtures đạt;29 focused backend checks cho report/implementation/handoff và frontend tsc/Vite build đạt; git diff --check đạt |

Lỗi đọc monitor đầu tiên được retry tự động và đã hồi phục; nguyên nhân chi tiết của
RuntimeError đó chưa được lưu. Ba lỗi report xảy ra trước diagnostics mới, nên không suy
đoán trường sai cụ thể. Bản sửa đã thêm JSON schema và kiểu từng trường vào report prompt,
lưu field/type validation với input bị loại, đồng thời giữ error class trong lỗi run.
Khi hết budget, Run card hiện **Report cần xử lý**, chi tiết hiện counter và lý do dừng;
không ghi “Chờ outputs” khi phần bị chặn là report. User sau đó duyệt “cứ sửa report tới khi ổn”.
Đã ghi authorization trong `report-retry-authorization.json`, tăng limit riêng run này từ3 lên4,
không reset counter hoặc thay budget run khác. Lượt4 qua model thật thành công ngay sau sửa.
Report đã đọc lại, khớp metric, split/count và refs; lưu facts/hash và AI assistance. Không thêm
training hoặc submit. Sau restart, GUI History mở lại được run/report và hiện Report4/4.

Evidence local (ignore Git): `.workbench/readiness/t09-live-observations.json`,
`t09-before-restart.json`, `t09-after-restart.json`, `t09-pending-before-restart.json`,
`t09-pending-after-restart.json`, `t09-proposal-review.png`, `t09-running-gui.png`,
`t09-report-blocker-gui.png`, `t09-report-completed-gui.png`,
`t09-gui-before-restart.json`, `t09-gui-after-restart.json`.
Run root chứa approved context, source/notebook/checks, collection-manifest, result-facts,
collection-state và outputs. Regression cases double approval/stale/missing data/wrong session
và observer restart dùng local fixtures, không tạo thêm GPU run.

Kiểm scope diff xác nhận source stock ngoài `ai_scientist/workbench/` và Codex adapter donor
không bị rewrite. Mốc mục tiêu dưới8giờ chưa được chứng minh; số tests không là bằng chứng
đạt mốc thời gian hoặc đạt chất lượng nghiên cứu.

## Nhật ký triển khai T01–T08

Các mục bên dưới ghi trạng thái tại thời điểm từng task được bàn giao; blocker/path/lệnh
lịch sử không thay thế hướng dẫn hiện hành phía trên hoặc bằng chứng T09.

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

## T03 — Library, project store và GUI

T03 đã hoàn thành hành trình tạo project → lưu nguồn/idea → xem context theo nguồn đã chọn → restart và mở lại. Clarification/proposal/approval/Codex job từ GUI được bổ sung ở T04 bên dưới; training thuộc T05/T06.

### Mở GUI

Frontend đã build tại `workbench-ui/dist`, được FastAPI serve cùng origin. Nếu backend T02 của bạn còn chạy, nhấn `Ctrl+C` ở cửa sổ đó rồi chạy lại để nạp code mới:

```powershell
& .\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --config config-mvp0.example.json
```

Mở `http://127.0.0.1:8000/`. Phiên preview dùng khi bàn giao T03 đang ở `http://127.0.0.1:8011/`; dữ liệu project dùng chung trên ổ đĩa, không nằm trong browser. Port không làm thay đổi project store.

1. Chọn project `Soil Grain Size MVP0` đã tạo, hoặc nhập tên để tạo project mới.
2. **Library:** thêm text/URL/dataset reference; sửa nguồn sẽ tăng version. Nút **Nhập nguồn T01** nhập 4 trang competition đã đọc và 1 reference schema/access. Các bản đọc từ 2026-10-06 không tự refresh từ Internet. Chỉ URL, không text → `reference_only`/“chưa đọc”; có text → `provided_text`, không khẳng định app đã fetch URL.
3. **Idea:** nhập và lưu bản nháp, chọn idea đã lưu và các checkbox nguồn, bấm **Xem context đã chọn**. UI hiện source ID/version/status cùng context hash và nội dung. Preview không gọi Codex; lựa chọn checkbox chưa được lưu thành proposal. T04 sẽ freeze snapshot trong proposal.
4. **Run:** hiện các run đã lưu; hiện chưa có training run.
5. **History:** xem proposal/run của đúng project. Khi bàn giao T03, project Soil chưa có idea; T04 đã thêm idea QA và proposal chờ user duyệt. Project `T03 QA — kiểm tra lưu dữ liệu` chứa dữ liệu test có nhãn QA, không dùng cho proposal training.

### Persistence và giới hạn

Mỗi project có DB authority riêng: `.workbench/projects/<project_id>/project.sqlite`. Schema version 1 gồm project_meta/resources/ideas/proposals/runs/logs, WAL/foreign keys/busy timeout và connection riêng cho mỗi operation. Danh sách project đọc các thư mục DB, không có catalog thứ hai. Artifact lớn/dataset không đưa vào DB.

Nguồn có ID, version và SHA256 trên kind/title/URL/content/status. PUT yêu cầu expected_version, trả 409 nếu edit stale. Context chỉ gồm idea và những nguồn được chọn, tối đa 30 nguồn/100 KB; resource ID thuộc project khác bị từ chối. Snapshot trong proposal được lưu riêng và không thay đổi khi sửa resource; proposal chưa duyệt bị đánh dấu STALE. Store primitive này chưa có public API tạo/approve proposal ở T03.

Library không tự tải paper/dataset/URL; nội dung nhập được hiển thị dưới dạng text đã escape. Bản import T01 ghi rõ mount chưa được xác minh và placeholder CSV không phải prediction hợp lệ. Không nhận path file tùy ý hoặc đọc toàn donor repo.

### Build/dev và kiểm tra

```powershell
# Trong workbench-ui:
npm ci
npm run build

# Trong thư mục repo:
& .\.venv-mvp0\Scripts\python.exe -m pytest tests\workbench -q
```

Dev: chạy backend ở 8000 và `npm run dev` trong `workbench-ui`, mở `http://127.0.0.1:5173/`; Vite proxy `/api` và `/health` về backend. Bản build dùng cùng origin, không bật CORS wildcard. Frontend giữ manifest/lock donor; attribution và licenses trong `workbench-ui/NOTICE.md` và `public/fonts/`. Advisory transitive đã ghi ở T01 chưa được sửa bằng nâng lock trong T03.

### Bằng chứng nghiệm thu T03 — 2026-10-06

- `npm run build` (`tsc -b && vite build`) thành công; React/Vite stack giữ donor lock.
- 8 focused test workbench đạt (5 T02 + 3 store/API T03): persistence/isolation/version, snapshot bất biến sau sửa nguồn, reference-only/context bound, stale edit/API/import idempotence.
- GUI thật đã tạo `Soil Grain Size MVP0` (`d062f7ee5f5a48f68442ed951d879275`), nhập 5 nguồn T01, không có idea training được tự tạo.
- GUI QA tạo nguồn URL thiếu text (`reference_only` v1), sửa thêm text (`provided_text` v2), lưu idea QA và xem context với đúng source ID/version/hash. Restart backend thật + reload vẫn giữ source v2, cùng ID và nội dung idea. Đổi về project Soil chỉ thấy 5 nguồn Soil, không thấy QA resource.
- Ảnh bằng chứng local: `.workbench/readiness/T03-library.jpg`. Không gọi Codex, push notebook hoặc training trong thao tác T03.

Blocker attach/mount T01 vẫn cần giải quyết trước submit; T03 không chứng minh P0-04 hoặc cả MVP0 hoàn thành.

## T04 — Clarification, proposal và approval gate

T04 đã triển khai flow **idea → Codex hỏi lại → lưu câu trả lời → proposal mới → user duyệt**. Codex chạy role `mvp0_plan` trong worker nền; GUI vẫn sử dụng được trong lúc chờ. Chưa gọi coder, tạo workload/notebook hoặc submit Kaggle. Approval chỉ pin proposal và tạo một run `APPROVED`; implementation thuộc T05.

### Kiểm thử bằng GUI

Chạy một backend T04 cho workspace. Nếu backend cũ còn chạy, dừng nó bằng `Ctrl+C` trước khi khởi động lại để nạp code mới:

```powershell
& .\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --config config-mvp0.example.json --port 8011
```

Mở `http://127.0.0.1:8011/`, chọn **Soil Grain Size MVP0 → Idea**. Phiên preview bàn giao T04 đã mở tại port này.

1. Xem idea **QA T04** đã lưu: conversation có câu hỏi Codex v1, câu trả lời QA và proposal v2 `AWAITING_APPROVAL`. Câu trả lời QA do agent nhập để kiểm flow, chưa phải quyết định hoặc approval của user.
2. Proposal v2 dùng CNN nhỏ từ đầu, resize 128×128, tối đa 3 epoch; 24 mẫu/127 ảnh thật, chia theo `sample_id` thành 20 train/4 validation, seed 42. Metric validation là log10-weighted EMD trung bình theo mẫu, không phải leaderboard score. Ngân sách tối đa 2 coder calls, 1 training attempt, 600 giây và 10 MB outputs.
3. Kiểm các phần mục tiêu, nguồn/version, split, metric, steps, budget, outputs và context hash. Nếu đồng ý baseline, user bấm **Duyệt proposal v2**. T04 chỉ tạo run đã duyệt, chưa chạy code/training. Bấm lại cùng approval không tạo run thứ hai.
4. Nếu muốn thay baseline, bấm **Sửa idea** trước khi duyệt rồi lập proposal lại. Sửa idea hoặc nội dung nguồn làm proposal chưa duyệt thành `STALE`; backend từ chối approval cũ với HTTP 409. Không sửa nguồn Soil chỉ để thử lỗi; dùng project QA riêng.
5. Để thử clarification mới, lưu idea mơ hồ trong project QA, chọn nguồn đủ nội dung và bấm **Lập proposal bằng Codex**. Khi có câu hỏi, nhập và **Lưu câu trả lời**, rồi chọn nguồn và lập proposal lại. Không tự retry hoặc tự duyệt. Reload browser/restart backend để kiểm conversation, proposal và hash còn nguyên; checkbox nguồn dùng cho lần lập tiếp theo cần chọn lại.

### Gate, persistence và giới hạn

- Proposal lưu body cùng snapshot nguồn, idea và conversation bất biến. Approval kiểm ID/version/hash và context hiện hành trong transaction, tạo intent duy nhất; implementation sau này phải đọc snapshot đã duyệt qua gate.
- Backend từ chối proposal thiếu field, data ref ngoài nguồn được chọn, file/code envelope, budget vượt 2 coder calls/1 training attempt/600 giây/10 MB. GUI không có endpoint gọi coder hoặc submit trong T04.
- Một planner job chạy tại một thời điểm. Restart lúc `PLANNING` chuyển idea sang `FAILED`, yêu cầu user chủ động thử lại; không replay Codex. Runtime `unknown` vẫn cần đối soát như T02.
- Context tối đa 30 nguồn/100 KB, nhưng adapter donor đưa prompt qua argv trên Windows nên có thêm giới hạn chiều dài thực tế. Nếu báo prompt quá dài, chọn ít nguồn hơn hoặc rút ngắn text; không tự bỏ nguồn. Proposal thật v2 dùng Evaluation, rules và T01 schema/access.
- URL-only vẫn là `reference_only`, không được coi là nguồn đã đọc. Planner không fetch URL hoặc gọi MCP; startup chỉ initialize/list tools. Giữ một backend cho workspace để gate worker áp dụng trên cùng process.
- Mount competition chưa được xác minh; approval không giải quyết blocker này. Cần kiểm quyền attach/mount trước submit T06.

### Bằng chứng T04 — 2026-10-06

- Codex thật từ GUI trả clarification v1 (`b5f4daca25704706a2ee82eb442582fe`), rồi proposal v2 (`16f3acfd93e949c28d9fa29a770c50a7`) trong project Soil. Idea `fa86d1ce590e44b7a296821e4735c601` có đủ conversation; v1 `STALE`, v2 `AWAITING_APPROVAL`.
- Context SHA256 v2: `b1fc518a787288f37f5ed01bd118aa1b67f1268bbb0b08f3d8c0ddea7e7bd50e`. Restart backend thật và reload GUI giữ nguyên proposal/version/hash/conversation, không tự lập lại proposal. History Soil có `runs: []`; không tạo workload/notebook hoặc push/training trong flow này.
- `python -m pytest tests/workbench -q` bằng `.venv-mvp0`: **15 passed** (5 T02 + 3 T03 + 7 T04). T04 kiểm clarification/ready, stale source/idea, wrong hash, double approve đồng thời, snapshot đã duyệt, payload sai, restart không replay, API/role gate và nguồn thay đổi lúc planner đang chạy. Fake MCP/coder call counts bằng 0 trước approval; failure cases không dùng GPU.
- `npm run build` (`tsc -b && vite build`) thành công. Donor runtime và code upstream giữ nguyên.
- Ảnh GUI: `.workbench/readiness/T04-clarification.jpg`, `.workbench/readiness/T04-proposal.jpg`.

- User đã bấm duyệt proposal v2; kiểm DB xác nhận `APPROVED` lúc `2026-10-06T06:15:10.520355+00:00` (13:15:10 giờ Việt Nam), context hash giữ nguyên. History có đúng một run `2d1cb7e9cd8b4a058e3efa1bcd6e9630`, state `APPROVED`, chưa có node/report hoặc kết quả thực thi. `runs: []` ở bằng chứng trên là trạng thái trước approval.

**Trạng thái:** T04 đã nghiệm thu, gồm baseline thật được user duyệt. **Chưa đánh dấu CP0-A hoàn thành**, vì readiness attach/mount T01 còn blocker. Implementation được bổ sung ở T05 bên dưới; chưa training.

## T05 — Code, notebook và preflight sau approval

T05 thêm hành trình **Run đã duyệt → Codex tạo source → app build notebook → preflight → mở artifacts**. Proposal/context lấy từ snapshot đã pin trong DB, không nhận body do client gửi và không đổi theo Library hiện tại. T05 không gọi push/train hoặc tải dataset về máy local.

### Sử dụng và kiểm thử GUI

Config thêm `kaggle_username` là username đã xác minh (`huynhtrungcuong` trong example), dùng làm owner của metadata; đây không phải credential. Alias MCP vẫn là `jhin_access_token.txt`; T06 phải đối chiếu owner này với account thật trước submit.

```powershell
& .\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --config config-mvp0.example.json --port 8011
```

1. Mở `http://127.0.0.1:8011/` → **Soil Grain Size MVP0 → Run**.
2. Với run `APPROVED`, bấm **Tạo code và notebook bằng Codex**. GUI chuyển `IMPLEMENTING`, hiện số lượt coder đã cấp; có thể chuyển tab trong lúc chờ.
3. Thành công: run giữ state `PREFLIGHT`, hiện **PASS** và các link source/notebook/context/metadata/checks/journal/manifest. Đây là notebook chuẩn bị cho T06, chưa phải remote run thành công.
4. Preflight fail: app cho đúng một lần sửa nếu còn ngân sách proposal, lưu code node child nối parent. Vẫn fail thì `FAILED`; GUI hiện lỗi và artifacts từng attempt. Không đổi split/metric để pass, không tự tăng coder budget.
5. Runtime bị ngắt hoặc lỗi: attempt đã cấp vẫn tiêu ngân sách. Chỉ chủ động bấm **Tiếp tục trong ngân sách còn lại** nếu còn lượt và đã đối soát worker `unknown`; restart không tự gọi coder hay submit. Bản đã PASS không cho tạo lại bằng cùng run.
6. Reload/restart để kiểm run, code hash, attempts và artifacts còn nguyên. Không tự chạy notebook local để kiểm training; execution/mount thuộc T06.

### Artifacts và kiểm tra

Run root: `.workbench/projects/<project_id>/runs/<run_id>/`. Bản PASS có `source/workload.py`, `payload.json`, `context.json`, `notebook.ipynb`, `kernel-metadata.json`, `checks.json`, `journal.json`, `bundle-manifest.json`; bản từng lượt nằm trong `attempts/1` và `attempts/2`. DB bổ sung bảng `implementation_attempts` cho counter/request/session/node/checks; dùng Node/Journal upstream nguyên bản. `exp_results_dir` của Node chưa điền ở T05 vì chưa có kết quả execution.

- Preflight chỉ `ast.parse`/`compile`, kiểm `run(context, emit)`, telemetry call, config/seed/bounds, nbformat/cell syntax và metadata. Không import/thực thi source Codex trong backend.
- Proposal yêu cầu checkpoint thì preflight kiểm có lời gọi serialization; đây là kiểm tra tối thiểu, không chứng minh checkpoint hợp lệ. Review source vẫn bắt buộc. Review lại source đã lưu không tiêu thêm coder call, không sửa source hay snapshot.
- Metadata private, Internet tắt, GPU bật/TPU tắt, slug `ailab-<run_id>`, `competition_sources` lấy từ các URL Kaggle trong snapshot đã duyệt. Mount `/kaggle/input/soil-grain-size-from-photos` vẫn là expectation, chưa quan sát runtime.
- Notebook dùng runner cố định, output `/kaggle/working/ailab_bundle/output`, tee stdout/stderr vào `runner.log`, ghi metric từng epoch và kiểm measurement hữu hạn/split evidence/artifact paths/output budget trước ghi `result.json`. Wall-clock watchdog chỉ chạy trong kernel remote, không retry training.
- Code SHA256 tính trên UTF-8 source giữ newline LF; manifest hash các file bundle để T06 đối chiếu trước submit. Code/config/metadata được lưu; chưa có measurements/report thật.
- Nếu prompt code/sửa vượt giới hạn argv Windows, app lưu nguyên request vào `coding-request.txt` trong attempt directory và chỉ cho Codex đọc file này bằng thao tác read-only. Không rút bớt snapshot hoặc sửa adapter donor.
- Static checks không chứng minh model đúng, không leak hoặc package/mount khả dụng. Phải review source khớp proposal và quan sát execution thật T06/T08.

Focused checks và build:

```powershell
& .\.venv-mvp0\Scripts\python.exe -m pytest tests\workbench -q
# Trong workbench-ui:
npm run build
```

### Bằng chứng và blocker T05 — 2026-10-06

- GUI thật đã gọi `mvp0_code` cho run `2d1cb7e9cd8b4a058e3efa1bcd6e9630`. Lượt 1 timeout 300 giây trước khi trả source, vẫn tiêu một lượt. Lượt 2 dùng timeout 600 giây cho sinh code (không đổi training budget); Codex session `01a10fe7-70d7-7f82-9c52-efc4d096ae8c` đã trả source/config thật. **2/2 coder calls đã dùng**, không tự cấp lượt thứ ba.
- Source SHA256 `8ad5e7fb1f5d88b9cc3da28c3326a14cb4c1fee000b345251633c7c84e563299`. Notebook nbformat/cell syntax, metadata private/competition_sources, entrypoint, config bounds/seed và telemetry runner đạt kiểm tra local. Metadata owner `huynhtrungcuong`, slug duy nhất `ailab-2d1cb7e9cd8b4a058e3efa1bcd6e9630`.
- Review source thấy 24 labels/127 ảnh thật; filename boundary matching duy nhất, split 20/4 theo mẫu seed42, mean photo predictions trước EMD theo mẫu, clip/cummax/last100, CNN scratch/MAE/3 epochs/deadline và output bound. Chưa thực thi source này ở local/Kaggle; không khẳng định accuracy hoặc execution success.
- **Blocker:** source tạo `validation_report.json` nhưng không lưu checkpoint trong expected outputs của proposal v2. Prompt coder ban đầu đã coi checkpoint là tùy chọn; đây là lỗi app và đã sửa prompt cùng checkpoint preflight guard. Recheck source nguyên bản không gọi coder, ghi `scope-review.json`, cập nhật checks/Node và run thành **FAILED** để chặn submit. Không sửa source, proposal/version/hash hoặc reset counter để bỏ qua lỗi.
- Sau restart, run FAILED, cùng code hash/Node/session/2 attempts và artifacts còn nguyên. Không tạo `result.json`/`metrics.json` đo được; không gọi MCP push/train. T01 mount blocker vẫn giữ nguyên.
- 25 focused test workbench đạt (15 T02–T04 + 10 T05), frontend build đạt. Checks gồm bounded repair/child Node, budget/restart, ownership/double click, source/config/notebook/metadata, telemetry finite/failed output, Windows request-file fallback, active-run admission và exact-hash review chặn submit. Ảnh bàn giao: `.workbench/readiness/T05-run-review.jpg`, `.workbench/readiness/T05-run-summary.jpg`.

### User tự kiểm thử thành công — 2026-10-06

- User tạo idea mới `916d5c40ac5040c29fe18be8eaa0a143` với prompt đầy đủ, chọn nguồn và duyệt proposal `46509c7b6a4d422397f3ef86dfb8de34` v1 lúc 14:03:30 giờ Việt Nam. Proposal mới ghi rõ checkpoint; không dựa vào context của idea cũ.
- User gọi tạo code từ GUI. Run mới `30af70766f794db2992219c330db4e97` ở **PREFLIGHT**, checks **PASS**, error null, dùng **1/2 coder calls**. Codex session `01a11006-7e47-7242-b829-dd0f70238d21`; Node `3c7e16ac15e74f068d0ef56ee89d89b2` được lưu.
- Source SHA256 `e16c10ef306ae631c21820e75a21d59d6fd27c38d80341e45ffd633f38b665fe`. Đối chiếu toàn manifest, hash source file và nbformat thành công. Metadata private/Internet tắt/GPU bật, owner `huynhtrungcuong`, competition source đúng và slug `ailab-30af70766f794db2992219c330db4e97`.
- Review source: đủ 24 mẫu/127 ảnh, boundary matching duy nhất, sorted sample_ids + NumPy default_rng seed42 đúng proposal mới, 20/4 nhóm disjoint; CNN scratch, MAE, 3 epoch, mean ảnh theo mẫu và EMD đúng công thức; có `torch.save` cho `soil_cnn_checkpoint.pt` trong output_dir và khai báo artifact tương đối.
- Chưa có `result.json` hoặc measurements thật; file checkpoint sẽ được tạo sau training, không phải trong T05. Source bật deterministic algorithms; T06 cần kiểm cấu hình CUDA/cuBLAS phù hợp trước launch, cùng package/mount/runtime, không suy diễn execution success từ preflight.

**Trạng thái T05:** **đã nghiệm thu qua thao tác GUI của user và artifact Codex thật.** Run cũ vẫn FAILED, history/counter giữ nguyên; blocker checkpoint của run cũ được giải quyết bằng proposal/run mới có user approval. Trạng thái submit/readiness tiếp theo nằm ở phần T06 bên dưới.

## T06 — Gửi notebook qua MCP và pin identity

**Trạng thái mới nhất 2026-10-06: T06/CP0-B đạt nghiệm thu.** Run xác minh
`e2545599e7e94f66b6fc9f682b23fa72` đã COMPLETE, đúng account `huynhtrungcuong`, version1,
kernel137301710/script_version216981117/session355701890. Log runtime xác minh mount
`/kaggle/input/competitions/soil-grain-size-from-photos` có165files, đủ3epochs và completion marker;
EMD cuối82.4352. GUI Run → **Cập nhật trạng thái từ Kaggle** hiện REMOTE_SUCCEEDED.
Hai run bổ sung được user cấp allowance riêng; mỗi run đúng một SaveKernel, không reset/run lại intent UNKNOWN cũ.
Xem [T06_DEBUG.md](T06_DEBUG.md) cho bản sửa parser ref, mount và cấu hình reconnect.
Ở thời điểm review T06, T08 chưa hoàn tất. Cập nhật 2026-10-06: T08 sau đó đã thu bốn output và report
cho exact session này; xem mục T08 bên dưới. Structured SSE khi notebook còn đang training vẫn chưa xác minh.
Backend dùng CLI npm thay executable desktop theo hash để tránh mất path khi app cập nhật.
Phần bên dưới mô tả luồng dùng và lịch sử lần gửi ban đầu; HTTP499 cũ không phải trạng thái của run xác minh mới.

T06 thêm **Run đã PASS → kiểm readiness đúng account → gửi notebook → lưu version/session → mở Kaggle**.
Backend dùng MCP stdio donor cho tất cả thao tác Kaggle; không đưa credential vào config, source hoặc prompt.

### Cách dùng GUI

**Nhiều run trong project:** lịch sử được giữ nguyên. Run remote đã kết thúc không khóa duyệt proposal mới.
User đã chọn `allow_new_run_after_idle_check=true`: UNKNOWN cũ chỉ cho phép tạo run mới sau khi MCP
xác minh đúng account và không còn session đang hoạt động. App lưu evidence đọc khi duyệt và kiểm lại
trước submit. Không reset counter, xóa UNKNOWN hay gửi lại notebook cũ. Mất kết nối/identity không xác minh
được thì giữ chặn. Một run local đang chuẩn bị hoặc remote đang chạy vẫn khóa lượt mới.

1. Chạy backend bằng lệnh trong phần T05, mở `http://127.0.0.1:8011/` → project → **Run**.
2. Với một run PREFLIGHT mới chưa có intent, nút **Gửi notebook và chạy trên Kaggle** kiểm account/token/cookie,
   rules đã được chấp nhận, quyền tham gia/xem, notebook support, file access, GPU quota, zero active sessions
   và ref mới chưa tồn tại. App không tự tham gia competition hoặc chấp nhận rules.
3. App lưu intent SUBMITTING trong SQLite trước đúng một MCP `push_notebook`. GUI hiện submit 1/1;
   nút gửi biến mất. Có thể chuyển Library/History trong lúc chờ.
4. Khi xác minh được identity, GUI hiện account/ref/version/kernel/session/script_version và link đúng script version.
   Nút **Cập nhật trạng thái từ Kaggle** chỉ inspect exact identity đã pin. Remote success là COLLECTING,
   chưa app COMPLETED; collection/report thuộc T08. T07 tự theo dõi nền bằng identity đã pin.
5. Nếu UNKNOWN, dùng **Đối soát lần gửi**. Đây là thao tác chỉ đọc, không retry push.
   Khi save thiếu version, donor chỉ nhận notebook ref UUID của intent, version1 và source SHA256 trùng notebook
   đã gửi, rồi xác minh exact version history. Không tìm đúng evidence thì giữ UNKNOWN và giữ gate.
6. Reload/restart giữ intent/counter/identity. SUBMITTING bị ngắt chuyển UNKNOWN; app không tự gọi push hoặc coder.
   Không reset counter hoặc đổi account để vượt intent. Với chính sách idle-check được user chọn,
   app có thể cho run mới sau xác minh Kaggle không còn phiên đang chạy; UNKNOWN cũ giữ nguyên.

### Triển khai và artifacts

- Ba wrapper additive: `workbench_inspect_run`, `workbench_logs_snapshot`, `workbench_collect_outputs`.
  Thêm `workbench_launch_readiness` và `workbench_reconcile_run` để không đưa logic credential vào app.
  Chữ ký/return shape các tool cũ giữ nguyên; SDK MCP vẫn `kagglesdk==0.1.37`, không bỏ guard.
- Donor cần các file mới `mvp0_mcp_tools.py`, `mvp0-workspace.json` cùng import registration trong `mcp_server.py`.
  Workspace collection config không chứa credential, chỉ cho phép `.workbench/projects/<project>/runs/<run>`.
  Collection còn được kiểm đúng run UUID, exact identity/success trước và sau download, path/size/hash và tối đa10MB.
  Tại review T06 chưa có outputs thật; T08 sau đó đã thu bốn outputs của run xác minh này và đối chiếu hash với manifest.
- Startup tự mở donor `proxy.py` ẩn nếu port80 chưa có listener, dùng executable/cwd trong config;
  đóng proxy do app tạo khi app đóng, giữ proxy có sẵn. Proxy donor chuyển Bearer token đã chọn qua đúng account,
  không fallback account khác. Readiness introspection dùng SDK qua proxy có sẵn vì đường api.kaggle.com trực tiếp
  báo lỗi trong probe; original donor SDK helper/runtime vẫn nguyên bản.
- Run root có `launch-readiness.json`, `submission-intent.json`, `remote-identity.json` khi pin được,
  `save-receipt.json` cho các lần gửi sau bản sửa diagnostic và `launch-diagnostic.json` của lần thực tế này.
  `submit-bundle/` giữ notebook/metadata/context/payload/checks/source cùng manifest bytes đã gửi;
  tất cả hash nguồn T05 được kiểm trước khi build. Source/config/snapshot giữ nguyên.
- Submit bundle cập nhật runner cố định: cấu hình `CUBLAS_WORKSPACE_CONFIG=:4096:8` trước torch/CUDA,
  ghi `AILAB_MOUNT` sau khi đọc mount thật. Metadata title bằng slug để provider không đổi ref vì title normalization.
  Không gọi Codex lần nữa, không đổi model/split/metric/ngân sách.
- API thêm POST `/api/projects/{project}/runs/{run}/submit` và `/reconcile`. Request không nhận account,
  code hoặc đường dẫn từ browser. Double click/HTTP retry/cancellation/restart không tạo push thứ hai.

### Bằng chứng và blocker — 2026-10-06

- GUI thật đã gửi run `30af70766f794db2992219c330db4e97`, proposal `46509c7b6a4d422397f3ef86dfb8de34` v1.
  Source SHA256 vẫn `e16c10ef306ae631c21820e75a21d59d6fd27c38d80341e45ffd633f38b665fe`, coder1/2;
  submit notebook SHA256 `40ff81f7883500d523214f1ce9205973477262cb3d1d4ef3c244da2dea21b9f9`.
- Live readiness account alias `jhin_access_token.txt`/username `huynhtrungcuong`: token active đúng owner,
  cookie đúng owner, canView/canParticipate/hasAcceptedRules true, userHasEntered/hasScripts true,
  có data files, GPU30h/TPU20h, zero active sessions; expected new notebook ref trả404 trước gửi.
  Quyền sử dụng competition đã được xác minh; mount vẫn cần evidence runtime.
- Donor proxy ghi đúng **một** POST SaveKernel bằng token account này, HTTP499 lúc14:35:55 VN.
  Authenticated exact view của ref sau đó HTTP404; GUI reconcile qua MCP vẫn UNKNOWN.
  Không biết nguyên nhân chi tiết HTTP499: bản nhận acknowledgment ban đầu chưa lưu response body;
  không dựng lại response hoặc coi499/404 là bằng chứng training success/definitively not submitted.
  Đã bổ sung safe bounded acknowledgment receipt cho code hiện tại, không chứa raw token/cookie/body.
- **Chưa có version/kernel/session/script_version pin hoặc runtime mount/metrics**; không gọi push lại,
  không tăng ngân sách hoặc thay dataset. Không đánh dấu T06/CP0-B/P0-04 đã đạt.
- Focused workbench tests kiểm idempotent submit, restart tại SUBMITTING, timeout/missing acknowledgment/mismatch,
  read-only reconciliation, wrong account/hash rejection và bounded/redacted receipt. Donor focused contracts kiểm
  registration/signature, exact-session mismatch, incomplete/wrong-account collection gate và legacy push shape.
  **34 workbench tests + 4 donor tests đạt**, frontend build thành công. Bằng chứng fixtures chỉ chứng minh các gate này.
- Restart backend thật trên8011 đã tự mở proxy donor ởport80; reload GUI giữ UNKNOWN, cùng identity intent/code hash,
  coder1/2 và submit1/1. Hai HTTP submit lặp trả `already_submitted: true`, không cấp push mới.
  Evidence `.workbench/readiness/T06-restart-check.json`, ảnh `.workbench/readiness/T06-run-status.png`.

**Trạng thái tại lần gửi đầu:** nghiệm thu real launch bị chặn bởi provider499 và thiếu exact identity.
Run xác minh mới ở đầu mục này đã giải quyết nghiệm thu T06; run đầu vẫn UNKNOWN để giữ lịch sử.
Run giữ UNKNOWN/submit1/1 sau restart, không có outputs/report và không tự chuyển T07.

### Debug T06 theo yêu cầu user

Xem [T06_DEBUG.md](T06_DEBUG.md): HTTP499 được quan sát ở upstream SaveKernel, chưa có execution để quy lỗi cho workload.
Đã sửa mất thông báo upload/reconcile và mismatch CRLF-file-hash với LF-text-hash do donor đọc trên Windows.
Intent giữ hash artifact gốc và bổ sung `submitted_source_sha256` đã kiểm trên frozen file;
notebook mới ghi LF. Proxy startup giữ log tại `.workbench/logs/kaggle-proxy.log`.
36 workbench tests + 5 donor tests đạt. Reconcile thật sau sửa vẫn UNKNOWN/submit1/1; không có submit mới.

## T07 — Theo dõi nền và log

Đã triển khai. Xem [T07_MONITORING.md](T07_MONITORING.md) cho cách kiểm bằng GUI,
bằng chứng terminal/restart và giới hạn live SSE. Review trước T08: 59 backend tests và 9 donor tests pass;
frontend build đạt. Đã kiểm endpoint SSE của exact session đã kết thúc; live training còn kiểm ở lượt tiếp theo/T09.
Mở **Run → e2545599 → Theo dõi Kaggle** để xem trạng thái và 21 log records.
Theo yêu cầu user, GUI chung đã bỏ biểu đồ metric/epoch và ETA để phục vụ general implement.

## T08 — Thu outputs, report và History

**Phạm vi hiện hành:** theo quyết định user ngày 2026-10-06, giữ T08 training như bản ban đầu.
General implement là phần mở rộng sau MVP0, cần sửa đồng bộ proposal/execution/results.
Lần khôi phục không chạy lại test suite, gọi report mới hay submit Kaggle.

Đã triển khai và kiểm chứng bằng run có sẵn `e2545599e7e94f66b6fc9f682b23fa72`; không gửi lại notebook hoặc chạy training.
App chỉ đánh dấu `COMPLETED` sau khi exact-session manifest, `result.json`, `metrics.json`, runner log,
report và journal đã được xác thực/lưu. Bốn output khớp size/SHA trong manifest. Run giữ coder `0/2`, submit `1/1`.
Report ghi EMD validation cục bộ (không phải leaderboard score), kết quả đo, giới hạn bốn mẫu validation và AI assistance.

**Mở kết quả trong GUI:** mở project → **History**; trong thẻ run đã hoàn tất, chọn **Mở chi tiết run**.
History hiện idea/proposal đã duyệt, nguồn và hash từ snapshot được pin, code hash, metric và artifact links.
Run panel hiện report preview và links tới `report.md`, `result-facts.json`, `output/result.json`,
`output/metrics.json`, `output/runner.log`, checkpoint, source và notebook. `Mở report` trả Markdown;
API cục bộ cho report và facts đã được kiểm HTTP 200. Files nằm trong
`.workbench/projects/d062f7ee5f5a48f68442ed951d879275/runs/e2545599e7e94f66b6fc9f682b23fa72/`.

**Giới hạn và recovery:** T07 đã xác minh terminal/SSE trên exact session đã kết thúc; live SSE khi training
vẫn chưa được xác minh. Một report call thật ban đầu trả `ValidationError`, sau đó report được lưu thành công.
State của lần chạy đó không lưu counter/request ID bền vững: có bằng chứng ít nhất một lỗi và một thành công,
nhưng tổng số lần gọi trước khi counter bền vững chưa xác minh. Counter cap ba lần, UNKNOWN không tự retry,
payload đã lưu được render lại mà không gọi Codex; run `COMPLETED` không bị replay sau restart.
Xem thêm [T07_MONITORING.md](T07_MONITORING.md) và [IMPLEMENT_MVP0.md](IMPLEMENT_MVP0.md#t08--thu-outputs-report-c%C3%B3-ngu%E1%BB%93n-v%C3%A0-history).
