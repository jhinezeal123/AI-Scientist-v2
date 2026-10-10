# QA benchmark và MLflow — 2026-10-10

## Kết luận

**QA trong scope CPU đã đạt.** Full suite cuối cùng **298 tests pass**;
frontend TypeScript/Vite build đã pass. Đợt đầu xác minh dataset public v1 và
hai root research 10/100 bước trên hai accounts, cùng chart/ranking MLflow;
benchmark và telemetry 10 bước có audit khôi phục được giữ nguyên trong lịch sử.

Đợt bổ sung đã đóng hai khoảng trống nghiệm thu: benchmark mới và research 10
bước hoàn tất tự động, không sửa DB/telemetry hoặc xuất bản thủ công; gate train
thiếu nguồn dữ liệu được Codex thật hỏi lại và API từ chối duyệt. Tổng hai đợt
bảy phiên CPU đặt TTL 600 giây, gồm hai phiên thất bại đã xác nhận dừng.
Run 100 bước của đợt trước cũng hoàn tất và đồng bộ tự động.

Đợt QA local dùng production build, Workbench API/storage/collector/hash/pinning và
MLflow SQLite thật. Codex planner, Kaggle terminal/readiness/name lookup/publication
được mô phỏng. Account/token và metric là dữ liệu QA, không phải kết quả nghiên cứu.

## Lỗi đã sửa

1. Catalog ở Idea bị cũ sau khi benchmark hoàn tất. Run thấy dataset mới nhưng
   form Training/Research chưa chọn được nếu không reload. Poll project hiện
   cập nhật history và catalog đồng thời. Đã tạo thêm benchmark và xác nhận
   tự xuất hiện tại Idea, không reload.
2. Gate MLflow chặn Working đúng nhưng API báo nhầm “MCP readiness”. Dùng lỗi
   tracking riêng, trả 503 với “MLflow chưa sẵn sàng; chưa mở phiên Kaggle.”
   Kiểm tra lại GUI và regression test: không provider call/terminal/Working record.
3. Proposal test-only hiển thị `train: null`; đổi thành “Tập train: Không có tập train”.
4. Title tự sinh cắt đúng tại dấu cách có thể bị gate từ chối. Cắt rồi bỏ khoảng
   trắng cuối ở cả backend/preview; thêm regression test tại ranh giới 50 ký tự.
5. Planner thật trả `text` không phải JSON hợp lệ. Chuyển planner CLI sang native
   structured output; schema bắt buộc đủ trường. Các dictionary linh hoạt
   split/metric/budget dùng JSON strings trên wire, adapter decode trước khi
   validator/domain xử lý. Đã chạy transport với Codex thật và tạo proposal thật
   đúng scope; không thêm parser fallback cho Markdown/prose.
6. Kaggle `datasets.get` trả 403 cho slug vắng mặt. 403 không được coi là tên
   trống: kiểm tra đầy đủ danh sách MY của account (gồm private), hết pagination
   mới xác nhận available. Lỗi quyền, sai owner, cursor/page lặp hoặc không đọc
   đủ đều chặn. Đã đối chiếu pagination bằng API thật và thêm sáu regression cases.
7. Agent benchmark tạo `evaluator_interface` dạng object có `function` và
   `cli`, trong khi validator chỉ chấp nhận string. Contract nay chấp nhận cả
   hai dạng và vẫn yêu cầu entrypoint không rỗng. Prompt cũng chỉ rõ log QA phải
   nằm ở `source/` ngoài package public. Test mới xác nhận object hợp lệ và
   file ngoài danh sách trong package vẫn bị chặn.
8. Agent lưu QA sidecar trong `working-agent/source/` local nhưng khai báo nó là
   output từ SSH, khiến backend chặn trước publication. Prompt nay yêu cầu ghi
   log ở `source/` trên Kaggle qua terminal.py và chỉ khai báo remote files.
9. KaggleHub attach dataset mới bị từ chối trong notebook noninteractive.
   Prompt Working nay hướng dẫn `DISABLE_KAGGLE_CACHE=1` cho download HTTP
   qua KaggleHub. Run 100 bước tải được ngay bằng đường này.
10. Hướng dẫn `elapsed_seconds` chưa rõ nghĩa; run 10 ghi thời lượng từng phép
    đánh giá, collector yêu cầu thời gian tích lũy. Prompt nay ghi rõ cumulative
    wall time từ lúc workload bắt đầu. Run 100 có đủ 100 điểm đúng contract,
    không telemetry error và tự đồng bộ MLflow.
11. QA bổ sung tái hiện lỗi transport: `set -e` trong một lệnh thành công
    bị giữ trong Bash; lệnh evaluator thiếu ID sau đó trả exit 2 và đóng shell
    trước khi gửi result marker. Nay reset inherited errexit trước mỗi request,
    giữ cwd/exports và trả nonzero bình thường. Command vẫn có thể bật `set -e`
    cho chính nó; prompt benchmark yêu cầu bắt negative check bằng
    `subprocess.run(check=False)`. Prompt cũng trả native WorkingPayload trực tiếp.
    Regression thực thi Bash thật đỏ trước sửa, xanh sau sửa; **58 test
    SSH/benchmark/system prompt pass**. Phiên phát hiện lỗi đã dừng, chưa có
    publication intent; chỉ retry một phiên sau sửa theo QA bổ sung đã duyệt.
12. Research bổ sung dùng `pip show` in gần 5.000 dòng license trong bước
    kiểm tra môi trường, làm chậm preflight. Hướng dẫn Working nay yêu cầu chỉ
    đọc version bằng `importlib.metadata.version` và tái sử dụng kiểm tra đã
    hoàn tất. Workload thật vẫn hoàn tất trong session đã đặt; không coi thời
    gian preflight/thu log là thời gian riêng của phép đánh giá.

## Kiểm tra GUI

| Tình huống | Kết quả |
| --- | --- |
| Ba mode Idea ngang cấp | Đạt |
| Thiếu metric/cách tính/test | Native validation chặn lưu |
| Test có dữ liệu, train trống | Lưu/duyệt/chạy benchmark được |
| Training/Research chưa chọn benchmark | Native validation chặn lưu |
| Preview title/slug, title dài | Đạt, title giới hạn 50 ký tự |
| Dataset trùng tên | Báo lỗi trước session; giữ APPROVED |
| Benchmark hoàn tất | Link public receipt và dataset v1 trong catalog mô phỏng |
| Catalog refresh | Benchmark mới tự xuất hiện, không reload |
| Hai root độc lập 10/100 steps, hai accounts | Cùng MLflow chart; cuối 0.2/0.1, hạng 2/1 |
| MLflow lỗi khi mở chart | Bỏ chart/ranking cũ, báo lỗi; không fallback |
| MLflow phục hồi, bấm thử lại | Chart và ranking phục hồi |
| MLflow lỗi trước Working | 503, giữ APPROVED; sau phục hồi chạy được |
| Hai run khác benchmark | Cảnh báo, không metric/ranking/curve chung |

Project QA: `036743a050014178946ee68905368e77`.
Latency benchmark: `dadd61e4e787448e9f78a04361b2f3f5`.
Runs 10/100: `6b80d2bfa71140a894e554d3a4f1ed81` / `40ca7a9a4aaf477089f84c77043dc056`.
Memory benchmark: `a658f6fd173c42008e6a8ac3467025e3`.
Run khác benchmark: `34ad3fb3542b465d9e05d9d26a968a7f`.

Run đầu tiên bị lỗi fixture dùng `session_id` thay cho `request_id`. Fixture đã sửa;
run đó không dùng để kết luận lỗi sản phẩm.

## Kiểm tra tự động

- Sau sửa QA: **30 test benchmark/comparison pass**, 49.46 giây.
- Bao gồm name syntax/collision/network gate, public verification, approval
  pinning, cross-project rejection, package hashes, legacy start/batch gate,
  nhóm trên 8 run, MLflow history/provenance/import recovery.
- TypeScript/Vite build pass sau sửa UI, 42 modules; diff check không lỗi whitespace.
- Một cảnh báo SQLAlchemy deprecation từ MLflow; không test lỗi.
- Full suite sau sửa planner/title: **290 pass**, 215.28 giây. Sau thay đổi
  name listing, **41 test benchmark/CLI pass**, 12.92 giây. Sau sửa interface:
  **31 test benchmark pass**, 24.81 giây. Không gọi kết quả 290 là full suite
  sau hai thay đổi mới nhất.
- Ảnh/dữ liệu riêng: `.workbench/qa-evidence`, `.workbench/qa-benchmark`.
- Full suite sau tất cả sửa QA: **297 pass**, 331.61 giây, một cảnh báo
  SQLAlchemy deprecation. Không có test đỏ.
- Full suite sau sửa lỗi inherited errexit từ đợt QA bổ sung: **298 pass**,
  313.85 giây; một cảnh báo SQLAlchemy deprecation, không test đỏ.

## Nghiệm thu Kaggle thật

Project live `534c1f082777446da6f8ff8ed8b4b125`, theo
[scope đã duyệt](BENCHMARK_QA_SCOPE.md). Tổng bốn phiên CPU, mỗi phiên đặt TTL
600 giây, không mở thêm phiên ngoài trần 40 phút session time.
Phiên benchmark đầu bị gián đoạn và Kaggle xác nhận đã dừng; không có publication
intent/receipt. Người dùng duyệt thêm một phiên CPU để giữ đủ benchmark + 2 research
trong tối đa 4 phiên/40 phút.

Dataset: [huynhtrungcuong/ais-benchmark-afa3900e44df43efa5a62d5c8c0ae4b3](https://www.kaggle.com/datasets/huynhtrungcuong/ais-benchmark-afa3900e44df43efa5a62d5c8c0ae4b3).
Publisher đã xác minh READY, public, version 1. Dataset chỉ có benchmark.json,
evaluate.py và test.csv (32 mẫu seed 42, train optional để trống). Hai research
run tải version 1 qua KaggleHub trên Kaggle và đối chiếu đủ ba SHA256.

| Run | Account | Steps | MSE cuối | MLflow hạng | Stop |
| --- | --- | ---: | ---: | ---: | --- |
| `c30f107afd3846d98229b3038859c4d9` | jhin_access_token.txt | 10 | 0.41824593099142654 | 2 | Xác nhận |
| `18fe361cac134ed382e0f83e4f17c74f` | 25520221_access_token.txt | 100 | 0.0013851734605946817 | 1 | Xác nhận |

Cả hai là root độc lập, không parent/variant. MLflow experiment `1` lưu đủ
10/100 points, benchmark provenance giống nhau. Đối chiếu lại predictions bằng
evaluator đã thu từ Kaggle cho cùng kết quả như output/metrics.json và MLflow.
Artifacts mỗi research run 7,438/7,029 bytes; workload command đều trong 60 giây.
GUI hiển thị dataset v1, hai curve và ranking 1/2.
Sau khi mọi phiên đã xác nhận dừng, backend đã được restart; catalog, hai run,
hash/predictions và MLflow comparison vẫn vượt qua toàn bộ đối chiếu trên.

### Audit khôi phục

- Benchmark retry `afa3900e44df43efa5a62d5c8c0ae4b3` đã thực thi evaluator:
  prediction `2*x+1` trả MSE 0.0013851734605946817; thiếu ID 31 bị từ chối.
  Ba public files được thu qua SSH với hash đúng; file QA sidecar chỉ ở local
  khiến danh sách output bị chặn. Sau khi xác nhận session dừng, không có
  publication intent và tên dataset available, đã dùng publisher hiện có để
  xuất bản chính gói đã xác minh, một lần, rồi đối soát receipt và catalog.
  `output/2026-10-10_QA_fixed_test_benchmark_attempt_1/benchmark-recovery.json`
  ghi thao tác này; trạng thái COMPLETED được phục hồi sau receipt public.
- Run 10 bước đã COMPLETED thật, nhưng các elapsed_seconds là thời lượng riêng
  của evaluator. Đối soát đủ 10 dòng gốc, final metric và output; giữ nguyên log,
  cộng dồn các thời lượng đã đo để nhập metric history vào MLflow. Các thời lượng
  này không tái tạo wall clock hoặc ETA của workload; chart/ranking dùng step và
  metric. Audit nằm ở
  `experiment/2026-10-10_QA_inference_10_steps_attempt_0/telemetry-recovery.json`.
- Run 100 bước dùng prompt đã sửa, có elapsed_seconds tích lũy hợp lệ và
  `mlflow-status.json` synced mà không khôi phục.

Evidence riêng trong `.workbench/acceptance/benchmark-2026-10-10/`:
`live-verification.json`, `live-comparison.json`. Ảnh GUI thật:
`.workbench/qa-evidence/live-mlflow-comparison.jpg` và
`live-mlflow-comparison-detail.jpg`. Các file QA riêng không đưa vào package public.

## QA bổ sung theo yêu cầu “QA đầy đủ”

Người dùng duyệt thêm ngày 2026-10-10. Ba phiên CPU bổ sung, mỗi phiên đặt
TTL 600 giây; không dùng GPU/TPU hoặc dữ liệu ngoài scope.

| Tình huống | Bằng chứng | Kết quả |
| --- | --- | --- |
| Train model, benchmark không có train, không chỉ định nguồn train | Idea `2da97e5b97204c2590a0141835887ed2`, proposal `abaef69598084f4da616f748986ce4b3` | Codex thật hỏi nguồn train, NEEDS_CLARIFICATION; duyệt trả 409; không tạo run/session |
| Benchmark bổ sung đầu tiên | `9f594b8a4d5247a38fb4f1db4dd4243b` | FAILED do shell bị đóng bởi inherited errexit; stop xác nhận, không publication intent/receipt |
| Benchmark retry sau sửa | `55102af922304bba8e70b2246e327a8b`, jhin_access_token.txt | Tự động COMPLETED, dataset public v1, QA sidecar thu qua SSH, stop xác nhận |
| Download public không dùng auth | HTTP session mới, không token/cookie/netrc | ZIP 2,848 bytes, đúng ba files/SHA256 trong receipt |
| Research inference không có train | `b1688d907cb649a994cc9b3b8ac7b7be`, 25520221_access_token.txt | Planner không hỏi train; KaggleHub tải v1, xác minh ba hashes; tự động COMPLETED |
| Telemetry và MLflow | 10 phép đánh giá thật; MSE 0.41824593099142654 | Cumulative elapsed cuối 0.5807402609998462 giây; không gap/error; tự sync experiment 2, chart/rank khớp |
| Evaluator đã xuất bản | Kiểm tra lại file thu từ Kaggle | Từ chối thiếu ID, trùng ID, thừa ID và prediction không hữu hạn |
| Đối soát dữ liệu bền vững | Tiến trình Python mới đọc SQLite với mode=ro | COMPLETED/stop, catalog/receipt và 10 MLflow metric points khớp API |

Dataset mới:
[huynhtrungcuong/ais-benchmark-55102af922304bba8e70b2246e327a8b](https://www.kaggle.com/datasets/huynhtrungcuong/ais-benchmark-55102af922304bba8e70b2246e327a8b).
Manifest SHA256 `39abe448800d6d5852d9ecc0e318d92d08bc7cc3490dc68030bed8dfe957ae3b`.
Benchmark/research artifacts 9,119/8,447 bytes; public package 6,161 bytes.
MLflow run `861686b8d37a4d559940d7a5fba3ecee`. Research là root độc lập;
benchmark retry giữ liên kết với lần thất bại. Không sửa lịch sử cũ để gọi là
nghiệm thu tự động.

GUI live xác minh catalog mới xuất hiện không reload, link public/dataset v1,
nguồn chart MLflow, một curve có 10 điểm và MSE cuối đúng. Bộ chart 10/100 bước
đã nghiệm thu ở đợt trước; benchmark mới có một research run, nằm trong experiment
riêng theo đúng benchmark/version bất biến.

Evidence: `.workbench/acceptance/benchmark-followup-2026-10-10/`, gồm
`train-gate-proposal.json`, `train-gate-approval-rejected.json`,
`anonymous-download.json`, `live-verification.json`, `live-comparison.json`,
`durability-verification.json`. Ảnh:
`.workbench/qa-evidence/followup-train-gate.png`, `followup-benchmark-public.png`,
`followup-mlflow-comparison.png`.

## Giới hạn kiểm chứng

Không có kết luận về GPU/TPU hoặc dữ liệu ngoài scope. Lệnh restart backend
cuối đợt bị bộ duyệt tự động từ chối với `blocked by policy`, không nêu lý do
chi tiết; lệnh không được thực thi. Đã kiểm tra dữ liệu bền vững từ tiến trình
đọc mới, nhưng không gọi đó là kiểm thử restart server. Backend hiện tại vẫn
hoạt động; không còn session QA chưa xác nhận dừng.
