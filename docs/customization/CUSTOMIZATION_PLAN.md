# Custom AI Scientist/v2 — nền tảng và kế hoạch tích hợp

Ngày: **2026-10-06**, Asia/Saigon.
User đã chọn fork AI Scientist/v2 và custom trực tiếp.

**Roadmap chính:** [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) — MVP 0 prototype đến MVP 7 team.
**Nhu cầu:** [DESIGN_BRIEF.md](DESIGN_BRIEF.md).
**Plan triển khai MVP 0:** [IMPLEMENT_MVP0.md](IMPLEMENT_MVP0.md) — stack và 9 task nghiệm thu.
Tài liệu này chỉ mô tả nền tảng/code cần custom; không thay các cửa nghiệm thu của roadmap.

## 1. Trạng thái thật

- Fork: [jhinezeal123/AI-Scientist-v2](https://github.com/jhinezeal123/AI-Scientist-v2).
- Upstream: [SakanaAI/AI-Scientist-v2](https://github.com/SakanaAI/AI-Scientist-v2).
- Checkout: D:/Documents/AI-Scientist-v2; branch codex/personal-implementation-agent.
- Baseline: 96bd51617cfdbb494a9fc283af00fe090edfae48; origin/upstream đã cấu hình.
- Đã tạo fork/branch và tài liệu. Chưa triển khai hoặc nghiệm thu MVP 0.
- Docs hiện ở local, chưa commit/push. Repo Kaggle giữ code/credentials tại D:/Documents/kaggle_token.

## 2. Giữ lõi nào của upstream

| Phần | Trách nhiệm trong sản phẩm custom | Chặng chủ yếu |
| --- | --- | --- |
| ai_scientist/treesearch/journal.py | Node/plan/code/parent, execution evidence, metric và artifact refs | MVP 0–3 |
| ai_scientist/treesearch/agent_manager.py | Stage và budget khi mở rộng research; MVP 0 chưa khởi động manager stock | MVP 2–3 |
| ai_scientist/treesearch/parallel_agent.py | Draft/debug/feedback khi mở rộng; MVP 0 dùng service mỏng với approval trước code | MVP 2, 5 |
| ai_scientist/treesearch/interpreter.py | Giữ cho local execution khi cần; Kaggle có execution adapter riêng | MVP 0–2 |
| Summary/plots | Phân tích bằng chứng và báo cáo, không bắt full paper pipeline | MVP 0–4 |
| ai_scientist/perform_ideation_temp_free.py | Ideathon tùy chọn, không tự cấp quyền coder/run | MVP 6 |

Journal và SQLite của app có cùng project/run identity và một nguồn trạng thái.
Không dùng hai database/scheduler độc lập rồi bắt user đồng bộ thủ công.
MVP 0 thêm entrypoint workbench và dùng Node/Journal nguyên bản; không rewrite launcher stock
hoặc khởi động toàn bộ BFTS pipeline. Chi tiết đường chạy tối thiểu nằm trong IMPLEMENT_MVP0.md.
Prompt thêm dataset/synthetic phải theo Library và scope đã duyệt.
Metric/split không tự đổi trong vòng tối ưu. User duyệt proposal trước code ở mọi harness.

## 3. Nguồn tái sử dụng từ repo Kaggle

Các đường dẫn sau tương đối với D:/Documents/kaggle_token; chưa được tích hợp trong fork.

| Nguồn | Phần cần dùng | Kiểm trước khi chuyển |
| --- | --- | --- |
| agent_platform/ports/agent_runtime.py; agent_platform/infrastructure/agent_runtime.py | AgentRuntime/CodexCliRuntime cho harness đầu tiên | Dependency slice, structured output, progress và cancel |
| mcp_server.py; kaggle_pool.py | MCP Kaggle/account/session | V0 có thể chạy MCP server từ repo cũ, không cần chuyển cả pool ngay |
| agent_platform/infrastructure/kaggle_notebook_env.py | Metadata/status/log/artifact patterns | Competition mount, exact identity, cursor/replay và collection thật |
| agent_platform storage/frontend | Library/project/history và GUI | Reuse phần nhỏ đủ flow; không đưa nguyên platform vào fork |

Giữ provenance/license khi copy/adapt. Credentials ở config local, không mang vào prompt/Library/repository.

## 4. Cách bắt đầu MVP 0

1. CP0-A: kiểm Codex/MCP/account/competition readiness, Library và proposal-only path.
2. CP0-B: approval version → coder → notebook/checks → submit thật trước mốc 3.75h mục tiêu.
3. CP0-C: collector/cursor, terminal result, artifact/metric và report.
4. CP0-D: restart/history/no-duplicate, hướng dẫn GUI và nghiệm thu đủ P0-01…P0-08.

MVP 0 là prototype. Vòng simple implementation đã chạy trước, sau đó mới mở nhiều run,
retrieval, harness thứ hai và Ideathon theo MVP 1–6. Team chỉ sau CP-PERSONAL.

Refactor chỉ làm khi cần và kiểm chứng giữ hành vi trước khi đổi behavior.
Không chạy mọi worker/stage/model dependency upstream để chứng minh prototype.
Các hạng mục, scope, deliverables, demo và acceptance từng MVP đều ở
[PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md); trạng thái thực cập nhật tại đó.
