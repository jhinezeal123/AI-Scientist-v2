# Một luồng nghiên cứu cho mỗi project

## Sử dụng

1. **Library:** thêm nguồn và chọn **Nguồn mặc định của project**. Lựa chọn lưu ngay trên backend.
2. **Workflow:** chọn human/agent, preset cho từng stage, số vòng và giới hạn lượt agent. Hybrid có thể lưu trước khi chọn account hoặc môi trường chạy.
3. **Idea:** nhập/lưu mục tiêu, loại công việc, benchmark và đầu ra mong muốn; dùng nguồn mặc định hoặc chọn nguồn riêng. Đây là nơi duy nhất chỉnh các lựa chọn khoa học này.
4. **Idea:** **Lập proposal và tiếp tục workflow** đưa chính idea đã chọn cùng phạm vi của nó vào n8n. Agent mô tả kế hoạch, chiến lược thí nghiệm, budget và yêu cầu phần cứng nếu có.
5. **Idea:** trao đổi và duyệt proposal tại đây. Tin nhắn yêu cầu phiên bản mới. Agent cần làm rõ thì không thể duyệt; backend cũng kiểm tra điều kiện này.
6. **Run:** mở run vừa tạo, chọn account, accelerator và thời hạn phiên tại **Cấu hình và chạy**. Budget và experiment manager nằm trong phần nâng cao. **Duyệt và chạy** ghim môi trường riêng của run, hoàn tất đúng human gate và cho n8n tiếp tục.

**Môi trường mặc định** trong Run chỉ điền sẵn lựa chọn cho run mới. Có thể bỏ qua trong Hybrid hoặc chọn **Dùng cấu hình này làm mặc định cho run mới** khi lưu hoặc chạy. Các run đã tạo giữ cấu hình riêng, kể cả khi bạn đổi mặc định.

Với **Full agent**, chọn một idea đã lưu rồi bấm **Dùng idea đang chọn làm phạm vi Full agent** trong Idea. Lưu môi trường mặc định trong Run trước khi giao quyền chạy tự động. Workflow chép phạm vi khoa học và môi trường đã cấp vào grant; thay đổi mặc định sau đó không sửa grant này.

Nếu phần cứng không phù hợp yêu cầu của proposal, budget vượt phạm vi đã duyệt hoặc chiến lược experiment manager thay đổi, **Lập lại proposal với cấu hình này** hủy run chưa bắt đầu, giữ proposal cũ làm lịch sử, rồi mở một lượt Hybrid mới với yêu cầu cấu hình mới. Proposal mới phải được duyệt trước khi chạy. Với run đã mở phiên, dùng Improve sau khi phiên kết thúc.

Workflow hiển thị tiến độ và đưa bạn tới Idea/Run khi cần thao tác. Nó không có form Idea/Proposal/Run riêng trên máy chủ.

## Điểm bắt đầu

- **Nghiên cứu mới:** human nhập/lưu/chọn idea ở Idea; agent sinh và đánh giá ứng viên theo preset của project.
- **Idea có sẵn:** dùng chính bản ghi đó cùng nguồn, mode, benchmark và đầu ra riêng của idea.
- **Kết quả của run trước:** agent sinh biến thể dựa trên kết quả; với human, mở run cha và tạo Improve, rồi chọn idea biến thể để tiếp tục. Baseline của run cha được ghim trong context.

## Lưu và kế thừa

- Mặc định lưu trong bảng `project_configuration` của `project.sqlite`, tại `.workbench/projects/<tên project>`.
- Nguồn riêng của idea lưu trong `idea_context`; phiên bản context đầy đủ vẫn được giữ trên từng proposal.
- Cấu hình có phiên bản; `idea` giữ phạm vi khoa học, `run` giữ mặc định môi trường, `workflow` giữ người thực hiện/preset/giới hạn điều phối.
- Mỗi run có bản ghi `run_execution_configuration` với phiên bản và dấu kiểm chứng cấu hình đã duyệt. Cấu hình được khởi tạo khi tạo run, lưu trong database của chính project; không lấy lại mặc định khi refresh trang.
- Các grant và run đã duyệt giữ scope, nguồn và preset đã ghim. Đổi mặc định áp dụng cho công việc mới. Grant cũ giữ hợp đồng admission cũ; các workflow mới dùng cấu hình riêng từng run.
- Dữ liệu cũ được giữ. Mặc định của project được khởi tạo một lần từ grant n8n gần nhất; grant Team cũ không được dùng làm mặc định.
- Khi project chưa có cấu hình workflow, đường lập proposal thủ công cũ vẫn dùng được để tương thích.
- Remote điều khiển cùng grant và các bước chờ qua API có scope; không lưu một cấu hình nghiên cứu riêng cho thiết bị.

## Trách nhiệm code

- `ProjectConfiguration`: lưu mặc định, nguồn riêng và quy tắc kế thừa.
- `IdeaConfiguration`: phạm vi cho idea mới và ideation được ủy quyền. Các đầu ra khoa học chỉnh trong Idea.
- `RunConfiguration`: hợp đồng môi trường thực thi, không chứa mode/benchmark/đầu ra khoa học.
- `RunExecutionConfigurations`: cấu hình, phiên bản, kiểm tra phạm vi và snapshot đã duyệt của từng run.
- `RunAdmission`: nối cùng cấu hình Run với thao tác thủ công hoặc human gate của n8n. Việc ghim cấu hình và hoàn tất gate diễn ra trong cùng giao dịch.
- `RunConfigurationEditor` và `RunExecutionFields`: một form dùng cho từng run; batch và môi trường mặc định dùng cùng bộ trường môi trường.
- `ProjectWorkflowControls`: nối thao tác Idea/Run với human gate của workflow đang sở hữu bản ghi.
- `WorkflowStore`: giao dịch lưu grant, human input và phiên bản proposal.
- `N8nResearchWorkflows`: cầu nối n8n; thứ tự stage và callback dùng workflow hiện có.
- `useProjectWorkflow`: đọc cùng trạng thái cho các tab và khôi phục CSRF từ phiên đăng nhập đã lưu.

## Kiểm chứng thay đổi

Tests bao phủ lưu nguồn qua khởi động lại, scope project, dùng lại idea, kế thừa baseline, proposal clarification, run admission và chuyển dữ liệu cũ. Tests dùng provider/Kaggle mô phỏng. QA giao diện dùng backend cục bộ thật để lưu cấu hình và kiểm tra qua refresh; không chạy nghiên cứu hoặc training thật cho lần thay đổi này.
