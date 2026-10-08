# Design Brief — General Implementation Agent

Ngày: **2026-10-06**, Asia/Saigon. Phiên bản: **3**.
Nguồn quyết định: câu trả lời trực tiếp của người dùng trong chat.
Trạng thái: **brief xác định nhu cầu và phạm vi; chưa phải nghiệm thu sản phẩm**.

Quyết định nền tảng mới của user: **fork AI Scientist/v2 và custom trực tiếp**.
Repo phát triển: [jhinezeal123/AI-Scientist-v2](https://github.com/jhinezeal123/AI-Scientist-v2).
Roadmap chính: [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md).
Nền tảng/tích hợp: [CUSTOMIZATION_PLAN.md](CUSTOMIZATION_PLAN.md).
Repo kaggle_token trở thành nguồn tái sử dụng Codex/Kaggle và tài liệu nghiên cứu.

## 1. Đích đến

Xây một General Implementation Agent dùng local, giúp người dùng chuyển idea thành
implementation có thể chạy, kiểm tra và báo cáo. Người dùng tập trung vào lý thuyết,
ý tưởng và quyết định nghiên cứu; sản phẩm xử lý công việc triển khai sau khi proposal được duyệt.

Dùng cá nhân trước. Sau khi bản cá nhân có giá trị thực tế, mở rộng thành workspace cho team 3–4 người.
Kaggle là môi trường thực thi đầu tiên. Thiết kế nghiệp vụ phải cho phép dùng lại với workshop,
paper hoặc chủ đề nghiên cứu khác.

**Mốc đầu tiên: một hành trình chạy thật từ GUI tới kết quả Kaggle trong dưới 8 giờ triển khai.**

## 2. Người dùng và vấn đề

Người dùng đầu tiên là sinh viên khoa học máy tính, quan tâm ML/AI/CV và lý thuyết.
Git và terminal ở mức sử dụng được; cần codebase đọc hiểu và bảo trì được cùng agent.

Các vấn đề cần giải quyết:

- Code thử một idea quá lâu, hạn chế số giải pháp có thể khảo sát.
- Implementation có bug, sai ý tưởng hoặc mắc lỗi cơ bản như data leakage.
- Khi nghiên cứu paper, phải giải thích lại context cho AI qua nhiều phiên.
- Phải chuyển test/code giữa AI, notebook và môi trường chạy bằng tay.
- Khó theo dõi mục đích, trạng thái, kết quả và lịch sử các thí nghiệm.

## 3. Kết quả có giá trị

| Mục tiêu | Dấu hiệu quan sát được |
| --- | --- |
| Tiết kiệm thời gian | Đo thời gian idea → proposal → code → kết quả; so với một công việc tương tự trước đây |
| Giảm thao tác | Sau nhập context/idea và duyệt proposal, không phải copy code/test hoặc upload notebook bằng tay |
| Implementation đúng ý tưởng hơn | Proposal diễn giải lại idea; implementation và checks đối chiếu với proposal đã duyệt |
| Hạn chế data leakage | Split và preprocessing được mô tả trước; checks kiểm các rủi ro cụ thể của dataset |
| Giữ kết quả | Idea, proposal, notebook, run identity, logs, metrics và report được lưu cùng project |
| Tái lập | Lưu nguồn dữ liệu, split, config/seed, dependency và phiên bản code đủ để chạy lại phạm vi đã hỗ trợ |

Chưa có số liệu baseline để cam kết mức tiết kiệm theo phần trăm. Thu số liệu từ lần dùng đầu tiên.
Checks giảm các lỗi đã xác định; không tuyên bố tự động bảo đảm mọi implementation đều đúng.

## 4. Hành trình và quyền quyết định

1. Người dùng tạo project và nhập đề bài, quy tắc, nguồn dữ liệu, paper hoặc baseline vào Library.
2. Người dùng nhập idea trong GUI.
3. Agent đọc context từ Library, diễn giải lại idea và hỏi khi còn mơ hồ hoặc thiếu thông tin thiết yếu.
4. Agent đưa proposal: mục tiêu, cách làm, dữ liệu/split, đánh giá, checks, tài nguyên và outputs dự kiến.
5. **Người dùng duyệt proposal trước khi agent viết code.**
6. Agent triển khai, kiểm tra và sửa lỗi trong phạm vi đã duyệt; đóng gói notebook.
7. App chạy notebook qua MCP Kaggle, theo dõi và thu kết quả.
8. Agent đọc bằng chứng chạy thật, báo cáo kết quả và lưu vào lịch sử project.

Approval gắn với phiên bản proposal và context. Đổi ý tưởng, split, đánh giá hoặc phạm vi tài nguyên
cần duyệt lại. Sửa bug trong phạm vi đã duyệt được tự động hóa có giới hạn.

Một approval có thể bao gồm quyền chạy một thí nghiệm Kaggle miễn phí đã mô tả trong proposal.
Không bắt người dùng duyệt lại mỗi thao tác kỹ thuật nhỏ trong phạm vi đó.
Agent không tự duyệt proposal hoặc tự mở rộng chi phí/phạm vi.

Việc nghĩ idea mặc định thuộc người dùng. Ideathon chỉ hoạt động khi người dùng bật.

## 5. Phạm vi theo lần bàn giao

**Cập nhật MVP2, 2026-10-08:** mỗi project dùng chung Library cho hai mode
Training/Research và Etc. Training/Research tái sử dụng tối đa pipeline gốc;
Etc không Tree Search, user bắt buộc mô tả đầu ra, phần kết quả của run là
Output và lưu tại `project/output/`, cùng cấp `library/` và `experiment/`.
User có thể copy kết quả Etc thành nguồn Library độc lập. Mode được ghim
trong idea/proposal/run; đổi mode trên GUI không đổi lịch sử hoặc phiên đang
chạy. Spec và task theo feature: [IMPLEMENT_MVP2.md](IMPLEMENT_MVP2.md).

| Chặng | Khả năng dùng được sau bàn giao |
| --- | --- |
| MVP 0 — Prototype <8 giờ | Library text/URL → idea/proposal → approval → Codex → notebook Kaggle thật → report/history qua GUI |
| MVP 1 — Workbench cá nhân | Nhiều project, Library PDF/file/source version, context và discussion/history qua nhiều phiên |
| MVP 2 — Implementation tổng quát | Training/Research gốc và Etc linh hoạt; Output → Library, scope/approval và kết quả bền vững |
| MVP 3 — Quản lý thí nghiệm | Nhiều run/account, status/live curves/ETA, queue/cancel/recovery, compare và tối ưu MCP/logs |
| MVP 4 — Retrieval/RAG | Tìm source/run bằng ngôn ngữ tự nhiên, evidence refs và context cho proposal mới |
| MVP 5 — Đa harness | Codex và harness thứ hai thật qua cùng AgentPort/GUI/approval/history |
| MVP 6 — Cá nhân hoàn chỉnh | IdeathonPort/HumanAdapter/AgentAdapter toggle, backup/restore/rerun và vận hành cá nhân đầy đủ |
| MVP 7 — Team 3–4 | Shared Library/project, identity/grants/attribution, phối hợp và shared resource control |

MVP 0 là prototype; bản cá nhân hoàn chỉnh chốt tại CP-PERSONAL sau MVP 6.
Bản team chốt tại CP-TEAM sau MVP 7. Chi tiết bài toán được giải quyết, checkpoint,
deliverables và tiêu chí từng MVP: [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md).

URL lưu trong Library phải phân biệt đã đọc nội dung và chỉ có metadata.
Agent không được coi việc lưu link là đã hiểu nội dung nguồn.
Dataset lớn lưu bằng reference/version/path; không sao chép toàn bộ data vào SQLite.

Notion/W&B, full checkpoint transfer và runtime API/ACP matrix từ kế hoạch trước không chặn V0.
Giữ workflow/journal hữu ích của upstream; custom theo nhu cầu sử dụng thực tế.

## 6. Yêu cầu kỹ thuật và tổ chức code

**Nền tảng:** fork Python AI Scientist/v2, giữ experiment workflow/journal làm lõi.
Python/FastAPI, React, SQLite và files local từ repo kaggle_token là nguồn tái sử dụng,
không mặc định chuyển toàn bộ platform sang fork. Đích đến là một app local và một scheduler.
GUI là cửa sử dụng hằng ngày. CLI phục vụ phát triển/chẩn đoán; product MCP không phải gate V0.

Library là một khả năng của project/workspace trong bản custom. Database mỗi project lưu context, ý tưởng, proposals,
requests, runs và liên kết artifacts. Files lớn nằm ngoài DB, có metadata/ref trong project.
Lịch sử của mỗi run cần nối được tới mục đích, proposal, source/context, account và kết quả.

**AgentPort:** một boundary nhỏ nhận context/task, trả progress/result/files và hỗ trợ hủy.
Repo kaggle_token đã có AgentRuntime và CodexCliRuntime; đánh giá chuyển contract/adapter đó
sang fork thay vì tạo hai abstraction trùng nhau. Chưa coi adapter đã được tích hợp trong fork.
Tên AgentPort mô tả trách nhiệm mong muốn, không bắt buộc đổi tên hàng loạt trong code.
Codex là adapter thật đầu tiên; Claude Code hoặc harness DeepSeek được thêm khi có nhu cầu và
cách gọi đã kiểm chứng. Không tạo adapter rỗng hoặc framework plugin tổng quát.

**IdeathonPort:** trách nhiệm riêng, xuất idea cùng nguồn Human/Agent.
Triển khai khi bắt đầu tính năng Ideathon. Toggle mặc định tắt; bật Ideathon không cấp quyền tự code/run.
Idea được chọn vẫn đi qua proposal và human approval.

**Retrieval:** bắt đầu bằng metadata/filter và text search, thêm SQLite FTS khi phù hợp.
RAG là truy xuất context liên quan rồi cung cấp cho agent cùng nguồn; không bắt buộc dùng vector DB.
MVP 4 cần nhận truy vấn như tìm run đã thử một idea, dùng một split hoặc đạt một kết quả cụ thể,
trả evidence refs để người dùng mở lại. Có thể chuyển yêu cầu thành filters/text matching có giới hạn.
Embedding/reranking chỉ thêm khi các truy vấn thực tế chứng minh nhu cầu, dùng tài nguyên sẵn có.

**MCP Kaggle:** adapter thực thi gọi MCP hiện có; dùng lại kaggle_pool và cơ chế account/session.
Bổ sung tool còn thiếu cho collection hoặc delta một cách nhỏ, giữ tương thích tool cũ.
Không xây lại account manager hoặc lách các kiểm tra dữ liệu/quyền để chạy notebook.

Code nghiệp vụ, UI, persistence và I/O vendor có trách nhiệm rõ. Tên và flow phải dễ đọc.
Không thêm microservices, broker, database server, agent fleet hoặc tầng abstraction không có nhu cầu.
Refactor chỉ khi cần cho luồng chính; tách refactor khỏi thay đổi hành vi.

## 7. Logs, tốc độ và tính đúng

- GUI đọc cache local; thao tác upstream chạy nền, có trạng thái và lỗi.
- Lưu account/ref/version/session của đúng run; không resolve lại mơ hồ ở mỗi lần lấy log.
- Log API/MCP mới nhận cursor và trả entries mới/next cursor; giữ các dòng giống nhau xuất hiện hợp lệ.
- Collector/cache dùng chung cho cùng run, tránh mỗi refresh mở stream/pull toàn bộ lịch sử.
- Khi restart/reconnect, cursor/generation và khoảng thiếu được xử lý rõ, không mất hoặc nhân đôi log.
- Có thể reuse cursor/delta logic trong platform nhưng phải kiểm chứng transport thực tế.
- Nếu upstream chỉ cung cấp replay snapshot, delta phía GUI/MCP chưa chứng minh giảm bytes upstream.
  Khi đó dùng cache, polling có giới hạn hoặc stream dài nếu provider hỗ trợ; báo đúng giới hạn.
- ETA chỉ hiển thị khi có tổng bước và tốc độ đo được; trường hợp thiếu dữ liệu ghi chưa đủ thông tin.

## 8. Bài nghiệm thu và tài nguyên

Bài nghiệm thu:
[Predicting Soil Grain Size Distributions from Images](https://www.kaggle.com/competitions/soil-grain-size-from-photos).

Nguồn user cung cấp: 7 account Kaggle của team với quyền dùng hợp lệ, credentials trong
D:\Documents\kaggle_token, và Codex CLI. V0 chỉ cần một account được chọn và kiểm readiness.
Không cần đưa token vào prompt/Library/report hoặc kiểm thử cả 7 account để chứng minh V0.

Ngày 2026-10-06 đã mở overview/evaluation/data/rules bằng web reader nhưng chưa lấy được nội dung
các trang động. Chưa xác minh metric chính thức, dataset schema, grouping, rules acceptance hoặc
quyền mount của account. Xác minh sớm bằng phiên/account được phép hoặc nội dung được nhập vào Library.
Không đoán metric, quy tắc split, leaderboard score hay khả năng truy cập dữ liệu.

V0 dùng dữ liệu thật của bài nghiệm thu, phạm vi nhỏ ghi rõ để chạy nhanh.
Kiểm split disjoint và fit preprocessing trên train; nếu dữ liệu có nhiều ảnh cùng mẫu thì kiểm
grouping trước chọn split. Không dùng dữ liệu giả để tuyên bố đã chạy cuộc thi thật.
Không đòi hỏi mô hình tốt nhất, cải thiện điểm hoặc submit leaderboard để đạt V0.

## 9. Ngân sách, thời gian và nguồn lực

- Không có ngân sách mua thêm hạ tầng/dịch vụ; dùng máy local, các account/quota và Codex hiện có.
- User đã cho phép kiểm thử bằng Codex CLI theo quyền sử dụng sẵn có.
- Không tự mua subscription, thuê compute hoặc chuyển sang endpoint tính phí mới.
- Quota/rate limit/runtime vẫn được tôn trọng; hết resource thì nêu action, không chạy vòng lặp vô hạn.
- Developer/bảo trì: người dùng và assistant. Codebase tinh gọn, dễ hiểu được ưu tiên.
- Mốc đầu tiên **<8 giờ** là mục tiêu MVP 0, không phải hoàn tất MVP 1–6 hoặc MVP 7 team.
- Tính cả việc kiểm readiness và chờ run trong kế hoạch. Login/rules/data access/provider queue là
  rủi ro thời gian phải kiểm sớm; blocker thật không được thay bằng mock hoặc claim thành công.
- Chưa chốt deadline bản cá nhân hoàn chỉnh/team; các khoảng giờ trong roadmap là dự toán cần rà lại sau prototype.

## 10. Tiêu chí đạt MVP 0 — prototype

| ID | Tiêu chí nghiệm thu |
| --- | --- |
| P0-01 | GUI lưu project Library có đề bài và nguồn data; context đọc lại sau restart, agent dùng đúng nguồn |
| P0-02 | Idea mơ hồ tạo câu hỏi/diễn giải; proposal chưa được duyệt thì không gọi coder, tạo implementation hoặc submit |
| P0-03 | Sau human approval, Codex CLI thật tạo notebook/implementation bám proposal; checks cơ bản đạt |
| P0-04 | Notebook chạy thật qua MCP Kaggle trên dữ liệu bài nghiệm thu; giữ đúng account/version/session và terminal result |
| P0-05 | Logs xem được trong GUI; gọi tiếp cursor chỉ nhận phần mới, không nhân đôi/mất dòng; polling không chặn UI |
| P0-06 | Kết quả/artifacts và báo cáo lấy từ run thật; demo training ghi metric theo step/epoch và vẽ curve, scope ghi rõ |
| P0-07 | Lưu idea → proposal → notebook → run → report trong project; restart giữ lịch sử và không tự submit trùng |
| P0-08 | Người dùng đi hết flow bằng GUI và hướng dẫn ngắn, không chuyển code/test/upload notebook bằng tay sau setup |

MVP 0 đạt khi tất cả tiêu chí trên có kết quả thực tế. Notebook tồn tại hoặc proposal thành công
chưa chứng minh run thành công. Training thất bại có thể tạo báo cáo chẩn đoán nhưng không đạt case chạy thành công.

## 11. Kiểm chứng tương xứng và bước tiếp theo

Dùng tests/checks tập trung: approval-before-code, context đúng project, split/preprocessing,
log cursor, submit không lặp và kết quả báo cáo. Chạy build và regression chịu tác động.
Một end-to-end thật bằng Codex/Kaggle có thể cung cấp bằng chứng cho nhiều tiêu chí, tránh lặp
model/provider traffic chỉ để tăng số test. Không xây hệ thống receipt mới hoặc benchmark toàn diện cho V0.

Không cần sửa mọi vấn đề team/integration không liên quan trước khi đi hết hành trình cá nhân.
Lỗi mất dữ liệu, sai idea, lộ credential, submit trùng hoặc báo kết quả sai vẫn là lỗi chặn hành trình.

User đã chọn fork AI Scientist/v2 làm nền tảng, custom workflow/journal cùng
Codex CLI, MCP Kaggle và GUI/Library theo nhu cầu cá nhân.
Checkpoint và trạng thái: [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md).
Kế hoạch tích hợp: [CUSTOMIZATION_PLAN.md](CUSTOMIZATION_PLAN.md).
Mục tiêu cùng 8 tiêu chí MVP không đổi. Chưa bật Ideathon tự động hoặc mở scope team.
Tài liệu nghiên cứu chi tiết được giữ trong checkout kaggle_token; các kết luận cũ về
tiếp tục phát triển trên kaggle_token đã được thay bằng quyết định fork.
