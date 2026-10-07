# Cấu hình prompt Working

Sửa trực tiếp các file UTF-8 trong thư mục này. Backend nạp prompt theo alias mỗi
lần sử dụng, không cache nội dung: thay đổi áp dụng cho lượt Working tiếp theo,
không cần restart backend sau khi tính năng này đã được nạp.

| Alias trong backend | File gốc | Vai trò |
| --- | --- | --- |
| `working.agent` | `working_agent.md` | Prompt trực tiếp gửi cho Codex CLI |
| `working.instructions` | `working_instructions.md` | Hướng dẫn được lưu vào `working-request.json` |
| `working.task` | `working_task.md` | Lời nhắc đọc yêu cầu và thực hiện công việc |

`aliases.json` ánh xạ alias sang đường dẫn file tương đối trong thư mục này.
Muốn dùng bản prompt khác, sửa tên file trong ánh xạ. Backend vẫn gọi cùng alias.

## Cách sửa

- `working_agent.md` có hai biến `{{workdir}}` và `{{task_prompt}}`; giữ chúng để
  agent nhận thư mục của run và lời nhắc tương ứng. Biến chưa được cung cấp sẽ báo lỗi.
- Trong `working_instructions.md`, mỗi đoạn cách nhau bằng một dòng trống sẽ trở
  thành một phần tử của `instructions`. File chứa đúng nội dung gửi cho agent;
  đừng thêm ghi chú quản trị vào file prompt.
- File được đọc theo UTF-8; hỗ trợ BOM và xuống dòng CRLF của Windows.
- Giữ hướng dẫn trả JSON khớp `WorkingPayload` (`succeeded`, `summary`,
  `limitations`, `output_files`). Schema phản hồi vẫn được định nghĩa trong
  `models.py`; sửa prompt không đổi schema đó.
- File thiếu, rỗng hoặc biến không hợp lệ được báo trước khi mở phiên Kaggle mới.

Proposal vẫn là ngữ cảnh riêng do người dùng duyệt. Nội dung prompt mặc định được
giữ nguyên khi chuyển từ chuỗi trong Python sang các file này.
