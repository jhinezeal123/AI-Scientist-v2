# MVP2 — hai mode Training/Research và Etc

Cập nhật: **2026-10-09**, Asia/Saigon. Nền bàn giao: `mvp1-2026-10-08`.
Roadmap: [PRODUCT_ROADMAP.md, mục 6](PRODUCT_ROADMAP.md#6-mvp-2--general-implementation-agent-cho-workshop-và-paper).

**Thiết kế hiện hành:** [Project run tree](PROJECT_RUN_TREE.md). User đã đổi sang
mỗi node là một run/phiên SSH riêng, draft/improve do user chọn, tự sửa lỗi trong
run; summary/report/plots/PDF/review là checkbox. Nội dung bốn stage bên dưới
ghi lại kế hoạch và lần triển khai M2-04 trước thay đổi này.

## Trạng thái đóng MVP2 — 2026-10-09

Thiết kế đã nghiệm thu là [PROJECT_RUN_TREE.md](PROJECT_RUN_TREE.md):

- Một cây chung cho project; mỗi node một run và một phiên SSH riêng.
- Proposal tạo một draft; user chọn Improve hoặc Etc để tạo run con.
  Agent tự sửa lỗi trong cùng run, không tự tạo debug node/bốn stage.
- Training/Research dùng Node/Journal và các module Summary, journal2report,
  plotting, writeup/compiler, review của repo gốc theo checkbox đã duyệt.
- Etc thực thi trực tiếp, bắt buộc mô tả đầu ra, lưu Output và copy kết quả
  thành nguồn Library độc lập. Hai mode dùng chung Library.
- Run con nhận code và memory_journal đã ghim; artifact cha cấp qua link.
  Chỉ xóa node lá đã dừng, xóa file thật trên ổ đĩa.

Các mô tả bốn stage/AgentManager và GUI card trong các mục dưới đây là lịch sử
kế hoạch M2-04 trước khi user thay thiết kế, không phải hành vi run mới.
Không sửa scope/approval của các run lịch sử. Phạm vi QA và các nhánh chưa thử
được ghi rõ trong release note và báo cáo project run tree.

## 1. Yêu cầu đã chốt

Một project có hai mode dùng chung Library:

- **Training/Research:** tái sử dụng tối đa pipeline nghiên cứu của repo gốc,
  gồm Agentic Tree Search, implementation/tuning/research/ablation, execution
  feedback, journal và report. Chỉ tuning và bổ sung điểm nối cần cho Codex,
  Kaggle SSH, workspace project, nguồn và budget đã duyệt.
- **Etc:** Working trực tiếp, linh hoạt, không Agentic Tree Search. User bắt
  buộc mô tả đầu ra mong muốn. Run giữ thông tin/status/log/Stop/artifacts như
  hiện tại; phần Report được thay bằng **Output**. Kết quả lưu trong thư mục
  `output/` của project và có thể được copy thành nguồn Library.

User luân phiên đổi mode trong cùng project. Mode là lựa chọn hiển thị/tạo
công việc mới; mỗi idea/proposal/run phải giữ mode của nó. Đổi mode trên GUI
không đổi mode của run đang chạy hoặc lịch sử và không làm mất Library.

Task chia theo feature; **user tự QA/demo sau mỗi task**. Agent bàn giao code,
hướng dẫn thao tác và checklist, chờ user duyệt trước khi làm task tiếp theo.
M2-01/M2-02/M2-03 đã được user duyệt. M2-02 có hai pipeline browser QA thật.
M2-04 và thiết kế project run tree thay thế đã được QA bằng browser, Codex CLI
và Kaggle SSH thật; user nghiệm thu và cho đóng MVP2 ngày 2026-10-09.
Bản chốt: [MVP2_RELEASE.md](MVP2_RELEASE.md).

## 2. So sánh hành vi

| Thành phần | Training/Research | Etc |
| --- | --- | --- |
| Library | Chung của project | Chung của project |
| Idea/proposal | Hypothesis/method, data/evaluation và thí nghiệm theo yêu cầu | Mục tiêu, nguồn, cách thực hiện và mô tả đầu ra user đã nhập |
| Approval | User duyệt proposal trước Working | Cùng approval hiện có |
| Execution | Tree Search gốc, bốn stage | Agent làm trực tiếp qua terminal Kaggle |
| Debug | Draft/debug/improve và feedback gốc | Agent đọc lỗi và sửa trong cùng Working; không tạo cây |
| Tiêu chí | Protocol/method và evidence của thí nghiệm | Đầu ra user yêu cầu và thực thi có thật |
| Metric/split/checkpoint | Theo thí nghiệm được duyệt | Không bắt buộc; chỉ dùng nếu nhiệm vụ yêu cầu |
| Phần kết quả trong run | Report, cây và artifacts | Output: nội dung/kết quả và file tải/xem được |
| Thư mục run | `project/experiment/<lượt>/` | `project/output/<lượt>/` |
| Chọn kết quả làm nguồn | Các khả năng hiện có | Nút copy một kết quả sang Library |

Etc không cần bảng phân loại task, recipe/template training, DSL checks,
preflight notebook, chữ ký run/emit, metric/seed cố định hoặc bộ artifact
bắt buộc. Mô tả đầu ra do user nhập không được thay bằng đầu ra do planner tự
đoán. Agent có thể hỏi rõ nội dung đó nếu còn mơ hồ.

Các cơ chế chung tiếp tục áp dụng: approval đúng version/scope, account,
phiên SSH, log và thu file, xác nhận Kaggle dừng, project ownership và recovery.
Không có quota tổng số lượt code/submit. User quyết định từng lượt, budget
thời gian/tài nguyên là thiết lập của phiên. Không thêm gate nghiệp vụ cho Etc
ngoài mô tả đầu ra và approval hiện có; kiểm tra đường dẫn/hash phục vụ lưu
đúng file, không phải preflight triển khai.

## 3. Mode và proposal

- GUI có lựa chọn rõ **Training/Research / Etc** trong project, nhớ lựa chọn
  đang dùng. Idea/run cards có nhãn mode để phân biệt lịch sử trong project.
- Idea mới lấy mode đang chọn. Khi mở idea/run cũ, nội dung và nhãn thể hiện
  mode đã lưu, không dùng mode đang chọn để diễn giải lại dữ liệu.
- Etc có ô **Đầu ra mong muốn**: mô tả tự do của user, không buộc tên file hay
  JSON schema. Đầu ra có thể là nội dung trả lời, bảng, CSV, ảnh, dataset, code,
  PDF hoặc kết quả khác. Mô tả không rỗng trước khi lập/duyệt proposal.
- Mode và mô tả đầu ra nằm trong context đã ghim của proposal/approval/run.
  Sửa mode hoặc đầu ra của một idea cần lập/duyệt proposal mới; không dùng
  approval cũ cho mode khác.
- Retry giữ mode/proposal/đầu ra đã duyệt. Variant mới có thể chọn mode mới
  trong cùng project và phải có proposal/approval mới; parent giữ nguyên.
- Dữ liệu cũ thiếu mode có đường đọc tương thích, giữ layout và report hiện
  có; không sửa snapshot/approval/hash lịch sử để gán lại hành vi.
- Prompt cho hai mode nằm trong `ai_scientist/workbench/system_prompt/`,
  backend gọi qua alias. Prompt Etc tối giản, không ghép instructions research.

## 4. Lưu Output của Etc

```text
.workbench/projects/<tên project>/
├── project.sqlite
├── library/
│   └── <tiêu đề nguồn>/vN/...
├── experiment/
│   └── <lượt Training-Research>/...
└── output/
    └── <lượt Etc>/...
```

Mỗi lượt Etc có thư mục riêng, tên dễ đọc theo tiêu đề/ngày/attempt theo cách
đặt tên hiện tại, không ghi đè lượt khác. Project `output/` là nơi chứa run
bundle Etc và kết quả đã thu; thư mục `output/` của agent trong Kaggle là nơi
agent tạo file trước khi backend thu. Không chuyển experiment cũ sang output.

SQLite giữ liên kết tương đối tới thư mục run. Bundle Etc dùng lại lưu
proposal/context, source, log, manifest và file kết quả hiện có; không tạo
journal cây/stage/token research hoặc `report.md` bắt buộc. Metadata/log cần
để xem lại và retry cùng nằm trong bundle, không lưu thêm bản sao kết quả ở
một workspace riêng ngoài project.

Trong Run Etc:

- Giữ card, trạng thái, account/phiên, log, ngân sách phiên, Stop và retry.
- Phần **Output** hiển thị kết quả dạng nội dung và các file đã thu. Tái sử
  dụng artifact page cho danh sách file dài và download; chỉ preview loại file
  hiện hỗ trợ. File khác vẫn xuất/tải được.
- Kết quả lỗi/partial đã thu có trạng thái rõ, không nhận là hoàn thành chỉ vì
  tồn tại file. Không tạo report AI riêng nếu user chỉ cần đầu ra công việc.
- Backend chỉ công bố kết thúc khi đã xác nhận Kaggle dừng. Restart đọc lại
  kết quả/log đã lưu và không tự chạy lại agent hoặc mở phiên mới.

## 5. Copy Output thành nguồn Library

User chọn một kết quả đã lưu của run Etc → **Thêm vào Library** → đặt tiêu đề
nguồn → backend copy kết quả vào Library của chính project.

- Copy server-side từ kết quả đã thu, không bắt user download rồi upload.
- Là bản sao thật, không move/symlink hoặc chỉ lưu đường dẫn tới output gốc.
  Xóa output/run sau đó không làm mất nguồn Library đã copy; xóa nguồn không
  xóa file output gốc.
- Với file: giữ bytes và tên/định dạng gốc; dùng Library versioning/hash,
  naming và ingestion hiện có. Với output là nội dung text: lưu thành nguồn
  text bằng luồng Library hiện có.
- Lưu provenance tối thiểu: run nguồn, đường dẫn kết quả và hash khi có file.
  Nguồn mới không mang quyền truy cập session/credential của run.
- File không trích được text vẫn được lưu và hiển thị đúng ingestion status;
  không yêu cầu nó phải là paper/PDF hoặc được coi là đã hiểu.
- Không đặt quota mới cho kết quả. Nếu giới hạn intake hiện tại cản copy file
  thực tế, xử lý ở điểm nhập/copy này, không thay copy bằng URL/reference.
- Nguồn mới có thể được chọn cho proposal ở cả hai mode như nguồn Library
  bình thường. Chưa tự động thêm nguồn đó vào proposal hoặc tự chạy agent.

## 6. Trách nhiệm và tái sử dụng

Chỉ một hệ thống project/approval/run và một lifecycle Kaggle chung.
WorkingService quản lý connect/SSH/log/thu file/Stop/recovery; mode quyết định
đường thực hiện và nơi lưu kết quả. Tái sử dụng hai đường execution hiện đã có:
TreeSearchRun và Working trực tiếp (`search.enabled=false`). Mode do proposal
đã duyệt quyết định, không nhận một cờ từ client để đổi mode sau approval.

| Phần gốc/hiện có | Cách sử dụng |
| --- | --- |
| AgentManager, ParallelAgent/chính sách draft-debug-improve | Training/Research; tránh viết lại thuật toán và pipeline stage |
| Node/Journal, MetricValue, save_run, bfts_utils | Experiment Training/Research và viewer/layout gốc |
| MinimalAgent execution feedback, interpreter.ExecutionResult | Training/Research; chỉ đổi điểm nối execution/provider cần thiết |
| log_summarization, journal2report, plotting/writeup/review | Tận dụng cho Training/Research theo outputs đã duyệt; không chạy trong Etc mặc định |
| perform_ideation_temp_free, Semantic Scholar | Nền cho Ideathon human + agent sau này; không thêm ideation tự động vào MVP2 |
| Codex worker, SSH bridge, Working lifecycle, log/manifest/recovery | Chung cả hai mode |
| LibraryFiles, import_file/ingestion/versioning/named_paths | Library chung và copy kết quả Etc thành nguồn |
| RunView/artifact page và GUI card/detail | Run chung, render Report hoặc Output theo mode |

Bê nguyên logic gốc khi môi trường/contract tương thích. Phần gắn provider API,
GPU/process pool local và đường dẫn workspace cần điểm nối phù hợp Codex/SSH;
không chạy launcher nguyên bản để tạo thêm session hoặc provider trả phí.
Nguồn và budget được duyệt tiếp tục là scope của Training/Research. Các bước
plotting/writeup/review/multi-seed chỉ chạy khi được yêu cầu/duyệt; không tuyên
bố đã tích hợp chỉ vì file/module còn trong fork.

## 7. Task theo feature

| Task | Feature | Bàn giao cho user QA | Trạng thái |
| --- | --- | --- | --- |
| **M2-01** | Hai mode, proposal và prompt theo mode | Đổi mode cùng project, Library chung, Etc bắt buộc mô tả đầu ra, approval ghim đúng mode | Đã bàn giao (`28d7342`); user cho phép tiếp tục M2-02 |
| **M2-02** | Working Etc và Output | Chạy trực tiếp không cây, run detail có Output, kết quả trong project/output | Đã triển khai (`f9b13d7`); browser QA hai pipeline đạt, user duyệt và cho tiếp tục M2-03 |
| **M2-03** | Copy Output sang Library | Chọn kết quả, đặt tiêu đề, copy thành nguồn dùng ở cả hai mode | Đã triển khai (`dca41a4`); user duyệt và cho tiếp tục M2-04 |
| **M2-04** | Training/Research dùng lại repo gốc | Theo thiết kế project run tree thay thế: mỗi node một run; outputs tùy chọn dùng module gốc | Đã nghiệm thu; feature `95026aa`, live QA/fixes `70bb6b5`; user duyệt đóng MVP2 |

Thứ tự M2-01 → M2-02 → M2-03 → M2-04. Mỗi task có code/hướng dẫn và commit
riêng; user QA rồi duyệt task tiếp. Refactor cấu trúc cần thiết giữ hành vi,
kiểm chứng và commit riêng trước behavior theo skill pattern-design. Không
tách QA/demo thành task phát triển; không tự mở phiên Kaggle hoặc chạy tests
khi chưa được yêu cầu. Khi user yêu cầu kiểm thử, ưu tiên browser workflow và
regression nhỏ theo phần bị tác động.

### M2-01 — Hai mode, proposal và prompt

**Phạm vi:** GUI chọn mode/đầu ra, metadata idea/context/proposal/run, approval,
prompt alias và read compatibility. Chưa đổi engine execution ở task này;
Etc chưa có đường chạy thì GUI phải nói rõ và không phát research thay thế.

Ghi chú hiện hành: giới hạn chưa mở Working Etc của M2-01 đã được gỡ ở M2-02.
Đoạn bàn giao M2-01 bên dưới mô tả phiên bản tại commit `28d7342`.

**Bàn giao M2-01 (2026-10-08):** có chọn mode theo project (lưu tại browser),
mode/đầu ra của idea, snapshot approval và nhãn run; hai prompt planner đọc theo
alias. Database lên schema 8 chỉ thêm cột idea, không sửa JSON/hash proposal cũ.
Run cũ hiển thị “Phiên bản cũ” và giữ đường chạy/artifacts. Etc được lưu nháp,
lập/duyệt proposal; backend và GUI chặn Working cho tới M2-02. Retry tiếp tục
dùng cùng proposal; variant cho chọn mode mới. Các approval chưa mở phiên không
khóa việc retry run đã kết thúc. Build frontend và compile Python đã thành công;
QA tính năng do user thực hiện theo hướng dẫn bên dưới. Backend đã khởi động
lại tại `http://127.0.0.1:8011/`, health OK; cả 6 project lên schema 8. Fingerprint
của body/snapshot/hash của 13 proposal cũ giống nhau trước và sau migration.

**Cách QA trên GUI:**

1. Mở project, ghi nhận nguồn đang có ở Library. Đổi “Mode cho idea mới” ở bên
   trái sang Etc, chuyển project rồi quay lại/refresh: lựa chọn vẫn là Etc và
   Library giữ nguyên. Mode này chỉ dùng làm mặc định khi tạo idea/variant.
2. Tạo idea “Tạo dữ liệu mẫu”, nội dung “Tạo 100 dòng dữ liệu bán hàng giả”, để
   đầu ra trống rồi lưu. Nút lập proposal bị khóa và có hướng dẫn nhập đầu ra.
3. Bấm “Sửa idea”, nhập đầu ra “Một CSV gồm 100 dòng với các cột ngày, sản phẩm,
   số lượng, đơn giá; kèm mô tả ngắn bằng tiếng Việt”, lưu và lập proposal.
   Kiểm tra proposal phản ánh mô tả, không tự thêm bốn stage hay protocol training.
4. Khi proposal chờ duyệt, sửa mô tả thành 200 dòng. Proposal v1 phải thành
   STALE, không còn nút duyệt; lập lại để có version/hash mới. Thử đổi mode của
   draft cũng phải làm proposal chờ duyệt thành STALE.
5. Duyệt proposal Etc hợp lệ, mở Run: nhãn Etc, đầu ra đúng snapshot, nút Working
   vô hiệu và nêu M2-02. Đổi mode ở sidebar không đổi nhãn/nội dung run này.
6. Tạo idea Training/Research mới: so sánh LogisticRegression và SVC trên
   make_moons, chọn bằng validation rồi đánh giá test. Kiểm tra proposal bám
   phương pháp, dữ liệu và đánh giá. Sau duyệt, form Working vẫn có bốn stage.
7. Mở run/idea cũ: nhãn “Phiên bản cũ”, report và artifacts vẫn mở được. Từ run
   đã kết thúc, tạo variant Etc: được chọn mode/đầu ra và phải lập/duyệt proposal
   mới. Tạo lượt Working mới (retry) vẫn dùng proposal/mode đã duyệt của parent.

Idea đã APPROVED không sửa phạm vi tại chỗ: tạo idea mới hoặc variant từ run đã
kết thúc. Đổi tiêu đề chỉ đổi tên hiển thị, không làm proposal stale. Lưu thay
đổi phạm vi draft làm sạch trao đổi cũ; các proposal cũ vẫn còn trong lịch sử.
Các thao tác lập proposal dùng Codex thật; M2-01 QA không cần mở Kaggle.

**User QA:**

- [ ] Đổi Training/Research ↔ Etc trong project, Library giữ nguyên; chuyển
  project rồi quay lại vẫn đọc đúng idea/run của project.
- [ ] Etc thiếu mô tả đầu ra không lập/duyệt proposal; nhập mô tả thì planner
  phản ánh đúng yêu cầu và không tự thêm protocol training/Tree Search.
- [ ] Training/Research proposal bám hypothesis/method/data/evaluation.
- [ ] Sửa mode/đầu ra làm proposal chờ duyệt cần lập lại; approval cũ không
  cấp quyền cho mode mới. Đổi lựa chọn GUI không đổi run đang chạy/lịch sử.
- [ ] Retry/variant và dữ liệu cũ đọc được, không ghi lại snapshots/hash cũ.

### M2-02 — Working Etc và Output

**Phạm vi:** dùng lại execution trực tiếp, cấp thư mục project/output, thu
file và trình bày Output. Giữ lifecycle/Stop/recovery. Chưa cần copy Library.

**Bàn giao M2-02 (2026-10-08):** backend chọn execution bằng mode đã ghim;
Etc bỏ qua cấu hình Tree Search từ client và dùng một Working agent qua bridge
SSH hiện có. Prompt riêng qua alias `working.etc` → `working_etc.md`, không ghép
instructions research. Etc không tạo Node/Journal, `logs/0-run`, token tracker
hoặc report nghiên cứu. Training/Research và run cũ tiếp tục đường chạy có sẵn.

Mỗi project có `output/`; lần bấm Working đầu tiên cấp thư mục
`output/YYYY-MM-DD_<tiêu đề>_attempt_N/`. Retry Etc cấp bundle mới, giữ proposal
và chuyển feedback/source đã thu vào bundle đó. `context.json` giữ input được
duyệt; `source/` và `output/` chứa file thu qua SSH; `output.json` giữ nội dung,
trạng thái, giới hạn và bằng chứng Stop; `working-manifest.json`, `working-stop.json`
và `working.log` giữ bằng chứng. Monitor tiếp tục đọc log từ SQLite của project.
Workspace agent nằm trong chính bundle, không tạo workspace bên ngoài project.

GUI Run Etc có form phần cứng/thời hạn, Log/Stop/retry và mục **Output**. Nội
dung text xuất hiện trực tiếp; một link mở trang file Output (gồm kết quả và
source đã thu), dùng lại artifact page. Text/CSV/JSON/code, ảnh PNG/JPEG/GIF/WebP
và PDF mở xem được; mọi file đã thu vẫn tải được. Định dạng khác chỉ tải file.
Etc không cần report.md, metric, checkpoint hoặc file kết quả theo mẫu để hoàn tất;
nội dung-only có thể nằm trong summary và danh sách file rỗng. Summary thành công
vẫn phải khớp các file/lệnh SSH đã xác minh. Kiểm tra này chỉ xác nhận việc thực
thi/thu file, không tự đánh giá được chất lượng mọi đầu ra user yêu cầu.

File chỉ được đưa vào manifest sau khi tải đủ và khớp SHA256. Nếu lỗi/Stop, giữ
file đã thu được khi terminal còn đọc được; hiển thị chưa hoàn tất. Terminal bận
hoặc mất kết nối có thể không thu thêm được file trước Stop. Chỉ công bố COMPLETED
khi summary thành công, collection hoàn tất và có receipt đúng phiên Kaggle đã
dừng. Restart đọc metadata/log đã lưu và chỉ đối soát/dừng phiên còn mở; không
chạy lại agent hoặc submit. Việc copy Output → Library dành cho M2-03.

**Cách QA trên GUI:**

1. Refresh `http://127.0.0.1:8011/`. Dùng một project QA, chọn Etc và tạo idea:
   “Dùng Python standard library tạo 100 dòng dữ liệu bán hàng giả, seed 42.
   Ngày nằm trong tháng 10/2026; số lượng và đơn giá dương. Tính tổng doanh thu.”
   Đầu ra mong muốn: “CSV 100 dòng gồm date, product, quantity, unit_price,
   revenue; JSON tổng hợp số dòng và tổng doanh thu; source Python và tóm tắt
   tiếng Việt dựa trên kết quả thực thi. Không cần train model hoặc report PDF.”
2. Lập proposal, xem rồi duyệt. Trong Run chọn CPU, thời hạn 30 phút và bấm
   Bắt đầu Working. Etc chỉ có phần cứng/thời hạn; không có ngân sách bốn stage.
3. Xem log remote Python/code/thực thi. Trong lúc chạy, đổi mode sidebar sang
   Training/Research: run này vẫn Etc. Sau cùng chỉ được COMPLETED khi có dòng
   xác nhận Kaggle dừng. Output phải có tóm tắt và CSV/JSON/source xem/tải được.
4. Xem đường dẫn bundle trong Output: thuộc project/output, có context, manifest,
   Stop, log và file đã thu; không có journal/cây/report nghiên cứu do backend tạo.
   CSV đủ 100 dòng; tổng doanh thu JSON phải khớp các dòng CSV.
5. Bấm Tạo lượt Working mới: proposal/mode giữ nguyên, bundle attempt khác và
   feedback/source từ lượt cũ. Chỉ mở thêm phiên khi bạn bấm Bắt đầu Working.
6. Kiểm tra nội dung-only với idea “Đọc một nguồn text đã chọn, dùng terminal
   Kaggle đếm số dòng và từ, giải thích kết quả”; đầu ra “Trả số dòng, số từ và
   giải thích ngắn bằng tiếng Việt; không cần tạo file kết quả”. Output được
   hiển thị mà không cần metric/report/file theo mẫu.
7. Với run QA không cần hoàn tất, bấm Stop trong lúc Working: phải qua STOPPING,
   chờ xác nhận dừng rồi CANCELLED. Output ghi chưa hoàn tất; file thu được vẫn
   mở/tải được. Không dùng sự tồn tại của một file để báo COMPLETED.
8. Sau một run đã kết thúc, refresh hoặc restart backend bằng lệnh thường dùng:
   Output/log/đường dẫn không đổi, không submit lại. Mở run Research cũ: vẫn có
   cây/report và experiment tương ứng.

QA trên đây dùng Codex/Kaggle thật do user chủ động chạy. Tại bàn giao code, agent triển khai chỉ
build frontend/compile Python, đọc lại code và trạng thái backend; chưa chạy
pipeline Kaggle hoặc bộ kiểm thử tính năng cho M2-02.
Backend đã khởi động lại tại port 8011, health OK và không có job đang chạy.
Cả 6 project hiện có đã có thư mục output; nội dung/hash của 13 proposal cũ
giữ nguyên sau restart.

**Browser QA thật theo yêu cầu user (2026-10-08):**

- Project riêng `QA M2-02 Etc Output` (`97988f9e052646eba8309bc1541a9206`).
  Mọi thao tác tạo Library/idea, lập/duyệt proposal, Start Working, retry,
  mở/tải Output được thực hiện qua browser; kiểm tra byte/hash và số liệu
  bằng cách đọc các file thực đã thu. Không gọi API để bỏ qua luồng GUI.
- Run `4a801ad1f5164745a0b5be680b04d0ab`: một phiên CPU trên huynhtrungcuong,
  proposal `27bc5b9a234f44498246c84791ed1971`, v1. CSV đúng 100 dòng, miền giá trị
  đúng nguồn Library; revenue từng dòng và tổng JSON khớp phép cộng Decimal:
  **28931.41**. Ba file source/CSV/JSON tổng **7790 bytes**, khớp SHA256.
  Nút Mở CSV/JSON và Tải file hoạt động; bản tải khớp byte với bundle.
- Run `3b630d65f8504d5f8aaa9d6f72d2e2d9`: proposal
  `0784cafe45e74a538631880670650546`, v1. Đếm toàn bộ nguồn Library qua Python
  remote: **9 dòng, 92 từ, 553 ký tự Unicode**, khớp file gốc. Trả nội dung
  trong Output, `output_files=[]` và manifest files rỗng; vẫn COMPLETED.
- Cả hai run chỉ gọi Working agent một lần, không Node/Journal/cây/report
  nghiên cứu. Receipt đúng session có `stopped=true`, status `complete`,
  rồi run mới COMPLETED. Sidebar đổi sang Research không đổi Run Etc.
- Retry `8b72c08f1b764f5caa983e9784bcfad6` giữ proposal đầu, có bundle attempt_1
  và feedback/source tham khảo, ở APPROVED; không tạo thêm working_runs/session.
- Restart backend khi không có job chạy; refresh browser vẫn mở hai Output
  và log cũ, không gọi lại agent/submit. Backend health OK; 13 proposal trước
  QA giữ nguyên fingerprint `27328d0a807336118c2366f8ef287e86460bf5305b52c20b6a096ce73737a71a`.
- Bằng chứng local: `.workbench/acceptance/m2-02-2026-10-08/verification.json`,
  `output-completed.jpg`, `output-files.jpg`, `content-only-completed.jpg`;
  bundle thực ở project/output. Không sửa code tính năng trong lượt QA này.
- Chưa thử trực tiếp nhánh Stop giữa công việc, timeout, mất SSH/thu file dở
  và ảnh/PDF preview. Chưa chạy pipeline Research mới trong QA M2-02.

**Checklist QA:**

- [x] Idea Etc có đầu ra đã mô tả → proposal → approval → Working trực tiếp.
- [x] Không gọi AgentManager, không stage tuning/research/ablation, không hiện
  ngân sách bốn stage hay cây trên run Etc.
- [x] Kết quả/nội dung/files nằm đúng project/output/<lượt>; mở/tải qua Output.
- [x] Hai run Etc và retry có thư mục riêng; retry chưa mở Kaggle khi chưa Start.
- [x] Log/Stop tự động/retry/restart giữ trạng thái thật và xác nhận dừng;
  không cần report.md/metric/checkpoint để hoàn thành Etc.
- [x] Chỉ mode/scope đã duyệt được chạy; swap GUI không đổi execution hiện hành.
- [ ] Stop giữa công việc, timeout/mất SSH/thu file dở: hiển thị phần chưa hoàn tất.
- [ ] Pipeline Training/Research mới vẫn ở experiment (run Research cũ đã mở
  được với cây/report; dữ liệu lịch sử giữ nguyên).

### M2-03 — Copy Output sang Library

**Phạm vi:** thao tác chọn kết quả/đặt tiêu đề, copy server-side, Library
metadata/ingestion/provenance. Tận dụng import/version/naming hiện có.

**Bàn giao M2-03 (2026-10-09):** mục Output trong Run Etc và trang File Output
có nút **Thêm vào Library**. Chọn một file đã thu hoặc **Nội dung Output**, nhập
tiêu đề rồi bấm **Copy vào Library**. Nguồn mới ở Library của chính project;
link **Mở Library** chuyển đến danh sách nguồn. Không tự chọn nguồn vào idea.

Backend dùng lại `ProjectStore.import_file`, `LibraryFiles`, ingestion và cách
đặt tên thư mục/version hiện có. File được copy bytes gốc; nội dung text thành
`output.txt` UTF-8. Library giữ `original.<định dạng>`, `source.md`,
`ingestion.json` và text/pages nếu trích được. Tên trùng tạo thư mục có hậu tố
theo Library, không ghi đè nguồn đã có. Bản copy độc lập với bundle Output;
thay file Library về sau vẫn qua cơ chế tăng version hiện có.

Metadata ghi run/proposal/version/context, loại kết quả, đường dẫn file,
bytes/SHA256, thời điểm copy, trạng thái/giới hạn của Output và bằng chứng Stop
tại thời điểm đó. Chi tiết nguồn có mục **Nguồn gốc từ Output**. File/nội dung
được ghim hash lúc chọn; nếu đổi trước khi copy, backend từ chối và yêu cầu chọn
lại. Chỉ đọc file thuộc manifest của Run Etc trong project, không đọc đường dẫn
tùy ý hoặc file qua symlink/junction. Khóa đường dẫn hiện có phối hợp thao tác
copy với đổi tên/xóa project/nguồn.

Có thể copy phần kết quả đã thu của run chưa hoàn tất; nguồn ghi rõ trạng thái
đó và không biến run thành COMPLETED. Copy không gọi Codex/Kaggle, không chạy
code, không thêm approval, không thay mode/proposal/run hoặc nguồn đang chọn.
Giới hạn nhập file 25 MB và trích text 2 MB vẫn là intake Library hiện có;
file lớn hơn chưa được nghiệm thu trong task này. Không dùng URL/reference thay
cho bản copy khi thao tác thành công.

**Cách QA không cần mở phiên Kaggle mới:**

1. Refresh `http://127.0.0.1:8011/`, chọn project **QA M2-02 Etc Output** và
   Run `4a801ad1`. Ở Output bấm **Thêm vào Library**, chọn `output/sales.csv`,
   đặt tiêu đề “Doanh thu giả — 100 dòng” rồi copy. **Mở Library**, chọn card
   nguồn mới: tên/thư mục đúng, bản gốc CSV tải được; text đã trích đủ 100 dòng
   dữ liệu. SHA256 bản gốc phải khớp SHA256 trong Nguồn gốc từ Output.
2. Quay lại Run, mở **các file Output**, dùng nút copy ở trang này với
   `output/summary.json`. Kiểm tra file gốc JSON vẫn có `row_count=100`,
   `total_revenue=28931.41`; run/output gốc không đổi.
3. Mở Run `3b630d65`, copy **Nội dung Output** với tiêu đề “Kết quả đếm nguồn”.
   Nguồn Library có bản gốc `output.txt` và text đã trích, đúng nội dung Output
   nói về 9 dòng/92 từ/553 ký tự. Nội dung không cần có file trên Kaggle để copy.
4. Copy CSV lần nữa với cùng tiêu đề: Library tạo tên có hậu tố `(2)`; nguồn
   thứ nhất và các phiên bản không bị ghi đè. Có thể xóa nguồn QA thừa bằng
   nút xóa nguồn hiện có, kiểm tra CSV Output gốc vẫn mở được.
5. Sang Idea, lưu draft Etc có đầu ra rồi chọn nguồn vừa copy, bấm xem context:
   có đường dẫn Library/version/hash, không pump nội dung CSV vào context.
   Làm tương tự với draft Training/Research trong cùng project. Không cần bấm
   lập proposal hoặc Working để kiểm tra thao tác chọn/preview này.
6. Refresh/backend restart rồi mở lại Library: provenance và bản gốc vẫn có.
   Khi cần thử xóa run, chỉ dùng run QA không cần thiết: bản copy Library vẫn
   mở được. Xóa run hiện tại là ẩn/khôi phục theo cơ chế đã có; bản copy không
   đọc lại bundle gốc để mở/tải hay đưa cho agent.

Nhánh binary/PDF, Output partial, file/hash đổi và file vượt intake chưa được
QA qua browser ở lượt triển khai này. Build frontend, compile Python và review
code được thực hiện trước bàn giao; các checkbox dưới đây dành cho user QA.
Backend đã mở lại ở port 8011, health OK và không có job/Working chưa dừng.
Body/snapshot/hash của cả 15 proposal trong 7 project giữ nguyên trước/sau
khởi động. Chưa thực hiện thao tác copy thật trong lượt triển khai M2-03.

**User QA:**

- [ ] Chọn file hoặc output text → Thêm vào Library → nguồn xuất hiện đúng tên.
- [ ] File copy giữ bytes/hash; mở nguồn và chọn vào proposal ở cả hai mode.
- [ ] Bản copy độc lập: xóa một run QA không cần thiết không làm mất nguồn đã
  copy; không dùng project/run thật của user để thử xóa khi chưa được yêu cầu.
- [ ] Nguồn không có text vẫn có bản gốc/trạng thái đúng; tên trùng xử lý theo
  Library hiện có, không ghi đè nguồn/phiên bản khác.
- [ ] Copy không gọi agent, mở Kaggle, tự duyệt hoặc tự chọn nguồn cho proposal.

### M2-04 — Training/Research dùng lại repo gốc

**Phạm vi:** đối chiếu đường research hiện tại với toàn pipeline upstream;
nối lại thành phần cần thiết, giữ logic gốc tối đa. Chỉ tuning nguồn/budget,
provider/SSH và đường dẫn project. Report/cây và thí nghiệm tiếp tục chuyên biệt
cho Training/Research; không general hóa bốn stage để ép dùng cho Etc.

**Spec triển khai (2026-10-09):** proposal Training/Research mới có phần
`research` để ghim summary/report và các phần user yêu cầu: plots, writeup PDF,
review, seeds/stages. Approval ghim phần này cùng body hiện có; form Working
không bật thêm thành phần ngoài proposal. Etc không dùng phần này, proposal cũ
thiếu nó giữ đường chạy trước M2-04. Không sửa snapshot/hash lịch sử.

- Dùng AgentManager, branch selection, Node/Journal/save_run hiện có. Tuning và
  ablation dùng ý tưởng/chính sách gốc với phạm vi dữ liệu/budget đã duyệt.
- Mỗi node lưu lệnh/output/returncode SSH và parent; lỗi có log thật cho debug.
- Summary và report dùng `log_summarization.get_stage_summary` và
  `journal2report`; review dùng `perform_llm_review.perform_review` qua adapter
  client Codex. Không khởi tạo provider API trả phí khác.
- Multi-seed dùng điểm nối của evaluator ParallelAgent gốc, thực thi tuần tự
  trên cùng SSH; seeds/split/method lấy từ proposal. Đánh giá seed không trở
  thành ứng viên để chọn seed tốt nhất.
- Plot dùng aggregator gốc, thay runner local bằng runner SSH. PDF dùng prompt,
  template và compile sequence gốc của writeup; adapter lưu bản thảo và chạy
  compiler ở Kaggle. Không tự tìm citations/VLM hoặc cài TeX ngoài yêu cầu;
  thiếu compiler/bản PDF hợp lệ được báo lỗi và giữ bản thảo.
- Lưu `research/pipeline.json` với trạng thái, lý do và artifact của từng phần;
  report cuối giữ nội dung nghiên cứu cùng evidence Stop. Dữ liệu/thư mục node
  không ghi đè. Restart đọc trạng thái, không replay phần còn thiếu.

Nghiệm thu qua GUI: proposal hiển thị phần research trước approval; chạy đủ
bốn stage bằng một SSH; mở log một node và thấy output/returncode thực; các
thành phần ngoài approval có trạng thái không yêu cầu; report/cây/artifacts đọc
được và thuộc project/experiment; đổi sang Etc vẫn không có research pipeline.
QA live do user thực hiện, không tự mở Kaggle hoặc gọi agent trong triển khai.

**Bàn giao M2-04 (2026-10-09):**

Đối chiếu [launcher upstream](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py)
và các module đi kèm. Bảng dưới phân biệt hàm chạy thật trong tích hợp với
những phần chỉ được tái sử dụng prompt/template:

| Phần | Tái sử dụng | Điều chỉnh cho Workbench |
| --- | --- | --- |
| Điều phối bốn stage | `AgentManager`, search policy, `Node`/`Journal`, `save_run` | Agent factory gọi Codex, thực thi trên SSH; budget phiên và scope đã duyệt |
| Tuning / ablation | `_generate_hyperparam_tuning_idea`, `_generate_ablation_idea` và parser gốc | Gắn ý tưởng vào request node; không mở rộng dữ liệu/method ngoài proposal |
| Debug | `Node.absorb_exec_result(ExecutionResult)` và policy debug gốc | `execution.json` chứa lệnh, stdout, returncode; parent được cấp log thật |
| Multi-seed | `_run_multi_seed_evaluation` gốc và vòng ghép kết quả vào Journal | Hook runner tuần tự trên SSH, exact seeds/stages; mean và sample std; không chọn seed tốt nhất |
| Summary | `get_stage_summary`, `get_node_log` gốc | Client Codex; lưu JSON theo stage và schema interchange gốc |
| Report | `journal2report`, `Journal.generate_summary` | Client query hiện có; report cuối bổ sung metadata và xác nhận Stop |
| Figures | `aggregate_plots` gốc, prompt và reflection gốc | Inject client/runner SSH; chỉ dùng node evidence đã thu, kiểm tra script/file kết quả |
| PDF | Prompt/template ICBINB hoặc ICML, `compile_latex` gốc | Adapter quản lý draft/reflection/compile qua SSH; không gọi toàn bộ `perform_writeup` |
| Review | `perform_review` gốc | Một reviewer văn bản qua Codex; đọc report hoặc PDF đã tạo, lưu JSON |

Các điểm nối upstream là kwargs/config tùy chọn; launcher gốc giữ đường local
khi không truyền chúng. Workbench không gọi nguyên launcher: launcher tự tạo
provider clients, giả định GPU/process pool và compiler local, đồng thời có
cleanup tiến trình không phù hợp với backend đang quản lý phiên Kaggle.
Adapter sử dụng chung deadline, worker, token usage thật và kết nối SSH.

Proposal mới hiển thị **Phạm vi Research**. Summary/report bật mặc định; plots,
PDF, review và extra seeds chỉ được planner bật khi user yêu cầu, và hiện rõ
trước approval. Thay phạm vi bằng idea/trao đổi rồi lập proposal mới; form
Working vẫn chỉ chọn phần cứng, thời hạn phiên và số bước tìm kiếm. Tất cả
phần đã yêu cầu phải thành công để Working được COMPLETED; backend còn phải
xác nhận Kaggle dừng. Lỗi một phần giữ bằng chứng/draft và hiển thị lý do.

Run có **Pipeline Research**: trạng thái từng phần và link mở kết quả; danh sách
đầy đủ vẫn ở trang Artifacts. Các file thêm nằm trong chính experiment:

```text
.workbench/projects/<tên project>/experiment/<lượt>/
├── logs/0-run/
│   ├── nodes/<id>/{execution.json,search-request.json,manifest.json,result.json,source/,output/}
│   ├── *_summary.json
│   └── selection-feedback.txt
├── research/
│   ├── pipeline.json
│   ├── stage-<n>-summary.json
│   ├── report.md
│   ├── multi-seed.json           # nếu đã yêu cầu
│   ├── paper.pdf                 # nếu compile thành công
│   └── latex/{template.tex,compile.log,...}
├── figures/                     # nếu đã yêu cầu
├── auto_plot_aggregator.py       # nếu đã yêu cầu
├── review_text.txt              # textual review, nếu đã yêu cầu
└── report.md                    # nghiên cứu + evidence backend/Stop
```

Input cho aggregator được stage riêng tại `research-input/` trong cùng remote
workspace; không tính các bản sao evidence này thành output mới. Mỗi node vẫn
giữ bytes/hash riêng. Lệnh SSH ghi tối đa 600.000 ký tự stdout cho một lệnh,
node giữ tối đa 2.000.000 ký tự và cờ truncated; log Working vẫn dùng cửa sổ
đọc từng phần hiện có. Đây là giới hạn lưu log, không phải quota số lượt user.

**Phạm vi chưa nối / giới hạn:**

- Citation search, novelty check tự động và VLM review không nằm trong tích hợp
  này. Bài chỉ dùng tài liệu Library đã chọn; không tự tìm mạng hoặc gọi provider
  khác. Review là nhận xét bằng mô hình, không phải kết quả thực nghiệm mới.
- PDF đặt mục tiêu 4 hoặc 8 trang theo template/prompt. Hiện chỉ xác nhận file
  đã compile và có trang đọc được; chưa tự nghiệm thu số trang nội dung/chất lượng
  xuất bản bằng toàn bộ vòng VLM/reflection của writeup gốc.
- Phiên Kaggle cần sẵn `pdflatex`, `bibtex` và các package TeX cần thiết. Không
  tự cài TeX; thiếu compiler thì phần PDF báo lỗi, giữ draft/compile.log. User
  muốn chuẩn bị compiler trong phiên phải mô tả rõ trong idea/proposal.
- Split/method giữ nguyên qua seed là yêu cầu của agent; backend đối chiếu seed
  và metric với JSON đã thu, không tự chứng minh được mọi chi tiết protocol của
  mã do agent viết. Chỉ chọn bằng validation; không dùng test để tìm seed.
- Các phần thêm cần thời gian Codex trong deadline Working cấu hình hiện có
  (`working_seconds` trong `.workbench/config.local.json`) và TTL phiên. Tăng
  TTL riêng không tự tăng deadline Working. Không tạo thêm phiên để bù timeout.
- Proposal cũ không có `research` giữ đường chạy cũ; retry cùng proposal không
  tự được thêm các phần mới. Lập proposal mới để QA M2-04. Etc không gọi pipeline.

**Cách user QA:**

1. Refresh GUI, dùng project QA và chọn Training/Research. Tạo idea mới, ví dụ:

   > So sánh mô hình trên make_moons: 2.000 mẫu, noise 0,25, seed dữ liệu/split
   > 42; train/validation/test 60/20/20. Baseline LogisticRegression với
   > StandardScaler; tuning C; research SVC RBF; ablation bỏ scaler. Chỉ chọn
   > mô hình bằng validation accuracy. Mỗi fit tối đa 30 giây, output tối đa
   > 5 MB. Lưu source, metric JSON, CSV dự đoán test và report kỹ thuật tiếng
   > Việt. Chạy summary và review report bằng văn bản; không cần figures/PDF
   > hay thêm seed training. Không mở thêm phiên.

2. Lập proposal: **Phạm vi Research** phải có summary/report/review, không có
   plots/PDF/seed. Đọc split/method/budget rồi tự duyệt. Working chọn CPU, TTL
   đủ cho deadline đã cấu hình và một bước mỗi stage để thử nhỏ trước.
3. Xem cây bốn stage. Ở Artifacts mở một node `execution.json`: phải có lệnh,
   stdout thực, returncode; trong cây click node xem log/plan/parent. Xem tên
   ý tưởng tuning/ablation đã lưu, không tự dùng thêm dataset ngoài proposal.
4. **Pipeline Research** phải hiển thị tree/summary/report/review hoàn tất và
   phần khác không yêu cầu. Mở report, JSON stage summary và `review_text.txt`.
   Report phải đối chiếu kết quả đã thu và có evidence phiên Kaggle đã dừng.
5. Muốn QA multi-seed, lập idea/proposal riêng yêu cầu repeat training với seeds
   `[0,1]` tại stage 2 và 3, giữ split 42. GUI phải ghi đúng seeds/stages trước
   duyệt. `research/multi-seed.json` phải có đủ bốn lần repeat, mean/sample std
   khớp metric JSON từng seed có `training_seed`; seed node không được chọn
   làm kết quả tối ưu chỉ vì metric tốt hơn.
6. Muốn QA figures/PDF, yêu cầu riêng trong idea (ICBINB 4 trang hoặc ICML 8
   trang), nêu output/budget và compiler cần dùng. Kiểm tra scope trước duyệt.
   Nếu compiler chưa có, PDF phải failed, giữ draft/log và Run không COMPLETED;
   không dùng file PDF cũ từ một lượt compile lỗi để báo thành công.
7. Refresh/restart khi run đã kết thúc: đọc được scope/status/report/artifacts,
   không chạy lại phần còn thiếu. Với run QA đang làm, Stop phải giữ phần chưa
   xong là interrupted và chờ xác nhận Kaggle dừng. Đổi sang Etc trong cùng
   project: giữ Library, không có bảng Research trên Run Etc, Output copy vẫn dùng.

Build frontend và compile Python đã đạt; chưa chạy unit/browser QA hoặc mở
phiên Kaggle M2-04 trong lượt triển khai này. Các checkbox là nghiệm thu của user.
Backend đã khởi động lại tại port 8011, health OK và không có Working chưa xác
nhận dừng. Body/snapshot/hash của 15 proposal trong 7 project giữ nguyên qua
restart. Metadata/Library/Output lịch sử không được chuyển sang pipeline mới.

**User QA:**

- [ ] Training/Research chạy đủ bốn stage bằng engine gốc trên một phiên SSH.
- [ ] Draft/debug/improve, selection, feedback và code/output/parent được lưu
  đúng; protocol/budget user đã duyệt được giữ.
- [ ] Mỗi phần được nối (summary/plot/writeup/review/multi-seed) có bảng trạng
  thái thực và cách gọi; phần ngoài outputs đã duyệt không tự chạy.
- [ ] Report/cây/artifacts mở được, experiment đúng project, node cũ không bị
  ghi đè và restart không replay.
- [ ] Sau đó đổi sang Etc trong cùng project vẫn dùng Library chung, không
  chạy research prompts/engine và Output → Library vẫn dùng được.

## 8. Điều kiện đóng MVP2

User QA/demo sau từng feature; ghi evidence thực trong run/Output/experiment
và cập nhật trạng thái đã triển khai/đã nghiệm thu theo bằng chứng. Dùng lại
bằng chứng MVP1 còn hợp lệ, không yêu cầu chạy lại toàn pipeline chỉ để đóng mốc.

- Training/Research: workshop và phần paper ngoài prototype, proposal đúng
  scope, debug có evidence, report đối chiếu phương pháp/kết quả/giới hạn.
- Etc: user mô tả đầu ra → proposal/approval → Working trực tiếp → Output,
  xác nhận dừng → copy một kết quả sang Library → dùng nguồn đó ở mode còn lại.
- Mode/version/approval/project isolation/restart có hiệu lực ở cả hai.
- Chưa có run thật hoặc chưa được user QA thì ghi chưa nghiệm thu; không tính
  fixture hoặc sự tồn tại module upstream thành khả năng đã hoàn thành.

Ideathon hybrid human + agent vẫn là bước sau; mode Training/Research giữ
nền pipeline upstream để nối ideation vào idea/proposal/approval dùng chung.
