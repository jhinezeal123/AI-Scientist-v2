# Một luồng nghiên cứu cho mỗi project

## Sử dụng

1. **Library:** thêm nguồn và chọn **Nguồn mặc định của project**. Lựa chọn lưu ngay trên backend.
2. **Run:** mở **Cấu hình Run mặc định của project** để chọn loại công việc, benchmark/đầu ra, account, phần cứng, thời hạn, budget và experiment manager. Lưu tại đây; chưa chạy agent hay Kaggle.
3. **Workflow:** chọn human/agent, preset cho từng stage, số vòng và giới hạn lượt agent. **Lưu cấu hình Workflow** ghép phần điều phối với cấu hình Run và Library đã lưu, chuẩn bị một lượt nghiên cứu.
4. **Idea:** nhập/lưu idea, dùng nguồn mặc định hoặc chọn nguồn riêng. **Lập proposal và tiếp tục workflow** dùng cấu hình project đã lưu và đưa chính idea này vào n8n.
5. **Idea:** trao đổi và duyệt proposal tại đây. Tin nhắn yêu cầu phiên bản mới. Agent cần làm rõ thì không thể duyệt; backend cũng kiểm tra điều kiện này.
6. **Run:** kiểm tra cấu hình đã ghim rồi duyệt bắt đầu. Agent mới được thực hiện thí nghiệm sau bước này, trừ khi bạn đã chọn Full agent và giao quyền chạy trong cấu hình.

Workflow hiển thị tiến độ và đưa bạn tới Idea/Run khi cần thao tác. Nó không có form Idea/Proposal/Run riêng trên máy chủ.

## Điểm bắt đầu

- **Nghiên cứu mới:** human nhập/lưu/chọn idea ở Idea; agent sinh và đánh giá ứng viên theo preset của project.
- **Idea có sẵn:** dùng chính bản ghi đó cùng nguồn, mode, benchmark và đầu ra riêng của idea.
- **Kết quả của run trước:** agent sinh biến thể dựa trên kết quả; với human, mở run cha và tạo Improve, rồi chọn idea biến thể để tiếp tục. Baseline của run cha được ghim trong context.

## Lưu và kế thừa

- Mặc định lưu trong bảng `project_configuration` của `project.sqlite`, tại `.workbench/projects/<tên project>`.
- Nguồn riêng của idea lưu trong `idea_context`; phiên bản context đầy đủ vẫn được giữ trên từng proposal.
- Cấu hình có phiên bản; phần `run` lưu độc lập với phần `workflow`. Workflow chỉ đọc cấu hình Run và không ghi đè nó. Các grant và run đã duyệt giữ scope, nguồn và preset đã ghim. Đổi mặc định áp dụng cho công việc mới.
- Dữ liệu cũ được giữ. Mặc định của project được khởi tạo một lần từ grant n8n gần nhất; grant Team cũ không được dùng làm mặc định.
- Khi project chưa có cấu hình workflow, đường lập proposal thủ công cũ vẫn dùng được để tương thích.
- Remote điều khiển cùng grant và các bước chờ qua API có scope; không lưu một cấu hình nghiên cứu riêng cho thiết bị.

## Trách nhiệm code

- `ProjectConfiguration`: lưu mặc định, nguồn riêng và quy tắc kế thừa.
- `RunConfiguration`: hợp đồng và kiểm tra budget cho cấu hình do Run quản lý. `ProjectRunConfiguration` là giao diện sở hữu việc chỉnh/lưu phần này; Workflow chỉ hiển thị tóm tắt và liên kết tới Run.
- `ProjectWorkflowControls`: nối thao tác Idea/Run với human gate của workflow đang sở hữu bản ghi.
- `WorkflowStore`: giao dịch lưu grant, human input và phiên bản proposal.
- `N8nResearchWorkflows`: cầu nối n8n; thứ tự stage và callback dùng workflow hiện có.
- `useProjectWorkflow`: đọc cùng trạng thái cho các tab và khôi phục CSRF từ phiên đăng nhập đã lưu.

## Kiểm chứng thay đổi

Tests bao phủ lưu nguồn qua khởi động lại, scope project, dùng lại idea, kế thừa baseline, proposal clarification và run admission. QA giao diện sử dụng API thật với n8n/provider/Kaggle mô phỏng; không chạy nghiên cứu hoặc training thật cho lần thay đổi này.
