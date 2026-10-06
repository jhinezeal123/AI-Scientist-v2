# T06 — Chẩn đoán SaveKernel HTTP499, 2026-10-06

## Run GUI mới 787afc70: lỗi context và prompt coder

Run `787afc7076204e4f8c5b73344404b107`, kernel137309408,
script_version216996114/session355718475, version1/account huynhtrungcuong:
SaveKernel có acknowledgment thành công, remote ERROR trước training.
Exact terminal log kiểm trước/sau identity ghi
`RuntimeError: Runtime contract must provide exactly one input mount.`

Hai lỗi app được xác định:

1. Prompt coder cung cấp runtime_contract nhưng bundle chỉ truyền input_mounts;
   generated source đọc context.runtime_contract và nhận object rỗng. Bundle đã bổ sung
   runtime_contract.input_mounts khớp input_mounts; prompt liệt kê rõ trường runtime này.
2. Prompt coder ghi cứng Soil split20/4/all24, trái proposal v2 đã duyệt subset12/train9/val3.
   Source của run lỗi thực sự dùng20/4. Đã bỏ instruction ghi cứng và yêu cầu dùng đúng
   proposal.split.method/subset và ghi actual group/image counts.

Preflight hiện là static compile/schema check nên chưa phát hiện mismatch này; không thực thi
workload local. Run đã submit giữ source/hash/context/intent/counter nguyên trạng, không gửi lại.
Bản sửa chỉ áp dụng bundle/prompt của run tương lai; chưa được kiểm chứng bằng một training mới.
Log đầy đủ lưu tại run `provider-terminal-log.json`; không gửi thêm notebook/GPU trong chẩn đoán.

## Cập nhật: nguyên nhân timeout tải artifact và phòng lỗi Codex path

- Backend đã chuyển sang `codex.exe` của bản CLI npm đang cài (0.160.1),
  thay đường dẫn `OpenAI/Codex/bin/<hash>/codex.exe` của desktop app.
  Desktop app cập nhật không còn xóa executable backend đang dùng.
  CLI npm được cập nhật độc lập; cấu hình vẫn kiểm tra executable tồn tại khi khởi động.
- Đo cùng artifact metrics.json 632 byte: HTTP headers sau 1.437s với SDK transport,
  0.687s với requests trực tiếp; checksum giống nhau. SDK cold initialization 2.219s.
- Collector trực tiếp tải đủ bốn artifact trong 8.782s. Qua stdio MCP cũ,
  timeout tái hiện 21.531s và 21.578s; worker chưa chạy đến main/module xử lý.
- Thử chỉ thêm CREATE_NO_WINDOW cho Windows process creation: worker bắt đầu chạy,
  MCP tải đủ bốn artifact trong 17.547s. Đây là lỗi khởi chạy worker bên dưới MCP ẩn,
  không có bằng chứng timeout này do browser/CDN trả file chậm.
- Sửa helper SDK boundary của donor: Windows dùng subprocess ẩn với private module entry,
  truyền credential qua stdin, giữ whole-operation deadline và pinned SDK0.1.37.
  Bypass venv launcher để kill đúng worker; Linux giữ multiprocessing hiện có.
  Không sửa vendor kagglesdk, không tăng timeout, không gửi thêm notebook/GPU run.
- MCP stdio mới sau sửa tải đủ metrics/result/log/checkpoint trong 8.782s;
  exact owner/version/kernel/script/session và file size được kiểm trước/sau,
  SHA256 trùng collector trực tiếp. Local output đã có; GUI collector/report T07/T08 chưa triển khai.
- Bốn focused checks đạt: hidden parent + binary/error round trip, timeout transport,
  slow headers/body hard interrupt, worker exit không receipt.
- Backend đã restart với CLI path mới, health OK và 17 MCP tools. MCP desktop của chat hiện tại
  vẫn giữ module Python cũ; cần reconnect Kaggle MCP/restart Codex để nhận bản sửa.
  Structured SSE chưa được kiểm lại; không suy từ sửa download rằng SSE đã hoàn tất.

Bằng chứng: `.workbench/readiness/artifact-timing.jsonl`, `T06-collected.json`,
`T06-mcp-artifacts-verified.json`. Artifact nằm trong `output/` của run
`e2545599e7e94f66b6fc9f682b23fa72`, tổng 263239 byte.

## Kết quả sau restart và sửa tích hợp

**T06/CP0-B đạt nghiệm thu:** run `e2545599e7e94f66b6fc9f682b23fa72` đã COMPLETE,
SaveKernel HTTP200/version1, account `huynhtrungcuong`, kernel137301710,
script_version216981117, session355701890. Exact version/session kiểm trước/sau terminal REST log;
`AILAB_MOUNT` xác nhận `/kaggle/input/competitions/soil-grain-size-from-photos` có165files,
3epochs hoàn tất trong21.874s, EMD cuối82.43520124919444 và `AILAB_COMPLETE` chứa đúng run UUID.
Collector đọc đã tải result/metrics/runner.log/checkpoint sau sửa worker (xem cập nhật phía trên); report/GUI collection còn T07/T08.

User đã cấp riêng hai lần chạy bổ sung, mỗi lần tối đa600s và một SaveKernel:

| Run | Phản hồi và kết quả |
| --- | --- |
| `669d2173173a43e7a3ca1c2662b237b7` | HTTP200/version1; kernel137300676/script_version216979205/session355699777; ERROR trước training vì mount cũ thiếu `competitions/` |
| `e2545599e7e94f66b6fc9f682b23fa72` | HTTP200/version1, pin identity và runtime mount; COMPLETE |

Những sửa đổi đã kiểm chứng:

- Backend restart ban đầu bị executable path cũ sau cập nhật app; config đã trỏ binary Codex hiện có.
- MCP của Codex dùng Python global/SDK0.1.30 trong khi backend dùng donor venv/SDK0.1.37.
  Đã sửa command MCP thành donor venv và kiểm readiness thật thành công qua connector.
  Đây không phải bằng chứng SDK0.1.30 gây HTTP499 đầu tiên của backend.
- Proxy SaveKernel luôn dùng kết nối mới và không replay POST khi mất phản hồi; các route cũ khác giữ hành vi.
- Kaggle trả `ref=/code/owner/slug`; parser cũ chỉ chấp nhận `owner/slug`, gán nhầm UNKNOWN cho HTTP200.
  Parser mới chỉ chấp nhận các cách viết tương đương của đúng expected ref, reject account/slug/host/version khác.
  Ack đã persist có thể phục hồi read-only; run chẩn đoán đầu đã đối soát thành REMOTE_FAILED mà không push lại.
- Remote source metadata của competition139732 có `mountSlug=competitions/soil-grain-size-from-photos`.
  Sửa bundle context/coder runtime contract và đúng một đường dẫn trong workload; không đổi model/config/metric/split.
  Code SHA mới `4c86e95307c3e3fb1f04fd6fb3273a52b9fceb9c7df0d1b976f4e358e62b57e1`;
  approved context SHA vẫn `d609540bad98a43e6c856519837b0174eb52ec0fb8c7188d855f5dee88ece97e`.

Hai run mới dùng one-off diagnostic script và production SubmissionService/MCP trong allowance explicit,
không phải thêm tính năng retry UNKNOWN tự động. Source/run/intent cũ giữ nguyên; không thêm lượt Codex.
GUI kiểm nút cập nhật trạng thái, identity/link đúng phiên; HTTP submit lặp lại trả already_submitted, không thêm SaveKernel.
**45 workbench tests, 8 donor focused tests và test proxy pool cũ đạt.**

Evidence: `.workbench/readiness/T06-runtime-verified.json`, `T06-provider-diagnostic.json`,
`T06-verification-run.json`, run `scope-review.json`, `remote-identity.json`, `save-receipt.json`,
`terminal-log-evidence.json`, `launch-diagnostic.json`.
Structured SSE log probe chưa kiểm lại; timeout download đã sửa và kiểm bằng MCP mới.
T07/T08 tiếp tục bằng run đã COMPLETE, không cần chạy GPU lại để debug collector.

HTTP499 đầu tiên không tái xuất hiện trong hai lần mới. Body đầu đã mất, nên nguyên nhân chi tiết
của499 vẫn chưa được chứng minh; không kết luận fresh connection là nguyên nhân duy nhất.
Các mục dưới đây giữ chẩn đoán lịch sử trước khi có run thành công.

## Kết luận có bằng chứng

Lỗi quan sát được xảy ra ở bước upload/save/run request, trước khi pin được notebook/session.
Proxy donor nhận **HTTP499 từ upstream Kaggle** và chuyển nguyên status về MCP.
Không có bằng chứng workload `source/workload.py` đã chạy; chưa thể quy lỗi này cho code training.
Chưa đủ thông tin để phân biệt lỗi nội bộ Kaggle với request bị Kaggle từ chối: body lỗi ban đầu đã mất.

| Thành phần | Bằng chứng |
| --- | --- |
| AI Scientist → MCP | GUI thực gọi `push_notebook`, donor đã phát POST SaveKernel bằng đúng account |
| MCP → proxy → Kaggle | Log gốc lúc14:35:55 VN: SaveKernel HTTP499. Trong `proxy.py`, status này lấy từ `conn.getresponse().status`; lỗi kết nối do proxy tự tạo dùng502 |
| Request builder donor | Intercept offline với chính frozen notebook: một POST, JSON38859bytes, notebook text không đổi ngoài newline đọc file, private/GPU/competition_sources/timeout600/SAVE_AND_RUN_ALL đúng các giá trị caller đưa vào |
| Remote lookup | Authenticated exact view HTTP404; ListKernels search ref UUID của đúng account/public+private trả0; ListKernelSessions trả0. Đây là bằng chứng quan sát tại thời điểm debug, không bảo đảm rằng request mất phản hồi không thể hoàn tất muộn |
| Credentials/read transport | ListKernels đọc được notebook smoke đã có của account; readiness trước gửi đã xác minh token active đúng owner và rules/access. Không có bằng chứng toàn bộ MCP hoặc token mất hiệu lực |

Thử intercept dùng credential fixture và chặn `urlopen`, **không gửi SaveKernel thật**.
Regression test xác minh donor giữ cả HTTP499 và thông báo upstream, bridge AI Scientist đọc đúng JSON string của legacy MCP.
Điều này chứng minh ranh giới/serialization được kiểm offline, không chứng minh Kaggle chấp nhận mọi field của request thật.

## Hai lỗi AI Scientist đã sửa

1. **Mất nguyên nhân upload:** bản đầu `_submit` chỉ lưu `ValueError`, không lưu acknowledgment body;
   reconcile sau đó còn ghi đè thông báo upload. Bản hiện tại lưu safe bounded `save-receipt.json` và acknowledgment
   trong intent, hiện lỗi SaveKernel đã lọc credential, giữ nguyên `submission_error` khi reconcile fail.
   Original response không thể phục hồi và không được dựng lại. Proxy do app mở giờ ghi `.workbench/logs/kaggle-proxy.log`
   thay vì bỏ stdout/stderr; log proxy chứa status/endpoint/account alias, không raw Authorization/body.
2. **Sai hash khi đối soát trên Windows:** notebook file T06 có CRLF, trong khi donor `open(...).read()` gửi LF text.
   Hash file giữ nguyên `40ff81f7883500d523214f1ce9205973477262cb3d1d4ef3c244da2dea21b9f9`;
   hash UTF-8 text thực được gửi là `d860ecc9db3b857e006694df9616fac9c21d4cb0f269be61a8a49bffb613bcdb`.
   App bổ sung immutable `submitted_source_sha256`; reconcile dùng hash text này, không thay hash artifact gốc.
   Intent cũ chỉ được bổ sung giá trị sau kiểm đúng hash/path của frozen file. Notebook mới được ghi LF rõ ràng.

Lỗi newline sẽ cản reconciliation sau mất acknowledgment; **không có bằng chứng nó gây HTTP499**.
Source/config/proposal/budget/coder counter và bytes frozen notebook của run cũ không đổi.

## Kiểm chứng sau sửa

- **36 workbench tests + 5 donor focused tests đạt.** Có regression cho legacy499 được giữ qua bridge/reconcile,
  CRLF→LF hash, immutable transmitted hash và không thêm push khi debug/reconcile.
- Restart backend8011 thành công, proxy có log file. Reconcile thật dùng đúng transmitted hash, giữ original HTTP499
  cùng lỗi read hiện tại; run vẫn UNKNOWN/submit1/1, chưa có version/session.
- Evidence: `.workbench/readiness/T06-request-debug.json`, script offline `debug_t06_request.py`,
  run `launch-diagnostic.json` và SQLite intent của `30af70766f794db2992219c330db4e97`.

## Phần chưa xác định

Không biết message chi tiết của HTTP499 đầu tiên, nên không kết luận lỗi quota, GPU availability,
timeout provider hay field cụ thể. SDK mô tả `sessionTimeoutSeconds` là runtime limit thấp hơn global maximum;
không có bằng chứng min3600 hoặc rằng600 bị từ chối. Không tăng timeout/ngân sách theo phỏng đoán.

Run cũ vẫn UNKNOWN, không push lại/reset counter. Blocker identity/mount đã được giải quyết bằng run xác minh mới ở mục đầu.
