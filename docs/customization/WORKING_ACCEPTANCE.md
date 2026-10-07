# Nghiệm thu Working MVP0 — 2026-10-07

## Kết luận và phạm vi

Luồng Working hiện hành đã đi hết qua GUI: nhập idea, lập proposal bằng Codex thật,
duyệt, mở Kaggle, agent viết/chạy code qua SSH, thu files/report và xác nhận Kaggle dừng.
Đã restart backend thật và mở lại kết quả qua GUI; không gọi lại agent hoặc submit.

Đây là nghiệm thu tác vụ tổng quát **CPU, Python stdlib, dữ liệu synthetic**. Không dùng
lượt này để tuyên bố training/finetune, GPU/TPU hoặc dữ liệu ngoài đã đạt trên Working.
Training của MVP0 cũ đã nghiệm thu riêng trong `MVP0_RUN_GUIDE.md` và T09 của plan.
Không chứng minh target tổng thời gian triển khai dưới 8 giờ.

## Hành trình thực tế

| Mục | Bằng chứng |
| --- | --- |
| Project | `MVP0 Working — nghiệm thu SSH`, `829d4582bcd840cc85d38c8fc2efccbd` |
| Idea | `CSV synthetic trên Kaggle`, `a4904ecceaed4d4989dfac8449c77dd3` |
| Proposal | `e705717b7a9a4920b3c97f9cff4b4b6f`, v1; không nguồn, split/metric/checkpoint bắt buộc |
| Run thành công | `abb8c794372545208ef2f59028330995` |
| Notebook riêng tư | `huynhtrungcuong/ai-scientist-ssh-abb8c7943725`, version 1, kernel 137471750 |
| Phần cứng/thời hạn | CPU; 600 giây, đã chọn tại GUI |
| Agent | Codex CLI thật, `gpt-6-luna`, effort `max`; 1 lượt Working |
| Remote work | 8 lệnh qua terminal SSH hiện có; source do agent viết, không sửa workload bằng tay |
| Bắt đầu | 2026-10-07 10:32:38 UTC |
| Xác nhận dừng | 2026-10-07 10:39:53 UTC; khoảng 7 phút 15 giây, trong TTL |
| Kết quả app/Kaggle | `COMPLETED` / `complete`, `stop_confirmed=true` |

Từ màn hình Run, có thể chọn **Tạo lượt Working mới** để tham khảo kết quả hiện có.
Lượt mới chỉ bắt đầu khi user bấm Working. Ba lượt chẩn đoán thất bại được giữ nguyên
với report và bằng chứng dừng; không sửa trạng thái cũ để tạo thành công.

## Dữ liệu và đối chiếu độc lập

Agent dùng `random.Random(42)`: id 1…1000; x1, x2 uniform(-1,1);
y = 3*x1 − 2*x2 + Gaussian noise(0,0.05).

Đọc CSV đã thu ở local và đối chiếu độc lập, không thực thi source của agent:

- Đúng header `id,x1,x2,y`, 1.000 dòng, ID đúng 1…1000, không missing.
- Tất cả giá trị khớp seed/công thức ở tolerance 1e-12.
- Min/max/mean đọc lại khớp `summary.json` ở tolerance 1e-12.
- Source chỉ import thư viện chuẩn; proof ghi cwd `/kaggle/working/ai-scientist/<run_id>`,
  Python 3.13.15 và executable `/usr/bin/python3`, không ghi toàn bộ environment.
- Backend kiểm byte count/SHA256 của 4 file; file tải qua artifact endpoint khớp bytes.

| Cột | Min | Max | Mean |
| --- | ---: | ---: | ---: |
| x1 | -0.999188120605425 | 0.9998156570184185 | 0.015520165980168426 |
| x2 | -0.9986481369757916 | 0.9991448337549027 | -0.013336582792399293 |
| y | -4.76967495676853 | 4.646614911567232 | 0.0724143239363649 |

| File | Bytes | SHA256 |
| --- | ---: | --- |
| `source/generate_data.py` | 2581 | `bab8ddd0d64cdf90961feea340d9c48a3741620b7472d3428b7378b7e338fc2d` |
| `output/synthetic.csv` | 62777 | `7e49e9cf1d628cee6bd31b68981b027a93b80aee4c00dfb32fda88474c5312f1` |
| `output/summary.json` | 513 | `9e07b8bcd28cd879251668c884ceb31a1d78a2a8d100a07e3e43c1c2ebbe455b` |
| `output/execution_proof.json` | 247 | `43ab666252507ddbba75d3e396784d1d75a81f30188ce3b2cbaf36ad71639369` |

Tổng source/output 66.118 bytes, dưới ngân sách 2 MB của idea. Không train, cài package
hoặc upload dataset public trong lượt này.

## Restart và dữ liệu lưu

Sau khi hoàn tất, backend đã được khởi động lại. GUI vẫn mở đúng run/report và log.

- 9 artifact files/links giữ nguyên; hash trên disk không đổi.
- 1.762 log records, cursor `1:1762`, tổng 78.851 ký tự không đổi.
- `agent_called=1`, `command_count=8`, tổng 4 run của project không đổi.
- Runtime state vẫn completed cho đúng Working request; submission intent/receipt
  donor không đổi. Log startup chỉ có ListTools, không có gọi tool tạo notebook.
- Markdown endpoint chuẩn hóa CRLF thành LF; nội dung report giữ nguyên.

Kết quả lưu tại:

`D:/Documents/AI-Scientist-v2/.workbench/projects/829d4582bcd840cc85d38c8fc2efccbd/runs/abb8c794372545208ef2f59028330995/`

Report: `report.md`; bằng chứng file: `working-manifest.json`; bằng chứng dừng:
`working-stop.json`; journal: `journal.json`.

Bằng chứng kiểm tra và screenshot local nằm trong
`D:/Documents/AI-Scientist-v2/.workbench/acceptance/working-2026-10-07/`:
`before-restart.json`, `after-restart.json`, `artifact-hashes.json`,
`donor-submit-hashes.json`, `04-completed.jpg`, `06-report-proof.jpg`.
Các file local và credential không được đưa vào Git.

## Lỗi tích hợp đã xử lý

| Lỗi | Nguyên nhân / bản sửa | Bằng chứng |
| --- | --- | --- |
| UNKNOWN lịch sử chặn duyệt dù reference không đọc được | Token không đủ quyền đọc notebook cũ. Đọc account idle bằng tool hiện có, kiểm đúng account và count=0, giữ UNKNOWN cũ | `3939372`; 21 focused tests |
| SSH thoát 255 không thông báo | Environment mặc định của MCP thiếu `PROGRAMDATA`; Win32 OpenSSH cần biến này. Chỉ truyền lại biến cần thiết | `ffbe905`; 24 focused tests và `ssh -V` trên environment đã sửa |
| Working response bị lồng sai JSON | Runtime và task cùng mô tả envelope; chuyển Working sang native CLI output schema, adapter tạo RuntimeResult một lần | `600547b`; 24 focused tests và payload thật đọc được |
| Mọi lệnh CLI bị policy chặn | `--ignore-user-config` bỏ cả `windows.sandbox="elevated"`; backend chưa truyền lại. Chọn rõ sandbox Windows, giữ workspace-write | `c29806b`; thử A/B local: cùng lệnh đọc file bị chặn / thành công; 10 tests; 8 lệnh Kaggle thật |

Ba run lỗi `546f22c5…`, `c1eff55d…`, `8ba72624…` đều có `stopped=true` và Kaggle
status `complete`. Không gửi lại notebook của những run đó.

Thiết lập Windows dựa trên [hướng dẫn sandbox chính thức](https://learn.chatgpt.com/docs/windows/windows-sandbox).
Không nới sandbox ra toàn máy để xử lý lỗi quyền.

Sau các bản sửa, toàn bộ `tests/workbench` đạt **112 passed** (59,08 giây).
Một lượt trước đó của test HTTP local gặp WinError 10053; chạy lại nguyên tập SSH
không đổi assertion đạt 10/10, và suite cuối đạt đầy đủ. Không thay assertion hoặc
bỏ test để tạo kết quả xanh.
