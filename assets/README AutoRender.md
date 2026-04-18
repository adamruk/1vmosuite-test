# 🎭 1vmo Auto Render v3

## 🎯 Hướng dẫn sử dụng

### Input Controls
- 📥 Select: Thêm video vào danh sách xử lý
- 🗑️ Delete: Xóa video đã chọn khỏi danh sách
- ❓ Help: Hiển thị hướng dẫn sử dụng

### Config Management
- 🔍 Filter: Lọc encoder theo nhóm
  - 🕹️ Ultimate: Chất lượng cao nhất
  - 🎮 Gaming: Tối ưu cho game
  - 🎬 Movie: Tối ưu cho phim
  - 🎵 Music: Tối ưu cho nhạc
  - 🎥 Social: Tối ưu cho mạng xã hội
- Encoder Controls:
  - ♻️ Add: Thêm encoder mới
  - 🛠️ Edit: Sửa encoder hiện tại
  - 🗑️ Delete: Xóa encoder đã chọn
  - 🔄 Refresh: Tải lại danh sách encoder
- Di chuột vào ℹ️ để xem tooltip chi tiết về encoder.

### Render Modes
- Single Render:
  - Chọn nhiều encoder từ danh sách
  - Mỗi video sẽ được xử lý với từng encoder riêng biệt
  - Tạo ra nhiều file output tương ứng với số encoder đã chọn
- X Render:
  - Chọn tối đa 5 encoder theo thứ tự xử lý
  - Video sẽ được xử lý tuần tự qua các encoder đã chọn
  - Kết quả là một file output duy nhất đã qua tất cả các bước xử lý
  - Hiển thị tiến trình chi tiết cho từng bước xử lý

### Output Controls
- 📍 Directory: Chọn thư mục lưu video output
- 📂 Open: Mở thư mục đầu ra
- 🚀 Start: Bắt đầu quá trình render
- 🛑 Stop: Dừng quá trình render

### Output List
Hiển thị thông tin của các file đã xử lý:
- Số thứ tự
- Tên file gốc
- Tên file output
- Thời lượng (Loading... khi đang xử lý)
- Độ phân giải (Loading... khi đang xử lý)
- Trạng thái xử lý:
  - 🟡 Processing: Đang xử lý
  - 🟢 Completed: Hoàn thành
  - 🔴 Error: Lỗi (kèm thông tin lỗi) 