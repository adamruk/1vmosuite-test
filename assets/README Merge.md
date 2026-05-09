# 🧩 1vmo Merge v3

## 🎯 Hướng dẫn sử dụng

### Input Controls
- 🔵 Group 1: Thêm video/ảnh vào nhóm 1
- 🟢 Group 2: Thêm video/ảnh vào nhóm 2
- 🟠 Group 3: Thêm video/ảnh vào nhóm 3
- 🔴 Group 4: Thêm video/ảnh vào nhóm 4
- 🎵 Audio: Thêm file âm thanh
- ❌ Delete: Xóa file đã chọn
- ❓ Help: Hiển thị hướng dẫn sử dụng

### Configuration
- Number of Videos: Chọn số lượng video/ảnh cần ghép (1-4)
- Layout Mode: Chọn cách sắp xếp video/ảnh
  - Single: Chỉ xử lý 1 video/ảnh
  - Horizontal: Video/ảnh nằm cạnh nhau
  - Vertical: Video/ảnh xếp bên trên dưới
  - Overlay: Video/ảnh phụ chồng lên video/ảnh chính
  - 2x2 Grid: Sắp xếp 4 video/ảnh thành lưới 2x2
- Output Format: Chọn tỷ lệ khung hình đầu ra
  - Free: Giữ nguyên tỷ lệ khung hình
  - 16:9: Chuyển đổi sang tỷ lệ 16:9
  - 9:16: Chuyển đổi sang tỷ lệ 9:16
  - 1:1: Chuyển đổi sang tỷ lệ vuông
- Video Ratio (khi chọn 2 video & Horizontal/Vertical):
  - Điều chỉnh tỷ lệ giữa video 1 và 2
  - Mặc định 5:5 (2 video bằng nhau)
- Audio Source: Chọn nguồn âm thanh
  - Longest: Lấy từ video dài nhất
  - Shortest: Lấy từ video ngắn nhất
  - Custom Audio: Sử dụng file âm thanh tùy chọn
- Audio Mode (khi chọn Custom Audio):
  - 🔁 Order: Sử dụng file âm thanh theo thứ tự
  - 🎲 Random: Sử dụng file âm thanh ngẫu nhiên
- Overlay Options (khi chọn chế độ Overlay)
  - Overlay Group: Chọn nhóm video chồng lên
  - Opacity: Điều chỉnh độ trong suốt (0-100%)

### Preview
- Hiển thị trước cách sắp xếp video/ảnh
- Cập nhật tự động khi thay đổi cấu hình
- Hiển thị số lượng video/ảnh và tỷ lệ khung hình
- Hiển thị trực quan tỷ lệ giữa các video/ảnh

### Output Controls
- 📍 Directory: Chọn thư mục lưu video
- 📂 Open: Mở thư mục đầu ra
- ⚡ Boost: Chế độ tăng tốc xử lý
  - OFF: Chế độ thường - chất lượng tốt hơn
  - ON: Chế độ nhanh - xử lý nhanh hơn
- 🚀 Start: Bắt đầu ghép video
- 🛑 Stop: Dừng quá trình ghép

### Output List
Hiển thị thông tin của các file đã xử lý:
- Số thứ tự
- Tên file gốc
- Tên file output
- Thời lượng
- Độ phân giải
- Định dạng
- Trạng thái xử lý:
  - ⏳ Waiting: Đang chờ xử lý
  - 🔄 Processing: Đang xử lý
  - 🟢 Completed: Hoàn thành
  - 🔴 Error: Lỗi
  - 🟡 Cancelled: Đã hủy

### Lưu ý
- Hỗ trợ nhiều định dạng video: MP4, AVI, MKV, MOV, WMV, FLV, WEBM
- Hỗ trợ nhiều định dạng ảnh: JPG, JPEG, PNG, BMP, GIF, TIFF
- Hỗ trợ nhiều định dạng âm thanh: MP3, WAV, M4A, AAC, OGG, FLAC, WMA
- Tự động lưu cấu hình và đường dẫn cuối cùng
- Hỗ trợ xử lý đa luồng (tối đa 3 luồng)
- Tự động cập nhật phiên bản mới
