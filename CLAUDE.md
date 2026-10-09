# CLAUDE.md — Automation Football Dashboard

Tài liệu giới thiệu dự án cho Claude Code (và người mới tham gia). Viết bằng tiếng Việt; tên hàm, selector, thuật ngữ kỹ thuật giữ nguyên tiếng Anh.

| | |
| --- | --- |
| Cập nhật | 2026-10-09 |
| Môi trường | Windows 11 · Python 3.14 · Playwright 1.60 (Chromium đã cài) · dự án không dùng Node/bundler (không có `package.json`) |
| Git | **Chưa phải git repo** → chưa có lịch sử/rollback (xem §6, mục "Safety net") |
| Việc đang chuẩn bị | Chuyển từ "3 file xlsx" sang "dán 1 link Flashscore". Thiết kế chi tiết: [docs/detailed-design-url-ingestion.md](docs/detailed-design-url-ingestion.md). **Chưa có dòng code nào của phần mới được viết.** |

## 1. Dự án là gì

Công cụ tạo **dashboard phân tích hiệu suất + bảng player stats + match report (PDF)** cho một trận bóng đá từ dữ liệu Flashscore.

Giao diện là **một file HTML tĩnh** ([match_report.html](match_report.html)): hiển thị tỉ số, so sánh 2 đội (Home/Away), 6 tab (Overall, Shots, Attack, Passes, Defense, Goalkeeping), timeline trận đấu, "Match story" (sơ đồ + đội hình + dự bị + HLV) và nút **Export PDF**.

### Hiện trạng (as-is)

```text
Flashscore ──▶ flashscore_scraper.py  ──▶ flashscore_<home>_vs_<away>_<ts>.xlsx   (player stats, 7 tab × 2 đội)
          ──▶ flashscore_summary.py  ──▶ summary_<home>_vs_<away>_<ts>.xlsx       (timeline + logo)
          ──▶ flashscore_lineups.py  ──▶ lineups_<home>_vs_<away>_<ts>.xlsx       (5 ảnh chụp lineups)
                                          (lưu vào ~/Downloads)
                     người dùng upload 3 file vào ──▶ match_report.html ──▶ dashboard ──▶ PDF
```

### Mục tiêu (to-be — đã chốt với người dùng ngày 2026-10-09, chưa triển khai)

Dán **1 link** Flashscore (ví dụ `https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n`) → backend local tự crawl → dashboard + bảng player stats + match report. Bỏ bước xlsx trung gian.

Quyết định đã chốt: (1) **thay hẳn** 3 ô upload xlsx bằng 1 ô nhập URL; (2) **chạy local** trên máy người dùng; (3) Lineups lấy **dữ liệu có cấu trúc từ DOM** (không OCR) đưa thẳng vào `state.lineupText`. Phần còn lại của web (Render, Exporter, demo) giữ nguyên.

## 2. Cấu trúc thư mục (hiện tại)

| Đường dẫn | Vai trò |
| --- | --- |
| [match_report.html](match_report.html) | Web app 1 file, 1.18 MB, 2456 dòng. CSS dòng 11–479 · HTML 481–576 · 5 `<script>` inline: demo data (578–581), `JSZipLite` (582–774), core `state`/`App`/parse xlsx (775–1093), `LineupOCR` + `Render` (1094–2303), `Exporter` PDF (2304–2453). CDN: SheetJS 0.18.5, Chart.js 4.4.1, jsPDF 2.5.1, html2canvas 1.4.1; Tesseract.js nạp lazy khi cần OCR |
| [flashscore_scraper.py](flashscore_scraper.py) | Player stats → xlsx (sheet `"<MÃ ĐỘI> - <Tab>"`, ví dụ `JOH - Shots`) |
| [flashscore_summary.py](flashscore_summary.py) | Timeline sự kiện + logo → xlsx (sheet `Summary`, `Timeline`) |
| [flashscore_lineups.py](flashscore_lineups.py) | Chụp 5 khối lineups → xlsx (ảnh nhúng) |
| [.claude/launch.json](.claude/launch.json) | Cấu hình preview: `python -m http.server 8777` (tên `static`) |
| [docs/detailed-design-url-ingestion.md](docs/detailed-design-url-ingestion.md) | Thiết kế chi tiết việc chuyển sang "1 link URL" |
| `__pycache__/` | Cache Python (bỏ qua) |

Dự kiến thêm (xem design doc §3.3, **chưa tồn tại**): `server.py`, `crawler/`, `tests/`, `requirements.txt`.

## 3. Mô hình dữ liệu của web (hợp đồng bất biến)

`match_report.html` chỉ cần 4 đối tượng trong `state`; mọi nguồn dữ liệu (xlsx, demo, URL mới) đều phải đưa về đúng hình dạng này:

```js
state.data = {                       // bắt buộc
  matchTitle: "Johor DT  vs  Svay Rieng",   // 2 dấu cách quanh " vs "; Render tách bằng /\s+vs\s+/
  matchDate: "",                            // luồng cũ luôn rỗng
  home: "JOH", away: "SVA",                 // mã đội 3 ký tự = khoá tra cứu, không hiển thị
  teams: { JOH: { "Top Stats":{headers:[...], rows:[{Player, Position, ...}]},
                  Shots, Attack, Passes, Defense, Goalkeeping, General },   // 7 tab
           SVA: { ... } }
}                                    // mọi giá trị ô là string: "9.0", "73/81 (90%)", "-"
state.summary = { events:[{minute,half,side,team,type,player,detail,score}],
                  homeLogo, awayLogo /*data URL*/, finalScore:{h,a} } | null   // tuỳ chọn
state.lineupImages = { formation, starting_xi, substituted, substitutes, coaches }  // data URL; chỉ dùng làm "cổng" hiển thị + fallback
state.lineupText   = { formation:{players:[{num,name,ok,side,x,y}],w,h},          // kết quả OCR HOẶC dữ liệu cấu trúc
                       starting_xi:[{homeNum,awayNum,home:{name,ok},away:{name,ok}}],
                       substituted:{home:[{on,off,min}],away:[...]},
                       substitutes:[...cùng dạng starting_xi], coaches:{home:{name,ok},away:{name,ok}} } | null
```

Điểm tích hợp quan trọng: `LineupOCR.run()` ([match_report.html:1373](match_report.html#L1373)) thoát sớm nếu `state.lineupText` đã có → gán dữ liệu cấu trúc vào đó là đủ để Render vẽ Match story mà không chạy OCR. `renderOverall()` ([:1477](match_report.html#L1477)) chỉ dựng thẻ Match story khi `state.lineupImages` có khoá tương ứng.

## 4. Chạy & phát triển

```powershell
pip install playwright openpyxl pillow
playwright install chromium

python flashscore_scraper.py     # hỏi link; ghi xlsx vào %USERPROFILE%\Downloads
python flashscore_summary.py
python flashscore_lineups.py     # (đang hỏng trên giao diện Flashscore hiện tại — xem §7)

python -m http.server 8777       # xem http://localhost:8777/match_report.html (hoặc launch.json "static")
```

Sau khi triển khai (dự kiến): `python server.py` → mở `http://127.0.0.1:8778`, dán link, bấm Generate. Port 8778 và tên cấu hình `app` trong `launch.json` là đề xuất, xem design doc §3 và §8.

Phát triển front-end: không có build step. Sửa trực tiếp file HTML, tải lại trang. Demo ("explore with sample data") dùng dữ liệu nhúng sẵn ở dòng 579–580 nên không cần crawl (vẫn cần mạng để tải thư viện CDN và font).

## 5. Quy ước code

- **Python**: Playwright **sync API**, hằng số cấu hình ở đầu file, log/print bằng tiếng Việt kèm ký hiệu ✓/✗/⚠, chọn selector theo thứ tự ưu tiên (`data-testid` → BEM ổn định như `smv__*`, `duelParticipant__*` → `[class*="…"]`). Class kiểu `wcl-side_YylQz` có **hậu tố hash đổi theo bản build**, không bao giờ dùng nguyên văn.
- **JS trong HTML**: phong cách gọn (arrow function, `const`, template string), không framework, không module; mỗi khối là một IIFE/đối tượng (`U`, `App`, `LineupOCR`, `Render`, `Exporter`). Màu/khoảng cách lấy từ CSS variable ở `:root` (`--good`, `--home`, `--away`, `--panel`, …). UI text tiếng Anh; comment/log lẫn Việt–Anh.
- Dữ liệu stats luôn là **string**; hàm `U.num`, `U.parseFraction`, `U.rankVal` lo việc ép kiểu — không đổi kiểu dữ liệu ở nguồn.

## 6. Guardrails (BẮT BUỘC)

1. **Không đổi bất kỳ tính năng nào ngoài phạm vi đã được duyệt.** Nếu yêu cầu chưa rõ hoặc cần đụng vùng ngoài phạm vi → **hỏi lại người dùng trước**, đừng tự quyết.
2. **Ba script legacy (`flashscore_*.py`) và `__pycache__`: không sửa** (kể cả "sửa nhỏ"), không xoá. Code mới là file mới; được phép tham khảo/copy logic, không `import` từ script legacy.
3. **`match_report.html` chỉ sửa theo "Change surface"** ở design doc §7.1. Các khối đóng băng (phải giữ nguyên từng byte): `JSZipLite`, `U`, `LineupOCR`, `Render`, `Exporter`, `App.loadDemo/enter/setTeam/setTab/exportPDF`, toàn bộ CSS hiện có, dòng 579–580 (demo data). Sau mỗi lần sửa phải chạy kiểm tra diff-budget + golden snapshot (design doc §9).
4. **Đừng đọc/in cả file HTML**: dòng 579 (~58 KB) và 580 (~996 KB base64) làm tràn context. Dùng `Grep`, `Read` với `offset/limit`, hoặc script Python đọc có chọn lọc.
5. **Không tin selector cũ — kiểm chứng trên trang thật** (Playwright MCP hoặc script thử). Flashscore đã đổi DOM giữa 06/2026 và 10/2026 (xem §7). Khi extractor trả rỗng cho trận đã có dữ liệu, coi đó là lỗi, không phải "trận không có dữ liệu".
6. **Giữ nguyên tham số `?mid=`** của URL trận khi dựng URL tab con; `normalize_match_url()` của script legacy làm rơi nó.
7. **Safety net**: repo chưa có git. Trước khi sửa `match_report.html` phải có bản khôi phục (git commit hoặc bản sao) và đối chiếu SHA-256 baseline ở design doc phụ lục B. Chỉ `git init`/commit/push khi người dùng yêu cầu.
8. **Hoàn thành ≠ "chạy được một lần"**: một thay đổi chỉ xong khi (a) golden snapshot của luồng demo không đổi, (b) diff khớp Change surface, (c) luồng mới chạy với ít nhất trận tham chiếu `vLuGlk0n` (Johor DT 6–0 Svay Rieng), (d) CLAUDE.md/design doc được cập nhật nếu hành vi thay đổi.
9. Việc xoá code mồ côi sau khi thay UI (parser xlsx, `JSZipLite`, SheetJS) và gỡ 3 script legacy là **Phase 5, cần phê duyệt riêng**.

## 7. Sự thật cần nhớ / vấn đề đã biết (kiểm chứng 2026-10-09 trên trận `vLuGlk0n`)

| Chủ đề | Sự thật |
| --- | --- |
| `flashscore_scraper.py` (stats) | **Vẫn đúng**: 7/7 tab load được, header trùng khớp header trong demo, combobox đội cho `["ALL","JOH","SVA"]`. |
| `flashscore_summary.py` (timeline) | **Hỏng một phần**: các hàng sự kiện nay nằm trong `<ol class="smv__period-list">`; extractor cũ duyệt `root.children` nên chỉ trả 2/21 sự kiện (sai nội dung) và `side` rỗng. Cần extractor mới theo `li[class*="smv__participantRow"]`. |
| `flashscore_lineups.py` | **Hỏng**: `.section`, `.lf_field`, `.lf_formation`, `.lf_sidesBox` đều trả 0 phần tử; ảnh `coaches` rơi vào fallback chụp viewport (sai nội dung). DOM mới dùng `data-testid="wcl-lineupsGroup"` / `wcl-lineupsField`. |
| Sân Formation | Ngang khi viewport ≥ ~900 px, **dọc** khi ≤ ~760 px. Demo cũ là sân dọc (nhà trên, khách dưới); `LineupOCR.parseFormation` giả định đúng như vậy. Khi cần toạ độ, đo ở viewport 420 px. |
| Banner cookie | OneTrust hiện sau ~1 s và **chặn click**. `is_visible(timeout=…)` không chờ — dùng `locator.wait_for(state="visible")`; nút `#onetrust-reject-all-handler` / `#onetrust-accept-btn-handler`. |
| Khoá ghép dữ liệu | `data-analytics-player-id` có ở bảng stats, danh sách lineups và sơ đồ → ghép được cả 3 nguồn theo id (đã thử: 22/22 đá chính, 0 sai lệch tên). |
| HTML thô của Flashscore | Không chứa dữ liệu trận (tải 893 KB, không có tên cầu thủ) → bắt buộc render JS (headless Chromium). |
| Demo & OCR | Demo vẫn dùng ảnh + Tesseract → **không được xoá `LineupOCR`** dù luồng URL không dùng. |
| Thời gian | Crawl 1 trận ≈ 45–60 s tuần tự (đo: lineups 4 s, summary 3 s, mỗi tab stats ~5.7 s). |

## 8. Mẹo debug

- Soi DOM thật bằng Playwright (MCP `browser_evaluate`/`browser_run_code_unsafe` hoặc script riêng); đếm selector trước, rồi mới viết extractor.
- Khi đổi extractor: lưu fragment HTML làm fixture và test bằng `page.set_content()` (offline, xác định) trước khi test trên trang thật.
- Trận tham chiếu #1 (kỳ vọng tại 2026-10-09): Johor DT 6–0 Svay Rieng, mã đội `JOH`/`SVA`, 16+16 dòng "Top Stats", 21 sự kiện (6 bàn, 5 thẻ vàng, 10 thay người), lineups 11+11 đá chính, 12+11 dự bị, sơ đồ `3-4-2-1` vs `4-2-3-1`, HLV `Xisco` / `McConkey M.`.
