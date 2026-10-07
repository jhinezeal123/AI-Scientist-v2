# Kaggle qua Tailcat + SSH: bản thử độc lập

Codex ở máy local. Code, terminal và dữ liệu ở Kaggle. Notebook chỉ khởi động một
SSH server có thời hạn; trong cùng session có thể sửa/chạy code nhiều lần.

Đã thử trên Windows x64 → Kaggle Linux CPU ngày **2026-10-07**.
[Kết quả và giới hạn](D:/Documents/AI-Scientist-v2/docs/customization/KAGGLE_TAILCAT_EXPERIMENT.md)

## Chuẩn bị

- Chạy từ `D:\Documents\AI-Scientist-v2`.
- Dùng Python của donor: `D:\Documents\kaggle_token\.venv\Scripts\python.exe`.
  Môi trường thử có `kagglesdk==0.1.37` và `cryptography==50.0.2`.
- Có OpenSSH `ssh` và `scp` trong PATH.
- Config `.workbench/config.local.json` hiện chọn account `huynhtrungcuong`.
- Account cần có Internet cho notebook và quyền đọc competition Soil.

Script tải Tailcat **v0.7.0** cho Windows và Linux, kiểm SHA-256 của archive.
Proxy account được dùng lại ở port 80; nếu chưa có, script chạy riêng `proxy.py`
của donor ở nền. Không cần khởi động MCP server để dùng các lệnh bên dưới.

## Thử một lượt mới

```powershell
$pocPython = 'D:\Documents\kaggle_token\.venv\Scripts\python.exe'

& $pocPython tools/kaggle_tailcat/poc.py prepare
& $pocPython tools/kaggle_tailcat/poc.py push
& $pocPython tools/kaggle_tailcat/poc.py connect
& $pocPython tools/kaggle_tailcat/poc.py probe
& $pocPython tools/kaggle_tailcat/poc.py shell
```

| Lệnh | Làm gì? |
|---|---|
| `prepare` | Tạo run ID, khóa riêng cho lượt này, notebook và metadata. Chưa submit. |
| `push` | SDK gửi notebook private CPU một lần qua proxy với token của account đã chọn. |
| `connect` | Chờ SSH tối đa 240 giây và đọc thông tin môi trường remote. |
| `probe` | Upload Python, kiểm mount/schema Soil, tạo 50 dòng synthetic data, lấy output/log qua SFTP và kiểm hash source. |
| `shell` | Mở terminal Bash trong thư mục làm việc của lượt này trên Kaggle. |

Trong Bash remote, có thể xem kết quả:

```bash
ls
cat result.json
tail -n 4 probe.log
python3 probe.py
exit
```

`exit` chỉ đóng terminal. Khi làm xong, chạy ở PowerShell local:

```powershell
& $pocPython tools/kaggle_tailcat/poc.py stop
```

Lệnh này tạo marker qua SSH để bootstrap đóng server và kết thúc notebook bình thường.
TTL mặc định 480 giây, timeout notebook 570 giây; đây là giới hạn của bản thử CPU.

Một lệnh remote riêng lẻ hoặc kiểm đường truyền:

```powershell
& $pocPython tools/kaggle_tailcat/poc.py ssh --command 'ls /kaggle/input/competitions/soil-grain-size-from-photos'
& $pocPython tools/kaggle_tailcat/poc.py network
```

`network` có thể báo không đạt đường direct sau 10 giây trong khi SSH qua DERP vẫn dùng được.

## State và lỗi

- Mỗi lượt có thư mục `.workbench/tailcat-poc/<run_id>/`; `latest.json` chọn lượt mới nhất.
- Có thể chọn rõ một lượt bằng `--state <đường_dẫn_state.json>`.
- State và notebook sinh ra có khóa tunnel tạm thời. Giữ trong `.workbench`, notebook private;
  SSH private key và token Kaggle không được gửi vào notebook.
- Dừng lượt đang dùng trước khi chuẩn bị lượt kế tiếp. `prepare` tạo một lượt mới và cập nhật pointer.
- `push` ghi submit intent trước khi gửi. Nếu mất phản hồi, không bấm gửi lại cùng lượt;
  kiểm notebook/session trên Kaggle hoặc qua control plane hiện tại.
- Khi SSH mất kết nối, TTL vẫn kết thúc bootstrap. Có thể cần nút Stop trên Kaggle hoặc
  API dự phòng để dừng sớm; `stop` qua SSH không hoạt động khi tunnel chưa lên/đã mất.
- Kiểm status bằng endpoint của SDK 0.1.37 trả 404 trong lần thử. Bản này không cung cấp
  lệnh status dựa trên endpoint đó. Kết quả nghiệm thu được xác minh bằng MCP cũ.

Đây là prototype riêng; GUI workbench hiện tại chưa chuyển sang execution backend này.
