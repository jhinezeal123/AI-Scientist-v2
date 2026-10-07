# Working qua SSH — 2026-10-07

## Luồng sử dụng

1. Lưu nguồn và idea, lập proposal và duyệt như trước.
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
mỗi lượt mới có ID riêng. Mỗi lượt thực hiện workload được duyệt, với thời gian/dung lượng
trong proposal. Agent báo lỗi để user quyết định lượt tiếp theo; không tự chạy lại workload.

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

Run cũ vẫn xem được log, artifacts và report. Các endpoint notebook cũ còn phục vụ
khả năng tương thích; GUI dùng Working cho những run chưa có phiên Kaggle cũ.
UNKNOWN cũ được kiểm tra bằng token đối với notebook reference đã lưu, không cần cookie.
Đây là kiểm tra các notebook Workbench đã biết, không phải kiểm kê mọi phiên ngoài Workbench.

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
bao gồm khởi động và làm việc. Training/output vẫn theo proposal đã duyệt.
CLI được tìm lại khi đường dẫn cũ không còn tồn tại sau cập nhật: PATH, rồi bản
desktop hiện có. Backend không tự đổi model hoặc đăng nhập account khác.

## Bằng chứng kiểm thử

- Bộ kiểm thử Workbench, bao gồm luồng Working qua gateway HTTP thật với terminal
  fixture: **95 passed**.
- Kiểm thử donor cho request ID, cancellation, Bash thật ở local, cwd/exports/env,
  redaction, timeout, tương thích các tool cũ và proxy không replay submit: **16 passed**.
- Frontend TypeScript/Vite build thành công.
- Theo phạm vi user đã duyệt, **chưa tạo phiên Kaggle mới để nghiệm thu tích hợp này**.
  Các fixture không chứng minh độ trễ mạng, cấp phát GPU/TPU hay khả năng của agent trên dữ liệu thật.

Chạy backend như trước rồi mở lại GUI để dùng bản mới:

```powershell
& .\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --port 8011
```

Không dùng `--smoke` để kiểm thử Working: tùy chọn đó chỉ kiểm tra lượt planning.
