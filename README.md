# Automation Football Dashboard

Dán **một link trận đấu trên Flashscore** → nhận ngay **dashboard phân tích hiệu suất**, **bảng chỉ số cầu thủ** và **match report PDF** cho trận đó.

Dự án dành cho Analyst / Coach: giao diện trắng–đỏ, trung lập hai đội, tiếng Anh; tài liệu kỹ thuật bằng tiếng Việt.

## Tính năng

- **Nhập liệu bằng một link** Flashscore (giữ tham số `?mid=`); crawler dùng Playwright (Chromium headless) lấy header, timeline, player stats, line-ups (kèm toạ độ sơ đồ) và team stats.
- **8 tab**: Summary · Team · Attack · Passing · Defending · Goalkeeping · Players · Line-ups, cùng bộ lọc Both teams / Home / Away.
- **Insight tự động** (ngưỡng đặt ở một chỗ duy nhất: `INSIGHT_THRESHOLDS` trong `match_report.html`), đánh giá cầu thủ theo vai trò GK/DEF/MID/FWD, per-90, xếp hạng trong trận.
- **Export PDF**: *Full analyst report* (≤ 14 trang) hoặc *Coach brief* (4 trang).
- **Hai chế độ chạy**: local một người dùng (`server.py`) và **bản cloud nhiều người dùng** (FastAPI + SQLite: đăng nhập, thư viện trận, chia sẻ, hạn mức), có cấu hình Docker và Hugging Face Spaces.
- Nút **demo** chạy offline với dữ liệu mẫu (line-ups đọc bằng OCR Tesseract).

## Bắt đầu nhanh (chế độ local)

Yêu cầu: Windows/Linux/macOS, Python 3.12+ (đã dùng 3.14), kết nối mạng.

```powershell
pip install -r requirements.txt
playwright install chromium

python server.py          # mở http://127.0.0.1:8778 → dán link → Generate report
```

Chạy crawler riêng bằng dòng lệnh:

```powershell
python -m crawler "<link trận>" --out result.json
```

Biến môi trường hữu ích: `FS_PORT` (mặc định 8778) · `FS_PARALLEL` (số trang tải song song, mặc định 3) · `FS_HEADLESS=0` (xem trình duyệt) · `FS_DEBUG=1` (lưu HTML bước lỗi vào `debug/`).

> Chỉ hỗ trợ trận **đã kết thúc** và giải có tab *Player stats*. Mã Python (`crawler/`, `server.py`) chỉ nạp lúc khởi động — sửa xong phải khởi động lại server.

## Bản cloud (nhiều người dùng)

```powershell
pip install -r requirements-cloud.txt
python -m cloud                                   # web + worker → http://127.0.0.1:8000
python -m cloud.admin create-admin --email ban@example.com

cd deploy; docker compose up -d --build          # cả stack (Caddy + web + worker), cần deploy/.env
```

- Hướng dẫn dựng VM và vận hành: [deploy/runbook.md](deploy/runbook.md); triển khai lên Hugging Face Spaces: [deploy/hf/runbook-hf.md](deploy/hf/runbook-hf.md).
- Mặc định `REGISTRATION=approval` (nhóm kín). Điều khoản Flashscore cấm scrape và công khai lại dữ liệu — **không** mở đăng ký công khai khi chưa cân nhắc vấn đề pháp lý (xem [thiết kế cloud](docs/detailed-design-cloud-deployment.md) §3).

## Cấu trúc thư mục

| Đường dẫn | Vai trò |
| --- | --- |
| `match_report.html` | Web app một file: CSS, HTML, JS (state, `Metrics`, `Insights`, `Views`, `Report` PDF). Không build step |
| `server.py` | Server stdlib cho chế độ local, API `/api/matches` |
| `crawler/` | Playwright crawler: header, player stats, timeline, lineups, team stats, kiểm tra chéo |
| `cloud/` | Bản cloud: auth, hàng đợi job, thư viện, chia sẻ, backup, admin CLI |
| `deploy/` | Dockerfile, docker-compose, Caddyfile, runbook, cấu hình Hugging Face |
| `tools/` | Công cụ bảo vệ HTML (`verify_frozen`, `check_diff_budget`, `html_guard`), golden snapshot, lưu fixture |
| `tests/` | `unit/`, `e2e/`, `cloud/`, `live/` (chạm Flashscore, chỉ chạy khi `FS_LIVE=1`), `fixtures/` |
| `docs/` | Thiết kế chi tiết: luồng URL, redesign dashboard, triển khai cloud |

## Kiểm thử

```powershell
python -m unittest discover -s tests -t .          # unit + e2e (cần mạng cho CDN; FS_SKIP_PDF=1 bỏ test PDF chậm)
python tools/verify_frozen.py
python tools/check_diff_budget.py
python tools/golden_demo.py --check

$env:FS_LIVE="1"; python -m unittest discover -s tests/live -t .   # test live, ~10 phút
```

## Tài liệu

- [CLAUDE.md](CLAUDE.md) — tổng quan dự án, mô hình dữ liệu, quy ước, guardrails
- [docs/detailed-design-url-ingestion.md](docs/detailed-design-url-ingestion.md) — luồng dán link + selector đã kiểm chứng
- [docs/detailed-design-dashboard-redesign.md](docs/detailed-design-dashboard-redesign.md) — dashboard & PDF
- [docs/detailed-design-cloud-deployment.md](docs/detailed-design-cloud-deployment.md) — bản cloud

## Lưu ý pháp lý

Dữ liệu thuộc Flashscore. Dự án phục vụ mục đích học tập / phân tích nội bộ; hãy tự kiểm tra điều khoản sử dụng của Flashscore trước khi dùng với số đông hoặc công khai kết quả.
