# Runbook — Chạy Match Performance trên Hugging Face Spaces (tài khoản PRO)

Một Docker Space chạy cả web + worker (`python -m cloud.hf_main`, cổng 7860). Ổ đĩa của Space **không bền** ⇒
dữ liệu (tài khoản, thư viện trận) được đồng bộ với một **Dataset riêng tư** `<user>/match-performance-data`
mỗi 10 phút (chỉ khi có thay đổi) và khi Space tắt; khởi động lại thì tự tải về. Không tốn thêm chi phí.

## 1. Đăng nhập Hugging Face trên máy Windows (một lần)

1. huggingface.co → Settings → **Access Tokens** → *Create new token* → loại **Write** → sao chép token.
2. PowerShell:
   ```powershell
   cd "C:\Automation Football Dashboard"
   python -m pip install huggingface_hub==2.3.0
   python -c "from huggingface_hub import login; login()"      # dán token khi được hỏi (không hiện ký tự)
   ```

## 2. Đẩy code lên Space

```powershell
python tools/push_hf_space.py --admin-email ban@example.com
```

Script tạo Space public `match-performance` (SDK docker), Dataset riêng tư `match-performance-data`, đặt Variables,
đặt Secret `HF_TOKEN` (chính token đã đăng nhập — dùng để ghi Dataset), rồi upload đúng các file cần chạy.

## 3. Đặt mật khẩu admin (chỉ bạn biết)

Space → **Settings → Variables and secrets → New secret**: `BOOTSTRAP_ADMIN_PASSWORD` = mật khẩu ≥ 10 ký tự.
Space tự khởi động lại; lần đầu build mất ~5–10 phút (tab **Logs**). Admin chỉ được tạo khi DB chưa có admin —
về sau đổi Secret này không ghi đè mật khẩu.

## 4. Dùng

- Mở **trực tiếp** `https://<user>-match-performance.hf.space` (nút ⋮ → *Embed this Space* → *Direct URL*).
  Trong khung nhúng trên huggingface.co, cookie đăng nhập bị trình duyệt chặn và app đặt `X-Frame-Options: DENY`.
- Đăng nhập bằng email admin → dán link Flashscore → báo cáo.
- Người khác tự đăng ký → admin duyệt ở trang **Admin**.
- **Email:** chưa cấu hình SMTP thì thư (link xác minh, đặt lại mật khẩu) chỉ in ở tab **Logs** của Space
  (`[mail:console]`) — chỉ chủ Space xem được. Muốn gửi thật: thêm Secrets `SMTP_HOST=smtp.gmail.com`,
  `SMTP_PORT=587`, `SMTP_USER=<gmail>`, `SMTP_PASS=<App password của Google>`, Variable `MAIL_FROM`.

## 5. Chống ngủ (miễn phí)

Phần cứng CPU basic ngủ sau 48 h không có truy cập. Tạo monitor HTTP(S) miễn phí trên **UptimeRobot** tới
`https://<user>-match-performance.hf.space/api/health`, chu kỳ 5 phút. (Cách làm phổ biến, Hugging Face không
cam kết; Space vẫn có thể khởi động lại khi cập nhật/bảo trì — dữ liệu được khôi phục từ Dataset.)

## 6. Vận hành

| Việc | Cách làm |
| --- | --- |
| Cập nhật phiên bản | Chạy lại `python tools/push_hf_space.py --admin-email …` |
| Xem log | Tab **Logs** của Space |
| Sao lưu | Tự động vào Dataset (lịch sử commit = các phiên bản cũ). Tải bằng tay: Dataset → Files → `app.db.gz` |
| Khôi phục bản cũ | Dataset → History → mở commit cũ → tải `app.db.gz` → upload đè lên `app.db.gz` → Settings của Space → *Factory rebuild* (ổ trống ⇒ tải bản đó về) |
| Crawl bị tạm dừng (Flashscore chặn) | Trang Admin → *Resume crawling* |
| Rủi ro mất dữ liệu | Tối đa ~10 phút gần nhất nếu Space bị tắt đột ngột (`HF_SYNC_MINUTES`) |
| Token an toàn hơn | Tạo token *fine-grained* chỉ ghi Dataset `match-performance-data`, thay Secret `HF_TOKEN` |
| Báo cáo lỗi `E_INTERNAL … Locator.click / wait_for: Timeout` | Space phải chạy `FS_PARALLEL=1` (đã đặt sẵn). Tải song song trên máy 2 vCPU làm menu chọn đội của Flashscore không mở kịp — kiểm chứng: `FS_PARALLEL=3` lỗi 9/9, `=1` thành công 12/12 |
| Chẩn đoán crawler ngay trên Space | Đặt Variable `FS_DIAG_URL=<link trận>` (+ `FS_DIAG_CRAWLS=3` để crawl thật 3 lần) ⇒ Space khởi động lại, kết quả nằm ở Dataset `diag/<thời điểm>/` (report.json, ảnh chụp, HTML, crawls.json). Xong thì **xoá** 2 biến |

