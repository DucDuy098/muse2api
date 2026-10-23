# Muse2API Studio 1.6.8

Ứng dụng tiếng Việt cho Windows: tạo ảnh/video, chat Muse và điều khiển qua Telegram.

## Tải bản Windows không cần Python

Mở [Release v1.6.8](https://github.com/bitgacon/muse2api/releases/tag/v1.6.8).
- **Muse2API_VI_Portable_1.6.8.zip**: bản đầy đủ, giải nén toàn bộ rồi mở `Muse2API_Studio.exe` hoặc `05_MO_GUI.bat`.
- **Muse2API_Update_1.6.7_to_1.6.8.zip**: cập nhật bản portable 1.6.7. Chờ tác vụ xong, dừng dịch vụ và đóng GUI/CMD, giải nén chép đè; giữ nguyên `.env` và `data`.

Giữ thư mục `_internal` bên cạnh EXE. Máy cần Windows 10/11 x64, Chrome hoặc Edge và kết nối Internet. Không cần cài Python cho bản portable.

## Chức năng 1.6.8

- Chọn tài khoản cho tạo ảnh/video độc lập, chuỗi đồng bộ nhân vật và chat GUI/web.
- Mỗi tài khoản chạy một lô prompt lần lượt; các tài khoản chạy song song trong phiên trình duyệt có cookie riêng.
- Nhật ký và thư viện lọc theo tài khoản. Tạo lại mặc định dùng tài khoản thực tế của tác vụ lỗi; có thể tạo độc lập bằng tài khoản khác.
- Thư mục thư viện và tải tự động được nhóm theo tài khoản.
- Đính kèm PNG/JPG/WEBP và MD/TXT/CSV/XLSX/XLS/PDF/DOCX. Tối đa 8 ảnh và 8 tài liệu, mỗi tệp 5 MB.
- Chat giữ cùng hội thoại; chuỗi đồng bộ gửi bộ tham chiếu một lần. Video mặc định 10 giây.
- Bot Telegram hỗ trợ chat, tạo ảnh/video, ảnh tham chiếu và gửi kết quả. Cấu hình token và User ID được phép trong phần Cài đặt.

Ví dụ: chọn A, gửi lô 100 prompt; chọn B, gửi lô khác 100 prompt. A1…A100 và B1…B100 chạy song song, từng lô giữ đúng thứ tự.

Xem [hướng dẫn 1.6.8](HUONG_DAN_1.6.8.txt), [GUI/Telegram](HUONG_DAN_GUI_TELEGRAM.md) và [báo cáo QA](docs/QA_RELEASE_1.6.8.json).

## Chạy từ mã nguồn

Dùng Python 3.12 x64. Trên Windows chạy `01_CAI_DAT.bat`, sau đó `05_MO_GUI.bat` hoặc `02_CHAY_MUSE2API.bat`.

Cấu hình, API key, cookie, token, lịch sử và kết quả được tạo tại máy người dùng. Không đưa `.env`, thư mục `data` hay profile trình duyệt lên GitHub.

## Xác minh

Kiểm thử giả lập: 2 tài khoản × 100 prompt; thứ tự, khóa tài khoản, tạo lại, chat/chuỗi cố định và thư mục riêng. Chromium thật kiểm tra cookie cách ly, giao diện và đính kèm. EXE đã chạy thử với Python bị loại khỏi PATH; gói cập nhật được thử giữ `.env` và `data`.

Chưa xác nhận tạo nội dung thực tế trên Muse hoặc chạy trên máy Windows sạch khác. Khả năng nhận tài liệu và kết quả tạo sinh phụ thuộc dịch vụ Muse.

## Giấy phép và ghi nhận

[MIT License](LICENSE). Phát triển từ [bynne2602/muse2api](https://github.com/bynne2602/muse2api), dựa trên [czg86389-hub/muse2api](https://github.com/czg86389-hub/muse2api). Giữ giấy phép và ghi nhận upstream khi phân phối lại. Xem [README upstream](docs/README.upstream.md).
