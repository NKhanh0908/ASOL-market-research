# Game đáng chú ý và hiện diện trong BXH

Thay điểm tiềm năng tổng hợp bằng tín hiệu có bằng chứng. Quy tắc đã được thống nhất
trong trao đổi với người dùng; triển khai trên Dashboard iOS, API radar, export và CLI stats.

## Tín hiệu và thứ tự

1. Tăng ở nhiều thị trường: tăng ít nhất 20 hạng/1 ngày hoặc 30 hạng/3 ngày tại ít nhất hai nước.
2. Đang tăng: đạt ngưỡng trên tại một nước.
3. Mới vào BXH: có BXH hoàn chỉnh hôm trước, game vắng mặt; hôm nay xuất hiện.
4. Chưa có tín hiệu nổi bật: có dữ liệu so sánh nhưng không đạt các điều kiện trên.
5. Chưa đủ dữ liệu so sánh: không có mốc hợp lệ; không gọi là ổn định hoặc mới vào.

Mỗi game xuất hiện một dòng, có lý do theo từng nước. Cùng nhóm thì ưu tiên số nước
đang tăng, rồi thứ hạng hiện tại tốt hơn, rồi app ID để thứ tự ổn định. Giới hạn 50 dòng
của radar được giữ. Grossing và mô hình kiếm tiền là thông tin tham khảo, không cộng điểm.
Không có điểm tổng, HOT WAVE hoặc xác suất thành công.

## Dữ liệu hợp lệ

Chỉ dùng snapshot complete của Apple/iOS/Casual 7003/Top 100, cùng collection và ngày UTC
(theo ngày của bộ phân tích iOS hiện có). Ưu tiên bản canonical hợp lệ, nếu chưa có dùng
bản hoàn chỉnh mới nhất trong ngày. Không trộn Free với Grossing, Android với iOS,
ngày khác nhau hoặc snapshot partial. Không suy ngược độ phủ từ tổng hợp lịch sử.

Hiện diện = số thị trường quan sát thấy game / số thị trường có BXH hoàn chỉnh cùng ngày.
Danh sách nước đi kèm; không có mẫu hợp lệ thì hiển thị chưa đủ dữ liệu, không dùng /11.
Mẫu số chỉ nói về dữ liệu đã thu thập, không khẳng định bao phủ toàn bộ khu vực/thị phần.
Lọc một nước ở Dashboard giới hạn game cần xem; bằng chứng đa thị trường vẫn sử dụng
tập quan sát toàn bộ cùng ngày. CSV/JSON radar giữ bộ lọc của trang.

Xuất hiện thêm: xét giao của các nước có dữ liệu hôm qua và hôm nay; game đã xuất hiện
ở ít nhất một nước trong giao hôm qua và mới xuất hiện ở nước khác trong giao hôm nay.
Nước bắt đầu được thu thập hôm nay không tạo tín hiệu này. Nếu game biến mất ở nước khác,
hiển thị cả nước mất để tránh diễn giải việc đổi thị trường thành tăng độ phủ ròng.

## Tích hợp và giới hạn

- Dashboard/API/export radar dùng `stats/noteworthy.py`; không cần chạy lại analysis cũ.
- Trang iOS, game detail và CSV dữ liệu dùng cùng phép đếm hiện diện (cùng collection).
- Bookmark mới không gửi điểm; Shortlist không hiển thị/xuất cột điểm trong CSV.
- Giữ dữ liệu điểm lịch sử và hàm tính cũ để tương thích dữ liệu/caller cũ; chúng không
  tham gia danh sách mới. Không xóa hay chuyển đổi dữ liệu người dùng.
- Android chưa tích hợp vào radar. Không thay đổi crawler, scheduler hoặc phân loại kiếm tiền.
- Kiểm thử: ngưỡng 1/3 ngày, nhiều nước, thiếu baseline, thêm nước crawl, thêm/mất thị trường,
  loại trừ Grossing/ngày khác/partial, API, CSV và hiển thị trên các trang.
