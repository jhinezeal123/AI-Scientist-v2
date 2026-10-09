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
- `mcp_server.py`: chỉ cung cấp `kaggle_ssh_start`, `workbench_account_idle`.

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
Cả MCP và CLI SSH dùng chung Python của Workbench. Proxy riêng chạy trên
`127.0.0.1:8013`, kiểm tra đúng tên dịch vụ và thư mục root trước khi dùng.
MCP sở hữu vòng đời proxy; backend không còn tự khởi động proxy legacy port 80.
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

Backend tự khởi động MCP và proxy. Không cần mở một MCP thứ hai. Sau khi
di chuyển repo sang máy/thư mục khác, cập nhật đường dẫn config và cấu hình
credential local; source không phụ thuộc checkout `D:/Documents/kaggle_token`.
Phiên cũ tạo ở donor bên ngoài vẫn giữ private state ở đó; các run đã dừng
và artifact trong project tiếp tục đọc được.

## QA ngày 2026-10-09

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
