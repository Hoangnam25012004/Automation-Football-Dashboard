# CLAUDE.md — Automation Football Dashboard

Tài liệu giới thiệu dự án cho Claude Code (và người mới tham gia). Viết bằng tiếng Việt; tên hàm, selector, thuật ngữ kỹ thuật giữ nguyên tiếng Anh.

| | |
| --- | --- |
| Cập nhật | 2026-10-09 |
| Môi trường | Windows 11 · Python 3.14 · Playwright 1.60 (Chromium đã cài) · dự án không dùng Node/bundler (không có `package.json`) |
| Git | Repo git, nhánh `main`. Commit gốc `d4a4da6` = **baseline** trước khi đổi (công cụ kiểm tra so với commit gốc). Danh tính commit đặt riêng cho repo; `core.autocrlf=false` (mọi file dùng LF) |
| Trạng thái | Luồng "dán 1 link Flashscore" **đã triển khai** theo [docs/detailed-design-url-ingestion.md](docs/detailed-design-url-ingestion.md) (Phase 0–5; Phase 5 duyệt 2026-10-13: gỡ mã đọc xlsx mồ côi, **xoá 3 script legacy**, tải song song, chữ chân trang "Data from Flashscore"). Thay đổi sau baseline **chưa commit** |

## 1. Dự án là gì

Công cụ tạo **dashboard phân tích hiệu suất + bảng player stats + match report (PDF)** cho một trận bóng đá từ dữ liệu Flashscore.

Giao diện là một file HTML ([match_report.html](match_report.html)). Nội dung gồm:

- tỉ số và so sánh 2 đội;
- 6 tab: Overall, Shots, Attack, Passes, Defense, Goalkeeping;
- timeline trận đấu;
- "Match story": sơ đồ, đội hình, dự bị, HLV;
- nút **Export PDF**.

```text
Người dùng dán link ─▶ match_report.html ─POST /api/matches─▶ server.py (127.0.0.1:8778)
                                ▲                                   │ 1 worker thread
                                └── poll GET /api/matches/{id} ◀────┤ crawler/ + Playwright (Chromium headless)
                                    → state.* → App.enter() → Render ▼
                                                              www.flashscore.com
```

Quyết định đã chốt với người dùng: (1) **thay hẳn** 3 ô upload xlsx bằng 1 ô nhập link; (2) **chạy local**; (3) lineups lấy **dữ liệu có cấu trúc từ DOM** (không OCR) đưa thẳng vào `state.lineupText`. Nút demo vẫn giữ và vẫn dùng OCR như cũ.

## 2. Cấu trúc thư mục

| Đường dẫn | Vai trò |
| --- | --- |
| [match_report.html](match_report.html) | Web app 1 file. CSS đầu file · HTML · 4 `<script>` inline: demo data, core `state`/`App` + ô URL + `Api`, `LineupOCR` + `Render`, `Exporter` PDF. CDN: Chart.js 4.4.1, jsPDF 2.5.1, html2canvas 1.4.1; Tesseract.js chỉ nạp khi demo cần OCR |
| [server.py](server.py) | Server stdlib: phục vụ đúng `/` và `/match_report.html`, API `POST /api/matches`, `GET /api/matches/{id}`, `GET /api/health`; hàng đợi 1 job chạy + 1 chờ |
| [crawler/](crawler/) | `urls` (kiểm tra/dựng lại link, giữ `?mid=`) · `browser` (Chromium, chặn ảnh/font, banner cookie) · `header` · `player_stats` (7 tab × 2 đội) · `timeline` · `lineups` (cấu trúc + toạ độ sơ đồ) · `assemble` (JSON + kiểm tra chéo) · `run` (điều phối, tiến độ 10 bước, ngân sách 150 s) · `errors` (mã lỗi/cảnh báo) · `__main__` (CLI) |
| [tools/](tools/) | `verify_frozen.py`, `check_diff_budget.py`, `html_guard.py` (bảo vệ HTML) · `golden_demo.py` (golden snapshot luồng demo) · `capture_fixtures.py` (lưu fixture từ trang thật) |
| [tests/](tests/) | `unit/` (offline) · `e2e/` (giao diện + server với runner giả; cần mạng cho CDN) · `live/` (chạm flashscore.com, chỉ chạy khi `FS_LIVE=1`) · `fixtures/` · `golden/demo_views.json` · `output/` (bỏ qua trong git) |
| [requirements.txt](requirements.txt) | `playwright==1.60.0` (+ pillow, chỉ cho test) |
| [.claude/launch.json](.claude/launch.json) | `app` = `python server.py` (8778) · `static` = `python -m http.server 8777` (cũ, chỉ demo chạy được) |
| [docs/detailed-design-url-ingestion.md](docs/detailed-design-url-ingestion.md) | Thiết kế chi tiết + phụ lục selector/extractor đã kiểm chứng |

## 3. Mô hình dữ liệu của web (hợp đồng bất biến)

`match_report.html` chỉ cần 4 đối tượng trong `state`. Mọi nguồn (demo, luồng URL; trước đây là xlsx) phải đưa về đúng hình dạng này. Server trả chúng trong `result.stats / summary / lineups / lineupImages`:

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
```

Điểm tích hợp: `LineupOCR.run()` thoát sớm khi `state.lineupText` đã có ⇒ luồng URL không chạy OCR. Bất biến: `lineupImages[key]` tồn tại ⇔ `lineups[key]` khác `null`.

`event.type` dùng bộ nhãn mà `Render` so khớp bằng regex: `Goal`, `Own goal`, `Penalty goal`, `Substitution`, `Yellow card`, `Second yellow (→ red)`, `Red card`, `VAR`, `Penalty missed`.

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
```

Front-end không có build step: sửa thẳng file HTML rồi tải lại trang. Server đọc lại file ở mỗi request.

## 5. Quy ước code

- **Python**: Playwright **sync API**, chỉ chạy trong MỘT worker thread của server (không asyncio). Docstring/comment/log tiếng Việt; thông điệp hiển thị trên UI tiếng Anh. Selector theo thứ tự ưu tiên `data-testid` → BEM ổn định (`smv__*`, `duelParticipant__*`, `detailScore__*`) → `[class*="…"]`. Class kiểu `wcl-side_YylQz` có **hậu tố hash đổi theo bản build**, không bao giờ dùng nguyên văn. Extractor DOM viết bằng một hàm JS chạy qua `page.evaluate`, trả về số lượng để tự kiểm.
- **Lỗi**: mọi lỗi dừng job là `CrawlError(code)` (`crawler/errors.py`); bất thường không chặn kết quả thì vào `warnings[]`. **Không bao giờ trả rỗng im lặng.**
- **JS trong HTML**: phong cách gọn (arrow function, `const`, template string), không framework/module; màu lấy từ CSS variable ở `:root`.
- **Test**: `unittest` của stdlib. Test live phải có `@unittest.skipUnless(_support.LIVE, …)`. `tests/__init__.py` tắt ghi `.pyc` để thư mục gốc sạch.

## 6. Guardrails (BẮT BUỘC)

1. **Không đổi bất kỳ tính năng nào ngoài phạm vi đã được duyệt.** Yêu cầu chưa rõ, hoặc cần đụng vùng ngoài phạm vi → **hỏi lại người dùng trước**.
2. **Ba script legacy (`flashscore_*.py`) đã bị xoá ở Phase 5** theo yêu cầu người dùng; vẫn còn trong git ở commit baseline `d4a4da6` nếu cần tham khảo. Không khôi phục lại khi chưa được yêu cầu.
3. **`match_report.html` chỉ được khác baseline ở các điểm E1–E14** (design doc §7.1 và §13.5). Mọi lần sửa HTML phải chạy `tools/check_diff_budget.py` (khớp E1–E14), `tools/verify_frozen.py` (14/14 vùng đóng băng) và `tools/golden_demo.py --check`. Vùng đóng băng: `U`, `LineupOCR`, `Render` (trừ chuỗi E7), `Exporter` (trừ chữ chân trang PDF), `App.loadDemo/enter/setTeam/setTab/exportPDF`, toàn bộ CSS cũ, demo data. Muốn sửa thêm ⇒ cập nhật Change surface trong design doc **sau khi người dùng đồng ý**.
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
| Banner cookie | OneTrust hiện sau ~1 s và chặn click; dùng `locator.wait_for` rồi bấm `#onetrust-reject-all-handler` (`is_visible(timeout=…)` không chờ) |
| Thời gian | Tuần tự (`FS_PARALLEL=1`) ~28–32 s; song song mặc định 3 trang ~23–29 s cho cùng trận (đo 2026-10-13); mức 7 không nhanh hơn. Có lúc 40–75 s khi Flashscore chậm |
| Demo | Vẫn dùng ảnh + Tesseract ⇒ **không được xoá `LineupOCR`** |

## 8. Mẹo debug

- Crawler sai/thiếu dữ liệu: chạy `python -m crawler "<link>"` với `FS_DEBUG=1` (lưu HTML bước lỗi vào `debug/`) hoặc `FS_HEADLESS=0` (xem trình duyệt).
- Đổi extractor: lưu fixture bằng `python tools/capture_fixtures.py [--timeline-only] <link…>`, viết test offline (`page.set_content`), rồi chạy `tests/live`.
- Trận tham chiếu #1: Johor DT 6–0 Svay Rieng (`mid=vLuGlk0n`). Kỳ vọng:
  - mã đội `JOH`/`SVA`, 16+16 dòng Top Stats;
  - 21 sự kiện (6 bàn, 5 thẻ vàng, 10 thay người);
  - lineups 11+11 đá chính, 12+11 dự bị;
  - sơ đồ `3-4-2-1` vs `4-2-3-1`;
  - HLV `Xisco` / `McConkey M.`.
