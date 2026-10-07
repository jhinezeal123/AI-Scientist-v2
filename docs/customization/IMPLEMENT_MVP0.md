# IMPLEMENT_MVP0 — kế hoạch triển khai prototype cho dev

Ngày: **2026-10-06** · Trạng thái: **T01–T09 đã triển khai và nghiệm thu MVP0 trong scope prototype**.

**Cập nhật Working 2026-10-07 theo yêu cầu user:** code và submit đã gộp thành một
lượt agent làm việc qua SSH trong Kaggle. Đã nghiệm thu GUI thật từ idea đến report,
xác nhận dừng phiên và mở lại sau restart, với run `abb8c794…` tạo CSV trên CPU.
Luồng hiện hành không dùng notebook preflight/contract hoặc artifacts training bắt buộc.
Các bước coder/submit tách rời và gate training phía dưới ghi lại kế hoạch T01–T09 ban đầu;
xem [Working qua SSH](WORKING_SSH.md) và [bằng chứng nghiệm thu](WORKING_ACCEPTANCE.md)
cho hành vi hiện tại, phạm vi đã kiểm và các lỗi tích hợp đã sửa.

Nguồn yêu cầu: [DESIGN_BRIEF.md](DESIGN_BRIEF.md).
Checkpoint sản phẩm và các ID nghiệm thu: [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md#4-mvp-0--prototype-lần-sử-dụng-thành-công-đầu-tiên).
Nền tảng đã chọn: [CUSTOMIZATION_PLAN.md](CUSTOMIZATION_PLAN.md).

**Đích bàn giao:** user mở GUI local, import đề bài/data reference vào Library, nhập idea,
trả lời chỗ mơ hồ, duyệt proposal, rồi để **Codex CLI thật** tạo implementation/notebook,
app chạy notebook qua **MCP Kaggle hiện có**, lấy kết quả thật và báo cáo. Đóng/mở app vẫn xem được
nguồn, notebook và kết quả; app không tự submit lại run cũ.

**Giới hạn:** một người, một project nghiệm thu, một account được chọn, một run hoạt động tại một thời điểm.

**Điều chỉnh số lượt ngày 2026-10-07 theo yêu cầu user:** không giới hạn tổng số lượt code
hoặc execution do user yêu cầu. Mỗi lần bấm gọi coder một lượt, không tự gọi lượt tiếp theo.
Sau khi execution kết thúc, user dùng **Tạo lượt chạy mới** từ cùng proposal đã duyệt,
dùng lại code hoặc yêu cầu sửa rồi submit. Mỗi execution có run ID và identity riêng;
request gửi lặp của cùng execution được chống trùng. Các quota `coder_calls<=2` và
`training_attempts=1` trong kế hoạch nghiệm thu ban đầu dưới đây là lịch sử, không còn áp
dụng như quota user. Thời gian/dung lượng vẫn thuộc ngân sách mỗi execution đã duyệt.
Xem [hướng dẫn hiện hành](D:/Documents/AI-Scientist-v2/docs/customization/MVP0_RUN_GUIDE.md)
và [research framework](D:/Documents/AI-Scientist-v2/docs/customization/TRAINING_FRAMEWORK_RESEARCH.md).

**Điều chỉnh do user chọn:** project giữ nhiều run lịch sử. `REMOTE_SUCCEEDED` và `REMOTE_FAILED`
không khóa lượt mới. Khi `allow_new_run_after_idle_check=true`, UNKNOWN cũ có thể được giữ nguyên
trong lúc duyệt run mới, nhưng phải kiểm identity account và zero active sessions qua Kaggle MCP.
Kiểm lại trước submit; mỗi run vẫn chỉ có một durable submit intent và không gửi lại UNKNOWN.
Nếu không đọc/xác minh được phiên đang chạy thì giữ gate, không tự cho qua. Run local đang chuẩn bị
hoặc run đã pin đang chạy vẫn khóa lượt khác theo giới hạn một run hoạt động.
Đích lần sử dụng thành công đầu tiên **<8 giờ**, tính cả setup/readiness/queue/run; không phải thời hạn hoàn thành
toàn bộ sản phẩm. Có **9 task**, cùng tạo thành một MVP dùng được, không coi mỗi module là một MVP.

## 1. Scope và cửa nghiệm thu

Bài nghiệm thu: [Soil Grain Size from Photos](https://www.kaggle.com/competitions/soil-grain-size-from-photos).
Chạy một baseline training nhỏ trên **dữ liệu thật** của competition, có validation, metric theo step/epoch
và report. Mô hình/split/metric chỉ được chốt sau khi đọc được dữ liệu, evaluation và rules.
Không đoán bài toán từ tên cuộc thi. Local validation không được gọi là leaderboard score.

| ID | Điều kiện phải đạt | Task chính |
| --- | --- | --- |
| P0-01 | Library giữ đề bài/data reference qua restart; agent dùng đúng nguồn project | T01, T03, T04, T09 |
| P0-02 | Idea mơ hồ được hỏi lại; trước approval không gọi coder, tạo implementation hoặc submit | T04, T09 |
| P0-03 | Sau approval, Codex CLI thật tạo implementation/notebook bám proposal; checks cơ bản đạt | T02, T05, T09 |
| P0-04 | Notebook chạy thật qua MCP trên data competition; terminal success; lưu đúng account/kernel/version/session | T01, T06, T08, T09 |
| P0-05 | GUI nhận log delta theo cursor, không mất/nhân đôi dòng, kể cả nội dung lặp; UI phản hồi khi agent/run đang chạy | T07, T09 |
| P0-06 | Thu outputs/report/history; metric và visualization hiển thị theo task khi có artifact thật | T05, T08, T09 |
| P0-07 | Idea → proposal → code → run → report cùng project; restart không tự submit trùng | T03–T09 |
| P0-08 | Sau setup, user đi hết flow qua GUI, không copy code/test/upload notebook bằng tay | T03–T09 |

MVP 0 giải quyết N01/N02 bằng một luồng implement thực; N03 bằng Library text/URL;
N04/N05/N09 bằng status/log/metric/history tối thiểu; tạo boundary cho N06 và bước đầu của N08.
Chưa chứng minh general trên nhiều bài, chưa có RAG, nhiều account/run, harness thứ hai, Ideathon hoặc team.

Không có: tự nghĩ idea, BFTS nhiều nhánh, tuning/ablation/multi-seed, full paper reproduction,
PDF/OCR, vector DB, Notion/W&B, leaderboard submission, distributed scheduler, auth/team hoặc checkpoint resume training.
Khôi phục **theo dõi** một run sau restart thuộc scope; khôi phục optimizer/training thuộc MVP sau.

## 2. Baseline và cách custom clone

| Nguồn | Vị trí/baseline | Cách dùng trong MVP 0 |
| --- | --- | --- |
| Fork sản phẩm | `D:/Documents/AI-Scientist-v2`, branch `codex/personal-implementation-agent` | Đặt app, GUI, storage và tài liệu mới tại đây |
| AI Scientist/v2 upstream | `96bd51617cfdbb494a9fc283af00fe090edfae48` | Giữ source/license; dùng thật `Node`, `Journal`, `MetricValue`, `ExecutionResult` |
| Repo Kaggle hiện tại | `D:/Documents/kaggle_token`, baseline `b16597527ec0710862aa5a3cb2fc1a4f94d0edc1` | Chạy MCP ở đây; reuse Codex runtime và các helper có sẵn |
| Remote | origin: `jhinezeal123/AI-Scientist-v2`; upstream: `SakanaAI/AI-Scientist-v2` | Clone/fork đã có; không clone lại hoặc đổi origin |

Baseline hash là provenance, không phải bằng chứng runtime đã chạy. Hai checkout đang có thay đổi tài liệu local;
dev giữ chúng, không reset/clean để lấy một workspace trống.

### Quyết định thay đổi tối thiểu

1. **Thêm entrypoint `python -m ai_scientist.workbench`**, không sửa `launch_scientist_bfts.py` thành một app khác.
   Launcher stock kéo Torch/GPU/tree search/provider APIs/writeup ngay lúc import; không phù hợp đường local Windows này.
2. **Dùng nguyên `Node/Journal`**, thêm service mỏng điều phối approval → code → Kaggle → report.
   MVP 0 chỉ có node implementation và node sửa lỗi cục bộ khi cần; không khởi động `AgentManager`/`ParallelAgent`.
3. **Dùng nguyên `CodexCliRuntime` từ donor qua đường dẫn cấu hình**, chỉ tại module adapter.
   Không copy cả `agent_platform`, không viết lại subprocess/JSONL/timeout/cancel.
4. **Gọi MCP qua stdio**, không import `mcp_server.py` vào app và không gọi Kaggle SDK trực tiếp từ business service.
   Bổ sung ba tool nhỏ trong donor để lấy structured identity/logs/outputs; giữ nguyên tool cũ.
5. **Reuse scaffold frontend**, không mang nguyên `App.tsx` lớn với team/Notion/W&B sang fork.
   Tạo GUI nhỏ dùng React/CSS/SVG sẵn có, đủ hành trình nghiệm thu.

Dependency local vào donor là lựa chọn có chủ đích để giao prototype nhanh trên máy hiện có.
MVP 0 chưa là gói cài đặt độc lập; tách adapter thành module phân phối được là backlog sau khi flow thật thành công.
Ghi rõ đường dẫn và revision donor trong config/guide; không dùng đường dẫn máy này rải khắp service.

### Giữ, bỏ khỏi đường chạy, thêm

| Thành phần | Hành động cụ thể | Lý do/phạm vi |
| --- | --- | --- |
| `ai_scientist/treesearch/journal.py` | Giữ nguyên; dùng `append`, `get_node_by_id`, `Node.to_dict/from_dict` | Reuse trace plan/code/parent/result, không dựng journal thứ hai |
| `treesearch/utils/metric.py`, `interpreter.ExecutionResult` | Giữ nguyên; dùng kiểu dữ liệu | Không chạy local interpreter/GPU để train trong MVP 0 |
| `agent_manager.py`, `parallel_agent.py` | Giữ file, không import/khởi động trong entrypoint mới | Các stage stock và plan+code cùng call không đáp ứng approval trước code |
| Backend OpenAI/Anthropic stock | Giữ source; cài dependency nhẹ cần cho import journal; không gọi API | Tránh refactor upstream chỉ để bỏ vài dependency import |
| `Journal.get_best_node`, `generate_summary`, `save_experiment_notes` | Không gọi trên đường MVP 0 | Một số đường này tự gọi provider LLM; report dùng Codex đã cấu hình |
| Ideation, VLM, LaTeX/writeup/review, multi-seed/ablation | Giữ trong repo, không chạy/cài dependency nặng chỉ cho chúng | Chưa cần cho một implement run |
| Donor `AgentRuntime`/`CodexCliRuntime` và parser | Dùng module gốc, không đổi tên hàng loạt | AgentRuntime đã làm trách nhiệm AgentPort |
| Donor schema `planner/coder/analyst` | Không dùng cho role mới | Contract training cũ là synthetic CPU; không dùng cho competition data |
| Donor MCP/pool/account registry/proxy | Giữ hiện trạng; thêm wrapper có namespace `workbench_*` | Không viết account manager hay execution platform mới |
| Frontend package/lock/config và CSS | Copy/adapt phần cần dùng, ghi nguồn | Reuse stack sẵn có, không thêm chart/UI framework |
| Workbench service, project store, notebook builder, GUI | Thêm tại fork | Chỉ các trách nhiệm đang thiếu cho hành trình MVP 0 |
| `LICENSE`, notices, upstream README phía dưới | Giữ | Ghi attribution khi reuse; report ghi rõ có AI hỗ trợ |

**Không có structural refactor bắt buộc trong plan mặc định.** Code mới và registration tool là thay đổi behavior bổ sung.
Nếu phát hiện phải tách/move code cũ: characterization/existing tests phải xanh trước; tạo diff refactor riêng giữ hành vi,
kiểm lại rồi mới tạo diff behavior. Không gộp/squash hai phase. Không xác minh được preservation thì dừng nhánh refactor đó,
không tiếp tục behavior trên một nền chưa kiểm chứng. Áp dụng theo [pattern-design](C:/Users/DELL/.codex/skills/pattern-design/SKILL.md).

## 3. Stack chốt cho MVP 0

| Phần | Chọn gì | Ghi chú triển khai |
| --- | --- | --- |
| OS/runtime | Windows, Python **3.12**, Node hiện có **24.15.0** | Shell đã có Python 3.12.3; xác minh executable thực tại T01 |
| Backend | **FastAPI `>=0.115,<1`**, **Uvicorn `>=0.30,<1`**, **Pydantic `>=2.8,<3`** | Reuse range donor; một process, `workers=1`; bind `127.0.0.1` |
| Persistence | **stdlib `sqlite3`**, WAL, files local | Một DB mỗi project; không SQLAlchemy/Alembic/DB server |
| Agent | **Codex CLI hiện có**, `CodexCliRuntime`/`AgentRuntime` donor | Model/reasoning lấy từ cấu hình đang dùng; không mua API/model mới |
| MCP client | **MCP Python SDK `>=1.12,<2`**, stdio session dùng lại | Giữ nhánh v1 tương thích donor; không nâng v2 trong prototype |
| Kaggle execution | MCP cũ; SDK **`kagglesdk==0.1.37`** trong môi trường MCP nếu dùng helper donor SDK | Account/cookies/tokens vẫn ở donor; app chỉ biết alias và identity công khai |
| Notebook | **nbformat `>=5.10,<6`**, AST/`compile()` của Python | Build/validate notebook local; train/test thực trên Kaggle |
| Upstream journal import | `numpy`, `dataclasses-json`, `rich`, `humanize`, `black`, `jsonschema`, `backoff`, `funcy`, `openai`, `anthropic` | Dependency import của lõi stock; không tạo client/provider call |
| GUI | **React 18.3.1**, **ReactDOM 18.3.1**, **TypeScript 5.6**, **Vite 8.3.1**, plugin React 6.1.1 | Reuse package.json + package-lock.json + tsconfig/Vite config donor; `npm ci`, không tự nâng version |
| Visualization | Biểu đồ loss/metric từ telemetry và artifact links khi workload tạo | Theo quyết định user mới nhất, hiển thị chart khi có telemetry; GUI chưa hiển thị ETA |
| Job nền | `ThreadPoolExecutor(max_workers=1)` cho Codex + async collector MCP | Agent call blocking không chiếm event loop; không Celery/Redis |
| Test | `pytest>=8,<9`, frontend `tsc -b && vite build`, một GUI E2E thật | Chỉ test gate/identity/cursor/store và phần bị sửa |

T01 tạo `requirements-mvp0.txt` từ các dependency trực tiếp trên, rồi lưu version đã resolve thành
`requirements-mvp0.lock.txt`; không chạy `pip install -r requirements.txt` stock vì sẽ kéo toàn bộ research stack.
Các dependency journal chưa có pin được chốt từ môi trường import/test thành công; không ghi một pin tưởng tượng.
Frontend dùng **version resolved trong donor lock**, các số trên là baseline package manifest.
Không cài Torch/Transformers/datasets/CUDA/LaTeX/OCR/W&B local chỉ để khởi động GUI.
Thư viện train trên Kaggle được xác nhận từ environment/data/proposal và ghi vào report; không tự tải pretrained weights
hay bật Internet khi proposal chưa cần.

FastAPI tạo/đóng worker và MCP session trong [lifespan](https://fastapi.tiangolo.com/advanced/events/).
MCP giữ một `ClientSession` qua `stdio_client`, theo [SDK v1](https://github.com/modelcontextprotocol/python-sdk/blob/777b8d06710c140e3606b0d4598e2aa48546c266/README.md);
không spawn server mới cho mỗi tool call. SQLite WAL phục vụ readers/worker trên cùng máy,
theo [SQLite WAL](https://sqlite.org/wal.html); transaction ngắn, không giữ lock khi chờ Codex/Kaggle.

## 4. Bố cục code và trách nhiệm

```text
AI-Scientist-v2/
  ai_scientist/workbench/
    __init__.py
    __main__.py             # parse config, mở Uvicorn; không chứa business flow
    app.py                  # REST, lifespan, static GUI; composition tại đây
    models.py               # Library/proposal/result và state contracts Pydantic
    store.py                # project SQLite, atomic writes, history, log cursor
    service.py              # clarify/approve/implement/submit/collect/report
    runtime.py              # load AgentRuntime/CodexCliRuntime từ donor
    kaggle.py               # MCP client, response projection, collector
    notebook.py             # build nbformat, checks, runner cell, output contract
    prompts.py              # 3 role prompts + context/source references
  workbench-ui/             # scaffold donor; App/api/styles nhỏ cho MVP 0
  tests/workbench/          # các test tác động trực tiếp
  requirements-mvp0.txt
  requirements-mvp0.lock.txt
  config-mvp0.example.json  # đường dẫn/model/alias, không có token
  docs/customization/MVP0_RUN_GUIDE.md
  .workbench/               # ignore Git: config local, project DB, run files

kaggle_token/
  mvp0_mcp_tools.py         # register 3 wrapper; dùng helper/module hiện có
  mcp_server.py            # thêm registration, không đổi tool cũ
  agent_platform/tests/test_mvp0_mcp_tools.py
```

Không tạo thêm cây `domain/application/infrastructure` đầy đủ, DI container hoặc plugin framework.
`service.py` nhận store/runtime/MCP client qua constructor; UI không biết subprocess, cookie hay SDK.
Một boundary AgentRuntime đã đủ để đổi harness sau này; không thêm một AgentPort giống hệt.
Store/MCP client là module/class cụ thể, chưa cần thêm các Protocol cho mọi dependency.

### Storage và artifacts

```text
.workbench/projects/<project_id>/
  project.sqlite
  library/files/                    # bản text import nếu cần; dataset vẫn là reference
  runs/<run_id>/
    context.json                    # snapshot nguồn/idea/proposal đã duyệt
    source/workload.py               # source do Codex trả, app ghi
    source/config.json
    bundle/notebook.ipynb
    bundle/kernel-metadata.json
    checks.json
    output/result.json
    output/metrics.json
    output/runner.log
    report.md
    journal.json                    # export từ DB, không dùng làm state authority thứ hai
```

SQLite schema nhỏ, `schema_version=2`; khi khởi động, tự thêm cột `ideas.title` cho DB cũ:

- `project_meta`: id/name/created_at/schema_version.
- `resources`: id/kind/title/url/content/status/version/content_sha256.
- `ideas`: id/title/text/conversation_json/state/error/created_at. Tiêu đề tối đa 80 ký tự là nhãn
  hiển thị do user đặt; đổi tiêu đề không thay context hash, approval hoặc kết quả của run.
- `proposals`: id/idea_id/version/body_json/context_snapshot_json/context_sha256/state/approved_at.
- `runs`: id/proposal_id/node_id/node_json/state/intent_key UNIQUE/code_sha256/identity_json/artifact_dir/error/report_path.
- `logs`: run_id/generation/seq/text/stream, UNIQUE(run_id,generation,seq).

Project listing đọc các thư mục có `project.sqlite`; không thêm DB catalog rồi sync hai nguồn trạng thái.
Store là authority cho trạng thái/approval/identity; `node_json` là serialization của **Node upstream** trong cùng DB.
`journal.json` chỉ export để đọc/debug. Khi restore, dùng `Node.from_dict(copy.deepcopy(payload), journal)` theo thứ tự parent trước child:
method upstream có `.pop()` và sẽ mutate dict đầu vào. Node ID dùng lại trong run, không tự tạo ID journal khác.

Library MVP 0 nhận text và URL có description/text đi kèm. URL chưa fetch được có status `reference_only`;
không tự nhận đã đọc paper/rules chỉ vì có link. Dataset chỉ lưu ref/version/mount expectation, không đưa data lớn vào DB.
Prompt nhận snapshot nguồn đã chọn cùng resource ID/version; không đọc toàn donor repo có credentials.

## 5. Contracts để dev không phải tự đoán

### 5.1 Codex runtime: reuse nguyên adapter, đổi role/payload của app

Donor runtime import ba module liên quan: `agent_platform.ports.agent_runtime`,
`agent_platform.infrastructure.agent_runtime`, `agent_platform.ports.research_outputs`.
`runtime.py` thêm donor root đã kiểm chứng vào Python search path **một lần lúc bootstrap** rồi import;
đường dẫn lấy từ config. Chỉ composition/adapter có dependency này, không business module.

Dùng role **`mvp0_plan`**, **`mvp0_code`**, **`mvp0_report`**. Chúng không có trong `research_output_schema`,
nên adapter dùng generic result envelope. Không dùng role `coder` cũ rồi vá contract synthetic.
Với cả ba role, yêu cầu envelope `{ "text": "<JSON của role>", "files": {} }`.
Code nằm trong trường JSON `source` ở role code; app tự ghi `workload.py`. Cách này tránh bắt model tạo base64 notebook/files.
Reject `files` không rỗng trong MVP 0; không ghi tùy ý file từ model.

| Role | JSON trong `RuntimeResult.text` | Quyền được phép |
| --- | --- | --- |
| `mvp0_plan` | `needs_clarification`, `questions`, `paraphrase`, `objective`, `data_refs`, `split`, `metric`, `implementation_steps`, `budget`, `expected_outputs` | Proposal/câu hỏi, chưa implementation |
| `mvp0_code` | `source`, `config`, `implementation_summary`, `checks_explained` | Sau approval; source thực hiện đúng proposal snapshot |
| `mvp0_report` | `summary`, `interpretation`, `limitations`, `suggested_next`, `evidence_refs` | Đọc facts/output đã thu; không chạy experiment mới |

Pydantic `extra='forbid'` cho payload; validate riêng từng role. Prompt ghi source IDs, refs, budget và các field bắt buộc.
JSON/schema lỗi trả lỗi hữu ích và cho retry có giới hạn; không coi parse fail là run thành công.

Giữ cách adapter gọi `codex exec --json --ephemeral --sandbox read-only` và parser JSONL hiện có.
CLI tạo kết quả source qua response, app ghi vào job directory **sau approval**; không cần nâng sandbox để Codex sửa repo.
Xác minh flags/protocol bằng CLI cài thật ở T01/T02; không sửa adapter dựa trên suy đoán version.
[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) là nguồn chính thức cho `exec`/JSONL.

### 5.2 Approval, scope và chống submit trùng

Proposal approval pin `proposal_id/version`, context hash, split/metric và budget. Library/idea thay đổi làm proposal cũ stale;
API trả `409` nếu duyệt phiên bản/hash cũ. Không chỉ disable button ở frontend.

State chính:

```text
NEEDS_CLARIFICATION → AWAITING_APPROVAL → APPROVED → IMPLEMENTING → PREFLIGHT
→ SUBMITTING → QUEUED/RUNNING → COLLECTING → ANALYZING → COMPLETED
                                      ↘ FAILED / UNKNOWN
```

Proposal giữ các state trước implementation; run giữ các state từ implementation trở đi.
`FAILED` có bước/error và artifacts hiện có; `UNKNOWN` dùng khi chưa chứng minh được kết quả submit/identity/status.
Remote COMPLETE mới cho collect; app COMPLETED đòi hỏi outputs hợp lệ và report đã lưu.

- `approve` transaction kiểm version/hash, tạo một run với `intent_key = proposal_id + version`, trả run hiện có nếu double click.
- Trước tool push, lưu **SUBMITTING + slug mới duy nhất theo run_id + notebook hash + account alias** và commit transaction.
- Save response phải lấy exact ref/version; resolver/tool inspect trả kernel/session/script-version IDs để pin.
- Timeout/mất kết nối khi push là **UNKNOWN**, không tự gọi push lần nữa. GUI có “Đối soát run” chỉ đọc remote theo slug/intent.
  Không biết save đã xảy ra thì không suy diễn “chưa chạy”.
- Restart chỉ resume observer/collect/report có đủ identity; không tự khởi động coder hay submit cho job dở dang.
  IMPLEMENTING/PREFLIGHT bị ngắt được hiện lỗi có thể tiếp tục qua GUI, trong scope đã duyệt; bước submit không tự retry.
- Đổi hypothesis/data/split/metric/budget phải ra proposal mới; bugfix trong scope có thể tự làm.

Budget mặc định trong proposal: **tối đa 2 coder calls** (draft + một sửa preflight),
**1 remote training attempt**, thời gian training dự kiến ≤10 phút, outputs cần thu ≤10 MB.
Nếu training remote fail, báo chẩn đoán; chạy attempt mới cần duyệt proposal/budget mới qua GUI.
Giới hạn này giúp MVP 0 có vòng sửa lỗi cục bộ mà không dựng scheduler/agent tree nhiều nhánh.
Task guide không được dùng approval để tự mở quyền nghĩ idea/tuning hoặc dùng account khác.

### 5.3 Notebook và kết quả thực

Source contract nhỏ: `run(context, emit) -> dict`. `context` gồm run_id, code/context hash,
input mounts, output_dir, config và split/metric đã duyệt. `emit(step, metrics, total_steps=None)`
ghi telemetry có prefix JSON vào stdout, đồng thời vào metrics file. Không cần checkpoint engine cũ.

App build notebook bằng `nbformat.v4.new_notebook/new_code_cell`, rồi
[validate](https://nbformat.readthedocs.io/en/latest/api.html#nbformat.validate). Cells:

1. Metadata/context/config/source IDs và đường dẫn mount đã kiểm ở T01.
2. Instrumentation/runner cố định: ghi source, tạo `/kaggle/working/ailab_bundle/output`, tee stdout ra `runner.log`, flush metric.
3. Source do Codex trả và lời gọi `run(context, emit)`; check data/split nằm trong workload.
4. Validate measurement hữu hạn, ghi `result.json`/`metrics.json`, in completion marker.

**Giữ tên `ailab_bundle/output`** vì helper `_project_exact_output_files` donor đã lọc layout này.
Không đổi path rồi viết lại output collector. Notebook metadata dùng `competition_sources`
để mount competition; `push_notebook_core` đã chuyển field này sang SaveKernel request.
Xác minh SDK/provider nhận đúng source ref và notebook thấy file thật, không chỉ metadata có URL.

`result.json` tối thiểu: schema_version, run_id, proposal_id/version, code_sha256, context_sha256,
data refs/mounts, split mô tả/counts, seed/config, measurements, artifacts, elapsed_seconds, environment versions.
`metrics.json`: danh sách `{step, epoch?, elapsed_seconds, metrics:{name:finite_number}, total_steps?}`.
Không cố định metric name/direction trước readiness. Các hash đối chiếu context/code; data refs ghi version/manifest
nếu provider cung cấp, không giả vờ đã checksum toàn bộ dataset khi chưa đọc.

Checks local chỉ validate schema/syntax/contract và metadata; không chứng minh ML đúng hoặc hết data leak.
Runtime checks trên Kaggle kiểm mount/file/column/shape hữu ích, split không giao nhau và grouping theo nguồn đã xác minh;
preprocessing fit trên train, evaluation dùng validation. Nếu grouping chưa rõ thì hỏi ở proposal, không tự chọn random split.
Report ghi rõ dataset subset và giới hạn của baseline. Không cần leaderboard submission để đạt MVP 0.

### 5.4 MCP bridge: ba wrapper bổ sung, tương thích tool cũ

Thêm `register_mvp0_tools(mcp)` trong donor `mvp0_mcp_tools.py`, gọi từ `mcp_server.py`.
Các wrapper resolve account bằng pool nội bộ; không trả token/cookie/header ra app hoặc report.

| Tool mới | Contract trả về | Code dùng lại |
| --- | --- | --- |
| `workbench_inspect_run(account, kernel_ref, version, expected_session_id?, expected_kernel_id?, expected_script_version_id?)` | Account/ref/version/kernel_id/script_version_id/session_id/status/observed_at; mismatch hoặc status lạ là lỗi/UNKNOWN | `_resolve_exact_session`, `_session_status_single`, vocab status donor |
| `workbench_logs_snapshot(account, kernel_session_id)` | Session ID + ordered records `{data,stream_name,...}` + lỗi/truncation metadata; không footer text | `KaggleSdkAccountClient.session_logs`, parser/bounded transport donor |
| `workbench_collect_outputs(account, pinned_identity, destination)` | Exact identity + manifest paths/bytes/sha256; không đẩy blob/base64 lớn qua MCP | `_read_exact_remote_view`, `_project_exact_output_files`, `_safe_output_path`, `download_output` |

Tool client dùng `list_accounts`, `push_notebook`, `resolve_session_id` hiện có khi phù hợp;
parse JSON/string content một lần ở boundary. MCP `isError`, exception hoặc payload sai đều thành lỗi có bước cụ thể.
Không lấy trạng thái bằng cách đoán từ log footer hoặc “có completion text”.

Inspect/collect xác minh đúng owner/kernel/version/session, không dùng latest-by-slug làm bằng chứng version.
SDK `status()`/`output_page()` có đường current-version; không gọi chúng riêng rồi coi đã pin.
Helper exact output hiện kiểm cả current view/version: mỗi run dùng **kernel slug mới**, không tạo version khác khi đang theo dõi.
Nếu user sửa kernel remote làm version/view lệch, báo mismatch; không thu outputs của phiên khác.

Collection sau terminal success: nhận `result.json`, `metrics.json`, `runner.log` và artifact nhỏ được khai báo;
giới hạn tổng 10 MB, kiểm size/hash/path và identity trước/sau download, ghi temp rồi rename.
Destination nằm trong output root job đã cấu hình, không nhận đường dẫn tự do từ prompt.
Không copy `KaggleNotebookEnv` nguyên khối với launch gate/bundle/checkpoint platform cũ:
chỉ gọi helper sẵn có từ wrapper, reuse downloader và validation cần cho kết quả.

### 5.5 Log delta, status và telemetry

Một collector mỗi run; GUI polling API local khoảng 2 giây. Collector upstream khoảng 3–5 giây,
backoff tối đa 30 giây khi lỗi/queue; dừng polling sau terminal + collection xong.
MCP và agent là hai đường nền riêng; request GUI không chờ một Codex call hoặc log socket.

- Provider log có thể là replay snapshot. Merge theo **vị trí/prefix record ổn định**, không `set(text)` hoặc unique(text).
  `[A,A]` so với `[A]` phải thêm đúng một `A`; poll lại `[A,A]` không thêm.
- Snapshot ngắn hơn nhưng là prefix của bản đã lưu có thể là replay chưa đọc hết: giữ bản đã lưu,
  không xóa log hoặc báo run hoàn tất. Không dùng `new_lines` dựa trên timing 2 giây của pool cũ làm cursor.
- Snapshot không khớp prefix/nguồn bị cắt: đánh dấu gap/reset có generation, không âm thầm nối bằng so khớp text.
  File `runner.log` ở terminal là nguồn đối soát cuối; không tuyên bố P0-05 đạt khi còn gap chưa đối soát.
- API local trả `{generation, entries:[{seq,text,stream}], next_cursor, has_more, gap}` từ SQLite.
  GUI append theo generation/seq, hết `has_more` mới chờ poll tiếp; restart giữ log/cursor đã commit.
- Reuse ý tưởng/fixture `_session_log_delta` donor cho cursor/prefix/gap; DB local là authority.
  Nếu helper cần signature khác, viết phần projection nhỏ ở boundary, không thay tool cũ.
- Telemetry parse từ prefix JSON của notebook, không scrape số trong prose. ETA chỉ khi có total_steps và tốc độ đo được;
  nếu chưa có thì hiện “Chưa đủ dữ liệu”. Curve từ telemetry cache, đối soát `metrics.json` lúc kết thúc.

**Giới hạn phải công khai:** delta local giảm payload/DOM phía GUI và tránh mỗi refresh gọi upstream.
Transport donor hiện có thể mở SSE replay lại và giới hạn read window; chưa chứng minh giảm bytes Kaggle→MCP.
T01/T07 kiểm thực tế log replay của demo nhỏ. Không quảng cáo đã giải quyết đầy đủ N08; tối ưu stream dài/cursor provider thuộc MVP 3.
Nếu transport không cho log đầy đủ trong giới hạn, phải sửa đúng điểm đó hoặc ghi P0-05 chưa đạt, không nới tiêu chí.

### 5.6 REST và GUI tối thiểu

| API | Hành vi |
| --- | --- |
| `GET /api/health` | Readiness/runtime/MCP/config errors đã lọc, không secret |
| `GET/POST /api/projects` | List/tạo project; prototype demo chỉ cần một project |
| `GET/POST /api/projects/{id}/resources` | Library text/URL, version/status |
| `POST /api/projects/{id}/ideas` | Tạo idea + conversation |
| `GET /api/ideas/{id}` | State/error/conversation/proposal mới nhất; GUI poll trong lúc planner chạy |
| `POST /api/ideas/{id}/proposal` | Background plan/clarification, trả task/state; user bổ sung câu trả lời qua cùng endpoint |
| `POST /api/proposals/{id}/approve` | Version/hash gate; tạo/return run; queue coder |
| `GET /api/projects/{id}/runs` | History gồm purpose/status/metric/report link |
| `GET /api/runs/{id}` | Chi tiết proposal/source/checks/identity/metrics/report |
| `GET /api/runs/{id}/logs?cursor=...` | Delta local; không gọi Kaggle trong route |
| `POST /api/runs/{id}/reconcile` | Đối soát UNKNOWN chỉ đọc remote, không submit |
| `GET /api/runs/{id}/artifacts/{name}` | File allowlist trong job root: notebook/source/result/report và outputs đã xác minh |

UI một trang, ba khu vực: **Library → Idea/Proposal → Run**.
Theo yêu cầu user sau T09, bỏ tab History; kết quả, log, artifacts và report xem trong chi tiết run.
Hiện câu hỏi, assumption/split/metric/budget trước nút “Duyệt và triển khai”; disable nút khi stale/đang xử lý.
Run có progress stage, exact Kaggle link, log, lỗi và mở artifacts/report.
Đã approved thì các bước trong scope chạy tự động; không bắt user approve từng cell/tool.
Không dựng trang settings/team/sidebar phức tạp. Setup config chỉ một lần; daily workflow qua GUI.

## 6. Chín task triển khai, acceptance và thời gian

Timebox dưới đây là ngân sách wall clock mục tiêu, không cam kết queue/provider.
Submit trước **3.75 giờ** để làm collector/report trong lúc Kaggle chạy. T06 phần inspect/output wrapper nên
được kiểm spike ngay T01; không để đến giờ 4 mới phát hiện output không đọc được.

| Task | Timebox từ lúc bắt đầu | Dependency | Checkpoint |
| --- | --- | --- | --- |
| T01 | 0–0.50h | Tài nguyên hiện có | Readiness thật và dependency lock |
| T02 | 0.50–0.90h | T01 | Journal/runtime chạy được, chưa implement idea |
| T03 | 0.90–1.50h | T02 | Library bền vững + GUI/API spine |
| T04 | 1.50–2.25h | T03 | **CP0-A:** proposal/clarification/approval gate |
| T05 | 2.25–3.00h | T04 | Source/notebook/checks từ Codex thật |
| T06 | 3.00–3.75h | T01 spike, T05 | **CP0-B:** submit thật, identity pin |
| T07 | 3.75–5.00h | T03, T06 | Theo dõi/status/log nền; Kaggle đang chạy |
| T08 | 5.00–6.00h | T05–T07 + remote success | **CP0-C:** outputs/report/history |
| T09 | 6.00–7.75h | T01–T08 | **CP0-D:** E2E/restart/guide; gồm buffer sửa blocker |

### T01 — Kiểm chứng readiness và chốt môi trường

**Tiến độ 2026-10-06:** artifact/setup/probe đã bàn giao tại [MVP0_RUN_GUIDE.md](MVP0_RUN_GUIDE.md). Account/API/quota/rules/schema/group IDs đã kiểm chứng; quyền attach/mount competition còn blocker được ghi cụ thể. Chưa đánh dấu competition-ready hoàn toàn; chưa chạy training. T02/T03 có thể tiếp tục.

**Giải quyết:** điều kiện thật cho N01/N03/N08; tránh xây GUI xong mới biết data/runtime bị chặn.
**Bàn giao:** môi trường nhẹ, config example, dependency lock, readiness note trong run guide.

**Chi tiết cài đặt:**

1. Kiểm checkout/revision và Python/Node/Codex path/version, existing model/reasoning; giữ changes local.
   Tạo `.venv-mvp0` ở fork. MCP dùng Python executable donor đã kiểm; nếu thiếu pin SDK thì tạo venv riêng cho bridge,
   không nâng global environment hoặc môi trường cũ mà chưa kiểm tương thích.
2. Cài đúng dependency subset mục 3, `npm ci` bằng scaffold/lock donor. Probe import Node/Journal và runtime module;
   lưu version resolve. Không yêu cầu OpenAI/Anthropic API key chỉ để import; không gọi provider stock.
3. Spawn MCP stdio với cwd donor. Kiểm tools/list và một account user đã cho phép, cookie/API readiness và quota phù hợp;
   không kiểm cả 7 account. Proxy port 80 của donor là dependency hiện có: xác minh khởi động/health, báo đúng lỗi nếu bị chặn.
4. Xác minh rules/evaluation/data schema/group identifiers/mount eligibility bằng account/source được phép.
   Lưu text/ref vào Library sau T03; nếu chỉ đọc được link thì ghi chưa đọc và hỏi rõ ở proposal.
5. Read-only spike exact status/log/output helpers trên kernel/version có sẵn nếu có; xác minh layout/SDK.
   Không có run sẵn thì kiểm tool/import/shape trước và ghi phần remote collection còn chờ T06/T08.
   Chỉ chạy training baseline khi proposal user đã duyệt; readiness không cấp quyền code idea.

**Nghiệm thu:** Python/MCP/Codex CLI executable thật hoạt động; import không kéo Torch/GPU;
MCP account đúng username; xác định được data access/metric/split constraints đủ tạo proposal, hoặc ghi blocker cụ thể.
CLI smoke chỉ JSON/echo readiness, không tạo workload. Không có secret trong stdout/doc/config example.
Không đánh dấu T01 đạt readiness competition nếu rules/schema/quyền mount còn chưa xác minh.
**Kiểm:** version/import/tools probe và nội dung readiness note; chưa cần Kaggle training run riêng.
**Đối chiếu:** P0-01/P0-03/P0-04 prerequisites; chưa đủ đạt các P0 này.

### T02 — Bootstrap runtime và journal bằng code có sẵn

**Tiến độ 2026-10-06:** đã triển khai skeleton/runtime/role contracts/journal round-trip; CLI smoke thật và focused checks đạt. Lệnh chạy và bằng chứng ở [MVP0_RUN_GUIDE.md](MVP0_RUN_GUIDE.md#t02--runtime-và-journal-bootstrap). Chưa triển khai T03 hoặc notebook/training.

**Giải quyết:** N06 boundary và N09 trace; tạo đường thực vào lõi fork và Codex, không viết harness mới.
**Bàn giao:** `runtime.py`, composition skeleton và journal round-trip hoạt động.

**Chi tiết cài đặt:**

1. Nạp donor path ở bootstrap; dùng AgentRuntime/CodexCliRuntime original và RuntimeRequest/Result/Progress.
   Không copy một class thiếu `HeadlessCliRuntime` helpers hoặc `research_outputs` import dependency.
2. Dùng role names mục 5.1; validate generic envelope + role payload trong app. Giữ timeout/output/cancel của adapter;
   config model/reasoning từ môi trường user, không hardcode model mới.
3. Tạo Node/Journal upstream thật, test serialize/restore parent/metric trên deepcopy; map node_id vào run metadata.
   Không dùng `get_best_node`/summary stock có provider call. Chưa khởi động AgentManager/ParallelAgent.
4. App lifespan quản lý một worker Codex và một MCP session; shutdown đóng session/worker có thời gian giới hạn,
   ghi job bị ngắt. Blocking `.run()` vào executor, không trong async route.

**Nghiệm thu:** một request generic nhỏ bằng Codex CLI thật parse thành RuntimeResult; không gọi API stock;
Node/Journal round-trip giữ id/parent/plan/code/metric; API health trả trong khi worker chờ.
Source upstream/runtime donor không bị sửa chỉ để bootstrap. Nếu có structural refactor phát sinh, hai phase phải riêng như mục 2.
**Kiểm:** focused runtime parser/timeout checks donor còn áp dụng + test journal round-trip; một CLI smoke thật là đủ,
không chạy mọi harness/provider test.
**Đối chiếu:** P0-03/P0-07 nền tảng, chưa chứng minh notebook/run thật.

### T03 — Library/store và GUI spine dùng được

**Tiến độ 2026-10-06:** đã triển khai project SQLite/store/resources API và GUI Library/Idea/Run/History. GUI thực đã tạo project Soil, nhập 5 nguồn T01; project QA kiểm version/status/context và giữ dữ liệu sau restart. Build frontend và 8 focused test workbench đạt; chi tiết/lệnh chạy ở [MVP0_RUN_GUIDE.md](MVP0_RUN_GUIDE.md#t03--library-project-store-và-gui).

**Giải quyết:** N02/N03/N09: context có nơi lưu chung và user bắt đầu thao tác qua GUI.
**Bàn giao:** schema mục 4, resources API và GUI Library/Idea/Run/History khung đơn giản.

**Chi tiết cài đặt:**

1. Tạo DB theo project, foreign keys, WAL, transaction ngắn/busy timeout; connection theo thread/request,
   không share tùy ý một sqlite connection qua worker. Không dùng migration framework cho schema đầu tiên.
2. Resource text/URL có id/version/hash/status. Idea/conversation/proposal/run lưu riêng, linked IDs;
   artifacts bên ngoài DB. Snapshot context bất biến cho proposal/run, không gửi toàn Library vô hạn vào prompt.
3. Copy package/lock/config frontend donor; tạo App/api nhỏ. Reuse CSS cần dùng, không copy Notion/W&B/team panels.
4. Dev: Vite proxy `/api` tới `127.0.0.1:8000`; bàn giao: FastAPI serve frontend build cùng origin.
   Không CORS wildcard/cloud hosting; không cần thiết kế lại giao diện đầy đủ.
5. Import nguồn competition đã đọc ở T01 bằng GUI; URL chưa đọc gắn status rõ.

**Nghiệm thu:** GUI tạo project, thêm đề bài/data ref/idea; restart mở lại đúng text/version/status;
project không đọc nhầm resources của project khác; agent context snapshot dùng source IDs nhìn được trên UI.
**Kiểm:** store persistence/isolation/version snapshot test và thao tác GUI thực; frontend build.
**Đối chiếu:** P0-01, phần Library/GUI của P0-07/P0-08.

### T04 — Clarification/proposal và approval trước code

**Tiến độ 2026-10-06:** T04 đã nghiệm thu: planner service/API, conversation/proposal GUI và approval transaction với version/hash/context gate đã triển khai. 15 focused test workbench và frontend build đạt; Codex thật từ GUI đã hỏi lại rồi tạo proposal v2 trên dữ liệu Soil thật. Restart giữ nguyên conversation/proposal/hash. User đã duyệt v2; DB xác nhận proposal `APPROVED`, đúng một run `2d1cb7e9cd8b4a058e3efa1bcd6e9630` ở state `APPROVED`, chưa có kết quả code/training. CP0-A chưa đạt vì readiness attach/mount T01 còn blocker. Bằng chứng và thao tác ở [MVP0_RUN_GUIDE.md](MVP0_RUN_GUIDE.md#t04--clarification-proposal-và-approval-gate).

**Giải quyết:** N01/N02: implementation bám idea user và không tự triển khai khi chưa duyệt.
**Bàn giao:** proposal-only Codex path, conversation UI và approval transaction.

**Chi tiết cài đặt:**

1. `mvp0_plan` nhận idea + source snapshot + rules/evaluation đã xác minh; diễn giải mục tiêu và hỏi thiếu data/split/metric/budget.
   Nếu thiếu thông tin trọng yếu, trả `needs_clarification=true`; payload câu hỏi được phép chưa có các field
   proposal hoàn chỉnh. Không tự lấy synthetic data thay competition.
2. User trả lời tại GUI; update conversation, tạo proposal version mới. UI hiện paraphrase, steps, data refs, split,
   metric/direction, subset/seed/budget và expected outputs.
3. Trước approval, service chỉ được gọi role plan; reject file/code payload ngoài schema;
   không tạo `workload.py`/notebook/run submit. Gate ở backend, không chỉ frontend.
4. Approval kiểm version/context hash, resource/idea hiện hành và concurrency; tạo intent/run một lần.
   Source snapshot được freeze; response trả run_id để GUI theo dõi tự động.

**Nghiệm thu:** idea mơ hồ tạo câu hỏi qua Codex thật; bổ sung xong có proposal rõ; chưa duyệt không có coder/file/push;
duyệt proposal stale bị 409; double click không tạo hai run. User duyệt một baseline nhỏ trên data thật.
**Kiểm:** fake runtime/MCP đo call count cho gate/stale/double click (chứng minh gate), cộng một proposal/clarification Codex thật.
**Đối chiếu:** P0-02; **CP0-A** chỉ đạt khi readiness + Library + proposal thật đều đạt.

### T05 — Codex implementation, notebook builder và preflight

**Tiến độ 2026-10-06:** **T05 đã nghiệm thu** qua lượt user tự kiểm thử GUI: idea mới → proposal được user duyệt → gọi coder → run `30af70766f794db2992219c330db4e97` ở `PREFLIGHT`, checks PASS, không có lỗi, dùng 1/2 coder calls. Codex thật tạo source/notebook, code có `torch.save` và khai báo checkpoint artifact; review split/metric/budget khớp proposal mới. Manifest/code hash và nbformat đã đối chiếu đạt; 25 focused test workbench và frontend build trước đó đạt. Run cũ thiếu checkpoint vẫn FAILED, giữ nguyên counter/history; không reset ngân sách hoặc sửa proposal cũ. Chưa submit/training; mount T01 vẫn chưa xác minh. Bằng chứng ở [MVP0_RUN_GUIDE.md](MVP0_RUN_GUIDE.md#t05--code-notebook-và-preflight-sau-approval).

**Giải quyết:** N01/N02: bỏ bước copy code vào notebook, giảm lỗi cấu trúc/sai scope cơ bản.
**Bàn giao:** source, notebook, metadata và checks; Node implementation trong journal.

**Chi tiết cài đặt:**

1. Sau approval gọi `mvp0_code` với snapshot đã pin; yêu cầu `run(context, emit)` theo mục 5.3,
   real data mounts, split assertions và emission mỗi step/epoch. Bắt buộc giữ metric/split/budget proposal.
2. App validate JSON/config/source, ghi `source/workload.py` trong run root; Node(plan/code/id) upstream ghi vào DB.
   Không thực thi source chưa biết trong backend để train hoặc tải dataset về máy local.
3. `ast.parse`/`compile` source, kiểm entry function, config bounds, notebook nbformat,
   metadata/code_file/competition_sources/private flag và output contract. Lưu checks pass/fail cùng code hash.
4. Nếu preflight local fail, cho một coder sửa với lỗi cụ thể trong scope; node child nối parent.
   Vẫn fail thì dừng, hiện lỗi trên GUI; không gọi Codex loop vô hạn.
5. Build notebook cố định instrumentation/runner cells + source. Tạo kernel slug duy nhất `ailab-<run_id>`;
   không hardcode file paths/schema competition từ suy đoán. Chọn model baseline gọn, không thêm dependency tải mạng nếu không cần.

**Nghiệm thu:** source và notebook do Codex CLI thật tạo sau approval, checks local đạt;
metadata mount competition đúng; notebook có telemetry/result writing và source/config phản ánh proposal.
Lỗi preflight được sửa tối đa một lần hoặc báo fail rõ; không sửa metric/split để làm xanh.
**Kiểm:** notebook schema/source syntax/output contract/metadata test; review source khớp proposal;
run thật T06/T08 mới chứng minh execution. Syntax pass không đủ chứng minh model/data leak correctness.
**Đối chiếu:** P0-03; nền tảng P0-06/P0-07.

### T06 — MCP wrappers và submit pin đúng run

**Trạng thái 2026-10-06: T06/CP0-B đạt nghiệm thu submit + pin identity + runtime mount.**
Sau hai allowance chẩn đoán riêng được user xác nhận, run `e2545599e7e94f66b6fc9f682b23fa72`
nhận SaveKernel HTTP200/version1 và đã COMPLETE: kernel137301710, script_version216981117,
session355701890, account `huynhtrungcuong` (`jhin_access_token.txt`). Log đúng session xác minh
`/kaggle/input/competitions/soil-grain-size-from-photos` có165files, đủ3epochs và completion marker.
Sửa parser `ref` dạng `/code/owner/slug`, mount thiếu `competitions/`, cấu hình executable/SDK sau reconnect,
và proxy không replay SaveKernel khi mất phản hồi. Mô hình/config/metric/split giữ nguyên; workload chỉ đổi một đường dẫn.
Run đầu `30af70766f794db2992219c330db4e97` vẫn UNKNOWN với HTTP499; không sửa lịch sử/reset counter/push lại.
Hai run mới dùng one-off diagnostic script qua production SubmissionService/MCP, mỗi run đúng một SaveKernel,
không thêm lượt Codex; GUI đã kiểm cập nhật trạng thái và link identity. Đường GUI submit đầu được kiểm trước đó.
Tại thời điểm review T06, T07/T08 chưa triển khai GUI collector/report; timeout download do Windows worker startup đã sửa,
MCP mới tải đủ bốn artifact và kiểm identity/size/SHA256; structured SSE chưa kiểm lại;
runtime mount/epochs đã được xác minh bằng terminal REST log với exact version/session kiểm trước/sau.
Xem [T06_DEBUG.md](T06_DEBUG.md), [MVP0_RUN_GUIDE.md](MVP0_RUN_GUIDE.md#t06--gửi-notebook-qua-mcp-và-pin-identity).

**Giải quyết:** N02/N08/N09: app tự upload/run và thu đúng phiên; reuse MCP thay account/execution rewrite.
**Bàn giao:** ba structured wrapper, client bridge, submit path và identity bền vững.

**Chi tiết cài đặt:**

1. Làm wrapper mục 5.4 trong donor; register additive, giữ chữ ký/shape tool cũ.
   Reuse account resolver/exact-view helpers/SDK downloader; không đưa credential vào workbench config hoặc prompt.
2. Pin SDK môi trường MCP theo dependency helper thực dùng; chạy focused tests old tools bị chạm.
   Không bỏ version guard SDK để pass probe.
3. Commit intent SUBMITTING trước `push_notebook`; gọi bằng account alias được chọn và bundle tuyệt đối đã kiểm root.
   Parse save response → exact ref/version → resolve exact kernel/session/script_version.
4. Persist identity atomically; UI hiện Kaggle link/status. Không resolve bằng latest slug ở mỗi poll.
   Retry read/resolve hữu hạn được phép; retry push sau timeout không được phép.
5. Save timeout/response thiếu identity → UNKNOWN; reconcile chỉ đọc kernel/version history theo intent;
   tìm đúng phiên thì pin, không đủ evidence thì giữ UNKNOWN và hiển thị lý do.

**Nghiệm thu:** trước mốc mục tiêu 3.75h, GUI đã submit notebook thật qua MCP, lưu identity account/ref/version/kernel/session;
notebook mount data thật được chứng minh ở runtime. Mismatch session/version bị reject;
double click/HTTP retry/restart ở SUBMITTING không phát sinh push thứ hai.
**Kiểm:** wrapper contract/error/identity mismatch tests và một submit thật của proposal đã duyệt.
**Đối chiếu:** phần execution của P0-04/P0-07/P0-08; **CP0-B**. Terminal success còn chờ T08.

### T07 — Collector nền, log delta và status

**Điều chỉnh scope theo user:** giao diện Run phục vụ general implement, chỉ hiển thị status/log.
Đã bỏ curve, metric selector, epoch cards và ETA khỏi GUI chung. Các yêu cầu curve/ETA bên dưới
không còn là điều kiện nghiệm thu bắt buộc của T07. Telemetry/visualization là tùy chọn theo tác vụ;
tác vụ tạo synthetic data, EDA, PCA hoặc đọc ảnh không bắt buộc phát metric training.

**Cập nhật 2026-10-06:** đã triển khai collector exact identity, SQLite cursor/generation,
API delta, GUI status/log và observer restart. MCP thật của run `e2545599…` trả 21 records,
3 điểm EMD, terminal COMPLETE; đối chiếu `runner.log` không có gap. Backend restart giữ cursor
`1:21` và đúng 21 records, không phát sinh submit/coder. Run lỗi `787afc70…` có 77 records,
terminal ERROR và traceback runtime. Focused fixtures kiểm replay/cursor/gap/identity/restart.
Tại thời điểm bàn giao T07 chưa kiểm live khi training. T09 đã kiểm live session_stream
trên run `f45680b3…` và đối soát terminal; xem bằng chứng T09 bên dưới.

**Review trước T08:** đã sửa observer chết không tự hồi phục, trạng thái COMPLETED bị downgrade khi đọc Kaggle,
GUI/history giữ trạng thái cũ và telemetry lỗi làm ngăn lưu log. 59 backend/9 donor tests pass, frontend build đạt.
Fresh MCP đã đọc đúng 21 records qua terminal snapshot và endpoint SSE của exact session đã kết thúc;
API paging/repeat/restart giữ cursor1:21, gap=false, submit1/1. Xem [T07_MONITORING.md](T07_MONITORING.md#review-trước-t08).
Không có lỗi đã biết chặn chuyển sang T08; live khi notebook đang training vẫn cần xác minh ở lượt tiếp theo/T09.

**Giải quyết:** N04/N08 và phần N09: user thấy run đang làm gì, GUI không đứng, giảm thao tác polling.
**Bàn giao:** collector một run, API delta/cursor, status/log và restart observer.

**Chi tiết cài đặt:**

1. Collector dùng identity đã pin; inspection/log read có timeout/bounded transport, no-overlap cho cùng run.
   Store commit sau từng lần quan sát; GUI chỉ đọc cache. Cấu hình cadence/backoff theo mục 5.5.
2. Merge records bằng prefix/vị trí, không content dedupe; seq/generation persist.
   Snapshot partial hoặc source gap có trạng thái rõ; đối soát terminal `runner.log`.
3. Parse telemetry emission của notebook và lưu metric points phục vụ facts/report.
   GUI chung chỉ hiện status/log; không yêu cầu curve hoặc ETA theo quyết định user.
4. Restart run đã pin resume monitor/collect; run chưa xác minh identity không push/coder lại.
   Provider state không biết/mismatch hiển thị UNKNOWN; network fail không thành training success/failure giả.
5. Terminal status được xác minh → collector chuyển COLLECTING hoặc FAILED, dừng poll phù hợp.

**Nghiệm thu:** khi Codex/Kaggle đang làm việc, GUI vẫn dùng được Library/history;
poll/reconnect/restart không nhân đôi logs; chuỗi `[A] → [A,A] → [A,A]` hiện đúng hai A;
delta cursor có paging/generation rõ. Run demo không còn gap chưa đối soát; status đúng exact session;
telemetry lưu các metric samples thực để đối soát outputs/report.
**Kiểm:** cursor/prefix/repeated-line/short-replay/reset/observer-restart fixtures + quan sát logs/metric run thật.
**Đối chiếu:** P0-05, phần monitoring của P0-06/P0-07. Không coi mocked logs là bằng chứng MCP thật.

### T08 — Thu outputs, report có nguồn và history

**Quyết định phạm vi 2026-10-06:** theo yêu cầu user, đã khôi phục T08 về hợp đồng training
ban đầu. General implement được để thành phần mở rộng sau MVP0, làm đồng bộ proposal,
execution và results; chưa triển khai phân loại run theo purpose.

**Cập nhật 2026-10-06:** T08 đã triển khai collection từ terminal cache khi app khởi động lại,
MCP exact-session manifest verification, đối soát result/metrics/runner log, report Codex có facts cố định,
journal integration và artifact links trong Run/History. Run `e2545599e7e94f66b6fc9f682b23fa72`
đã được thu và hoàn tất: 4 artifact outputs, report/facts lưu dưới run root, primary EMD đo được lần lượt
194.10373890251748, 105.20358728202889 và 82.43520124919444; database ghi `COMPLETED`, submit 1/1,
coder 0/2. API mở được `report.md` (HTTP 200, `text/markdown`) và UI preview hiện measurement, refs cùng output links.
Trong GUI chọn card ở **Run** để xem preview; link `report.md`,
`result-facts.json` và output artifacts mở qua artifact API trong run root.
Một lần gọi report thật đầu trả `ValidationError`, run vẫn `COLLECTING`; report thật sau đó được lưu và run hoàn tất.
Runtime/collection state cũ không lưu bộ đếm report nên tổng số lần gọi trước counter bền vững chưa xác minh.
Prompt envelope, lưu payload trước trạng thái worker completed, cap ba lần thử, UNKNOWN/interruption/restart
và không lặp report đã lưu được kiểm fixture; không gọi lại Codex cho run đã `COMPLETED`.
Kiểm cuối của bản ban đầu: 72 backend tests, 8 donor MCP tests và frontend build đều pass.
Lần khôi phục này không chạy lại test suite, gọi Codex report hoặc submit Kaggle.

**Giải quyết:** N04/N05/N09: không mất kết quả, biết idea đó cho kết quả gì và mở lại bằng GUI.
**Bàn giao:** outputs local, report Codex + facts, history nối đủ chuỗi bằng chứng.

**Chi tiết cài đặt:**

1. Chỉ collect sau terminal success của exact session. MCP download vào job output root;
   kiểm manifest identity/path/size/hash và result run_id/code/context hash, measurement hữu hạn.
2. Đối soát metrics/runner.log với dữ liệu đã cache; đóng gap nếu có nguồn đầy đủ,
   không nối bằng text dedupe. Metrics và visualization là artifact tùy tác vụ; UI dùng chung chỉ cần status/log.
3. Facts table do app đọc `result.json/metrics.json`: status, data subset, split/count, metric, config/seed,
   elapsed/environment, code/proposal và artifact refs. Không để model tự viết số thay measurement.
4. `mvp0_report` nhận facts/artifacts có giới hạn để diễn giải kết quả/limitations/next idea;
   render Markdown với facts cố định và evidence refs có thật. Report ghi AI assistance; suggested next không tự chạy.
5. Dùng `Node.absorb_exec_result(ExecutionResult(...))` để lưu stdout/thời gian/lỗi thực;
   cập nhật `analysis`, `metric=MetricValue(...)` với primary metric/direction đã duyệt, `plot_data` và `exp_results_dir`.
   Lưu serialization cùng run report path trong store; History nối idea/objective/source refs từ
   context đã duyệt (không đọc lại idea/resource hiện hành), proposal/version, code/context hash,
   metric và artifact/report links. Regression fixture sửa idea/title hiện hành sau approval nhưng
   History vẫn trả đúng snapshot đã ghim.
   Remote success nhưng thiếu outputs/report vẫn chưa app COMPLETED.

**Nghiệm thu:** một run competition thật terminal success, result/metrics/logs thu đúng phiên;
report chứa measurement đo được và refs mở được; artifact/output đúng run/version hiện trong GUI.
Mở lại history thấy proposal/source/notebook/report. Training fail chỉ được report fail, chưa đạt MVP 0 success.
**Kiểm:** result/manifest mismatch/missing metric/log mismatch, report failure/interruption/restart/idempotency fixtures
và collection/report Codex thật của run T06.
**Đối chiếu:** P0-04/P0-06/P0-07; **CP0-C**. Nếu remote chưa xong, tiếp tục phần UI/guide T09,
nhưng không đánh dấu checkpoint đã đạt.

### T09 — Nghiệm thu qua GUI, restart và bàn giao

**Đã nghiệm thu 2026-10-06:** 78 backend tests (gồm regression tests T09 và report budget repair) đạt;
12 donor/MCP/Windows-worker tests và 5 runtime fixture tests đều đạt; frontend build đạt.
Source upstream ngoài `ai_scientist/workbench/` và Codex runtime donor không bị rewrite.
Restart backend thật giữ nguyên 24 artifact links, 21 records/cursor `1:21`, context/history/report
và submit của run thành công cũ `e2545599…`. Run đó có source được sửa path trong lúc chẩn đoán,
nên không dùng thay bằng chứng golden path hoàn toàn qua GUI.
User đã duyệt proposal T09 v1 `93d367ebf0d143f6b9fa1b0de54cb812` để chạy run mới
`f45680b33f3d40c0bdfaa6275e6869d2` qua GUI, đúng scope CNN [16,32,64], split20/4/seed42,
2 coder calls/1 submit/3epochs/600s/10MB. Coder thật lượt1 qua preflight, source hash
`d316d0b31a0b2928f0f88aed3a804a3addf468a5159e96ec6e9d3db2945c4100`.
Submit1/1 thành công: owner huynhtrungcuong, version1, kernel137345547,
script_version217065827/session355795064. Runtime mount165files, split20/4 groups/108+19 ảnh;
3 epochs EMD184.78710864267654 →109.24989188610095 →70.26776872201779,
elapsed30.892590729s. Observer tự hồi phục sau lỗi đọc đầu, nhận live session_stream
22 records/cursor1:22 khi RUNNING; terminal REST đối soát21 records/cursor2:21, gap=false.
Bốn outputs đã xác minh manifest/hash, chưa sửa source/data bằng tay.
**Blocker đã sửa:** ba report calls đầu bị `ValidationError`, counter3/phase retry_exhausted;
run giữ COLLECTING. Đã bổ sung schema/type cụ thể trong prompt, diagnostics
không chứa inputs và giữ tên ValidationError thay vì Error chung chung.
Run card/chi tiết đã hiện phase và report counter để phân biệt outputs đã thu với report hết lượt;
user cho phép sửa tiếp, tăng limit riêng run này lên4 và giữ nguyên3lượt đã dùng.
Lượt4 tạo report đúng schema/facts, app COMPLETED; mặc định run khác vẫn giới hạn3report calls.
29 focused checks report/implementation/handoff và toàn bộ78backend tests đạt; frontend build đạt.
Restart backend thật sau COMPLETED giữ 28 artifact links, report/context/history/log/counters/collection
state nguyên vẹn, không thêm coder/report/submit. GUI History mở lại đúng report/run đã duyệt;
đạt P0-01…08/CP0-D. Mốc thời gian dưới8giờ chưa được chứng minh. Xem bằng chứng T09 trong MVP0_RUN_GUIDE.md.

**Giải quyết:** N02/N09: sản phẩm tự dùng được sau setup, có bằng chứng đạt prototype.
**Bàn giao:** GUI hoàn chỉnh cho scope, `MVP0_RUN_GUIDE.md`, demo artifacts và bảng P0 đạt/chưa đạt.

**Chi tiết cài đặt:**

1. Hoàn thiện UI lỗi/progress/approval/history/artifact links; user đi từ Library tới report mà không mở code editor
   hoặc tự push notebook. Reuse run T06/T08 khi nó đã đi đúng workflow, không chạy lại Kaggle chỉ để quay demo.
2. Run focused backend tests cho gate/store/cursor/identity/result và tests donor wrappers bị thay đổi;
   frontend build; kiểm nguyên code upstream/runtime donor chưa bị rewrite ngoài scope.
3. Kiểm double approve, stale proposal, missing data reference và wrong-session outputs bằng local fixtures/API;
   không cần dùng thêm GPU runs cho failure cases.
4. Restart app sau run thành công: context/history/report vẫn còn, push count không tăng;
   restart lúc monitor run thật nếu còn chạy để chứng minh observer recovery, hoặc test observer recovery với fixture đã thu.
5. Guide ghi prerequisites/config thực, một lệnh khởi động app, URL, thao tác GUI, vị trí project/artifacts,
   cách xử lý UNKNOWN/reconcile và các giới hạn. Handoff gồm app build/lock/config example; không cần Docker/installer.
6. Điền P0-01…P0-08 và CP0-A…D trong PRODUCT_ROADMAP bằng evidence refs thật.
   Dùng 1.75h cuối cho integration/blocker; không mở thêm tính năng khi còn acceptance đỏ.

**Nghiệm thu:** đủ tám P0; user làm được toàn flow sau setup qua GUI, một real Codex→MCP→Kaggle training run thành công,
report/log/history mở lại sau restart; không duplicate submit. Guide dùng được từ checkout hiện có,
không cần agent chỉnh source/data bằng tay ngoài các bước setup đã ghi.
**Kiểm:** một end-to-end thật + restart + focused checks/build; không chạy full upstream GPU/paper suite.
**Đối chiếu:** P0-01…P0-08; **CP0-D** và bàn giao MVP 0.

## 7. Lệnh/khởi động dev phải bàn giao

Entrypoint đã triển khai và chạy trên checkout hiện có. Setup đầy đủ và thao tác GUI xem
[MVP0_RUN_GUIDE.md](MVP0_RUN_GUIDE.md#khởi-động-từ-checkout-hiện-có).

```powershell
# Chạy từ D:/Documents/AI-Scientist-v2 sau setup, với config.local.json và GUI đã build.
.\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --port 8011
```

URL của lệnh trên `http://127.0.0.1:8011` (không truyền port thì mặc định 8000).
Entrypoint khởi động backend, MCP stdio và serve GUI build;
không yêu cầu user mở thêm MCP terminal mỗi ngày. Trong dev có thể chạy Vite riêng bằng scaffold script.
`config.local.json` tối thiểu: donor_root, donor_python, codex_executable, codex_model,
codex_reasoning_effort, kaggle_account_alias, workspace_root. Paths/model lấy từ T01,
không điền token hoặc endpoint paid. `.workbench`, venv, node_modules/dist local và runtime logs phải được ignore phù hợp.

## 8. Bằng chứng nghiệm thu và quy tắc dừng

Không dựng receipt/test platform mới. Một run directory và bảng P0 trong roadmap là đủ:

| Bằng chứng | Điều chứng minh |
| --- | --- |
| Library DB + context snapshot | P0-01; đúng nguồn/version |
| Approval record + focused call-count tests | P0-02; chưa duyệt không coder/push; stale/double-click gate |
| Codex role/session metadata + source/notebook/checks | P0-03; runtime thật và implementation đã kiểm cơ bản |
| MCP launch/inspect identity + terminal observation | P0-04; account/ref/version/session thật, không chỉ notebook validate |
| Persisted cursor/log + poll/restart test + final log reconciliation | P0-05; delta và không mất/nhân đôi trong scope demo |
| Exact manifest + result/metrics/report | P0-06; số liệu/report có nguồn |
| DB/history sau restart + unchanged push count | P0-07 |
| GUI walkthrough + run guide | P0-08 |

**Nếu sát mốc 8 giờ:** bỏ polish và backlog, giữ nguyên các P0 đã chốt. Nếu auth/rules/data mount,
SDK/helper contract, log completeness hoặc queue/provider chặn, ghi rõ blocker và việc đã dùng được.
Không thay competition bằng synthetic, đổi sang direct API bypass MCP, coi local syntax pass là Kaggle success,
hay hạ approval/log/provenance để tuyên bố hoàn thành. Thời gian vượt target phải được báo đúng.

**Dừng khi đủ P0-01…P0-08**, bàn giao prototype và bằng chứng; không tự làm MVP 1/team.
Backlog ngắn sau MVP 0: loại dependency path donor bằng packaging phù hợp, general hóa workload/repair (MVP 2),
transport log và nhiều run/account (MVP 3), retrieval (MVP 4), harness thứ hai (MVP 5), Ideathon (MVP 6), team (MVP 7).
Phần Library/PDF, durability và nhiều project của MVP 1 theo roadmap chính, không kéo vào tám giờ prototype.
