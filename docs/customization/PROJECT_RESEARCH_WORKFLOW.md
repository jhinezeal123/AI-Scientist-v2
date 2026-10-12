# Một luồng nghiên cứu cho mỗi project

## Sử dụng

1. **Library:** thêm nguồn và chọn **Nguồn mặc định của project**. Lựa chọn lưu ngay trên backend.
2. **Workflow:** chọn human/agent, preset cho từng stage, benchmark, đầu ra và giới hạn. **Lưu cấu hình project** lưu mặc định và chuẩn bị một lượt nghiên cứu; chưa chạy agent hay Kaggle.
3. **Idea:** nhập/lưu idea, dùng nguồn mặc định hoặc chọn nguồn riêng. **Lập proposal và tiếp tục workflow** dùng cấu hình project đã lưu và đưa chính idea này vào n8n.
4. **Idea:** trao đổi và duyệt proposal tại đây. Tin nhắn yêu cầu phiên bản mới. Agent cần làm rõ thì không thể duyệt; backend cũng kiểm tra điều kiện này.
5. **Run:** kiểm tra cấu hình đã ghim rồi duyệt bắt đầu. Agent mới được thực hiện thí nghiệm sau bước này, trừ khi bạn đã chọn Full agent và giao quyền chạy trong cấu hình.

Workflow hiển thị tiến độ và đưa bạn tới Idea/Run khi cần thao tác. Nó không có form Idea/Proposal/Run riêng trên máy chủ.

## Điểm bắt đầu

- **Nghiên cứu mới:** human nhập/lưu/chọn idea ở Idea; agent sinh và đánh giá ứng viên theo preset của project.
- **Idea có sẵn:** dùng chính bản ghi đó cùng nguồn, mode, benchmark và đầu ra riêng của idea.
- **Kết quả của run trước:** agent sinh biến thể dựa trên kết quả; với human, mở run cha và tạo Improve, rồi chọn idea biến thể để tiếp tục. Baseline của run cha được ghim trong context.

## Lưu và kế thừa

- Mặc định lưu trong bảng `project_configuration` của `project.sqlite`, tại `.workbench/projects/<tên project>`.
- Nguồn riêng của idea lưu trong `idea_context`; phiên bản context đầy đủ vẫn được giữ trên từng proposal.
- Cấu hình có phiên bản; các workflow grant và run đã duyệt giữ scope, nguồn và preset đã ghim. Đổi mặc định áp dụng cho công việc mới.
- Dữ liệu cũ được giữ. Mặc định của project được khởi tạo một lần từ grant n8n gần nhất; grant Team cũ không được dùng làm mặc định.
- Khi project chưa có cấu hình workflow, đường lập proposal thủ công cũ vẫn dùng được để tương thích.
- Remote điều khiển cùng grant và các bước chờ qua API có scope; không lưu một cấu hình nghiên cứu riêng cho thiết bị.

## Trách nhiệm code

- `ProjectConfiguration`: lưu mặc định, nguồn riêng và quy tắc kế thừa.
- `ProjectWorkflowControls`: nối thao tác Idea/Run với human gate của workflow đang sở hữu bản ghi.
- `WorkflowStore`: giao dịch lưu grant, human input và phiên bản proposal.
- `N8nResearchWorkflows`: cầu nối n8n; thứ tự stage và callback dùng workflow hiện có.
- `useProjectWorkflow`: đọc cùng trạng thái cho các tab và khôi phục CSRF từ phiên đăng nhập đã lưu.

## Kiểm chứng thay đổi

Tests bao phủ lưu nguồn qua khởi động lại, scope project, dùng lại idea, kế thừa baseline, proposal clarification và run admission. QA giao diện sử dụng API thật với n8n/provider/Kaggle mô phỏng; không chạy nghiên cứu hoặc training thật cho lần thay đổi này.
