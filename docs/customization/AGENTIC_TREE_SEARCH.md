# Agentic Tree Search trong Workbench

## Yêu cầu đã chốt

Người dùng chọn đủ bốn giai đoạn của repo gốc: implementation → baseline
tuning → creative research → ablation. Một lần bấm Working mở một phiên Kaggle;
mọi node chạy tuần tự qua kết nối SSH đó. Proposal vẫn phải được duyệt trước.

## Thiết kế

- Dùng trực tiếp `treesearch.agent_manager.AgentManager.run`, `Stage`,
  `StageTransition`, chính sách chọn nhánh của `ParallelAgent`, `Journal`/`Node`
  và bộ xuất cây HTML của repo. Không viết bộ điều phối bốn giai đoạn thứ hai.
- Thêm điểm nối nhỏ cho provider Codex và agent thực thi SSH. Provider API và
  process pool/GPU local của launcher gốc tiếp tục là mặc định của launcher đó.
- Mục tiêu từng giai đoạn phải nằm trong phạm vi proposal. Không tự bổ sung
  dataset HuggingFace, kéo dài training hoặc tạo paper ngoài phạm vi đã duyệt.
- Người dùng chọn số bước tối đa cho mỗi giai đoạn khi bắt đầu Working. Đây là
  ngân sách tìm kiếm của phiên, không phải giới hạn tổng số lượt của người dùng.
- Node lỗi trở thành nhánh debug; node tốt làm baseline cho tuning/research/
  ablation. Lưu từng bản code, outputs, feedback và quan hệ cha/con trước khi
  chọn bước tiếp. Không ghi đè bằng chứng của node cũ.
- Dừng/restart giữ dữ liệu đã lưu và chỉ đối soát/dừng phiên cũ, không replay.
- Nguồn Library tiếp tục được stage và đọc qua đường dẫn.

## Dữ liệu

Các lượt mới dùng `experiment/YYYY-MM-DD_<idea_title>_attempt_N/` bên trong
thư mục project, cùng cấp với `library/` (N tăng để
tránh trùng tên), chứa `idea.md`, `idea.json`, `logs/0-run/`,
`token_tracker.json`, report và bằng chứng dừng. Journal và bản xuất riêng của
từng giai đoạn nằm trong các thư mục stage của `logs/0-run/`. `unified_tree_viz.html` hiển thị
một cây duy nhất nối node của toàn bộ lượt Working, dùng màu phân biệt stage.
SQLite giữ đường dẫn tương đối trong project. Experiment Workbench đã lưu ở
`workspace/experiments/` được di chuyển vào đúng project khi backend khởi động,
giữ nguyên bytes/hash. Migration kiểm tra project/run trong `idea.json`, không
ghi đè thư mục đích và không đụng experiment không thuộc Workbench. Run notebook
cũ ở `runs/<run_id>/` giữ vị trí hiện có.
`review_text.txt` lưu feedback/chọn kết quả thực tế của cây, không phải review
paper. PDF chỉ có khi tác vụ thực sự tạo PDF; không tạo file giả. Token chưa
được runtime cung cấp được ghi là chưa biết; không báo số 0 như số đo thực tế.
Chi phí và reasoning tokens chưa có số đo được ghi `null`.

Với cấu hình hiện tại, thư mục gốc là
`D:\Documents\AI-Scientist-v2\.workbench\projects\<tên project>\experiment`:

```text
.workbench/projects/<tên project>/
├── project.sqlite
├── library/
└── experiment/
    └── YYYY-MM-DD_<idea_title>_attempt_N/
```

Mỗi experiment chứa:

```text
experiment/YYYY-MM-DD_<idea_title>_attempt_N/
├── idea.md
├── idea.json
├── logs/0-run/
│   ├── unified_tree_viz.html
│   ├── search-state.json
│   ├── stage_1_initial_implementation/  # cây gộp các substage
│   ├── stage_2_baseline_tuning/
│   ├── stage_3_creative_research/
│   ├── stage_4_ablation_studies/
│   ├── stage_<substage>/               # journal/export gốc
│   ├── nodes/<node_id>/                # source, output, manifest, result
│   └── feedback/
├── token_tracker.json
├── review_text.txt
├── source/
├── output/                            # kết quả của node được chọn
├── report.md
└── working-stop.json
```

Tên node dùng ID gốc để giữ quan hệ cây; node đặt ngay dưới `nodes` để tránh
đường dẫn quá dài trên Windows. Log terminal thực tế tiếp tục nằm trong Log
Working. File `Node._term_out` dùng tóm tắt của node, không thay thế log terminal.
Xóa nguồn dọn bản gốc và các bản sao Library trong cả workspace feedback và
workspace thực thi của experiment thuộc project đó; report/code cũ giữ nguyên.

## Sử dụng và cấu hình

1. Tạo idea, chọn nguồn, lập và duyệt proposal như trước.
2. Trong Run, mở “Ngân sách tìm kiếm của phiên” để chỉnh số bước tối đa của
   implementation/tuning/research/ablation. Mặc định 3 bước mỗi stage; baseline
   kế thừa không tính là một bước mới. Stage có thể hoàn tất sớm.
3. Bấm “Bắt đầu Working”. Các nhánh draft/debug/improve chạy qua một terminal
   SSH; backend thu bằng chứng, chọn kết quả và xác nhận Kaggle dừng.
4. GUI hiện đường dẫn đầy đủ bên trong project. “Mở cây thí nghiệm” mở một cây
   chung ở trên và chi tiết node ở dưới. Chọn node để xem code/metric/feedback;
   màu thể hiện stage, nút “Xem node cha” đi theo quan hệ đã lưu. “Artifacts đã lưu” mở danh sách
   file. Tạo lượt Working mới cấp `attempt_N` mới, không đổi node/artifact cũ.

Các prompt nằm trong `ai_scientist/workbench/system_prompt/`, alias trong
`aliases.json`: `search.node`, `search.node_instructions`, `search.query`,
`search.stage_goals`. Sửa goals phải giữ đủ bốn khóa `1`–`4`.
Thời gian tối đa toàn Working theo `working_seconds` trong config local và TTL
phiên Kaggle; các ràng buộc proposal tiếp tục được đưa cho agent. Không có quota
tổng số lượt. Stock multi-seed/GPU process pool không được chạy thêm trong
Workbench; launcher gốc vẫn giữ các mặc định riêng của nó.

## Trình tự

1. Refactor điểm nối provider/agent và phân giải đường dẫn artifact; chạy tập
   regression hiện có rồi commit riêng, giữ nguyên hành vi.
2. Tích hợp executor SSH/Codex, bốn giai đoạn, layout experiment và giao diện.
3. Kiểm thử browser bằng provider/SSH local có đo số lần gọi; không tạo phiên
   Kaggle mới trong phạm vi kiểm thử này. Bàn giao rõ phần chưa kiểm chứng thật.

## Checklist nghiệm thu

- [x] Launcher gốc tiếp tục dùng provider/process pool mặc định (review điểm nối).
- [x] Một Working đi qua đủ bốn stage của AgentManager gốc.
- [x] Có nhánh draft/debug/improve và parent ID khôi phục đúng.
- [x] Mỗi stage có thể dừng theo ngân sách; không có vòng substage vô hạn.
- [x] Một SSH/bootstrap cho cả cây; dừng và chứng minh dừng trước COMPLETED.
- [x] Artifact từng node bất biến; kết quả được hash khi thu qua SSH.
- [x] Layout experiment có idea, journal, cây HTML và trạng thái token usage.
- [x] GUI mở được cây và artifacts; refresh/restart vẫn xem được kết quả.
- [x] Run cũ, retry, variant và project isolation tiếp tục hoạt động.
- [x] Không gọi preflight/contract notebook cũ hoặc in toàn bộ Library vào prompt.

## Bằng chứng nghiệm thu local — 2026-10-08

- Refactor riêng: `fdf958a`, 34 regression trước/sau đều đạt. Behavior được
  triển khai sau commit này.
- Targeted backend: 71 passed; kiểm tra bổ sung cho xóa nguồn/cancel/recovery
  sau thay đổi cuối: 25 passed. Hai tập có phần giao nhau, không cộng thành
  số trường hợp riêng biệt. Frontend `tsc -b && vite build` đạt.
- Browser local đi từ tạo project/nguồn/idea → proposal → approval → Working
  → report/dừng → restart → tạo lượt mới. Hai experiment, mỗi lượt có 7 node:
  draft lỗi → debug thành công, tuning 2, research 2, ablation 1.
- Counters: fake SSH=2, bootstrap=2, stop=2; Codex thật=0, Kaggle thật=0.
  Restart không replay; SHA256 của cả 93 file lượt đầu giữ nguyên sau retry.
  Viewer mở và đổi stage được. Dữ liệu/bằng chứng/screenshot nằm ở
  `.workbench/acceptance/tree-search-2026-10-08/`.
- Kiểm thử node thất bại và người dùng dừng: lưu checkpoint failed/interrupted,
  hủy worker, thu proof dừng, không mở phiên thứ hai.
- Chưa chạy Codex/Kaggle thật qua bốn stage; chưa chạy toàn launcher gốc với
  process pool/GPU local. Nghiệm thu remote thật vẫn thuộc M1-04.

Ngoài phạm vi: tự động viết/review PDF không được yêu cầu trong proposal;
điều phối nhiều phiên Kaggle song song; chạy Kaggle thật để nghiệm thu.

## Đóng gói theo project — 2026-10-08

- Experiment và Library nằm cạnh nhau trong project. Attempt được cấp riêng
  theo project; hai project có cùng tiêu đề idea đều có thể bắt đầu ở attempt_0.
- Sao chép/di chuyển cả project giữ được đường dẫn run tương đối. Các log/config
  lịch sử có thể chứa đường dẫn tuyệt đối cũ; app phân giải artifacts qua SQLite,
  không dùng các đường dẫn lịch sử đó để mở hoặc chạy lại agent.
- Migration dùng rename, không tạo bản sao giữ lại ở thư mục chung. Nếu bị ngắt
  sau rename trước khi cập nhật DB, startup xác minh ownership ở đích và sửa
  liên kết. Lỗi cập nhật DB khôi phục vị trí nguồn.
- Windows truy cập artifact sâu bằng extended path namespace; GUI vẫn hiện
  đường dẫn thông thường. Không đổi thiết lập Windows hoặc rút ngắn tên project.
- Targeted sau thay đổi: 38 passed; frontend build đạt. Hai experiment fixture
  đã chuyển vào `QA Tree Search/experiment/`; toàn bộ 93 file của lượt đầu giữ
  nguyên SHA256, thư mục chung cũ đã được dọn khi rỗng. Browser mở được cây/report
  sau migration và tạo lượt `attempt_2` hoàn tất tại vị trí mới; hash lượt đầu
  vẫn giữ nguyên. Không mở Kaggle thật hoặc gọi Codex thật.

## Viewer một cây — 2026-10-08

- Node kế thừa giữa các stage được gộp theo ID; màu là stage tạo ra node lần
  đầu. Bản sao baseline không làm mất cạnh cha/con của node gốc. Không nối các
  node chỉ vì chúng được chạy liên tiếp; nhiều draft độc lập giữ nguyên gốc.
- Tái sử dụng journal, thuật toán layout và cách biểu diễn metric của exporter
  gốc. Render SVG tương tác trong trang, không cần tải p5 hoặc fetch từng stage.
- Cây nằm trên; nội dung node nằm dưới và chiếm toàn chiều ngang. Code/log
  thu gọn, chỉ mở khi cần. Node lỗi vẫn có màu stage và nhãn “Có lỗi”.
- URL viewer của run cũ render bằng journal đã lưu và template hiện tại, không
  ghi lại artifact lịch sử hoặc gọi agent để chọn kết quả. Lượt mới lưu HTML
  gộp tại mỗi checkpoint. Khi run đang chạy, viewer kiểm tra cập nhật mỗi 15
  giây; run đã dừng không poll. Có nút “Cập nhật cây” để tải lại thủ công.
- 9 kiểm tra local đạt; kiểm tra browser trên run thật đã hoàn tất `20070c81`
  thấy đúng 4 node/3 cạnh, bốn màu stage, chọn node/code/node cha hoạt động và
  chi tiết nằm dưới cây. Không mở lại phiên Kaggle.
