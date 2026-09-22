# Thiết kế — Scheduler thu thập hằng ngày trên Web

**Ngày:** 2026-09-22
**Trạng thái:** Chờ người dùng duyệt để triển khai

## Mục tiêu

Thay thao tác CLI vận hành hằng ngày bằng giao diện web: người dùng có thể chạy ngay một lượt thu thập Top Free iOS Việt Nam, bật/tắt lịch tự động mỗi ngày lúc 07:00 theo múi giờ Việt Nam (`Asia/Ho_Chi_Minh`), và xem trạng thái trên Dashboard.

Phạm vi ban đầu chỉ là **Top Free VN**. Không cấu hình Windows Task Scheduler, không crawl Top Grossing, và không thay đổi pipeline collect → analyze hiện hữu.

## Kiến trúc

Khi `casual_scout serve` chạy, FastAPI tạo một scheduler nền trong cùng process. Scheduler so sánh thời gian hiện tại ở `Asia/Ho_Chi_Minh` với lịch 07:00, tạo một run `scheduled` tối đa một lần mỗi ngày và dùng launcher hiện hữu để chạy collect → analyze.

Cấu hình lịch (`enabled`, `time`, `country`, `chart_type`) và ngày đã kích hoạt gần nhất được lưu trong SQLite. Scheduler đọc cấu hình sau startup, vì vậy trạng thái bật/tắt được giữ qua restart server. Scheduler không chạy bù khi server hoặc máy tắt vào 07:00; Dashboard hiển thị lần chạy thành công gần nhất để dữ liệu cũ không bị hiểu nhầm là dữ liệu mới.

Khóa collector hiện tại là cơ chế chống trùng lặp. Nếu có run đang active, scheduler và nút chạy ngay không tạo run thứ hai.

## Giao diện và API

Dashboard có thẻ **Thu thập dữ liệu** gồm nút `Crawl ngay`, trạng thái run gần nhất/đang chạy, số game hợp lệ và thời điểm thành công gần nhất. Nút này tạo run Top Free VN, sau đó hiển thị tiến độ bằng cơ chế trạng thái run hiện có.

Thẻ **Lịch tự động** hiển thị `Mỗi ngày 07:00 (UTC+7)`, công tắc bật/tắt và ghi chú rằng web server phải chạy liên tục. Công tắc dùng endpoint có CSRF; thay đổi có hiệu lực cho lần kế tiếp, không can thiệp run đang chạy.

Các endpoint đề xuất:

- `GET /api/schedule`: cấu hình lịch và trạng thái chạy gần nhất.
- `PATCH /api/schedule`: bật/tắt lịch, chỉ nhận cấu hình đã hỗ trợ.
- `POST /runs`: tiếp tục là endpoint tạo run thủ công; mở rộng để cố định Top Free VN từ Dashboard.

`/runs` vẫn là nơi xem log, lỗi và lịch sử chi tiết.

## Xử lý lỗi

Nếu collect hoặc analyze thất bại, run được ghi trạng thái lỗi/partial theo pipeline hiện hữu. Scheduler ghi nhận lần đã kích hoạt để không lặp vô hạn trong cùng ngày và sẽ thử lại vào ngày kế tiếp. Lỗi không được che giấu; Dashboard dẫn người dùng tới `/runs`.

## Kiểm thử nghiệm thu

- Đến 07:00 UTC+7, khi lịch bật và không có run active, scheduler tạo đúng một run Top Free VN.
- Scheduler không tạo run thứ hai trong cùng ngày hoặc khi collector đang khóa.
- Tắt lịch ngăn run tự động; restart app vẫn giữ lựa chọn bật/tắt.
- Nút `Crawl ngay` tạo run Top Free VN và trả trạng thái có thể quan sát.
- Lịch không chạy bù sau khi startup ngoài giờ 07:00.

## Giới hạn vận hành

Scheduler nằm trong web process, vì vậy chỉ hoạt động khi `serve` còn chạy và máy có mạng. Nếu cần bảo đảm chạy khi server tắt hoặc máy restart, đây là một yêu cầu mới và sẽ dùng Windows Task Scheduler hay hạ tầng scheduler riêng.
