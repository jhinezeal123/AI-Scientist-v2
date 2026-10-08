# M1-03 — Tạo idea biến thể từ kết quả đã lưu

Ngày: 2026-10-08. Trạng thái: đã nghiệm thu local, 2026-10-08; M1-04 chưa nghiệm thu.
Tham chiếu: IMPLEMENT_MVP1.md / CP1-C, PRODUCT_ROADMAP.md / P1-05.

## 1. Đích đến và phạm vi

Người dùng mở một run đã kết thúc, nhập tiêu đề, mục đích mới và thay đổi,
tạo một idea mới có quan hệ với run cha. Sau đó họ chọn nguồn, trao đổi, lập
proposal và duyệt phạm vi mới trước khi chủ động bấm Working. Kết quả mới
được lưu vào đúng project/run. Code, proposal, approval và artifacts của run
cha giữ nguyên. Luồng áp dụng cho công việc tổng quát, không giới hạn training.

M1-03 bàn giao local trên localhost:8011. Nghiệm thu browser toàn luồng dùng
runtime/MCP/SSH giả lập trong workspace riêng. Không gọi Codex trả phí, không
mở phiên Kaggle mới. Chạy biến thể thật và nghiệm thu toàn MVP1 thuộc M1-04.
Không thêm OCR/RAG, harness nhiều agent, History tab, gate notebook cũ hay hạn
mức số lượt. Không thay đổi chính sách xóa dữ liệu trong task này.

## 2. Luồng GUI

1. Trong chi tiết run, thêm nút **Tạo biến thể idea**. Nút có thể dùng khi run
   đã kết thúc: COMPLETED, FAILED, CANCELLED, REMOTE_SUCCEEDED, REMOTE_FAILED.
   Với Working SSH phải có stop_confirmed; UNKNOWN, COLLECTING và run đang
   hoạt động cần kết thúc/đối soát trước. Run đã xóa không được dùng làm đầu vào.
2. Mở form trong trang hiện tại: **Tiêu đề** (tối đa 80 ký tự), **Mục đích mới**,
   **Thay đổi so với run gốc**. Ba ô bắt buộc, trim và không chấp nhận chỉ dấu cách.
   Cho thấy run cha/mục tiêu cũ làm tham khảo. Không tự tạo idea chỉ vì mở form.
3. Bấm **Lưu idea biến thể** tạo đúng một idea DRAFT mới cùng project; chuyển
   sang tab Idea, chọn idea mới. Không tự gọi planner, không tạo run hay Working.
   Chặn bấm lặp trong lúc gửi. Backend dùng request_id để lặp cùng yêu cầu không
   tạo trùng; reuse ID cho parent/body khác phải báo conflict.
4. Chọn trước những nguồn cha đã dùng còn tồn tại. Proposal mới ghim version
   hiện hành khi người dùng yêu cầu lập. Nếu version đổi hoặc nguồn thiếu, GUI
   chỉ rõ và yêu cầu người dùng kiểm tra lựa chọn trước khi lập proposal.
   Không tự khôi phục nguồn đã bị xóa hay sửa snapshot cũ.
5. Idea/proposal hiển thị run cha, mục đích và thay đổi. Lập proposal dùng
   PlanningService hiện có, clarification/answer/approval hiện có. Không sao
   chép approval hoặc body proposal cũ để coi biến thể là đã được duyệt.
6. Duyệt proposal mới tạo run mới. Run mới hiển thị quan hệ biến thể, mục đích
   và thay đổi; bấm vào run cha mở đúng run trong cùng project. Working chỉ
   bắt đầu khi người dùng bấm nút hiện có sau approval.
7. Reload/restart giữ lineage, trao đổi và approval. Đổi project không lẫn dữ liệu.

**Tạo lượt Working mới** hiện có vẫn dùng cùng proposal đã duyệt (retry).
**Tạo biến thể idea** yêu cầu proposal/approval mới. UI/API phải thể hiện hai
quan hệ riêng; không thay ý nghĩa parent_run_id của retry hoặc khiến retry
của một variant mất lineage về baseline gốc.

## 3. Dữ liệu, baseline và context cho agent

- Lưu lineage bền vững gồm project, idea mới, parent run/proposal, purpose,
  change summary, created_at và request_id. Dùng cơ chế SQLite/JSON hiện có;
  migration idempotent, tương thích project cũ. Backend xác minh ownership,
  eligibility và trạng thái xóa trong transaction, không tin đường dẫn từ client.
- Lưu metadata provenance baseline tại lúc tạo: mục tiêu/proposal cha, các
  nguồn/version/hash đã ghim, kết quả thực tế đã lưu nếu có, và tham chiếu
  artifacts hữu ích kèm hash. Không ghi đè bảng/file cha để tạo con.
- Planner phải biết đây là biến thể, mục đích mới và thay đổi. Cho agent đường
  dẫn bản tham khảo đã stage gồm report và code text phù hợp nếu cha có,
  thay vì đưa toàn bộ code/log/artifacts vào prompt. Working nhận cùng lineage
  đã ghim trong approval, có baseline text để tham khảo; không dùng session
  hoặc credentials cũ. Tận dụng staging/workdir/gateway hiện có.
- Baseline chỉ lấy từ các file được backend cho phép đọc (saved artifacts /
  collection manifest); kiểm tra path, symlink/junction và SHA256. Không copy
  working-agent/terminal-access.json, endpoint gateway, token, DB hay arbitrary
  client path. Không scan cả thư mục run hoặc gửi binary dataset/checkpoint
  vào prompt. Code/report quá lớn hoặc thiếu phải ghi rõ là không cấp được,
  vẫn có thể tạo biến thể dựa trên metadata. Dùng giới hạn hiện có hoặc một
  giới hạn nhỏ rõ ràng (tối đa 1 MiB baseline text tổng cộng), không tạo framework.
- Hash và lineage phải thuộc context snapshot/hash được duyệt. Sau approval
  không đọc metadata mutable mới để thay phạm vi. Nếu baseline đã ghim bị thay
  file/corrupt thì báo lỗi trước agent/Kaggle, không âm thầm thay bằng bản mới.
  Việc source Library bị xóa vẫn theo hành vi hiện có.
- Report mới (backend Working report) nêu project/run mới, run cha, purpose
  và change summary; các link report/artifacts dùng ID của run mới. Summary
  dựa trên output được xác minh. Hoàn tất vẫn cần xác nhận Kaggle đã dừng.
- Lineage của con không biến mất khi parent được ẩn bởi tính năng xóa hiện có;
  link có thông báo phù hợp hoặc yêu cầu khôi phục. Không tự khôi phục parent.

## 4. Tổ chức triển khai theo pattern-design

1. Đọc skill và code liên quan. Ghi ngắn các phần chịu trách nhiệm: persistence,
   baseline staging, planner/Working coordination, API, GUI. Chọn giải pháp đơn
   giản, không dựng abstraction/framework cho một use case.
2. Refactor tối thiểu thật sự cần để thêm lineage/baseline, bảo toàn hành vi.
   Chạy các test hiện có sát phần đổi, phải xanh trước behavior. Commit riêng
   structural change. Không tạo refactor giả hay sửa phần không liên quan;
   nếu không cần refactor, giải thích bằng evidence trước phase behavior.
3. Implement behavior trong diff/commit riêng; không squash hai phase. Giữ
   proposal/approval gate, stop confirmation, project isolation, retry cũ.
4. Build UI, kiểm thử browser, sửa lỗi cần thiết. Cập nhật IMPLEMENT_MVP1.md
   và spec với trạng thái/bằng chứng chính xác. Commit task với prefix branch
   hiện có, push origin nếu không gặp conflict; không sửa commit MVP0/M1-02.

## 5. Checklist nghiệm thu

- [x] Browser mở run đã kết thúc, tạo biến thể bằng form; đúng title/purpose/changes.
- [x] Tạo variant chỉ thêm DRAFT idea; không planner call, không run/session mới.
- [x] Lập proposal mới thấy lineage và baseline file references, không full logs
      hoặc library contents trong prompt; agent fixture thực sự đọc baseline file.
- [x] Browser trả lời clarification, reload/restart, tiếp tục proposal; dữ liệu còn.
- [x] Working trước approval bị backend chặn; approval tạo đúng run mới, repeat
      approval trả cùng run; browser phải bấm Working riêng.
- [x] Browser Working giả lập đi qua request, SSH command/file collection,
      report, stop confirmation; report/artifact link đúng project/run mới.
- [x] Code/report/hash/source snapshots của parent trước/sau không đổi.
- [x] Replay request không tạo duplicate; đổi body khi reuse `request_id` và
      cross-project bị từ chối; unapproved/active/UNKNOWN/ineligible parent được
      chặn bởi backend. Thay parent cùng `request_id` không có route UI riêng.
- [x] Source cha đổi version hiển thị cảnh báo/review; proposal mới ghim version;
      snapshot cha không đổi. Variant dùng được khi parent không có code/report.
- [x] Browser fixture đã đi nhánh nguồn cha bị xóa: run cha `8077a3b8…` vẫn giữ
      snapshot nguồn `5c51b0b2…`; variant mới `1f9a3c51…` hiện đúng cảnh báo
      “Fixture source document: đã bị xóa; không tự khôi phục”. Planner bị khóa
      trước review. Sau khi thêm/chọn `Fixture replacement document` v1 và review,
      planner được mở; proposal v2 `cf9c64ae…` ở `AWAITING_APPROVAL`. Snapshot và
      `data_refs` chỉ có replacement `eea0aa48…`, không có nguồn đã xóa; lineage
      baseline cha vẫn giữ ID nguồn cha cùng hash đã ghim. Xóa chỉ dữ liệu fixture
      (6 file, khoảng 1.3 KB), không xóa project thật.
- [x] Correction tổng quát baseline: dùng manifest đã lưu để stage
      `source/generate_data.py` đã xác minh, kèm hash/nội dung; assertion nằm
      trong `test_variants.py`, thuộc targeted suite 34 passed.
- [x] Correction tài nguyên: Library stage giữ streaming iterator, Working
      bỏ lần stage Library lặp trước SSH; các test Library/Working trong suite
      targeted 34 passed.
- [x] Correction state UI: form biến thể reset khi đổi run; chọn lại DRAFT
      variant không có proposal lấy lại parent sources còn tồn tại. UI build
      xanh; browser surface trống nên chưa có browser readback cho hai hành vi.
- [x] Retry cũ vẫn dùng cùng proposal; variant/retry lineage không lẫn.
- [x] Parent hidden và project switch/reload không làm mất lineage hay nhầm links.
- [x] Targeted existing tests green; UI build green. Không có structural
      refactor cần kiểm chứng; chỉ thêm invariant transaction/ownership/hash/
      approval khó quan sát browser; không chạy full suite lặp lại.
- [x] Backend thật 8011 hoạt động với build mới; chỉ kiểm tra đọc trên dữ liệu
      người dùng. Workspace fixture/process/tab được dọn sau khi lưu evidence.
- [x] Không có Codex/Kaggle thật phát sinh; report ghi rõ fake vs live phạm vi.

Ghi chú evidence: counters và parent-hash JSON được lưu trong
`.workbench/acceptance/m1-03-variants-2026-10-08/`. Journey source-deletion có
evidence đã lưu: [source-deleted-warning.png](../../.workbench/acceptance/m1-03-variants-2026-10-08/source-deleted-warning.png),
[replacement-proposal.png](../../.workbench/acceptance/m1-03-variants-2026-10-08/replacement-proposal.png),
[source-deleted-proposal-dom.txt](../../.workbench/acceptance/m1-03-variants-2026-10-08/source-deleted-proposal-dom.txt)
và JSON kiểm tra snapshot/hash/counters tại
`.workbench/acceptance/m1-03-variants-2026-10-08/source-deleted-acceptance.json`.

Browser dùng mcp__cua_repl; đọc skill computer-use và tài liệu API trước thao
tác. Fixture 8012/workspace acceptance riêng được phép, tái dùng fixture M1-02
nếu phù hợp. Không click xóa dữ liệu người dùng để kiểm thử. Lưu vài ảnh chứng
minh các mốc quan trọng và log/counters provider giả lập.

## 6. Quy tắc delegation và chống lặp bug

Worker duy nhất dùng gpt-6-luna, max effort, không tự spawn thêm agent. Gửi
progress ngắn khoảng mỗi phút và khi hoàn tất phase, nêu giá trị đã dùng được,
không chỉ nêu số file. Orchestrator chờ trong thời gian worker làm việc.

Nếu cùng một bug đã thử sửa/kiểm tra hai lần liên tiếp mà không có tiến triển:
**dừng xử lý bug**, gửi orchestrator: expected/actual, bước tái hiện, command
và log lỗi (đã bỏ secrets), hai lần đã thử, files thay đổi, bằng chứng/hypothesis
và chỗ cần quyết định. Không nới assertion, xóa test hoặc lặp lần ba. Chờ plan
fix từ orchestrator rồi mới tiếp tục. Không che lỗi bằng fallback coi là thành công.

## 7. Báo cáo bàn giao cho orchestrator

Gửi checklist pass/fail kèm evidence; commit hash và diff theo phase; test/build
đã chạy thực tế; ảnh browser theo absolute path; provider call counters; hash
parent trước/sau; health backend; hạn chế còn lại. Orchestrator review cuối bằng
read-only commands; nếu cần sửa sẽ giao lại worker. Không claim M1-04 hoàn tất.
