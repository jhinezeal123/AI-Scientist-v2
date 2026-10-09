# Kaggle core trong AI Scientist

## Cấu trúc và phạm vi

Lõi Kaggle nằm tại `kaggle mcp/`, lấy từ donor
`jhinezeal123/kaggle_token@9bf4c85c8e060ebe022f285c1667a0edf5d4635f`.
`SOURCE.json` ghi commit, hash các file gốc và các phần được trích ra.
Đây là source snapshot được chọn lọc; cập nhật donor không tự đổi bản đóng gói.

- `interface_ai_scientist/`: bootstrap SDK, Tailcat Tokyo, SSH bền vững,
  trao đổi file, trạng thái và STOP.
- `account_store.py`, `proxy.py`, `proxy_control.py`: chọn đúng profile token
  và tái sử dụng kết nối HTTPS. SDK giữ pin `kagglesdk==0.1.37`.
- `account_runtime.py`, `cookie_client.py`, `auto_login/`: xác minh account
  và phiên đang chạy; dùng lại recovery/login gốc khi cookie hết hạn.
- `bootstrap_service.start`, `account_runtime.account_idle`: hàm Python nội bộ;
  backend gọi CLI `start`/`idle` qua adapter `DonorSession` hiện có.
  Đã xóa MCP server/registration và bỏ dependency MCP trực tiếp.

Không mang theo `agent_platform`, giao diện quản lý account, suite tool cũ,
notebook builder/preflight, tải log/artifact bằng browser hoặc tool dataset.
Workbench tiếp tục quản lý code, log, thu output và dừng phiên qua SSH.

## Cấu hình trên máy này

`.workbench/config.local.json` đã chuyển sang:

```json
{
  "donor_root": "D:/Documents/AI-Scientist-v2/kaggle mcp",
  "donor_python": "D:/Documents/AI-Scientist-v2/.venv-mvp0/Scripts/python.exe"
}
```

Tên trường `donor_*` được giữ để tương thích config và adapter hiện có.
CLI Kaggle/SSH dùng chung Python của Workbench. Proxy riêng chạy trên
`127.0.0.1:8013`, kiểm tra đúng tên dịch vụ và thư mục root trước khi dùng.
Backend tải trực tiếp proxy manager và sở hữu vòng đời proxy port 8013.
Không còn tiến trình/kết nối MCP trong luồng Working.
Có thể đổi port bằng `AI_SCIENTIST_KAGGLE_PROXY_PORT` trước khi mở backend.

Chỉ profile được chọn của `huynhtrungcuong` được cấu hình local trong
`kaggle mcp/profiles/`: registry, token và cookie. Không sao chép các profile
khác, database browser, virtualenv hoặc runtime phiên cũ. Mật khẩu auto-login
không được mang sang; có thể cấu hình riêng trong `profiles/credentials.json`.

`profiles/`, `.runtime/` và `logs/` được Git bỏ qua. Token/cookie/SSH key không
được commit. Tailcat được tải bản pin có kiểm tra SHA256 vào `.runtime/`.

## Cài đặt và khởi động

Từ root repo:

```powershell
py -3.12 -m venv .venv-mvp0
.\.venv-mvp0\Scripts\python.exe -m pip install -r requirements-mvp0.lock.txt
```

Copy `config-mvp0.example.json` sang `.workbench/config.local.json` nếu chưa có;
sửa các đường dẫn theo checkout và cấu hình account theo
[README Kaggle core](../../kaggle%20mcp/README.md). Đăng nhập Codex local.
Sau khi build frontend theo [hướng dẫn chạy](MVP0_RUN_GUIDE.md), mở backend:

```powershell
.\.venv-mvp0\Scripts\python.exe -m ai_scientist.workbench --port 8011
```

Backend tự khởi động proxy và gọi các action CLI. Sau khi
di chuyển repo sang máy/thư mục khác, cập nhật đường dẫn config và cấu hình
credential local; source không phụ thuộc checkout `D:/Documents/kaggle_token`.
Phiên cũ tạo ở donor bên ngoài vẫn giữ private state ở đó; các run đã dừng
và artifact trong project tiếp tục đọc được.

## QA bản đóng gói MCP ban đầu ngày 2026-10-09 (lịch sử)

Kiểm tra local: import toàn bộ lõi, pin SDK, danh sách đúng hai MCP tool,
health proxy xác minh root bản đóng gói, account idle `huynhtrungcuong`,
`pip check` và 14 kiểm thử connection/terminal đều qua. Một lượt kiểm thử
trước chuyển backend gặp WinError 10053 ở localhost bridge; chạy lại qua.

QA live tạo project **QA bundled Kaggle — CPU 09-10** qua GUI, gọi Codex CLI
lập proposal Etc, duyệt rồi bấm Working với CPU và TTL 10 phút. Workload
chỉ dùng thư viện chuẩn Python, tính tổng bình phương 1…1000, lưu JSON và
source; không cài package hoặc dùng GPU.

- Project: `d6637b69b3384c9fa9cc2069c73329b4`.
- Proposal: `97dd000afb1b4473ab36bf07092990f3`.
- Run: `a4ecb31adfe0420588a4cbd8fdfff29d`.

Kết quả live **PASS**:

- Một `SaveKernel` qua proxy riêng; bootstrap CPU và SSH sẵn sàng.
- Codex local thực hiện 3 lệnh qua cùng terminal; JSON tạo trên Kaggle Linux,
  Python 3.13.15, `sum_squares=333833500`, `verified=true`, tính trong
  `0.000078405` giây. Đối chiếu lại giá trị bằng phép tính local.
- Thu `source/check.py` (956 bytes) và `output/result.json` (238 bytes);
  tổng 1194 bytes. Hash cả hai khớp `working-manifest.json`.
- `working-stop.json`: `status=complete`, `stopped=true`, xác nhận lúc
  `2026-10-09T12:33:12.744646+00:00`. Run là `COMPLETED`, `stop_confirmed=true`.
- Restart backend: port 8013 và các tiến trình MCP/proxy cũ đã đóng;
  MCP/proxy bản đóng gói được mở lại. GUI vẫn đọc run/output/log, không submit
  hoặc gọi agent lại. Account-wide idle check xác nhận 0 phiên đang chạy.
- Review cuối phát hiện option `UserKnownHostsFile` gốc chưa quote đường dẫn
  có dấu cách, khiến OpenSSH ghi nhầm file `kaggle` ở root dù lượt chạy thành
  công. Đã quote option trong bản đóng gói; `ssh -G` xác nhận toàn bộ đường
  dẫn đúng. Chuyển host key đã ghi vào runtime của đúng phiên, dọn file phát
  sinh và restart để nạp bản sửa. Không cần submit lại cho kiểm tra parser này.

Bằng chứng local nằm trong
`.workbench/acceptance/bundled-kaggle-2026-10-09/`: `evidence.json`,
`completed-after-restart.png`, `backend.log` và backup config trước chuyển.
File QA trong project được giữ để user mở lại; dữ liệu `.workbench` không commit.

QA này kiểm chứng CPU bootstrap/SSH/thu file/STOP của bản đóng gói; không
chạy lại GPU, TPU, auto-login hết hạn hoặc toàn bộ tính năng MVP2.


## Chuyển sang backend CLI trực tiếp

Theo yêu cầu user, backend quản lý Kaggle trực tiếp, agent chỉ dùng terminal
SSH đã mở. Không còn MCP server, MCP tool hoặc vòng initialize/list_tools/
call_tool. Hai thao tác start/idle đã thành action CLI nội bộ; khóa request ID,
submit intent, resume cùng session, TTL, thu file/hash và STOP được giữ nguyên.
CLI thừa hưởng các biến OS/SSH/browser cần thiết và port proxy đã cấu hình;
không thừa hưởng token/API key provider từ môi trường backend.

Health trả `kaggle_backend: cli`. Lệnh khởi động backend và config `donor_*`
hiện có giữ nguyên. Legacy submission helper không được gắn vào app;
response decoder lịch sử còn lại không import hoặc khởi động MCP.

### QA CLI ngày 2026-10-09

Qua GUI tạo idea **CPU — backend CLI trực tiếp**, gọi Codex CLI lập proposal
`2427e060bbb7492e89ac8cf93abd80fb`, duyệt và chạy đúng một phiên CPU TTL 600 giây.
Run `e35fe0e1a34148d6b129fb45fcdbc7f7`, cùng project QA ở trên, **COMPLETED**.

- Bootstrap SDK và SSH qua CLI trực tiếp. Agent chạy 2 lệnh, tính tổng bình
  phương 1…1000 bằng thư viện chuẩn: `333833500`, `verified=true`, Linux,
  Python 3.13.15, tính trong `0.000089584` giây.
- Thu script 1017 bytes và JSON 238 bytes, tổng 1255 bytes; hash cả hai
  khớp manifest. Đối chiếu lại phép tính và hash bằng local Python.
- STOP xác nhận `complete`, `stopped=true` lúc
  `2026-10-09T13:07:56.511333+00:00`; idle CLI xác nhận 0 phiên đang chạy.
- SSH ghi `known_hosts` đúng trong `.runtime/.../<run_id>/`, không tạo file
  nhầm ở root. Backend shutdown đóng cả port 8011 và proxy 8013; restart
  vẫn đọc run/output/log và health trả `kaggle_backend=cli`.
- Không có tiến trình MCP của bundle. Kiểm thử adapter CLI, Working/idle,
  restart và các API bị ảnh hưởng đã qua; fixture cũ được đồng bộ với cwd
  workspace và tùy chọn report mặc định tắt của MVP2. `pip check` qua.

Bằng chứng local: `.workbench/acceptance/kaggle-cli-2026-10-09/`, gồm
`evidence.json`, `completed-after-restart.png`, `backend.log`. QA không chạy
GPU/TPU hoặc thử cookie hết hạn; các cơ chế đó dùng lại từ lõi donor.
