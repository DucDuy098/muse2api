# Studio desktop và Telegram — 13/10/2026

## Mở GUI

1. Dừng cửa sổ CMD chạy bản cũ bằng Ctrl+C hoặc đóng cửa sổ.
2. Chạy `05_MO_GUI.bat`, bấm **Chạy dịch vụ** và chờ **Sẵn sàng**.
3. Dùng trực tiếp các tab **Chat Muse**, **Tạo ảnh / video**, **Hàng loạt Excel / TXT**, **Thư viện / Tác vụ**, **Tài khoản**, **Cài đặt**, **Nhật ký**.

GUI dùng môi trường `.venv` và PySide6/Qt. Qt đã được cài trên máy hiện tại; trên máy khác, `05_MO_GUI.bat` sẽ gọi `06_CAI_GUI.bat` khi thiếu thư viện (cần Internet). Có thể dùng web như trước bằng `02_CHAY_MUSE2API.bat`; web có thêm **Chat Muse** và **Telegram**. Làm mới bằng Ctrl+F5.

GUI chỉ dừng dịch vụ do chính GUI mở. Nếu kết nối vào phiên CMD có sẵn, hãy dừng từ CMD. Đóng GUI sẽ dừng phiên dịch vụ và bot do GUI mở; tác vụ chưa hoàn tất có thể bị gián đoạn. Tệp hoàn tất và cài đặt được giữ lại.

## Chat và ảnh mẫu

Chat giữ ngữ cảnh nhiều lượt. Web có nhiều cuộc hội thoại và streaming; lịch sử lưu trên trình duyệt. Desktop lưu lịch sử tại `data/desktop_chat.json`, có nút Chat mới và gửi bằng Ctrl+Enter.

Cả tạo ảnh và video đều nhận bộ ảnh mẫu: chọn nhiều ảnh cùng lúc, đặt vai trò cho từng ảnh và bỏ ảnh không cần. Hỗ trợ PNG/JPG/WEBP, tối đa 8 ảnh, 5 MB/ảnh, tổng 20 MB. Desktop hiển thị ảnh mẫu bằng thumbnail và cho đặt vai trò. Thư viện hiển thị ảnh/video dạng thẻ; chọn thẻ để xem trực tiếp trong GUI. Video có phát/tạm dừng, thanh tua, âm lượng và phóng to. Thumbnail video được lưu tại `data/thumbnails` để các lần mở sau nhanh hơn.

Video mặc định 10 giây. Trong hàng loạt, cùng bộ ảnh mẫu áp dụng cho mọi prompt của lô. Nhập Excel `.xlsx` hoặc TXT UTF-8; Excel dùng cột Prompt/Mô tả hoặc cột A. Tạm dừng/dừng hàng đợi chỉ tác động prompt chưa gửi. Khởi động lại không tự gửi lại prompt bị gián đoạn.

Trong Cài đặt, chọn thư mục và bật tải tự động. Tệp gốc vẫn nằm trong `data/media`, có thể lưu thêm một bản qua Thư viện hoặc tự động sao chép vào thư mục đã chọn.

## Cấu hình Telegram

1. Tạo một bot riêng qua BotFather và lấy token.
2. Trong GUI **Cài đặt**, hoặc web **Telegram**, nhập token và Telegram **User ID** được cho phép (số, không phải username; nhiều ID ngăn cách bằng dấu phẩy).
3. Bật **Bật bot cùng dịch vụ**, giữ **Giữ ảnh gốc (gửi một tệp)**, bấm **Lưu Telegram** / **Lưu và áp dụng**.
4. Xem trạng thái. Khi kết nối thành công, mở bot trong Telegram và gửi `/start`.

Không cần gửi token vào cuộc trò chuyện Codex. Token không được trả về qua API trạng thái hoặc ghi vào nhật ký GUI. Để trống ô token khi chỉnh cài đặt để giữ token hiện có.

Cấu hình được lưu tại `data/telegram_config.json`. Có thể sao chép `telegram_config.example.json` tới đường dẫn này rồi điền:

```json
{"enabled": true, "token": "TOKEN_CUA_BAN", "user_ids": [123456789], "send_original": true}
```

Nếu gặp phiên dịch vụ cũ chưa có `/v1/telegram/settings`, GUI sẽ lưu cấu hình trên máy và báo cần khởi động lại, thay vì hiện lỗi Not Found. Đóng CMD/GUI cũ, mở GUI mới và bấm Chạy dịch vụ. Không cần chia sẻ token với Codex.

Khi sửa file trực tiếp, khởi động lại dịch vụ. Khi lưu qua giao diện đang kết nối dịch vụ, cài đặt được áp dụng ngay. Bot chỉ nhận lệnh trong chat riêng từ User ID được cho phép. Máy và dịch vụ cần đang chạy. Nếu bot đang được một dịch vụ khác dùng webhook, trạng thái báo lỗi; tool không tự xóa webhook của bot đó.

## Thao tác trên Telegram

| Lệnh / nút | Thao tác |
|---|---|
| `/start`, `/help` | Hiện hướng dẫn và bàn phím |
| `/chat` hoặc Chat Muse | Chọn chat; tin nhắn văn bản tiếp theo được gửi ngay tới Muse |
| `/new` hoặc Chat mới | Bắt đầu chat mới |
| `/image MÔ_TẢ`, `/video MÔ_TẢ` | Soạn yêu cầu ảnh hoặc video, chưa tạo ngay |
| Gửi ảnh / album hoặc ảnh dạng File | Thêm ảnh vào bản soạn; ảnh dạng File giữ chất lượng gốc |
| Nút vai trò dưới mỗi ảnh | Chọn tham khảo, nhân vật, bối cảnh, nền hoặc khung hình đầu |
| `/role 1 character` | Đặt vai trò theo số ảnh; giá trị `reference`, `character`, `scene`, `background`, `first_frame` |
| `/remove 1`, `/clearphotos` | Bỏ một ảnh hoặc toàn bộ ảnh mẫu |
| `/ratio 9:16` | Chọn `16:9`, `9:16`, `1:1` |
| `/duration 10` | Video 1–10 giây, mặc định 10 |
| `/generate` hoặc Tạo / Gửi | Gửi prompt và toàn bộ ảnh đã nhận để tạo media |
| `/status` | Xem trạng thái yêu cầu gần nhất |
| `/last` | Gửi lại tệp đã tạo, không tạo lại |
| `/cancel` | Bỏ bản soạn; không hủy tác vụ đã gửi tới Muse |

Sau khi gửi đủ bộ ảnh, mới bấm **Tạo / Gửi**. Nếu chỉ cần tạo từ mô tả, bỏ qua ảnh. Mỗi người có một yêu cầu đang xử lý; chat và tạo media tiếp tục dùng chung cơ chế khóa trình duyệt của core.

Ví dụ: `/video Pikachu ở ảnh 2 cầm búa ở ảnh 1 và phóng sét lên trời` → gửi 2 ảnh → đặt ảnh 1 `reference`, ảnh 2 `character` → `/generate`.

Mỗi kết quả chỉ gửi một tệp: video có thể xem và tải trực tiếp; ảnh gửi dạng File khi bật giữ ảnh gốc, hoặc dạng ảnh xem trước khi tắt. Chỉ dùng File dự phòng khi Telegram xác nhận từ chối bản xem trước; lỗi mạng không tự gửi lại để tránh trùng. Bot API hiện giới hạn tải lên file 50 MB, ảnh xem trước 10 MB; tệp vượt giới hạn vẫn nằm trong Thư viện trên PC. Tham khảo [Telegram Bot API](https://core.telegram.org/bots/api#sending-files).

## Mức kiểm tra

Đã kiểm tra cú pháp Python, GUI Qt với 7 tab và callback dữ liệu mẫu, hồi quy lưu cấu hình với API cũ trả 404 và không bỏ qua lỗi xác thực 401, giải mã/phát/tạm dừng/tua MP4 10 giây thực tế trên máy, xem ảnh trực tiếp, cache thumbnail video, dịch vụ desktop chạy không CMD và nhả cổng khi kết thúc, chat web streaming UTF-8/lịch sử, API cấu hình Telegram, allowlist và workflow bot bằng transport giả lập, gửi tệp gốc, không tạo lại khi cập nhật bị lặp, tạo ảnh/video với bộ ảnh mẫu, cùng các regression ảnh/video/tải tự động.

Người dùng đã xác nhận Muse nhận đủ hai ảnh ở bản trước. Đợt này chưa thử gửi/nhận với bot Telegram thật, và chưa kiểm tra chat/tạo media mới qua GUI. Phát video hiện có đã được kiểm tra bằng MP4 thật; đầu ra audio chưa được nghe kiểm tra. Trạng thái bot và kết quả thực tế cần được xác nhận sau khi nhập cấu hình của bạn.
