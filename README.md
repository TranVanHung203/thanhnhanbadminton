# Thành Nhân Badminton League

Ứng dụng quản lý giải cầu lông theo tháng, gồm ba luồng chính:

- Người tham gia gửi kết quả và minh chứng trận đấu.
- Mọi người xem trận đã duyệt, bảng xếp hạng, điểm, sao và hoa.
- Ban Tổ chức duyệt/từ chối/xóa bản ghi và khóa từng mùa giải.
- Tháng hiện tại tự động trở thành mùa giải mặc định; các tháng cũ vẫn có trong bộ lọc lịch sử.
- Tự động thống kê cơ cấu thưởng thành tích và ba danh hiệu thưởng thái độ theo từng tháng.

## Công nghệ

- Python 3.11 + Flask
- HTML/Jinja, CSS và JavaScript thuần
- MongoDB Atlas, database `thanh_nhan`

Ứng dụng luôn mở database qua `client["thanh_nhan"]`, không dùng database mặc định được ghi trong URI.

## Chạy tại máy

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

Mở `http://127.0.0.1:5000`. Các biến cần cấu hình trong `.env`:

- `MONGO_URI`: chuỗi kết nối MongoDB Atlas.
- `MONGO_DB_NAME=thanh_nhan`.
- `SECRET_KEY`: khóa phiên đăng nhập.
- `ADMIN_PASSWORD`: mật khẩu trang `/admin`.

## Google Drive trên Render

Không đưa file OAuth hoặc token lên Git. Trên Render, cấu hình các biến:

- `GOOGLE_OAUTH_CLIENT_ID`: Client ID của OAuth Web application.
- `GOOGLE_OAUTH_CLIENT_SECRET`: Client secret tương ứng.
- `GOOGLE_OAUTH_PROJECT_ID`: Project ID trên Google Cloud (không bắt buộc).
- `GOOGLE_OAUTH_REDIRECT_URI`: `https://TEN-DICH-VU.onrender.com/admin/google/callback`.
- `GOOGLE_DRIVE_FOLDER_NAME`: tên thư mục lưu ảnh trên Drive.

Cũng có thể dùng `GOOGLE_OAUTH_CLIENT_JSON` chứa toàn bộ JSON OAuth dạng thường
hoặc base64 thay cho hai biến client ID/client secret. URL callback phải được
thêm chính xác vào **Authorized redirect URIs** trong Google Cloud Console.

Sau lần kết nối đầu tiên tại trang quản trị, refresh token được lưu trong
collection `app_settings` của MongoDB nên không bị mất khi Render restart hoặc
deploy lại.

## Quy tắc đã mã hóa

- Vòng bảng ngày 1–21; vòng phân hạng từ ngày 22 đến cuối tháng.
- Mỗi trận có 2 vận động viên và 2 trọng tài khác nhau.
- Set đến 15, hòa 14–14 phải hơn 2, trần 17; thắng 2 set là thắng trận.
- 3 trận vòng bảng hợp lệ đầu tiên của từng người là chính thức; tối đa 5 trận tiếp theo là không chính thức.
- Trận chính thức: thắng 3 điểm, thua hoàn thành 1 điểm.
- Trận không chính thức: thắng 3 sao, thua hoàn thành 1 sao.
- Mỗi trọng tài của trận hợp lệ nhận 1 hoa.
- Người chỉ làm trọng tài không xuất hiện trong bảng xếp hạng vận động viên; họ được hiển thị ở bảng Hoa đồng hành riêng.
- Vòng phân hạng cộng điểm vào tổng tháng và không tạo sao.
- Chỉ trận có trạng thái `approved` mới ảnh hưởng bảng xếp hạng.
- Thưởng thành tích gồm 01 Giải Nhất, 03 Giải Nhì và 05 Giải Ba; hệ thống không tự phá các trường hợp đồng hạng cần thi đấu hoặc bốc thăm.
- Thưởng thái độ được xét lần lượt: Thành tích đối đầu ấn tượng → Ngôi sao thi đấu tích cực → Hoa đồng hành tích cực. Một người chỉ nhận tối đa một danh hiệu thái độ.
- Trạng thái giải thưởng là dự kiến khi tháng đang mở và trở thành chính thức khi mùa giải được khóa.

Thứ tự trước vòng phân hạng được lấy theo dự thảo Word: điểm chính thức → đủ 3 trận chính thức → sao. Sau khi có vòng phân hạng: tổng điểm tháng → sao. Các tình huống đồng hạng đặc biệt vẫn được đánh dấu để BTC xử lý.

## API chính

- `POST /api/matches`: gửi một bản ghi trận đấu.
- `GET /api/results?month=YYYY-MM`: lấy xếp hạng, thống kê giải thưởng và trận đã duyệt theo tháng.
- `GET /api/health`: kiểm tra kết nối MongoDB Atlas.
- `GET /nhap-ket-qua`: giao diện nhập kết quả.
- `GET /ket-qua`: giao diện xem kết quả.
- `GET /admin`: quản trị và duyệt dữ liệu.

## Kiểm thử

```powershell
python -m pytest -q
```
