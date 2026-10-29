# Detailed Design — Đưa Match Performance lên cloud cho nhiều người dùng chung

| Thuộc tính | Giá trị |
| --- | --- |
| Trạng thái | **v1.0 — Đã triển khai phần mã P1–P4** (2026-10-13), Q-A…Q-G chốt theo ★. Phần hạ tầng (P0 kiểm tra IP, P5 triển khai lên Oracle) do người dùng thực hiện theo [deploy/runbook.md](../deploy/runbook.md). Ghi nhận khi triển khai: **[§18](#18-ghi-nhận-khi-triển-khai-2026-10-13)**. **Cổng G0 (pháp lý, [§3](#3-cổng-g0--pháp-lý-và-nguồn-dữ-liệu)) phải qua trước khi mở cho người ngoài** |
| Ngày | 2026-10-13 |
| Phạm vi | Chạy dashboard + crawler + PDF trên một máy chủ cloud **miễn phí**, truy cập qua internet, **tài khoản riêng từng người**, **thư viện trận** dùng chung |
| Không thuộc phạm vi | Ứng dụng mobile; thanh toán/gói trả phí; phân tích trước/trong trận; đa ngôn ngữ |
| Tài liệu liên quan | [CLAUDE.md](../CLAUDE.md) · [detailed-design-url-ingestion.md](detailed-design-url-ingestion.md) (crawler, API job) · [detailed-design-dashboard-redesign.md](detailed-design-dashboard-redesign.md) (dashboard, PDF) |
| Ký hiệu | ✅ đã kiểm chứng (mã nguồn / tài liệu nhà cung cấp, 2026-10-13) · ⚠ thông tin bên thứ ba hoặc hay thay đổi — kiểm lại lúc triển khai · 🔒 không đổi · 🟡 cần bạn duyệt |

---

## 0. Tóm tắt

### 0.1 Trả lời ngắn

**Về kỹ thuật: làm được, với chi phí hạ tầng 0 đồng**, kèm 3 điều kiện bạn cần biết trước:

| # | Điều kiện | Vì sao |
| --- | --- | --- |
| C1 | **Cổng pháp lý G0** | Điều khoản của Flashscore cấm thu thập tự động và cấm cung cấp lại dữ liệu cho công chúng khi chưa có đồng ý ✅ ([§3](#3-cổng-g0--pháp-lý-và-nguồn-dữ-liệu)). Chạy cho chính bạn trên máy cá nhân và mở một dịch vụ công khai là hai mức rủi ro rất khác nhau |
| C2 | **Miễn phí = không cam kết** | Gói miễn phí không có SLA. Oracle đã **giảm một nửa** gói Always Free trong năm 2026 và từng vô hiệu hoá máy vượt hạn mức ⚠ ([§4](#4-hạ-tầng-miễn-phí)). Cần sao lưu và kế hoạch dự phòng |
| C3 | **Một máy, một địa chỉ IP** | Crawler cần Chromium nên phải chạy trên máy ảo, không chạy được trên serverless miễn phí. Flashscore có thể chặn IP của trung tâm dữ liệu ⇒ **phải thử thật ở Phase 0** trước khi đầu tư tiếp |

### 0.2 Quyết định đã chốt (AskUserQuestion, 2026-10-13)

| # | Câu hỏi | Bạn chọn | Hệ quả |
| --- | --- | --- | --- |
| K1 | Người dùng | **Công khai trên internet** | Cần chống lạm dụng, hạn mức, bảo mật đầy đủ; bị ràng buộc bởi cổng G0 |
| K2 | Hạ tầng | **Cloud, không tốn chi phí** | Oracle Cloud Always Free (máy ARM) làm chính; GCP e2-micro làm dự phòng ([§4](#4-hạ-tầng-miễn-phí)) |
| K3 | Truy cập | **Tài khoản riêng từng người** | Email + mật khẩu, xác minh email, vai trò admin/thành viên, admin duyệt hoặc khoá tài khoản |
| K4 | Lịch sử | **Lưu thư viện trận** | Mỗi trận crawl một lần, lưu kết quả; cả nhóm xem lại ngay, có link chia sẻ |

### 0.3 Giải pháp trong 8 dòng

1. **Một máy ảo Oracle Always Free** (Ubuntu ARM64, 2 OCPU / 12 GB) chạy **Docker Compose** với 3 dịch vụ: `caddy` (HTTPS tự động, reverse proxy), `web` (API + trang web), `worker` (crawler hiện có, **không đổi logic**).
2. **SQLite** (chế độ WAL) lưu người dùng, phiên đăng nhập, thư viện trận, hàng đợi job. Sao lưu hằng đêm lên Object Storage miễn phí.
3. **Thư viện trận:**
   - mỗi `mid` crawl đúng một lần, kết quả JSON (`schemaVersion` 2) được lưu lại;
   - lần mở sau trả kết quả ngay (< 1 s) thay vì 30–60 s ⇒ ít request tới Flashscore hơn.
4. **Tài khoản:** đăng ký bằng email, xác minh qua email (SMTP miễn phí), mật khẩu băm `scrypt`, cookie phiên `HttpOnly` + `Secure`, chống CSRF. Admin duyệt tài khoản mới (🟡 Q-B).
5. **Chống lạm dụng:**
   - hạn mức crawl mới theo người và toàn hệ thống;
   - ngắt mạch khi Flashscore chặn (`E_BLOCKED`);
   - giới hạn kích thước request và giới hạn tốc độ đăng nhập.
6. **Giao diện:**
   - thêm trang Đăng nhập / Thư viện / Admin;
   - trang báo cáo `match_report.html` giữ nguyên, chỉ thêm cách nạp kết quả từ thư viện (`?mid=`), cần mở khoá vùng đóng băng nhỏ (🟡 Q-E);
   - PDF vẫn tạo ở trình duyệt người dùng, server không tốn CPU.
7. **Chế độ local giữ nguyên 🔒:** `python server.py` trên 127.0.0.1 chạy y như hiện nay. Bản cloud là gói mới `cloud/`, dùng chung `crawler/`.
8. **Nguồn dữ liệu cắm thay được** (`DataSource`): hôm nay là crawler Flashscore; khi qua cổng G0 có thể thay bằng API có giấy phép mà không đổi dashboard.

### 0.4 Roadmap

| Phase | Nội dung | Điều kiện qua phase |
| --- | --- | --- |
| P0 | **Cổng G0** (pháp lý) + **spike hạ tầng**: tạo VM Oracle, chạy crawler từ IP trung tâm dữ liệu trên 9 trận tham chiếu | G0 có kết luận; ≥ 9/9 trận crawl thành công từ VM, không bị chặn |
| P1 | Đóng gói Docker (`web`, `worker`, `caddy`), SQLite + hàng đợi job, worker dùng `crawler/` | Toàn bộ test hiện có xanh + test mới của `cloud/` |
| P2 | Tài khoản: đăng ký, xác minh email, đăng nhập/đăng xuất, quên mật khẩu, admin | Test bảo mật ([§14](#14-kiểm-thử-và-nghiệm-thu)) xanh |
| P3 | Thư viện trận + link chia sẻ + trang báo cáo đọc từ thư viện | e2e luồng người dùng xanh |
| P4 | Hardening: hạn mức, ngắt mạch, CSP, sao lưu + khôi phục thử, giám sát | Diễn tập khôi phục thành công |
| P5 | Triển khai lên VM, tên miền, HTTPS, chạy thử nội bộ (closed beta) | 1 tuần ổn định |
| P6 | Mở rộng theo kết quả G0 (mở đăng ký công khai / đổi nguồn dữ liệu) | Bạn duyệt |

---

## 1. Hiện trạng và khoảng cách

| Khía cạnh | Hiện tại ✅ (mã nguồn) | Cần cho bản cloud |
| --- | --- | --- |
| Mạng | `server.py` chỉ bind `127.0.0.1:8778`, kiểm tra `Host`/`Origin` là localhost | Truy cập internet qua HTTPS, reverse proxy |
| Người dùng | Không có khái niệm người dùng | Tài khoản, phiên đăng nhập, vai trò |
| Job | `JobStore` trong bộ nhớ, tối đa 2 job (1 chạy + 1 chờ), giữ 30 phút | Hàng đợi bền vững (DB), nhiều người dùng, khử trùng lặp theo `mid` |
| Lưu trữ | Không lưu gì; tải lại trang là mất | Thư viện trận, link chia sẻ |
| Crawler | Playwright sync, 1 worker thread, `FS_PARALLEL=3`, ngân sách 150 s | Giữ nguyên logic 🔒; chạy trong tiến trình `worker` riêng |
| Front-end | 1 file HTML, PDF tạo ở trình duyệt | Thêm trang đăng nhập / thư viện / admin; nạp báo cáo theo `mid` |
| Bảo mật | Phù hợp máy cá nhân (local only) | Đủ cho internet công khai ([§9](#9-bảo-mật)) |

---

## 2. Yêu cầu

### 2.1 Chức năng

| ID | Yêu cầu |
| --- | --- |
| F1 | Đăng ký bằng email + mật khẩu; xác minh email; đăng nhập/đăng xuất; quên mật khẩu |
| F2 | Admin: duyệt/khoá/mở tài khoản, đổi vai trò, xem nhật ký, chỉnh hạn mức, bật/tắt đăng ký |
| F3 | Dán link Flashscore ⇒ nếu trận đã có trong thư viện: mở ngay; nếu chưa: xếp hàng crawl, hiện tiến độ như hiện nay |
| F4 | Thư viện: danh sách trận (đội, tỉ số, giải, ngày, người tạo), tìm theo tên đội/giải, sắp xếp theo ngày |
| F5 | Trang báo cáo của một trận: dashboard 8 tab + Export PDF (2 preset) như hiện nay |
| F6 | Link chia sẻ: thành viên đã đăng nhập mở bằng `/m/{mid}`; tuỳ chọn link công khai chỉ-xem có token, admin có thể thu hồi (🟡 Q-D) |
| F7 | Làm mới một trận (crawl lại) — giới hạn tần suất, chỉ admin hoặc người tạo |
| F8 | Xoá tài khoản theo yêu cầu người dùng (dữ liệu cá nhân) |

### 2.2 Phi chức năng

| ID | Yêu cầu | Mục tiêu |
| --- | --- | --- |
| N1 | Chi phí hạ tầng | **0 đồng/tháng** |
| N2 | Mở trận có sẵn trong thư viện | < 1 s (API), trang hiển thị < 3 s |
| N3 | Crawl trận mới | Như hiện nay: 25–60 s; hàng đợi hiển thị vị trí |
| N4 | Đồng thời | ~50 người xem cùng lúc; 1 crawl chạy + hàng đợi tối đa 20 |
| N5 | Bền vững dữ liệu | Mất tối đa 24 h dữ liệu (RPO), khôi phục < 2 h (RTO) |
| N6 | Bảo mật | Theo [§9](#9-bảo-mật); không lộ mật khẩu, không cho người lạ dùng crawler vô hạn |
| N7 | Không hồi quy | Chế độ local, dashboard, PDF, demo, toàn bộ test hiện có giữ nguyên 🔒 |

---

## 3. Cổng G0 — pháp lý và nguồn dữ liệu

### 3.1 Sự thật

Trang điều khoản của Flashscore (`flashscore.com/terms`, ✅ đọc qua trích đoạn 2026-10-13) nêu:

- không được trích xuất hoặc cung cấp cho công chúng một phần đáng kể nội dung cơ sở dữ liệu khi chưa có đồng ý rõ ràng;
- không được nhúng, tổng hợp, **scrape** hoặc tái tạo nội dung khi chưa có đồng ý;
- không được gửi **request tự động**.

Điều khoản trên các tên miền khác của Livesport (công ty chủ quản) yêu cầu cho phép **bằng văn bản** và nêu quyền đòi bồi thường theo luật sở hữu trí tuệ EU.

⇒ Mở dịch vụ **công khai** dựa trên việc crawl Flashscore là **vi phạm điều khoản sử dụng** và có rủi ro pháp lý. Mức rủi ro tăng theo số người dùng và mức độ công khai. Tài liệu này không phải tư vấn pháp lý; nên hỏi ý kiến luật sư trước P6.

### 3.2 Phương án

| PA | Mô tả | Pháp lý | Chi phí | Thay đổi kỹ thuật |
| --- | --- | --- | --- | --- |
| A | Xin **giấy phép / đồng ý bằng văn bản** của Livesport | Sạch nhất | Tuỳ thoả thuận (có thể có phí) | Không |
| B | Đổi sang **nhà cung cấp dữ liệu có giấy phép** (API thống kê bóng đá; nhiều nơi có gói miễn phí giới hạn số request/ngày ⚠) | Sạch nếu đúng điều khoản của họ | 0 đồng ở gói miễn phí; trả phí khi lớn | Viết adapter `DataSource` mới ánh xạ về hợp đồng `state` ([§5.4](#54-datasource--nguồn-dữ-liệu-cắm-thay)); độ phủ chỉ số có thể khác Flashscore |
| C | **Nhóm kín**: đăng ký cần admin duyệt, không quảng bá, phi thương mại, ghi rõ nguồn, cache để giảm request | Giảm rủi ro, **không loại bỏ** (vẫn là request tự động) | 0 | Đã có trong thiết kế (Q-B) |
| D | Công khai hoàn toàn bằng crawler Flashscore | Rủi ro cao nhất | 0 | — **Không khuyến nghị** |

**Đề xuất ★:**

1. Xây theo thiết kế này nhưng **khởi chạy ở chế độ C** (closed beta, admin duyệt từng tài khoản).
2. Song song, tìm hướng A hoặc B.
3. Chỉ mở đăng ký công khai (P6) khi đã có A hoặc B.

Kiến trúc đã tách `DataSource` nên đổi nguồn không ảnh hưởng dashboard.

### 3.3 Dữ liệu cá nhân của người dùng

Hệ thống lưu email, mật khẩu đã băm, nhật ký đăng nhập. Phải đáp ứng Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân (và GDPR nếu có người dùng EU):

- trang Chính sách quyền riêng tư;
- chỉ thu thập email;
- cho phép xoá tài khoản (F8);
- không đưa email vào log;
- lưu nhật ký tối đa 90 ngày.

---

## 4. Hạ tầng miễn phí

### 4.1 So sánh (⚠ số liệu gói miễn phí hay thay đổi — kiểm lại khi đăng ký)

| Lựa chọn | Tài nguyên miễn phí | Chạy được Chromium + worker liên tục? | Kết luận |
| --- | --- | --- | --- |
| **Oracle Cloud Always Free — Ampere A1 (ARM64)** | **2 OCPU / 12 GB RAM** (đã giảm từ 4/24 trong năm 2026, áp dụng khoảng 18/08/2026 ⚠); ổ đĩa block miễn phí; Object Storage miễn phí | Có. 1 crawl ~1–1,5 GB RAM với 3 trang song song ⚠ đo ở P0 | **Chọn ★** |
| Google Cloud e2-micro (Always Free) | 0,25–2 vCPU dạng burst, 1 GB RAM ⚠ | Rất chật: phải dùng `FS_PARALLEL=1` + swap, crawl chậm hơn | Dự phòng khi Oracle không có capacity |
| AWS Free Tier | t-series micro, chỉ 12 tháng ⚠ | Chật như trên | Không "miễn phí vĩnh viễn" |
| Render / Hugging Face Spaces (gói free) | Ngủ khi không có truy cập, ổ đĩa không bền | Có thể chạy nhưng mất dữ liệu khi khởi động lại | Không hợp với thư viện trận |
| Vercel / Cloudflare Pages / Supabase (free) | Hosting tĩnh, hàm serverless, Postgres | **Không** chạy được Playwright/Chromium trong giới hạn thời gian và kích thước | Không đủ một mình |

**Rủi ro Oracle cần chấp nhận** (⚠ tài liệu Oracle + báo cáo cộng đồng):

- **Thu hồi máy nhàn rỗi:** máy bị coi là nhàn rỗi nếu trong 7 ngày, phân vị 95 của CPU, mạng và RAM (riêng A1) đều < 20%. Biện pháp: worker canary chạy hằng đêm + theo dõi.
- **Không tạo được máy:** đôi khi báo "out of capacity" ⇒ thử vùng hoặc thời điểm khác.
- **Đăng ký cần thẻ thanh toán để xác minh** (không trừ tiền ở gói Always Free).
- **Hạn mức có thể giảm tiếp mà không báo trước.**

### 4.2 Dịch vụ phụ trợ (tất cả gói miễn phí ⚠)

| Nhu cầu | Đề xuất | Ghi chú |
| --- | --- | --- |
| Tên miền | **DuckDNS** (`<tên>.duckdns.org`) ★ hoặc tên miền riêng (~10 USD/năm — ngoài phạm vi 0 đồng) | Cần tên miền để có HTTPS |
| HTTPS | **Caddy** tự lấy chứng chỉ Let's Encrypt | Tự gia hạn |
| Email (xác minh, quên mật khẩu) | Dịch vụ SMTP có gói miễn phí (vài trăm email/ngày ⚠) | Cấu hình SPF/DKIM theo hướng dẫn nhà cung cấp |
| Sao lưu | Oracle Object Storage (Always Free) | Bản sao SQLite hằng đêm, giữ 14 bản |
| Giám sát | UptimeRobot (gói free) gọi `/api/health` mỗi 5 phút | Báo qua email khi chết |
| Mã nguồn / bản build | GitHub (repo private) | Build image ngay trên VM để khỏi cần registry |

### 4.3 Chi phí

| Hạng mục | Chi phí/tháng |
| --- | --- |
| VM, ổ đĩa, Object Storage (Oracle Always Free) | 0 |
| DuckDNS, Let's Encrypt, SMTP free tier, UptimeRobot free, GitHub | 0 |
| **Tổng** | **0** (khi vượt gói miễn phí thì phải trả phí — [§10](#10-chống-lạm-dụng-và-năng-lực)) |

---

## 5. Kiến trúc đích

### 5.1 Tổng quan

```text
Trình duyệt ──HTTPS──▶ caddy (443, Let's Encrypt, nén, giới hạn kích thước request)
                          │
                          ├── /            → web: index.html (đăng nhập, thư viện, admin)
                          ├── /m/{mid}     → web: match_report.html (dashboard + PDF, chạy ở trình duyệt)
                          └── /api/*       → web (ASGI, Python)
                                              │  SQLite (WAL) ── users, sessions, matches, results, jobs, audit
                                              │
worker (Python, Playwright sync, Chromium) ◀──┘  lấy job từ bảng jobs (poll 1 s)
   └─ crawler/ (🔒 logic giữ nguyên) ──HTTPS──▶ www.flashscore.com
```

| Dịch vụ | Trách nhiệm | Giới hạn tài nguyên (Docker) |
| --- | --- | --- |
| `caddy` | TLS, reverse proxy, file tĩnh, header bảo mật, `request_body max 64KB` | 128 MB |
| `web` | Auth, phiên, API thư viện/job/admin, hạn mức, trả trang | 512 MB |
| `worker` | Lấy job ⇒ `crawl(url, progress)` ⇒ ghi kết quả; ngắt mạch khi bị chặn | 4 GB, `shm_size` 1 GB, 1 job/lần |
| Ổ đĩa | `/data/app.db`, `/data/backups/` | Volume bền vững |

### 5.2 Phương án đã cân nhắc

| Quyết định | Chọn | Thay thế | Lý do |
| --- | --- | --- | --- |
| Framework web | 🟡 **Starlette/FastAPI + Uvicorn** ★ | Giữ `http.server` của stdlib | Internet công khai cần cookie, CSRF, form, middleware, timeout đáng tin cậy; stdlib không được thiết kế cho môi trường này. Phụ thuộc mới: `fastapi`, `uvicorn` (ghim phiên bản) |
| CSDL | **SQLite (WAL)** | Postgres (container hoặc Supabase free) | Một máy, lượng ghi thấp (vài trăm trận/ngày), sao lưu bằng 1 file. Chuyển sang Postgres khi cần nhiều máy — tầng truy cập dữ liệu viết qua một module `cloud/db.py` |
| Hàng đợi | **Bảng `jobs` trong SQLite** + worker poll | Redis / Celery | Không thêm dịch vụ; 1 worker là đủ |
| Tiến trình crawler | **Tiến trình `worker` riêng** | Thread trong web như hiện nay | Playwright sync cần 1 thread riêng; Chromium crash hoặc chiếm RAM không kéo sập web; giới hạn tài nguyên riêng |
| PDF | **Giữ ở trình duyệt** (html2canvas + jsPDF) | Render ở server | Server miễn phí ít CPU; không đổi tính năng PDF |
| Băm mật khẩu | **`hashlib.scrypt`** (stdlib; n=2¹⁴, r=8, p=1, salt 16 byte) | argon2 (thêm thư viện) | Đủ mạnh, không thêm phụ thuộc |

### 5.3 Cấu trúc thư mục (chỉ **thêm**; file cũ giữ nguyên 🔒 trừ mục Q-E)

```text
cloud/                     MỚI
  app.py                   ASGI app: route trang + /api/*
  auth.py                  đăng ký, xác minh, đăng nhập, phiên, CSRF, quên mật khẩu
  db.py                    SQLite: kết nối, migration, truy vấn
  library.py               thư viện trận, chia sẻ, làm mới
  jobs.py                  hàng đợi job, khử trùng lặp theo mid, hạn mức
  worker.py                vòng lặp worker: lấy job → crawler.crawl → lưu kết quả
  datasource.py            giao diện DataSource; FlashscoreSource bọc crawler/
  mail.py                  gửi email SMTP
  ratelimit.py             hạn mức + giới hạn tốc độ
  static/index.html        đăng nhập / đăng ký / thư viện / admin (cùng design system đỏ–trắng)
  migrations/001_init.sql
deploy/                    MỚI
  Dockerfile.web, Dockerfile.worker, docker-compose.yml, Caddyfile, .env.example
  backup.sh, restore.md, runbook.md
tests/cloud/               MỚI: unit + e2e của bản cloud (chạy cùng `python -m unittest discover`)
server.py, crawler/, match_report.html, tools/, tests/ hiện có — 🔒 (match_report.html: xem Q-E)
```

### 5.4 `DataSource` — nguồn dữ liệu cắm thay

```python
class DataSource(Protocol):
    name: str                                   # "flashscore"
    def parse_ref(self, url: str) -> MatchRef   # kiểm tra/chuẩn hoá link → khoá trận (mid)
    def fetch(self, ref: MatchRef, progress) -> dict   # → result đúng hợp đồng schemaVersion 2
```

- `FlashscoreSource` chỉ gọi `crawler.urls.parse_match_url` và `crawler.crawl` sẵn có.
- Nguồn có giấy phép (phương án B) sẽ là một lớp khác, ánh xạ về **cùng hợp đồng `state`** (CLAUDE.md §3).
- Khoá thư viện: `(source, match_key)`.

---

## 6. Mô hình dữ liệu (SQLite)

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  pw_hash BLOB NOT NULL, pw_salt BLOB NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin','member')) DEFAULT 'member',
  status TEXT NOT NULL CHECK (status IN ('pending','active','disabled')) DEFAULT 'pending',
  email_verified_at TEXT, created_at TEXT NOT NULL, last_login_at TEXT,
  daily_crawl_quota INTEGER                      -- NULL = mặc định hệ thống
);
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,                           -- SHA-256 của token (token thật chỉ nằm trong cookie)
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, ip TEXT, ua TEXT
);
CREATE INDEX sessions_user ON sessions(user_id);
CREATE TABLE email_tokens (                     -- xác minh email / đặt lại mật khẩu
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL CHECK (purpose IN ('verify','reset')), expires_at TEXT NOT NULL, used_at TEXT
);
CREATE TABLE matches (
  id INTEGER PRIMARY KEY, source TEXT NOT NULL, match_key TEXT NOT NULL,   -- ('flashscore', mid)
  source_url TEXT NOT NULL, home TEXT, away TEXT, score TEXT, competition TEXT, kickoff TEXT,
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL, refreshed_at TEXT NOT NULL,
  share_token TEXT UNIQUE,                       -- NULL = không có link công khai (Q-D)
  UNIQUE (source, match_key)
);
CREATE INDEX matches_kickoff ON matches(kickoff);
CREATE TABLE match_results (                     -- giữ các phiên bản khi làm mới
  id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  schema_version INTEGER NOT NULL, result_json TEXT NOT NULL,   -- ~130–150 KB/trận
  warnings_json TEXT NOT NULL, fetched_at TEXT NOT NULL
);
CREATE INDEX match_results_match ON match_results(match_id, fetched_at);
CREATE TABLE jobs (
  id TEXT PRIMARY KEY, source TEXT NOT NULL, match_key TEXT NOT NULL, url TEXT NOT NULL,
  requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  status TEXT NOT NULL CHECK (status IN ('queued','running','done','error')),
  progress_json TEXT, error_json TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT
);
CREATE UNIQUE INDEX jobs_active ON jobs(source, match_key) WHERE status IN ('queued','running');  -- khử trùng lặp
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, user_id INTEGER, action TEXT NOT NULL, detail TEXT
);
```

Ước lượng dung lượng: ~150 KB/trận ⇒ 10 000 trận ≈ 1,5 GB — nằm trong ổ đĩa miễn phí.

---

## 7. API

Mọi `/api/*` trả JSON. Mọi lệnh ghi (`POST`/`DELETE`) cần **phiên hợp lệ + header `X-CSRF-Token`**, trừ đăng ký và đăng nhập (chặn bằng giới hạn tốc độ).

| Method | Đường dẫn | Quyền | Mô tả |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | khách | `{email, password}` ⇒ gửi email xác minh; tài khoản `pending` |
| GET | `/api/auth/verify?token=` | khách | Xác minh email ⇒ chờ admin duyệt (Q-B) hoặc `active` |
| POST | `/api/auth/login` | khách | Đặt cookie `fs_session`; trả `csrf` |
| POST | `/api/auth/logout` | thành viên | Huỷ phiên |
| POST | `/api/auth/forgot` · `/api/auth/reset` | khách | Đặt lại mật khẩu bằng token email (hết hạn 30 phút, dùng 1 lần) |
| GET | `/api/me` | thành viên | Email, vai trò, hạn mức còn lại hôm nay |
| DELETE | `/api/me` | thành viên | Xoá tài khoản (F8) |
| GET | `/api/library?q=&page=` | thành viên | Danh sách trận (đội, tỉ số, giải, ngày, người tạo) |
| POST | `/api/matches` | thành viên | `{url}` ⇒ **có sẵn:** `{status:"done", mid}` · **chưa có:** `202 {jobId, position}` (cùng hình dạng API hiện nay) |
| GET | `/api/matches/{jobId}` | thành viên | Tiến độ như hiện nay (`progress`, `status`, `result` khi xong) |
| GET | `/api/library/{mid}` | thành viên, hoặc khách có `share_token` | `result` đã lưu (hợp đồng schemaVersion 2) |
| POST | `/api/library/{mid}/refresh` | admin / người tạo | Crawl lại (tối đa 1 lần/6 h/trận) |
| POST · DELETE | `/api/library/{mid}/share` | admin / người tạo | Tạo/thu hồi link công khai chỉ-xem (Q-D) |
| GET · POST | `/api/admin/users`, `/api/admin/users/{id}` | admin | Duyệt, khoá, đổi vai trò, chỉnh hạn mức |
| GET · POST | `/api/admin/settings` | admin | Bật/tắt đăng ký, hạn mức mặc định, ngắt mạch |
| GET | `/api/health` | công khai | `{ok, db, worker_heartbeat_age_s, queue}` (không lộ dữ liệu) |

Mã lỗi giữ bộ `E_*` hiện có, thêm:

| Mã | HTTP |
| --- | --- |
| `E_AUTH_REQUIRED` | 401 |
| `E_FORBIDDEN` | 403 |
| `E_CSRF` | 403 |
| `E_QUOTA` | 429 |
| `E_RATE_LIMITED` | 429 |
| `E_SOURCE_PAUSED` | 503 — đang ngắt mạch vì Flashscore chặn |

---

## 8. Luồng xử lý

### 8.1 Tạo báo cáo

```text
POST /api/matches {url}
 ├─ đăng nhập? CSRF? → không: 401/403
 ├─ DataSource.parse_ref(url) → sai: 400 E_URL_INVALID (như hiện nay)
 ├─ thư viện có (source, mid) với schemaVersion hiện hành? → có: 200 {status:"done", mid}   (không tốn hạn mức)
 ├─ có job đang chờ/chạy cùng mid? → trả jobId đó (khử trùng lặp, không tốn hạn mức)
 ├─ hạn mức người dùng / hệ thống / ngắt mạch → 429 E_QUOTA | 503 E_SOURCE_PAUSED
 └─ tạo job 'queued' → 202 {jobId, position}
worker: lấy job cũ nhất 'queued' → 'running' → crawl(url, progress) (progress ghi vào jobs.progress_json)
 ├─ thành công → INSERT matches/match_results (transaction) → job 'done'
 └─ CrawlError → job 'error' (error_json = CrawlError.to_dict()); E_BLOCKED ⇒ ngắt mạch (§10.3)
trình duyệt: poll GET /api/matches/{jobId} mỗi 1 s (như hiện nay) → xong: chuyển tới /m/{mid}
```

### 8.2 Mở trận từ thư viện

`/m/{mid}` ⇒ `match_report.html` ⇒ `GET /api/library/{mid}` ⇒ gán `state.*` ⇒ `App.enter()`. Dữ liệu và hiển thị giống hệt luồng dán link.

### 8.3 Khởi động lại và sự cố

- **Worker chết giữa chừng:** job `running` có `started_at` quá 5 phút được đặt lại thành `queued` (tối đa 1 lần), sau đó thành `error` `E_INTERNAL`.
- **Heartbeat:** worker ghi heartbeat mỗi 10 s; `/api/health` báo lỗi khi heartbeat cũ hơn 60 s.

---

## 9. Bảo mật

| Lớp | Biện pháp |
| --- | --- |
| Mạng | Security list của Oracle + `ufw`: chỉ mở 80/443 (HTTP→HTTPS) và 22 (SSH chỉ bằng khoá, tắt đăng nhập bằng mật khẩu, tắt root). Container không lộ cổng ra ngoài trừ `caddy` |
| TLS | Caddy + Let's Encrypt; HSTS 6 tháng |
| Header | `Content-Security-Policy` cho phép đúng các CDN đang dùng (cdnjs, jsdelivr cho Tesseract, Google Fonts) và `img-src data:`; `X-Frame-Options: DENY`; `Referrer-Policy: same-origin`; `X-Content-Type-Options: nosniff` |
| Mật khẩu | ≥ 10 ký tự, kiểm danh sách mật khẩu phổ biến (file nhỏ trong repo), `scrypt` + salt riêng, so sánh hằng thời gian |
| Phiên | Token ngẫu nhiên 32 byte; DB chỉ lưu SHA-256; cookie `HttpOnly; Secure; SameSite=Lax; Path=/`; hết hạn 14 ngày, cấp lại sau đăng nhập; đăng xuất ở mọi thiết bị khi đổi mật khẩu |
| CSRF | Token theo phiên, gửi qua header `X-CSRF-Token` cho mọi lệnh ghi; kiểm tra thêm `Origin` |
| Đăng nhập | Giới hạn 5 lần sai / 15 phút / (email, IP); thông báo lỗi chung chung (không tiết lộ email có tồn tại) |
| Quyền | Mọi truy vấn trận/job đều kiểm tra quyền phía server (chống IDOR); `share_token` 32 byte ngẫu nhiên, thu hồi được |
| SSRF | Giữ kiểm tra link chỉ `https://www.flashscore.com/match/football/…` hiện có ✅ (`crawler/urls.py`); tải logo chỉ từ `*.flashscore.com` ✅ (`header.fetch_data_url`) |
| Chromium | Chạy trong container `worker` bằng user không phải root, có sandbox của Chromium; giới hạn RAM/CPU; ngân sách 150 s/job (đã có) |
| Bí mật | `.env` trên VM (quyền 600): khoá phiên, mật khẩu SMTP, khoá Object Storage. Không commit lên git |
| Cập nhật | `unattended-upgrades` cho hệ điều hành; ghim phiên bản Python package/Playwright; xem lại phiên bản mỗi tháng |
| Log | Không ghi mật khẩu, token, email (ghi `user_id`); giữ 90 ngày |

Trước P5: chạy agent `security-reviewer` hoặc review bảo mật thủ công trên diff `cloud/`.

---

## 10. Chống lạm dụng và năng lực

### 10.1 Năng lực của máy miễn phí (⚠ đo lại ở P0)

| Thông số | Ước lượng |
| --- | --- |
| 1 crawl (3 trang song song) | ~1–1,5 GB RAM, 25–60 s |
| Worker | **1 job/lần** (Flashscore là nút thắt, không phải CPU) |
| Thông lượng tối đa lý thuyết | ~60–100 trận mới/giờ |
| Xem trận có sẵn | Gần như không tốn tài nguyên (JSON ~150 KB, nén gzip ~25 KB) |

### 10.2 Hạn mức (🟡 Q-C, giá trị mặc định ★)

| Hạn mức | Mặc định | Ghi chú |
| --- | --- | --- |
| Crawl trận **mới** / người / ngày | 10 | Mở trận có sẵn và khử trùng lặp không tính |
| Crawl / toàn hệ thống / giờ | 30 | Lịch sự với Flashscore, giảm rủi ro bị chặn IP |
| Hàng đợi tối đa | 20 job | Vượt ⇒ `429 E_QUOTA` "System busy" |
| Làm mới 1 trận | 1 lần / 6 h | |
| Đăng ký / IP / giờ | 3 | |

### 10.3 Ngắt mạch nguồn dữ liệu

- **Kích hoạt:** 2 job liên tiếp `E_BLOCKED` (HTTP 403/429 từ Flashscore) ⇒ tạm dừng crawl 30 phút (`E_SOURCE_PAUSED`), gửi email cho admin.
- **Leo thang:** lặp lại 3 lần trong 24 h ⇒ dừng đến khi admin mở lại.
- **Trong lúc ngắt:** thư viện vẫn xem được bình thường.

---

## 11. Thay đổi front-end

| Trang | Nội dung |
| --- | --- |
| `index.html` (MỚI, `cloud/static/`) | Đăng nhập / đăng ký / quên mật khẩu; **Thư viện** (ô dán link Flashscore + danh sách trận, tìm kiếm, phân trang); **Admin** (người dùng, cài đặt, ngắt mạch). Dùng cùng token CSS đỏ–trắng và Inter |
| `match_report.html` | Dashboard + PDF **giữ nguyên**. Thêm nạp theo `mid` (`/m/{mid}` hoặc `?mid=`) |

Cách nạp theo `mid` trong `match_report.html` (🟡 **Q-E**):

| Lựa chọn | Mô tả |
| --- | --- |
| ★ (a) | Thêm một khối `<script>` **mới** ở cuối file: nếu URL có `mid` ⇒ gọi `GET /api/library/{mid}`, gán `state.*` như `App.buildFromUrl` rồi gọi `App.enter()`. Khối này không sửa vùng đóng băng; chỉ cần thêm một cửa sổ "insert-only" RD8 vào `tools/html_guard.py` |
| (b) | Sửa `Api`/`App` (vùng đóng băng) để luồng dán link gọi API thư viện. Phải mở khoá vùng core |

Theo (a):

- Ô dán link trong `match_report.html` vẫn dùng `POST /api/matches` + poll như hiện nay. API cloud giữ **cùng hình dạng response**.
- Khi trận đã có sẵn, server trả ngay `{status:"done", result}`, nên dashboard hiện ra không cần đổi JS.
- Nút "New match" quay về màn hình nhập như cũ; trang Thư viện là trang riêng.

Chế độ local (`python server.py`) không có trang Thư viện và không cần đăng nhập — **giữ nguyên** 🔒.

---

## 12. Triển khai và vận hành

### 12.1 Dựng máy (một lần)

1. Đăng ký Oracle Cloud (cần thẻ để xác minh); chọn home region có capacity A1.
2. Tạo VM: `VM.Standard.A1.Flex`, **2 OCPU / 12 GB** (không vượt hạn mức Always Free ⚠), Ubuntu 24.04 ARM64, ổ boot 50–100 GB. Mở 80/443 trong security list.
3. Cài Docker + Compose plugin, `ufw`, `unattended-upgrades`, swap 2 GB.
4. DuckDNS: tạo tên miền, cron cập nhật IP (IP công khai của Oracle thường cố định khi dùng reserved IP).
5. `git clone` repo private ⇒ tạo `deploy/.env` từ `.env.example` ⇒ `docker compose up -d --build`.
6. Tạo admin đầu tiên: `docker compose exec web python -m cloud.admin create --email …`.
7. UptimeRobot giám sát `https://<tên>.duckdns.org/api/health`.

### 12.2 Phác thảo `docker-compose.yml`

```yaml
services:
  caddy:
    image: caddy:2            # ghim bản cụ thể khi triển khai
    ports: ["80:80", "443:443"]
    volumes: [./Caddyfile:/etc/caddy/Caddyfile:ro, caddy_data:/data]
    depends_on: [web]
    restart: unless-stopped
  web:
    build: {context: .., dockerfile: deploy/Dockerfile.web}
    env_file: .env
    volumes: [appdata:/data]
    mem_limit: 512m
    restart: unless-stopped
  worker:
    build: {context: .., dockerfile: deploy/Dockerfile.worker}   # FROM image Playwright Python v1.60 (ARM64 ⚠)
    env_file: .env
    environment: {FS_PARALLEL: "3"}
    volumes: [appdata:/data]
    shm_size: 1gb
    mem_limit: 4g
    restart: unless-stopped
volumes: {appdata: {}, caddy_data: {}}
```

⚠ Image Playwright chính thức cho Python: phải kiểm tra có bản `linux/arm64` (`docker manifest inspect mcr.microsoft.com/playwright/python:v1.60.0-noble`) ở P0. Nếu không có ⇒ dùng `python:3.14-slim` + `playwright install --with-deps chromium` (Playwright hỗ trợ Chromium trên Linux ARM64).

### 12.3 Sao lưu, cập nhật, giám sát

| Việc | Cách làm |
| --- | --- |
| Sao lưu | Cron 03:00: `sqlite3 app.db ".backup"` ⇒ nén ⇒ tải lên Object Storage; giữ 14 bản. **Diễn tập khôi phục ở P4** và mỗi quý |
| Cập nhật ứng dụng | `git pull` ⇒ `docker compose up -d --build`; mỗi bản phát hành gắn tag git để quay lui |
| Migration DB | `cloud/migrations/NNN_*.sql`, chạy tự động khi `web` khởi động; sao lưu trước khi chạy |
| Canary Flashscore | Cron hằng đêm chạy `crawl()` trên trận tham chiếu `vLuGlk0n` ⇒ lỗi thì gửi email cho admin (DOM Flashscore đổi). Cũng giữ cho VM không bị coi là "nhàn rỗi" |
| Giám sát | UptimeRobot + `/api/health` (DB, heartbeat worker, độ dài hàng đợi); cảnh báo khi ổ đĩa > 80% |
| Runbook | `deploy/runbook.md`: khởi động lại, khôi phục, xoay khoá phiên, khoá tài khoản, xử lý khi Oracle thu hồi máy (dựng lại trên GCP e2-micro từ bản sao lưu) |

---

## 13. Không hồi quy (bắt buộc)

| # | Bất biến | Cách đảm bảo |
| --- | --- | --- |
| R1 | `python server.py` (local) chạy y như hiện nay | Không sửa `server.py`; toàn bộ `tests/e2e`, `tests/live` hiện có giữ nguyên và phải xanh |
| R2 | `crawler/` không đổi hành vi | Bản cloud chỉ **gọi** `crawl()`; `tests/unit` + live panel xanh |
| R3 | Dashboard, PDF, demo/OCR không đổi | Guard HTML (RD1–RD7 + RD8 insert-only nếu Q-E=a), golden demo, golden OCR |
| R4 | Hợp đồng `result` / `state` không đổi | Thư viện lưu nguyên JSON `schemaVersion` 2; test so `GET /api/library/{mid}` với fixture |

---

## 14. Kiểm thử và nghiệm thu

| Lớp | Nội dung |
| --- | --- |
| Unit (`tests/cloud/`) | Băm/kiểm tra mật khẩu, phiên, CSRF, token email (hết hạn, dùng 1 lần), hạn mức, khử trùng lặp job, ngắt mạch, migration |
| Tích hợp | Web + SQLite tạm + worker giả (runner giả như `tests/e2e/test_url_flow.py`): đăng ký → xác minh → duyệt → đăng nhập → tạo báo cáo → thư viện → chia sẻ → thu hồi |
| Bảo mật | Không đăng nhập ⇒ 401 ở mọi API cần quyền; CSRF thiếu/sai ⇒ 403; người dùng A không làm mới/xoá trận của B (IDOR); thử sai mật khẩu bị chặn; header bảo mật có mặt; cookie đủ cờ |
| e2e trình duyệt | Đăng nhập → dán link (fixture) → dashboard → Export PDF; mở `/m/{mid}` từ thư viện; link chia sẻ ở cửa sổ ẩn danh |
| Tải | Script Python: 50 phiên xem thư viện đồng thời + 20 job xếp hàng ⇒ p95 API < 500 ms, không lỗi |
| Live (trên VM) | `FS_LIVE=1` panel 5 trận tham chiếu chạy **từ IP của VM** (P0 và hằng đêm) |
| Nghiệm thu | Toàn bộ test cũ + mới xanh; diễn tập khôi phục thành công; checklist bảo mật §9 đủ; bạn đăng nhập và tạo báo cáo thật trên tên miền |

---

## 15. Kế hoạch triển khai

| Phase | Việc chính | Đầu ra |
| --- | --- | --- |
| **P0** (1–2 ngày) | (1) Bạn quyết G0 (§3). (2) Tạo VM Oracle, cài Docker, chạy crawler hiện có từ VM trên 9 trận tham chiếu; đo RAM/thời gian; kiểm tra image ARM64 | Báo cáo go/no-go. **No-go nếu Flashscore chặn IP Oracle** ⇒ quay lại chọn hạ tầng/nguồn dữ liệu |
| P1 (3–4 ngày) | `cloud/db.py`, migration, `jobs.py`, `worker.py`, `datasource.py`, Dockerfile, compose, Caddyfile; API job tương thích hình dạng hiện tại | Chạy được trên máy dev bằng `docker compose` |
| P2 (3–4 ngày) | `auth.py`, `mail.py`, trang đăng nhập/đăng ký/quên mật khẩu, admin cơ bản | Test bảo mật xanh |
| P3 (3–4 ngày) | `library.py`, trang Thư viện, `/m/{mid}`, chia sẻ, làm mới; RD8 cho `match_report.html` (nếu Q-E=a) | e2e xanh; guard HTML xanh |
| P4 (2–3 ngày) | Hạn mức, ngắt mạch, CSP, sao lưu + diễn tập khôi phục, health, canary | Checklist §9, §12.3 |
| P5 (1–2 ngày) | Triển khai VM thật, DuckDNS, HTTPS, closed beta với vài người | 1 tuần ổn định |
| P6 | Theo G0: mở đăng ký công khai / đổi `DataSource` | Bạn duyệt |

Mỗi phase dừng lại báo cáo; không chuyển phase khi test đỏ. Không commit/push khi bạn chưa yêu cầu.

---

## 16. Rủi ro

| # | Rủi ro | Khả năng | Ảnh hưởng | Giảm thiểu |
| --- | --- | --- | --- | --- |
| RK1 | Vi phạm điều khoản Flashscore / bị yêu cầu dừng | **Cao** khi công khai | Cao | Cổng G0; chế độ nhóm kín; cache; `DataSource` để đổi nguồn |
| RK2 | Flashscore chặn IP trung tâm dữ liệu | TB | Cao | Thử ở P0; ngắt mạch; hạn mức toàn hệ thống; thư viện vẫn xem được |
| RK3 | Oracle thu hồi máy / giảm hạn mức / hết capacity | TB | Cao | Canary hằng đêm; sao lưu ngoài máy; runbook dựng lại trên GCP e2-micro |
| RK4 | Lạm dụng (spam đăng ký, crawl hàng loạt) | TB | TB | Xác minh email, admin duyệt, hạn mức, giới hạn tốc độ |
| RK5 | Lộ dữ liệu người dùng | Thấp | Cao | §9; review bảo mật trước P5; chỉ lưu email |
| RK6 | Flashscore đổi DOM | Đã từng xảy ra | TB | Canary hằng đêm + quy trình fixture/test hiện có |
| RK7 | Hết gói email miễn phí | Thấp | Thấp | Chỉ gửi email xác minh/đặt lại mật khẩu; admin kích hoạt thủ công được |
| RK8 | Quá tải khi nhiều người dùng | Thấp (nhóm kín) | TB | Thư viện + khử trùng lặp; hàng đợi có giới hạn; khi vượt ⇒ cần trả phí |

---

## 17. Quyết định cần bạn duyệt

Mỗi mục có đề xuất mặc định (★). Bạn chỉ cần trả lời những mục muốn khác.

| ID | Câu hỏi | Lựa chọn |
| --- | --- | --- |
| **Q-A** | **Cổng G0 — nguồn dữ liệu khi mở cho người ngoài** (§3) | ★ Xây theo thiết kế, khởi chạy **nhóm kín** (closed beta), song song tìm giấy phép hoặc API có giấy phép · Mở công khai ngay bằng crawler Flashscore (không khuyến nghị) · Chuyển hẳn sang API có giấy phép trước khi làm |
| Q-B | Đăng ký tài khoản | ★ Tự đăng ký + xác minh email + **admin duyệt** · Tự đăng ký + xác minh email (không cần duyệt) · Chỉ admin mời |
| Q-C | Hạn mức (§10.2) | ★ 10 crawl mới/người/ngày, 30 crawl/giờ toàn hệ thống · Giá trị khác |
| Q-D | Link chia sẻ công khai chỉ-xem (không cần đăng nhập) | ★ Có, admin/người tạo bật từng trận, thu hồi được · Không — chỉ thành viên đã đăng nhập |
| Q-E | Cách `match_report.html` nạp trận từ thư viện (§11) | ★ (a) thêm khối script mới, không sửa vùng đóng băng (thêm RD8) · (b) sửa `Api`/`App` |
| Q-F | Framework web | ★ FastAPI + Uvicorn (thêm 2 phụ thuộc, ghim phiên bản) · Giữ stdlib `http.server` |
| Q-G | Tên miền | ★ DuckDNS miễn phí · Tên miền riêng (~10 USD/năm, ngoài phạm vi 0 đồng) |

---

## Phụ lục A — Biến môi trường (`deploy/.env.example`)

| Biến | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `APP_BASE_URL` | `https://tenban.duckdns.org` | Dùng trong email và kiểm tra `Origin` |
| `SESSION_SECRET` | 64 ký tự ngẫu nhiên | Khoá phụ cho token |
| `DB_PATH` | `/data/app.db` | |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `MAIL_FROM` | | Gửi email |
| `REGISTRATION` | `approval` \| `open` \| `invite` | Q-B |
| `QUOTA_USER_DAILY`, `QUOTA_GLOBAL_HOURLY`, `QUEUE_MAX` | `10`, `30`, `20` | Q-C |
| `FS_PARALLEL`, `FS_HEADLESS` | `3`, `1` | Như hiện nay |
| `OCI_BUCKET`, `OCI_NAMESPACE`, … | | Sao lưu |

## Phụ lục B — Phác thảo `Caddyfile`

```text
{$APP_DOMAIN} {
  encode gzip
  request_body { max_size 64KB }
  header {
    Strict-Transport-Security "max-age=15552000"
    X-Content-Type-Options nosniff
    X-Frame-Options DENY
    Referrer-Policy same-origin
  }
  reverse_proxy web:8000
}
```

## Phụ lục C — Nguồn tham khảo (tra ngày 2026-10-13)

- Điều khoản Flashscore: [flashscore.com/terms](https://www.flashscore.com/terms); điều khoản Livesport: [livesport.eu/terms/flashscore_ae](https://livesport.eu/terms/flashscore_ae)
- Oracle Always Free: [tài liệu Oracle](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm); thay đổi hạn mức 2026: [InfoQ](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/), [Oracle Customer Connect](https://community.oracle.com/customerconnect/discussion/974422/ampere-a1-instance-disabled-after-aug-18-2026-always-free-limit-enforcement-tenancy-now-compliant)
- Playwright trong Docker: [playwright.dev/python/docs/docker](https://playwright.dev/python/docs/docker)

---

## 18. Ghi nhận khi triển khai (2026-10-13)

### 18.1 Đã làm

| Phase | Kết quả |
| --- | --- |
| P1 | `cloud/` (`config`, `db` + `migrations/001_init.sql`, `jobs`, `worker`, `datasource`, `library`, `errors`); Docker: `deploy/Dockerfile` (1 image cho `web` + `worker`, base `mcr.microsoft.com/playwright/python:v1.60.0-noble` — ✅ có bản amd64 + arm64), `docker-compose.yml`, `Caddyfile`, `.env.example` |
| P2 | `auth.py` (đăng ký → xác minh email → admin duyệt; đăng nhập; quên/đặt lại mật khẩu; xoá tài khoản; mời; vai trò), `security.py` (scrypt, token), `ratelimit.py`, `mail.py` (SMTP hoặc chế độ console) |
| P3 | `cloud/static/index.html` (Đăng nhập / Đăng ký / Thư viện / Admin / Tài khoản), `/m/{mid}`, link chia sẻ chỉ-xem, làm mới; khối RD8 trong `match_report.html` |
| P4 | Hạn mức người dùng/hệ thống/hàng đợi, ngắt mạch nguồn dữ liệu (2 lần `E_BLOCKED` ⇒ dừng 30 phút; 3 lần/24 h ⇒ chờ admin), CSP + header bảo mật, `/api/health` (503 khi worker im lặng > 60 s), `cloud/backup.py` (sao lưu + khôi phục + tải lên Object Storage qua PAR), `cloud/canary.py`, `cloud/admin.py` (CLI) |
| P0, P5 | **Người dùng thực hiện** theo [deploy/runbook.md](../deploy/runbook.md) (tạo VM Oracle, kiểm tra Flashscore không chặn IP, DuckDNS, SMTP, cron, UptimeRobot) |

### 18.2 Điểm lệch / bổ sung so với v0.1

| # | v0.1 | Thực tế | Lý do |
| --- | --- | --- | --- |
| 1 | CSP chặt cho mọi trang | Trang báo cáo (`/report`, `/m/{mid}`) có thêm `'unsafe-eval'`; trang đăng nhập/thư viện/admin **không** | Tesseract.js (OCR của nút demo, `LineupOCR` đóng băng) đánh giá chuỗi JS — kiểm chứng bằng e2e. Mọi dữ liệu người dùng vẫn được escape |
| 2 | — | Bản cloud **bắt buộc `?mid=`** trong link (`E_MID_REQUIRED`); bản local vẫn chỉ cảnh báo | Không có `mid` thì không xác định được khoá thư viện |
| 3 | Trả `{status:"done", result}` khi trận có sẵn | `POST /api/matches` luôn trả `202 {jobId, status, mid}`; trận có sẵn ⇒ tạo job `done` (cờ `cached=1`, không tính hạn mức) | `Api.start`/`Api.wait` (vùng đóng băng) dùng được nguyên vẹn |
| 4 | Thêm token CSRF vào `Api` | Khối RD8 bọc `window.fetch` khi ở chế độ cloud để tự gắn `X-CSRF-Token` cho lệnh ghi cùng origin; bọc `Api.wait`/`App.reset` để đổi địa chỉ trang (`/m/{mid}` ↔ `/report`) | Không sửa byte nào của vùng đóng băng (guard 6/6) |
| 5 | Cửa sổ RD8 insert-only trước `</body>` | Cửa sổ bắt đầu 2 dòng trước `</body>` | difflib gióng khối chèn trước `</script>` của khối `Report` |
| 6 | Hai Dockerfile | Một image, hai lệnh chạy | Giống nhau 100% mã nguồn; đơn giản hơn |
| 7 | — | Đăng ký trùng email trả cùng phản hồi như email mới, gửi thư báo cho chủ email | Không để lộ email nào đã có tài khoản |
| 8 | — | Link chia sẻ sai/đã thu hồi ⇒ chuyển về trang đăng nhập | Hành vi nhất quán với trang cần đăng nhập |
| 9 | — | Biến `TZ=Asia/Ho_Chi_Minh` trong `deploy/.env` | Container chạy UTC ⇒ Flashscore hiện giờ bóng lăn theo UTC (12:00 thay vì 19:00); kiểm chứng trên Docker |
| 10 | — | Đã chạy thử **toàn bộ stack bằng Docker Compose trên máy dev** (Caddy HTTPS `localhost` + web + worker): crawl trận thật trong container 35,8 s, PDF 4 trang, HSTS + CSP, sao lưu/khôi phục trong container | Kiểm chứng trước khi lên Oracle |

### 18.3 Kiểm thử

| Bộ | Nội dung |
| --- | --- |
| `tests/cloud/test_cloud_unit.py` | Mật khẩu, token, migration, ràng buộc schema (email không phân biệt hoa thường, 1 job đang chạy/trận, FK cascade), chuẩn hoá link |
| `tests/cloud/test_cloud_api.py` | Server Uvicorn thật + nguồn giả. Gồm: đăng ký/xác minh/duyệt/đăng nhập, không lộ email, lỗi đăng nhập chung chung + giới hạn tốc độ, quên mật khẩu, xoá tài khoản, admin không tự khoá mình, CSRF + Origin, 401/403 cho mọi API cần quyền, header bảo mật, 413, job → thư viện, khử trùng lặp, hạn mức, ngắt mạch, IDOR, link chia sẻ, làm mới, job treo được xếp lại, health, sao lưu/khôi phục |
| `tests/cloud/test_cloud_ui.py` | Trình duyệt thật. Gồm: đăng nhập → dán link → `/m/{mid}` → Line-ups; thư viện + bật chia sẻ; người xem ẩn danh; `/report` qua `Api` đóng băng + CSRF; PDF Coach brief dưới CSP; OCR demo dưới CSP; đăng ký → xác minh → admin duyệt; **không có vi phạm CSP nào trong console** |

Tổng toàn dự án: **137 test** unit/e2e xanh (6 test live bỏ qua khi không có `FS_LIVE=1`). Guard HTML: 6/6 vùng đóng băng, RD1–RD8, golden demo, golden OCR xanh.

### 18.4 Việc người dùng phải tự làm

Xem [deploy/runbook.md](../deploy/runbook.md):

1. Đăng ký Oracle Cloud và tạo VM ARM 2 OCPU / 12 GB.
2. Mở cổng 80/443.
3. Tạo tên miền DuckDNS.
4. **P0:** chạy canary trên 4 trận tham chiếu từ VM. Bị chặn ⇒ dừng.
5. Điền `.env` ⇒ `docker compose up -d --build` ⇒ tạo admin.
6. Cài cron (sao lưu, canary), bucket + PAR cho sao lưu, UptimeRobot.
7. Cổng G0: giữ chế độ đăng ký có duyệt cho đến khi có giấy phép dữ liệu.

## 19. Phương án Hugging Face Spaces (2026-10-29)

Người dùng có tài khoản **PRO** và chọn chạy trên Hugging Face. Lưu bền chọn phương án miễn phí: đồng bộ với Dataset riêng tư.

| Hạng mục | Thiết kế |
| --- | --- |
| Loại Space | Docker Space public, phần cứng CPU basic (2 vCPU / 16 GB), cổng 7860 |
| Tiến trình | `python -m cloud.hf_main`: web (Uvicorn) + worker + vòng đồng bộ trong **một** container (Space chỉ có 1 container). Không cần Caddy: Hugging Face lo HTTPS |
| Địa chỉ | `APP_BASE_URL = https://$SPACE_HOST` (biến Hugging Face tự đặt). Cookie `Secure`; người dùng mở trực tiếp `*.hf.space`. Khung nhúng trên huggingface.co không dùng được: cookie bên thứ ba + `X-Frame-Options: DENY` |
| Lưu bền | Ổ đĩa Space bị xoá khi khởi động lại ⇒ `cloud/hfsync.py`. Khi khởi động: tải `app.db.gz` từ Dataset `<user>/<space>-data` về (nếu ổ trống). Định kỳ `HF_SYNC_MINUTES` (10) và khi tắt: bản sao lưu SQLite nhất quán (API backup) được nén và upload, **chỉ khi dữ liệu đổi**. Lịch sử commit của Dataset = các phiên bản cũ. RPO ≤ 10 phút |
| Admin đầu tiên | Không có shell trên Space ⇒ Variable `BOOTSTRAP_ADMIN_EMAIL` + Secret `BOOTSTRAP_ADMIN_PASSWORD` (người dùng tự nhập). Chỉ tạo khi DB chưa có admin hoạt động; không bao giờ ghi đè |
| Ngủ | CPU basic ngủ sau 48 h không có truy cập ⇒ UptimeRobot (miễn phí) gọi `/api/health` 5 phút/lần (không được Hugging Face cam kết) |
| Bí mật | `HF_TOKEN` (Secret, ghi Dataset), SMTP (Secrets). Mã nguồn hiển thị công khai ở tab Files — không chứa bí mật |
| Đẩy code | `tools/push_hf_space.py`: chỉ gói `crawler/`, `cloud/`, `match_report.html`, `requirements-cloud.txt`, `deploy/hf/{Dockerfile,README.md}`; tạo Space + Dataset; đặt Variables/Secret |
| Kiểm thử | `tests/cloud/test_hf.py`: đồng bộ chỉ khi đổi, khôi phục trên ổ trống, không ghi đè DB đang có, admin đầu tiên chỉ tạo một lần, gói file chỉ chứa file chạy |

Hướng dẫn thao tác: [deploy/hf/runbook-hf.md](../deploy/hf/runbook-hf.md).

### 19.1 Sự cố sau khi triển khai (2026-10-29)

| Hiện tượng | Nguyên nhân (kiểm chứng ngay trên Space bằng `cloud/diag.py`) | Sửa |
| --- | --- | --- |
| `E_INTERNAL: TimeoutError at step "player_stats": Locator.click: Timeout 5000ms` (trên máy local không bị) | Trên máy 2 vCPU, tải 3–4 trang Flashscore song song (IP Mỹ còn có tab cá cược + quảng cáo) làm menu chọn đội (Radix) không mở kịp. Một trang đơn lẻ trên Space thì bình thường | `FS_PARALLEL=1` cho Space (`tools/push_hf_space.py`): `=3` lỗi 9/9, `=1` thành công 12/12 (33–43 s/trận). Crawler thêm `_click_retrying` (3 lần, Escape, lần cuối `force`) và `bring_to_front()` — vô hại ở local |
| 1/9 lần `W_NO_LINEUPS` | Trang line-ups lỡ lần đầu trên máy chậm | `run.py`: thử lại 1 lần bằng trang mới nếu còn ngân sách thời gian |
| Dataset sao lưu bị tạo **public** | `huggingface_hub` 2.x bỏ qua `private=True` | Dùng `visibility="private"` + kiểm tra/ép riêng tư mỗi lần khởi động; Dataset đã chuyển private khi còn trống |

