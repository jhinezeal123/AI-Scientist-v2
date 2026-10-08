# Library theo project và dọn idea/run

## Nguồn thật trên ổ đĩa

Nguồn được lưu tại:

`D:\Documents\AI-Scientist-v2\.workbench\projects\<tên project>\library\<tiêu đề nguồn>\v<version>\source.md`

Tên trên GUI khớp với tên thư mục. Ví dụ:

`D:\Documents\AI-Scientist-v2\.workbench\projects\Soil Grain Size MVP0\library\Soil competition — rules\v1\source.md`

Giữ dấu tiếng Việt và khoảng trắng. Các ký tự Windows cấm (`<>:"/\|?*`) được
đổi thành `_`; tên được giới hạn 120 ký tự. Nếu trùng tên trong cùng thư mục,
thêm `(2)`, `(3)`… và GUI hiển thị đúng tên đó. Khi sửa tiêu đề nguồn, thư mục
đổi theo; các phiên bản và snapshot đã duyệt giữ nguyên nội dung và hash.

Backend chuyển thư mục ID cũ sang tên khi khởi động. ID vẫn là khóa nội bộ của
API/database; không dùng làm tên thư mục. File ẩn `.resource.json` ghi ID và
các tên cũ để tìm đúng nguồn cho proposal đã lưu. Không sửa file này thủ công.

Mỗi file gồm tiêu đề, URL, trạng thái và nội dung đã cung cấp. URL chưa được tải
vẫn được ghi rõ là reference, không được xem là tài liệu đã đọc. Nguồn hiện có
được tạo file khi backend nâng cấp. Mỗi lần **Sửa nguồn → Lưu nguồn** tạo phiên
bản mới; phiên bản cũ được giữ để các proposal/run đã duyệt đọc đúng nội dung.
Sửa nội dung qua Library để giữ phiên bản và hash nhất quán.

Context chỉ chứa metadata: ID, tiêu đề, URL, trạng thái, phiên bản, hash và
`file_path`. Không còn chèn toàn bộ nội dung tài liệu vào prompt.

- Planner nhận bản sao các nguồn được chọn trong workspace riêng, có thể tìm
  bằng `rg` và đọc file khi cần. Planner chỉ đọc tài liệu, lập proposal và hỏi
  thông tin còn thiếu.
- Working nhận đúng phiên bản đã duyệt trong `library/` ở cả workspace riêng và
  thư mục làm việc trên Kaggle. Backend chuyển file qua SSH hiện có; agent đọc
  tài liệu trên Kaggle qua `terminal.py`.
- Tài liệu là dữ liệu tham khảo, không phải lệnh hệ thống. Không đưa credentials
  của account vào Library.
- Snapshot cũ đã duyệt giữ nguyên; khi thực hiện lại, backend chuyển phần nguồn
  cũ thành file đúng phiên bản để agent đọc.

## Câu hỏi và proposal

Khi Codex cần làm rõ, GUI chỉ hiện câu hỏi. Một câu hỏi hiện như hội thoại bình
thường; nhiều câu hỏi được đánh số. Đoạn diễn giải mục tiêu được giữ cho proposal
đã sẵn sàng, không lặp lại trước phần hỏi.

## Xóa và khôi phục

Mở chi tiết idea/run, bấm **Xóa idea** hoặc **Xóa run**. Mục đó được đưa vào
**Đã xóa**. Bấm card trong mục này để khôi phục.

Việc xóa khỏi danh sách giữ lại proposal, snapshot, logs và artifacts trên ổ đĩa;
không xóa notebook trên Kaggle. Xóa idea không tự xóa các run của nó. Run đang
hoạt động hoặc chưa xác nhận dừng phải được dừng/đối soát trước khi xóa. Run đã
xóa không được bắt đầu Working hoặc tạo lượt mới cho đến khi khôi phục.
