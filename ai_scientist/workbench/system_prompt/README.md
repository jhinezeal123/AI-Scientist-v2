# Cấu hình prompt planner và Working

Sửa trực tiếp các file UTF-8 trong thư mục này. Backend nạp prompt theo alias mỗi
lần sử dụng, không cache nội dung: thay đổi áp dụng cho lượt agent tiếp theo,
không cần restart backend sau khi tính năng này đã được nạp.

| Alias trong backend | File gốc | Vai trò |
| --- | --- | --- |
| `planner.training_research` | `planner_training_research.md` | Proposal nghiên cứu với bốn stage hiện có |
| `planner.etc` | `planner_etc.md` | Proposal triển khai trực tiếp theo đầu ra user mô tả |
| `working.agent` | `working_agent.md` | Prompt trực tiếp gửi cho Codex CLI |
| `working.instructions` | `working_instructions.md` | Hướng dẫn được lưu vào `working-request.json` |
| `working.etc` | `working_etc.md` | Prompt hoàn chỉnh cho Working Etc trực tiếp, không cây/report nghiên cứu |
| `search.node` | `search_node.md` | Tạo/chạy node Tree Search |
| `search.node_instructions` | `search_node_instructions.md` | Hướng dẫn thực hiện node |
| `search.query` | `search_query.md` | Đọc kết quả của node |
| `search.stage_goals` | `search_stage_goals.json` | Mục tiêu bốn stage |

`aliases.json` ánh xạ alias sang đường dẫn file tương đối trong thư mục này.
Muốn dùng bản prompt khác, sửa tên file trong ánh xạ. Backend vẫn gọi cùng alias.

## Cách sửa

- Hai file planner chứa prompt hoàn chỉnh cho từng mode; backend chọn alias từ
  snapshot của idea. Giữ `{{ready_schema}}` và `{{context}}` để chèn schema và
  context gồm đường dẫn Library, mode và đầu ra nguyên gốc. Không ghép prompt
  research vào Etc.
- `working_etc.md` là prompt riêng hoàn chỉnh của Etc. Giữ `{{workdir}}`; phần
  context nằm trong `working-request.json` gồm proposal/mode/đầu ra đã duyệt và
  terminal helper. Etc không nạp `working.instructions` hoặc prompt Tree Search.
- `working_agent.md` gồm cả lời nhắc đọc yêu cầu và thực hiện công việc. Giữ biến
  `{{workdir}}` để agent nhận thư mục của run. Biến chưa được cung cấp sẽ báo lỗi.
- Trong `working_instructions.md`, mỗi đoạn cách nhau bằng một dòng trống sẽ trở
  thành một phần tử của `instructions`. File chứa đúng nội dung gửi cho agent;
  đừng thêm ghi chú quản trị vào file prompt.
- File được đọc theo UTF-8; hỗ trợ BOM và xuống dòng CRLF của Windows.
- Giữ hướng dẫn trả JSON khớp `WorkingPayload` (`succeeded`, `summary`,
  `limitations`, `output_files`). Schema phản hồi vẫn được định nghĩa trong
  `models.py`; sửa prompt không đổi schema đó.
- File thiếu, rỗng hoặc biến không hợp lệ được báo trước khi mở phiên Kaggle mới.

Proposal vẫn là ngữ cảnh riêng do người dùng duyệt. Sửa prompt không sửa mode,
mô tả đầu ra hoặc hash của các proposal/run đã lưu.
