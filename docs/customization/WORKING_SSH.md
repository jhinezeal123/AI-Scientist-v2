# Working qua SSH — 2026-10-07

## Luồng sử dụng

1. Lưu idea, chọn nguồn nếu cần, lập proposal và duyệt.
2. Trong **Run**, chọn card của lượt đã duyệt.
3. Chọn CPU, GPU **T4 x2**, hoặc TPU; chọn thời gian tối đa của phiên.
4. Bấm **Bắt đầu Working**. Backend mở notebook bootstrap riêng tư bằng
   `kaggle_ssh_start`, kết nối SSH, rồi gọi Codex local để viết và chạy code trong Kaggle.
5. Xem **Log Working**. Backend thu `source/` và `output/`, kiểm tra byte count/SHA256,
   lưu journal, manifest và report, yêu cầu dừng phiên và kiểm tra trạng thái Kaggle.
6. Khi cần, bấm **Dừng Working**. Khi lượt kết thúc, bấm **Tạo lượt Working mới**
   để dùng cùng proposal và tham khảo source/log/summary cũ. Lượt mới chỉ chạy khi bấm Working.

Code và submit đã gộp vào một thao tác. Agent có thể khảo sát mount và packages thật
trước khi viết code. Agent không nhận Kaggle MCP, token account hoặc khóa SSH.
Model/reasoning lấy từ config hiện có; không cài Codex trong Kaggle.

Không giới hạn tổng số lượt do user yêu cầu. Bấm lặp cùng run không tạo thêm notebook;
mỗi lượt mới có ID riêng. Agent có thể kiểm tra, chạy, debug và sửa trong cùng phiên
để hoàn thành mục tiêu đã duyệt. Các giới hạn user yêu cầu trong proposal vẫn áp dụng.

## Proposal và các gate đã gỡ

Proposal dùng `WorkingProposal`: cần mục tiêu và bước thực hiện, không bắt buộc dataset,
split, seed, metric hay budget training. Idea tạo dữ liệu synthetic có thể không chọn nguồn.
URL chưa đọc được lưu đúng trạng thái `reference_only`; agent kiểm tra nội dung/mount trong
Working, không coi URL là dữ liệu đã xác minh.

Luồng Working không gọi preflight/bundle validator cũ. Code không cần chữ ký `run/emit`,
notebook template, `checkpoint`, `metrics.json` hoặc `result.json`. Các tác vụ được lưu
file phù hợp mục đích trong `source/` và `output/`.

Không áp trần mặc định 600 giây hoặc 10 MB trong proposal/thu file. `budget.output_bytes`
và giới hạn thời gian chỉ áp dụng khi được yêu cầu rõ trong proposal. Thời gian phiên và
thời gian lượt agent vẫn cấu hình riêng để backend dừng công việc đúng hạn. Kênh truyền
file vẫn kiểm tra đường dẫn, số file (tối đa 200), kích thước và hash; file lớn được truyền
theo từng phần. Không cần các artifact đặc thù training để ghi thành công.

## Trạng thái và điều kiện kết thúc

`APPROVED → STARTING → WORKING → STOPPING → COMPLETED / FAILED / CANCELLED`

- `STARTING`: tạo bootstrap và chờ SSH. Backend ghi request ID trước khi gọi MCP.
  Donor dùng ID này để tránh submit lại khi phản hồi bị mất.
- `WORKING`: agent dùng helper `terminal.py` để gửi lệnh vào **cùng một kết nối SSH
  và một Bash process**. Cwd và exports được giữ giữa các lệnh. CUDA/xác thực Kaggle
  được thừa hưởng từ tiến trình notebook bằng launcher trong donor.
- `STOPPING`: backend đã yêu cầu dừng nhưng chưa có bằng chứng dừng. Backend tiếp tục
  kiểm tra; không mở lượt mới và không ghi hoàn tất khi phản hồi chậm hoặc mất kết nối.
- `COMPLETED`: agent báo thành công, các file được kiểm tra và lưu, report đã lưu,
  **Kaggle đã xác nhận dừng** cho notebook riêng của run này.
- `FAILED` và `CANCELLED` cũng chỉ được ghi sau xác nhận dừng. Report phân biệt
  tóm tắt của agent với bằng chứng backend; đây không phải chứng minh thuật toán đúng.

Các lệnh bình thường dùng terminal hiện có. Backend có thể mở kết nối SSH khẩn cấp
để gửi STOP nếu terminal đang bận/hỏng, hoặc sau khi backend restart. TTL của bootstrap
là đường dừng dự phòng. Nếu không liên lạc được với Kaggle để xác nhận, run vẫn `STOPPING`.

Restart backend chỉ phục hồi việc dừng/đối soát; không replay agent, lệnh hay notebook.
Donor ghi cancel intent và khóa admission theo session ID để một yêu cầu startup
đến trễ không submit sau khi backend đã xác nhận request chưa được gửi.

Run cũ vẫn xem được log, artifacts và report. Các endpoint `/implement` và `/submit`
trả HTTP 410, hướng dẫn dùng Working; backend không khởi tạo executor, monitor hay
reporter training cũ. Các module/schema cũ còn trong repo cho dữ liệu và kiểm thử lịch sử,
không tham gia luồng đang chạy. Tạo lượt mới từ run cũ chỉ tham khảo source/log, không
build hoặc kiểm lại bundle cũ. Đối soát run cũ chỉ đọc trạng thái bằng token.
UNKNOWN cũ được kiểm tra bằng token đối với notebook reference đã lưu, không cần cookie.
Nếu reference UNKNOWN cũ không đọc được, backend dùng `workbench_account_idle` để
xác minh đúng account/cookie và toàn bộ phiên hoạt động. Chỉ cho lượt mới khi count=0,
idle=true và có timestamp; giữ nguyên UNKNOWN và không gửi lại notebook cũ.
Phép đọc này chỉ hỗ trợ lịch sử UNKNOWN, không kiểm format code/mount hay training contract.
Khi mọi reference đọc được, backend chỉ kiểm tra các notebook Workbench đã biết.

## Trách nhiệm các module

| Module | Trách nhiệm |
| --- | --- |
| `run_view.py` | Trình bày run và các kết quả cũ |
| `working.py` | Điều phối Working và quy tắc kết thúc |
| `working_store.py` | SQLite, log và bằng chứng dừng |
| `ssh_terminal.py` | Terminal SSH, gateway local cho agent, thu file |
| `terminal_client.py` | Helper stdlib được đặt trong workspace của agent |
| donor `interface_ai_scientist/session.py` | SDK bootstrap, SSH và đọc trạng thái Kaggle |
| donor `interface_ai_scientist/terminal_remote.py` | Một Bash process trong Kaggle và truyền file qua SSH |

Logic bootstrap/Tailcat vẫn nằm trong repo donor. Workbench chỉ sở hữu vòng đời
công việc và kênh lệnh dành cho agent.

## Config

Giữ `.workbench/config.local.json` hiện có. Các giá trị bổ sung mặc định:

```json
{
  "working_seconds": 900,
  "kaggle_session_seconds": 1800,
  "kaggle_accelerator": "cpu"
}
```

`working_seconds` là thời gian tối đa cho lượt Codex; TTL là thời gian bootstrap,
bao gồm khởi động và làm việc. Giới hạn user ghi rõ trong proposal vẫn được áp dụng;
proposal không còn các trần training/output mặc định của MVP0 cũ.
CLI được tìm lại khi đường dẫn cũ không còn tồn tại sau cập nhật: PATH, rồi bản
desktop hiện có. Backend không tự đổi model hoặc đăng nhập account khác.

Trên Windows, backend truyền `PROGRAMDATA` vào tiến trình MCP để OpenSSH khởi động
được. Lượt Working dùng `--ignore-user-config` để không đưa MCP/config cá nhân vào
agent; vì vậy backend đặt rõ `windows.sandbox="elevated"`, cùng `workspace-write`
và network access cho helper local. Sandbox Windows cần được setup sẵn trên máy.
Phản hồi cuối dùng schema `WorkingPayload` trực tiếp của CLI (`succeeded`, `summary`,
`limitations`, `output_files`); đây là định dạng báo kết quả, không phải contract
notebook, mô hình hoặc training.

## Bằng chứng kiểm thử

- Bộ kiểm thử Workbench, bao gồm luồng Working qua gateway HTTP thật với terminal
  fixture: **101 passed**; tập kiểm thử Working tổng quát sau bổ sung: **8 passed**.
- Kiểm thử donor cho request ID, cancellation, Bash thật ở local, cwd/exports/env,
  redaction, timeout, file trên 10 MB, tương thích các tool cũ và proxy không replay submit: **17 passed**.
- Frontend TypeScript/Vite build thành công.
- **Nghiệm thu GUI/Kaggle thật 2026-10-07:** idea → proposal bởi Codex thật → duyệt
  → Working CPU → 4 files đã kiểm hash → report → xác nhận dừng phiên. Run `abb8c794…`
  tạo đúng 1.000 dòng CSV, không missing; restart giữ 9 artifact links, 1.762 log records,
  1 lượt agent và 8 lệnh SSH. Xem [biên bản nghiệm thu](WORKING_ACCEPTANCE.md).
  Lượt này chứng minh tác vụ tổng quát CPU/stdlib, chưa kiểm GPU/TPU, finetune hoặc
  dữ liệu ngoài trên luồng Working mới. Training MVP0 cũ có bằng chứng riêng trong guide.

Chạy backend như trước rồi mở lại GUI để dùng bản mới:

```powershell
& .\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --port 8011
```

Không dùng `--smoke` để kiểm thử Working: tùy chọn đó chỉ kiểm tra lượt planning.
