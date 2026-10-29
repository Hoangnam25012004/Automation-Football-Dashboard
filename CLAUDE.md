# CLAUDE.md — Automation Football Dashboard

Tài liệu giới thiệu dự án cho Claude Code (và người mới tham gia). Viết bằng tiếng Việt; tên hàm, selector, thuật ngữ kỹ thuật giữ nguyên tiếng Anh.

| | |
| --- | --- |
| Cập nhật | 2026-10-13 (bản cloud) |
| Môi trường | Windows 11 · Python 3.14 · Playwright 1.60 (Chromium đã cài) · dự án không dùng Node/bundler (không có `package.json`) |
| Git | Repo git. `d4a4da6` (root) = trước luồng URL. Nhánh **`dashboard-redesign`**: `98e5623` = luồng URL Phase 0–5, gắn tag **`redesign-baseline`** — công cụ bảo vệ HTML so với tag này. Danh tính commit đặt riêng cho repo; `core.autocrlf=false` (mọi file dùng LF) |
| Trạng thái | (1) Luồng "dán 1 link Flashscore" đã triển khai và commit ([docs/detailed-design-url-ingestion.md](docs/detailed-design-url-ingestion.md), Phase 0–5). (2) **Thiết kế lại dashboard + PDF** cho Analyst/Coach đã triển khai R0–R4 theo [docs/detailed-design-dashboard-redesign.md](docs/detailed-design-dashboard-redesign.md) (2026-10-13), **chưa commit, chờ nghiệm thu (R5)**. (3) **Bản cloud nhiều người dùng** (`cloud/`, `deploy/`) đã triển khai phần mã P1–P4 theo [docs/detailed-design-cloud-deployment.md](docs/detailed-design-cloud-deployment.md); hạ tầng (P0/P5) do người dùng làm theo [deploy/runbook.md](deploy/runbook.md); **chưa commit** |

## 1. Dự án là gì

Công cụ tạo **dashboard phân tích hiệu suất + bảng player stats + match report (PDF)** cho một trận bóng đá từ dữ liệu Flashscore.

Giao diện là một file HTML ([match_report.html](match_report.html)). Nội dung gồm:

- match header: tỉ số, logo, người ghi bàn, giải/ngày/sân/trọng tài, xG · Shots · On target · Possession;
- 8 tab (theme trắng–đỏ, trung lập 2 đội, tiếng Anh): **Summary** (insight tự động, result vs performance, so sánh đội, timeline, theo hiệp, top performers) · **Team** (theo pha) · **Attack** · **Passing** · **Defending** · **Goalkeeping** · **Players** (đánh giá theo vai trò GK/DEF/MID/FWD, per-90, xếp hạng trong trận, hồ sơ cầu thủ) · **Line-ups** (id nội bộ `'overall'`);
- bộ lọc Both teams / Home / Away (chỉ ở Attack, Passing, Defending, Players);
- **Export PDF** = Full analyst report (≤ 14 trang); nút ▾ chọn thêm **Coach brief** (4 trang).

```text
Người dùng dán link ─▶ match_report.html ─POST /api/matches─▶ server.py (127.0.0.1:8778)
                                ▲                                   │ 1 worker thread
                                └── poll GET /api/matches/{id} ◀────┤ crawler/ + Playwright (Chromium headless)
                                    → state.* → App.enter() → Render(vỏ) → Views ▼
                                                              www.flashscore.com
```

Quyết định đã chốt với người dùng: (1) **thay hẳn** 3 ô upload xlsx bằng 1 ô nhập link; (2) **chạy local**; (3) lineups lấy **dữ liệu có cấu trúc từ DOM** (không OCR) đưa thẳng vào `state.lineupText`. Nút demo vẫn giữ và vẫn dùng OCR như cũ.

## 2. Cấu trúc thư mục

| Đường dẫn | Vai trò |
| --- | --- |
| [match_report.html](match_report.html) | Web app 1 file. CSS (design system đỏ–trắng, token ở `:root`) · HTML · 4 `<script>` inline: demo data · core `state`/`U`/ô URL/`Api`/`App` · `LineupOCR` + `Theme` + `Metrics` (dữ liệu, hàm thuần) + `INSIGHT_THRESHOLDS`/`Insights` + `Views` (8 tab) + vỏ `Render` · `Report` (PDF) + vỏ `Exporter`. CDN: Chart.js 4.4.1, jsPDF 2.5.1, html2canvas 1.4.1; Tesseract.js chỉ nạp khi demo cần OCR |
| [server.py](server.py) | Server stdlib: phục vụ đúng `/` và `/match_report.html`, API `POST /api/matches`, `GET /api/matches/{id}`, `GET /api/health`; hàng đợi 1 job chạy + 1 chờ |
| [crawler/](crawler/) | `urls` (kiểm tra/dựng lại link, giữ `?mid=`) · `browser` (Chromium, chặn ảnh/font, banner cookie) · `header` · `player_stats` (7 tab × 2 đội) · `timeline` · `lineups` (cấu trúc + toạ độ sơ đồ) · `team_stats` (tab STATS cấp đội, 3 phạm vi) · `assemble` (JSON + kiểm tra chéo) · `run` (điều phối, tiến độ 11 bước, ngân sách 150 s) · `errors` (mã lỗi/cảnh báo) · `__main__` (CLI) |
| [tools/](tools/) | `verify_frozen.py`, `check_diff_budget.py`, `html_guard.py` (bảo vệ HTML) · `golden_demo.py` (golden snapshot luồng demo) · `capture_fixtures.py` (lưu fixture từ trang thật) |
| [tests/](tests/) | `unit/` (offline) · `e2e/` (giao diện + server với runner giả; cần mạng cho CDN) · `live/` (chạm flashscore.com, chỉ chạy khi `FS_LIVE=1`) · `fixtures/` · `golden/demo_views.json` · `output/` (bỏ qua trong git) |
| [cloud/](cloud/) | **Bản cloud** (FastAPI + SQLite): `app` (route, CSRF, CSP) · `auth` (tài khoản, phiên) · `security` (scrypt, token) · `jobs` (hàng đợi, khử trùng lặp, hạn mức, ngắt mạch) · `worker` (gọi `crawler`) · `library` (thư viện trận, chia sẻ) · `datasource` (nguồn cắm thay) · `mail` · `ratelimit` · `backup` · `canary` · `admin` (CLI) · `migrations/` · `static/index.html` (đăng nhập/thư viện/admin) |
| [deploy/](deploy/) | `Dockerfile` (1 image cho web + worker), `docker-compose.yml` (caddy + web + worker), `Caddyfile`, `.env.example`, **`runbook.md`** (dựng VM Oracle → vận hành) |
| [requirements.txt](requirements.txt) | `playwright==1.60.0` (+ pillow, chỉ cho test) · [requirements-cloud.txt](requirements-cloud.txt): + `fastapi`, `uvicorn` (ghim phiên bản) |
| [.claude/launch.json](.claude/launch.json) | `app` = `python server.py` (8778) · `static` = `python -m http.server 8777` (cũ, chỉ demo chạy được) |
| [docs/detailed-design-url-ingestion.md](docs/detailed-design-url-ingestion.md) | Thiết kế chi tiết luồng URL + phụ lục selector/extractor đã kiểm chứng |
| [docs/detailed-design-dashboard-redesign.md](docs/detailed-design-dashboard-redesign.md) | Thiết kế lại dashboard + PDF: dữ liệu, `Metrics`/`Insights` (công thức, ngưỡng), design system, PDF, Change surface RD1–RD7; §15 = ghi nhận khi triển khai |

## 3. Mô hình dữ liệu của web (hợp đồng bất biến)

`match_report.html` cần 4 đối tượng bắt buộc trong `state` (+ 2 đối tượng tuỳ chọn từ `schemaVersion` 2). Mọi nguồn (demo, luồng URL; trước đây là xlsx) phải đưa về đúng hình dạng này. Server trả chúng trong `result.stats / summary / lineups / lineupImages / teamStats / meta`:

```js
state.data = {                       // bắt buộc  (= result.stats)
  matchTitle: "Johor DT  vs  Svay Rieng",   // 2 dấu cách quanh " vs "; Render tách bằng /\s+vs\s+/
  matchDate: "",                            // để rỗng như luồng cũ
  home: "JOH", away: "SVA",                 // mã đội = khoá tra cứu, không hiển thị
  teams: { JOH: { "Top Stats":{headers:["Player","Position",...], rows:[{Player, Position, ...}]},
                  Shots, Attack, Passes, Defense, Goalkeeping, General }, SVA: {...} }
}                                    // mọi giá trị ô là string: "9.0", "73/81 (90%)", "-"
state.summary = { events:[{minute,half,side,team,type,player,detail,score}],
                  homeLogo, awayLogo /*data URL*/, finalScore:{h,a} } | null
state.lineupImages = { formation, starting_xi, substituted, substitutes, coaches }
                     // luồng URL: PNG 1×1 trong suốt — chỉ là "công tắc" để renderOverall dựng thẻ Match story
state.lineupText   = { formation:{players:[{num,name,ok,side,x,y}],w:100,h:176}, starting_xi:[...],
                       substituted:{home,away}, substitutes:[...], coaches:{home,away} } | null
state.teamStats    = { overall:{rows:[{group,key,home,away,homePct,awayPct}]}, firstHalf, secondHalf,
                       possessionReliable } | null      // tab STATS cấp đội; demo = null
state.meta         = { competition, country, kickoff, referee, venue } | null   // trang trí; demo = null
```

`Metrics` ưu tiên số cấp đội của Flashscore (`teamStats`), thiếu thì cộng từ player stats (nhãn `*`/"derived"). Possession **không bao giờ suy ra**: khi Flashscore không có (50/50 ở mọi phạm vi ⇒ `possessionReliable=false`) hiện "Share of completed passes" thay thế.

Điểm tích hợp: `LineupOCR.run()` thoát sớm khi `state.lineupText` đã có ⇒ luồng URL không chạy OCR. Bất biến: `lineupImages[key]` tồn tại ⇔ `lineups[key]` khác `null`.

`event.type` dùng bộ nhãn mà `Views`/`Metrics` so khớp bằng regex: `Goal`, `Own goal`, `Penalty goal`, `Substitution`, `Yellow card`, `Second yellow (→ red)`, `Red card`, `VAR`, `Penalty missed`.

## 4. Chạy & phát triển

```powershell
pip install -r requirements.txt
playwright install chromium

python server.py                       # mở http://127.0.0.1:8778 → dán link → Generate report
python -m crawler "<link trận>" --out result.json     # chạy crawler bằng tay, in tóm tắt + cảnh báo

# Biến môi trường: FS_PORT (mặc định 8778) · FS_PARALLEL (số trang tải song song, mặc định 3; 1 = tuần tự) · FS_HEADLESS=0 (xem trình duyệt) · FS_DEBUG=1 (lưu HTML bước lỗi vào debug/)
```

Kiểm thử (chạy ở thư mục gốc):

```powershell
python -m unittest discover -s tests -t .                 # unit + e2e (cần mạng cho CDN; FS_SKIP_PDF=1 bỏ test PDF chậm)
$env:FS_LIVE="1"; python -m unittest discover -s tests/live -t .   # chạm flashscore.com (~10 phút)
python tools/verify_frozen.py ; python tools/check_diff_budget.py ; python tools/golden_demo.py --check
python tools/golden_ocr.py --check      # OCR line-ups của demo không đổi (hợp đồng B3; cần mạng cho Tesseract)
```

Bản cloud trên máy dev (`pip install -r requirements-cloud.txt`):

```powershell
python -m cloud                          # web + worker cùng tiến trình → http://127.0.0.1:8000 (DB ở data/app.db, thư in ra log)
python -m cloud.admin create-admin --email ban@example.com
cd deploy; docker compose up -d --build  # chạy cả stack như trên server (cần deploy/.env)
```

Test `tests/cloud/` tự bỏ qua nếu chưa cài FastAPI/Uvicorn.

Ngưỡng insight nằm ở `INSIGHT_THRESHOLDS` trong `match_report.html` (một chỗ duy nhất).

Front-end không có build step: sửa thẳng file HTML rồi tải lại trang. Server đọc lại file ở mỗi request. **Nhưng mã Python (crawler/server) chỉ nạp lúc khởi động** ⇒ sửa `crawler/` thì phải khởi động lại `python server.py` (đã gặp: server cũ ⇒ thiếu `teamStats`/`meta`).

## 5. Quy ước code

- **Python**: Playwright **sync API**, chỉ chạy trong MỘT worker thread của server (không asyncio). Docstring/comment/log tiếng Việt; thông điệp hiển thị trên UI tiếng Anh. Selector theo thứ tự ưu tiên `data-testid` → BEM ổn định (`smv__*`, `duelParticipant__*`, `detailScore__*`) → `[class*="…"]`. Class kiểu `wcl-side_YylQz` có **hậu tố hash đổi theo bản build**, không bao giờ dùng nguyên văn. Extractor DOM viết bằng một hàm JS chạy qua `page.evaluate`, trả về số lượng để tự kiểm.
- **Lỗi**: mọi lỗi dừng job là `CrawlError(code)` (`crawler/errors.py`); bất thường không chặn kết quả thì vào `warnings[]`. **Không bao giờ trả rỗng im lặng.**
- **JS trong HTML**: phong cách gọn (arrow function, `const`, template string), không framework/module; màu lấy từ CSS variable ở `:root` (Chart.js qua `Theme`, không màu cứng). Mỗi khối giao diện là hàm trả `{html, charts}` để dashboard và PDF dùng chung.
- **Design system** (redesign §7): một font Inter; cỡ chữ chỉ 12/14/18/22/24/40 px (mobile thêm 32); màu chữ chỉ `--ink`/`--ink-2`/`--ink-3`/`--brand`/trắng/`--pos`/`--neg`; đỏ = brand/đội nhà, **không bao giờ** nghĩa "xấu" (dùng `--neg` hổ phách). `tests/e2e/test_redesign.py` kiểm tự động.
- **Test**: `unittest` của stdlib. Test live phải có `@unittest.skipUnless(_support.LIVE, …)`. `tests/__init__.py` tắt ghi `.pyc` để thư mục gốc sạch.

## 6. Guardrails (BẮT BUỘC)

1. **Không đổi bất kỳ tính năng nào ngoài phạm vi đã được duyệt.** Yêu cầu chưa rõ, hoặc cần đụng vùng ngoài phạm vi → **hỏi lại người dùng trước**.
2. **Ba script legacy (`flashscore_*.py`) đã bị xoá ở Phase 5** theo yêu cầu người dùng; vẫn còn trong git ở commit baseline `d4a4da6` nếu cần tham khảo. Không khôi phục lại khi chưa được yêu cầu.
3. **`match_report.html` chỉ được khác tag `redesign-baseline` trong RD1–RD8** (redesign §10.1: CSS, header, markup dashboard, vùng `Render` cũ → `Theme`/`Metrics`/`Insights`/`Views`, vùng `Exporter` cũ → `Report`, 2 dòng RD7 trong `App`; **RD8** = khối `<script>` "cloud mode" trước `</body>` — cloud design §11, chỉ chạy khi `/api/me` của bản cloud trả JSON; với `server.py`/`file://` không làm gì). Mọi lần sửa HTML phải chạy `tools/check_diff_budget.py`, `tools/verify_frozen.py` (6/6 vùng đóng băng) và `tools/golden_demo.py --check`. **Vùng đóng băng**: head + CDN, màn hình nhập URL, loading overlay + toast, demo data, core (`state`/`TABS`/`U`/ô URL/`Api`/`App`), `LineupOCR`. Id/class mà `LineupOCR` điền (`lc-*`, `fm-*`, `ln-*`, `sub-*`) và id tab `'overall'` của Line-ups phải giữ. Muốn sửa thêm ⇒ cập nhật Change surface trong design doc **sau khi người dùng đồng ý**. Đổi giao diện có chủ đích ⇒ ghi lại golden: `python tools/golden_demo.py --write`.
4. **Đừng đọc/in cả file HTML**: hai dòng demo data dài ~58 KB và ~996 KB. Dùng `Grep`, `Read` với `offset/limit`, hoặc `tools/html_guard.py`.
5. **Không tin selector cũ — kiểm chứng trên trang thật** (Playwright MCP, `tools/capture_fixtures.py`, `tests/live`). Flashscore đã đổi DOM giữa 06/2026 và 10/2026.
6. **Giữ tham số `?mid=`** khi dựng URL tab con. **Thứ tự 2 đội trong URL không phải nhà/khách**; nhà/khách lấy từ header và được xác minh bằng logo.
7. Chỉ commit/push khi người dùng yêu cầu. Message commit kết thúc bằng dòng attribution theo hướng dẫn hệ thống.
8. **Hoàn thành ≠ "chạy được một lần"**. Một thay đổi chỉ xong khi:
   - `python -m unittest discover -s tests -t .` xanh;
   - 3 công cụ bảo vệ HTML xanh;
   - đã chạy thật với trận `vLuGlk0n`;
   - CLAUDE.md/design doc đã cập nhật nếu hành vi đổi.

## 7. Sự thật cần nhớ (kiểm chứng 2026-10-09 trên trang thật)

| Chủ đề | Sự thật |
| --- | --- |
| HTML thô của Flashscore | Không chứa dữ liệu trận ⇒ bắt buộc render JS (headless Chromium) |
| Player stats | URL `…/summary/player-stats/{top,shots,attack,passes,defense,goalkeeping,general}/?mid=…`. Đổi đội bằng combobox `[data-testid="wcl-selectButton"]` → `[role="option"]` (`ALL`, mã nhà, mã khách). Mỗi `<th>` có thêm nút "bóng" `wcl-shadow_` bị CSS ẩn (test offline phải ẩn lại) |
| Timeline | Hàng nằm trong `<ol class="smv__period-list">` với `aria-label` ∈ {`1st Half`, `2nd Half`, `Extra Time`, `Penalties`}. Icon: `goal-soccer`, `footballOwnGoal-ico`, `penalty-goal`, `penalty-missed`, `yellowCard-ico`, `redCard-ico`, `red-card-second`, `substitution`, `var`. **Hàng loạt luân lưu bị loại khỏi timeline** (ô thời gian là thứ tự lượt sút) |
| Trạng thái "đã kết thúc" | `Finished`, `After Extra Time`, `After 90 minutes` (luân lưu ngay sau 90'). Trận chưa đá/đang đá ⇒ `E_MATCH_NOT_FINISHED` |
| Lineups | `[data-testid="wcl-lineupsGroup"]` ×4 + `[data-testid="wcl-lineupsField"]`. Sân **dọc** khi viewport ≤ ~760 px ⇒ đo toạ độ ở 420 px. `data-analytics-player-id` ghép được stats ↔ lineups ↔ sơ đồ (0 sai lệch tên ở các trận đã thử) |
| Giải nhỏ | V.League 2, National League North… không có tab Player stats ⇒ `E_NO_PLAYER_STATS` (phát hiện qua thanh tab, ~8 s) |
| Hugging Face / tab nền (kiểm chứng 2026-10-29) | Trên máy chủ chậm (HF 2 vCPU), Chromium **không vẽ tab nền** ⇒ menu chọn đội (Radix) ở các trang tải song song không bao giờ "visible" (`E_INTERNAL … Locator.click/wait_for Timeout`; HF: FS_PARALLEL=3 lỗi 9/9, =1 chạy được). Sửa: `page.bring_to_front()` trước khi thao tác từng trang (player_stats, team_stats) + `_click_retrying` (3 lần, Escape, lần cuối `force`). IP Mỹ còn có thêm tab cá cược/quảng cáo. Chẩn đoán ngay trên Space: biến `FS_DIAG_URL` (+ `FS_DIAG_CRAWLS`) ⇒ `cloud/diag.py` tải báo cáo vào Dataset `diag/` |
| Banner cookie | OneTrust hiện sau ~1 s và chặn click; dùng `locator.wait_for` rồi bấm `#onetrust-reject-all-handler` (`is_visible(timeout=…)` không chờ) |
| Thời gian | Tuần tự (`FS_PARALLEL=1`) ~28–32 s; song song mặc định 3 trang ~23–29 s cho cùng trận (đo 2026-10-13); mức 7 không nhanh hơn. Có lúc 40–140 s khi Flashscore chậm. Từ redesign: +5–10 s cho team stats (tự bỏ qua khi còn < 25 s ngân sách ⇒ `W_NO_TEAM_STATS`) |
| Demo | Vẫn dùng ảnh + Tesseract ⇒ **không được xoá `LineupOCR`**; không có `summary`/`teamStats`/`meta` |
| Team stats (kiểm chứng 2026-10-13) | URL `…/summary/stats/{overall,1st-half,2nd-half}/?mid=…`; hàng `[data-testid="wcl-statistics"]`, tiêu đề nhóm `[data-testid="wcl-headerSection-text"]`, giá trị `[class*="wcl-value_"]` (khách trong `[class*="wcl-awayValue_"]`), tỉ lệ `[data-testid="wcl-caption-05"]`. 45 hàng/phạm vi; "Top stats" lặp lại 5 chỉ số. Link tab STATS cấp trên cũng có `aria-current` |
| Meta trận | `[data-testid="wcl-breadcrumbsItem"]` = [Football, quốc gia, giải - vòng]; `[data-testid="wcl-summaryMatchInformation"]` chứa Referee/Venue/Capacity/Attendance; ngày giờ `.duelParticipant__startTime` |

## 8. Mẹo debug

- Crawler sai/thiếu dữ liệu: chạy `python -m crawler "<link>"` với `FS_DEBUG=1` (lưu HTML bước lỗi vào `debug/`) hoặc `FS_HEADLESS=0` (xem trình duyệt).
- Đổi extractor: lưu fixture bằng `python tools/capture_fixtures.py [--timeline-only] <link…>`, viết test offline (`page.set_content`), rồi chạy `tests/live`.
- Trận tham chiếu #1: Johor DT 6–0 Svay Rieng (`mid=vLuGlk0n`). Kỳ vọng:
  - mã đội `JOH`/`SVA`, 16+16 dòng Top Stats;
  - 21 sự kiện (6 bàn, 5 thẻ vàng, 10 thay người);
  - lineups 11+11 đá chính, 12+11 dự bị;
  - sơ đồ `3-4-2-1` vs `4-2-3-1`;
  - HLV `Xisco` / `McConkey M.`;
  - team stats: xG 4.79–0.32, shots 25–7, xG theo hiệp 1.65→3.13 / 0.06→0.26, possession 50/50 ⇒ `possessionReliable=false`;
  - insight: I01, I03, I04, I12, I17 (+ ghi chú I20); PDF Coach brief 4 trang, Full 14 trang.
- Trận #2 Malaga 1–3 Villarreal (`GGiPsLP1`): possession thật 37–63, có VAR + penalty. Trận #3 Altglienicke 3–3 Wolfsburg (`d8pxv90m`): hiệp phụ + luân lưu.
- Trận #4 Coventry 4–1 Newcastle (`tW4rOkzg`, Premier League): bảng phụ lục PDF rộng nhất.
- Fixture đầy đủ (kể cả `team_stats_*.html`, `meta.html`) của 4 trận trên ở `tests/fixtures/<mid>/`.

## 9. Bản cloud — điều cần nhớ

- **Chế độ local giữ nguyên:** `server.py` không đổi. `cloud/` chỉ *gọi* `crawler.crawl()` (logic crawler dùng chung) và phục vụ cùng `match_report.html`.
- **Hợp đồng job giống `server.py`** (`{jobId, status, progress, result|error}`). Trận có sẵn trong thư viện ⇒ job `done` ngay (`cached=1`, không tính hạn mức).
- **Bảo mật:**
  - cookie phiên `fs_session` (HttpOnly, SameSite=Lax, Secure khi https);
  - mọi lệnh ghi cần `X-CSRF-Token` khớp phiên (cookie `fs_csrf`) và `Origin` đúng `APP_BASE_URL`;
  - CSP chặt ở `/`; trang báo cáo thêm `'unsafe-eval'` vì Tesseract của demo.
  - ⇒ Test Playwright trên trang `/` **không dùng được `wait_for_function` dạng chuỗi** (bị CSP chặn); dùng selector.
- **Bắt buộc `?mid=`** ở bản cloud (khoá thư viện = `mid`).
- **Docker:** 1 image (`deploy/Dockerfile`, base Playwright v1.60 noble — có amd64 + arm64). Container chạy UTC ⇒ đặt `TZ=Asia/Ho_Chi_Minh` trong `deploy/.env` để giờ bóng lăn đúng.
- **Cổng pháp lý G0:** điều khoản Flashscore cấm scrape và công khai lại dữ liệu ⇒ mặc định `REGISTRATION=approval` (nhóm kín). Không đổi sang mở công khai khi người dùng chưa duyệt (cloud design §3).
- **Sửa `crawler/` hoặc `cloud/`** ⇒ chạy cả `tests/cloud` (unit, API, UI) + rebuild image (`docker compose up -d --build`).
- **Hugging Face Spaces** (người dùng có PRO, chọn 2026-10-29): `cloud/hf_main.py` (web + worker một container, cổng 7860, `APP_BASE_URL` từ `SPACE_HOST`, admin đầu tiên từ Secret `BOOTSTRAP_ADMIN_*`), `cloud/hfsync.py` (ổ Space không bền ⇒ SQLite đồng bộ với Dataset riêng tư mỗi 10 phút + khi tắt), `deploy/hf/` (Dockerfile, README có YAML Space, `runbook-hf.md`), `tools/push_hf_space.py` (đẩy bằng token đã `login()` trên máy). Mở app ở địa chỉ `*.hf.space` trực tiếp (khung nhúng trên huggingface.co chặn cookie).

