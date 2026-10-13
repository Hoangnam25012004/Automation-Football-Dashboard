# Detailed Design — Tạo dashboard & match report từ 1 link Flashscore

| Thuộc tính | Giá trị |
| --- | --- |
| Trạng thái | **v1.2 — Đã triển khai Phase 0–5** (Phase 5 được duyệt và làm ngày 2026-10-13). Ghi nhận khi triển khai và các điểm lệch so với thiết kế: **[§13](#13-ghi-nhận-khi-triển-khai-2026-10-09)**; Phase 5: **[§13.5](#135-phase-5-2026-10-13)**. Thay đổi sau baseline chưa commit |
| Ngày | 2026-10-09 (v1.0 thiết kế · v1.1 triển khai) |
| Phạm vi | Thay luồng "3 file xlsx → upload vào web" bằng "1 link Flashscore → backend local crawl → dashboard / bảng player stats / match report (PDF)" |
| Baseline | `match_report.html` SHA-256 `B47EE9FB…AC63F` (đủ 64 ký tự ở [phụ lục B](#phụ-lục-b--baseline-sha-256)) |
| Tài liệu liên quan | [CLAUDE.md](../CLAUDE.md) |
| Ký hiệu | ✅ đã kiểm chứng trên trang Flashscore thật ngày 2026-10-09 · ⚠ giả định / chưa kiểm chứng, phải xác nhận khi triển khai · 🔒 vùng đóng băng (không được sửa) |

---

## 0. Tóm tắt

### 0.1 Yêu cầu

Người dùng dán **1 link** trận Flashscore (ví dụ `https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n`) vào website; website tự tạo **dashboard**, **bảng player stats** và **match report (PDF)**. Không còn bước trung gian "chạy 3 script → 3 file xlsx → upload".

Ràng buộc: hoàn thành không gây lỗi cho các chức năng khác; không thay đổi tính năng khác khi chưa được cho phép; có thắc mắc thì hỏi lại.

### 0.2 Giải pháp trong 6 dòng

1. Thêm một **backend local nhỏ** (`server.py`: Python stdlib + Playwright headless, **không thêm dependency runtime**) — vì dữ liệu Flashscore **không nằm trong HTML thô** (✅ V1) nên một trang HTML tĩnh không thể tự lấy được.
2. Backend nhận URL → kiểm tra/chuẩn hoá (giữ `?mid=`) → mở Chromium headless → crawl **3 nguồn**: player stats (7 tab × 2 đội), timeline + logo, lineups (dữ liệu có cấu trúc).
3. Trả về **một JSON đúng hình dạng mà `state` của web đang dùng** (`state.data`, `state.summary`, `state.lineupText`, `state.lineupImages`).
4. Front-end: thay 3 ô upload bằng 1 ô URL; hàm mới `App.buildFromUrl()` gán JSON vào `state` rồi gọi `App.enter()` **có sẵn**.
5. `Render`, `Exporter`, `LineupOCR` (demo vẫn cần), toàn bộ CSS hiện có, dữ liệu demo: **không sửa một byte** 🔒.
6. Chống hồi quy 3 lớp: (a) diff-budget + hash vùng đóng băng, (b) golden snapshot DOM của luồng demo, (c) test parity xlsx ↔ JSON cho stats.

### 0.3 Sáu phát hiện đã kiểm chứng làm thay đổi thiết kế

| # | Phát hiện (✅ trên trang thật) | Hệ quả thiết kế |
| --- | --- | --- |
| 1 | Scraper **lineups cũ hỏng hoàn toàn**: `.section`, `.lf_field`, `.lf_formation`, `.lf_sidesBox` đều trả **0** phần tử | Không thể chỉ "gom 3 script lại"; phải viết lại phần lineups |
| 2 | Scraper **timeline cũ hỏng một phần**: chỉ lấy **2/21** sự kiện (và sai nội dung), `side` rỗng → timeline + danh sách ghi bàn trên scorebar sẽ trống/sai | Extractor mới theo `li.smv__participantRow` — đã chạy thử: **21/21** |
| 3 | Scraper **stats cũ vẫn đúng**, header 7/7 tab khớp từng cột với demo | Tái dùng logic; giảm 14 → 7 lần `goto` bằng cách đổi đội tại chỗ |
| 4 | Sân Formation nay **nằm ngang** (viewport ≥ ~900 px); OCR cũ giả định sân **dọc** | Chọn lineups có cấu trúc (quyết định D3), đo toạ độ ở viewport 420 px (sân dọc) |
| 5 | `normalize_match_url()` cũ **làm rơi `?mid=`**; banner cookie hiện trễ và **chặn click**; `is_visible(timeout=…)` không chờ | Giữ `mid`; xử lý cookie bằng `wait_for` |
| 6 | `data-analytics-player-id` có ở bảng stats, danh sách lineups, sơ đồ → ghép được 3 nguồn: **22/22** đá chính, **10/10** vào sân, **22/22** trên sơ đồ nằm trong roster stats, **0** sai lệch tên | Lineups ghép theo id → tên khớp tuyệt đối với bảng stats nên `ratingFor()` luôn tìm được rating |

### 0.4 Roadmap

| Phase | Nội dung | Đụng tới file hiện có? | Cổng ra |
| --- | --- | --- | --- |
| 0 | Safety net: điểm khôi phục, golden snapshot, công cụ diff-budget | Không | G0 |
| 1 | Crawler core (`crawler/`) + CLI | Không (chỉ file mới) | G1 |
| 2 | Local server + hàng đợi job + API | Chỉ **thêm** 1 mục vào `.claude/launch.json` | G2 |
| 3 | Front-end: thay upload bằng ô URL | `match_report.html` — đúng 7 điểm sửa (§7.1) | G3 |
| 4 | Hardening + nghiệm thu | Không | G4 |
| 5 | *(Tuỳ chọn, cần phê duyệt riêng)* dọn code mồ côi, gỡ script legacy | Có | — |

Ước lượng thô cho 1 người: P0 ≈ 0,5 ngày · P1 ≈ 2–3 · P2 ≈ 1 · P3 ≈ 1 · P4 ≈ 1–2 ⇒ **6–8 ngày làm việc**.

### 0.5 Rủi ro lớn nhất

Flashscore đổi DOM — đã xảy ra một lần giữa 06/2026 và 10/2026 (§2). Cách chặn: ưu tiên `data-testid`/BEM, test extractor bằng fixture offline + canary live trên bộ trận tham chiếu, và **không bao giờ trả rỗng im lặng** — mọi bất thường đi vào `warnings[]`.

---

## 1. Bối cảnh, mục tiêu, ràng buộc

### 1.1 Hiện trạng (as-is)

#### 1.1.1 Luồng hiện tại

```text
Flashscore ─▶ flashscore_scraper.py ─▶ flashscore_<home>_vs_<away>_<ts>.xlsx  (stats)     ┐
           ─▶ flashscore_summary.py ─▶ summary_<home>_vs_<away>_<ts>.xlsx     (timeline)  ├─▶ ~/Downloads
           ─▶ flashscore_lineups.py ─▶ lineups_<home>_vs_<away>_<ts>.xlsx     (5 ảnh)     ┘
                                                  │ người dùng upload 3 file
                                                  ▼
            match_report.html: parse xlsx (SheetJS + JSZipLite) ─▶ state ─▶ Render ─▶ Export PDF
                                                  └─ ảnh lineups ─▶ Tesseract OCR ─▶ state.lineupText
```

#### 1.1.2 Thành phần và tình trạng trên Flashscore ngày 2026-10-09

| Thành phần | Làm gì | Tình trạng |
| --- | --- | --- |
| [flashscore_scraper.py](../flashscore_scraper.py) | 7 tab × 2 đội: mở combobox, chọn đội, đọc bảng; 14 lần `goto`; xlsx sheet `"<MÃ> - <Tab>"` | ✅ Đúng |
| [flashscore_summary.py](../flashscore_summary.py) | Header + logo + timeline bằng `JS_EXTRACT` duyệt `root.children` | ❌ Hỏng một phần (V8) |
| [flashscore_lineups.py](../flashscore_lineups.py) | Chụp 5 khối bằng `.section`/`.lf_*`; chạy `headless=False` | ❌ Hỏng (V10) |
| [match_report.html](../match_report.html) | Web 1 file, 2456 dòng, 1,18 MB: CSS 11–479 · HTML 481–576 · 5 `<script>` inline | Chạy tốt với dữ liệu cũ/demo |

Đặc điểm của 3 script legacy khiến **không nên `import` lại**: hàm `main()` dùng `input()` và ghi vào `~/Downloads`; `normalize_match_url()` bỏ `?mid=`; mỗi script tự `launch` một trình duyệt; 2/3 script đã hỏng.

#### 1.1.3 Cách web nạp dữ liệu hôm nay

| Hàm ([match_report.html](../match_report.html)) | Vai trò |
| --- | --- |
| `parseStatsWorkbook` ([:865](../match_report.html#L865)) | Sheet `"CODE - Tab"` → `state.data.teams[CODE][Tab] = {headers, rows}`; `home/away` = 2 mã đầu theo thứ tự sheet; `matchTitle` lấy từ ô chứa `" vs "` của sheet `Summary` |
| `parseSummaryWorkbook` ([:960](../match_report.html#L960)) | Sheet `Timeline` → `events`; ảnh nhúng `image1/image2` → logo; chuỗi `Final score: a - b` |
| `parseLineupWorkbook` ([:891](../match_report.html#L891)) | Ảnh nhúng theo từng sheet → `state.lineupImages` |
| `LineupOCR.compute` ([:1280](../match_report.html#L1280)) | Tesseract trên ảnh → `state.lineupText` (đối chiếu với roster của stats) |
| `App.build / loadDemo / enter / reset` ([:1021](../match_report.html#L1021)) | Điều phối; `enter()` vẽ scorebar, tab, nội dung |

Hợp đồng dữ liệu của `state` được mô tả ở [CLAUDE.md §3](../CLAUDE.md) và chi tiết hoá ở §5 dưới đây.

### 1.2 Mục tiêu và phi mục tiêu

#### Mục tiêu

- **G1** — 1 URL → dashboard đầy đủ (Overall + 5 tab stats + timeline + Match story) và PDF.
- **G2** — Dữ liệu stats tương đương luồng xlsx (parity); timeline/lineups đúng với giao diện Flashscore hiện tại.
- **G3** — Không hồi quy ở demo, `Render`, Export PDF.
- **G4** — Lỗi rõ ràng, có hướng xử lý, không treo UI.
- **G5** — Chạy local; không thêm dependency runtime ngoài Playwright (đã có).

#### Phi mục tiêu

- **NG1** — Không đổi UI/logic dashboard, `Render`, `Exporter`, công thức radar/điểm/so sánh.
- **NG2** — Không hỗ trợ trận chưa/đang diễn ra, hoặc trận không có player stats (báo lỗi rõ — §4.3).
- **NG3** — Không multi-user, không host, không đăng nhập, không DB, không cache dài hạn.
- **NG4** — Không sửa/xoá 3 script legacy (chỉ Phase 5 nếu được duyệt).
- **NG5** — Không thay đổi OCR dùng cho demo.
- **NG6** — Không đổi ngôn ngữ giao diện.

### 1.3 Ràng buộc của bạn → cơ chế đảm bảo trong thiết kế

| Ràng buộc | Cơ chế |
| --- | --- |
| Không gây bug ở chức năng khác | (1) Change surface hẹp, khai báo trước (§7.1); (2) vùng đóng băng kiểm bằng hash/diff-budget (§9.2); (3) golden snapshot luồng demo (§9.3); (4) chia phase có cổng; (5) rollback từng phase (§8) |
| Không đổi tính năng khác khi chưa được phép | Danh sách mục cần phê duyệt (§11); quy tắc cứng trong [CLAUDE.md §6](../CLAUDE.md); mọi thay đổi ngoài bảng §7.1 = Change Request |
| Hỏi lại khi chưa rõ | §11 liệt kê mọi điểm chưa rõ kèm mặc định; 3 câu hỏi lớn đã được hỏi và chốt (§1.4) |
| 1 link, không bước trung gian | Kiến trúc §3, API §4, crawler §6 |

### 1.4 Quyết định đã chốt và giả định

#### Đã chốt với bạn ngày 2026-10-09

| ID | Câu hỏi | Quyết định |
| --- | --- | --- |
| D1 | 3 ô upload xlsx xử lý thế nào? | **Thay hẳn bằng ô nhập URL** (gỡ UI upload + các hàm nối với nó; nút demo không bị yêu cầu gỡ nên giữ — C1) |
| D2 | Chạy ở đâu? | **Local trên máy bạn** (Windows, Playwright + Chromium đã cài) |
| D3 | Lineups lấy thế nào? | **Dữ liệu có cấu trúc từ DOM**, đưa thẳng vào `state.lineupText`; luồng URL không chạy OCR |

#### Giả định (có thể đổi — xem §11)

| ID | Giả định |
| --- | --- |
| A1 | 1 người dùng, 1 trận mỗi lần, Windows 11, Python 3.14 |
| A2 | Chỉ trận **bóng đá đã kết thúc** |
| A3 | Trang tiếng Anh (`www.flashscore.com`, locale `en-GB`) |
| A4 | Thứ tự đội trong combobox stats = `[home, away]` — được xác minh bằng logo (§6.4) chứ không chỉ tin |
| A5 | Hai mã 3 ký tự của hai đội khác nhau (nếu trùng: xử lý ở §6.4) |
| A6 | Dùng cá nhân/nội bộ, tốc độ thấp (1 job tuần tự) |
| A7 | Chromium do Playwright quản lý (`playwright install chromium`) |

---

## 2. Kiểm chứng thực tế

Phương pháp: Playwright MCP (Chromium) và script Python Playwright 1.60 chạy headless (Chromium 148), trên **trận tham chiếu #1** `mid=vLuGlk0n` — Johor DT 6–0 Svay Rieng (ASEAN Club Championship). Không file nào của dự án bị sửa trong quá trình kiểm chứng.

| ID | Kiểm chứng | Kết quả |
| --- | --- | --- |
| V1 | Tải HTML thô (không chạy JS) của 3 trang: summary, lineups, player-stats/top | ✅ HTTP 200, ~893 KB mỗi trang; **không** chứa `Hazmi`, `Aiman`, `smv__participantRow`, `wcl-tableBodyRow` ⇒ dữ liệu nạp bằng JS |
| V2 | Request mạng của trang | ✅ Có `global.flashscore.ninja/2/x/feed/…` (vd `dc_1_<mid>`, `df_dos_1_<mid>_`) với header chữ ký `x-fsign`; phản hồi `access-control-allow-origin: *` ⇒ API nội bộ không có tài liệu (phương án B, §3.2) |
| V3 | `fetch` cross-origin từ `example.com` tới trang Flashscore | ✅ Thành công (HTTP 200, ACAO `*`) nhưng chỉ lấy được HTML shell rỗng dữ liệu (V1) ⇒ không giải quyết nhu cầu |
| V4 | Python 3.14.0 + Playwright 1.60.0 + Chromium 148 **headless** | ✅ Cả 3 loại trang đọc được: lineups 4,0 s · summary 2,8 s · 1 tab stats cho 2 đội 5,7 s · tổng 13,2 s (đã chặn ảnh/font) |
| V5 | Banner cookie OneTrust | ✅ Hiện sau ~1,1 s. Bỏ qua ⇒ `TimeoutError: … <div id="onetrust-group-container"> intercepts pointer events` khi click combobox (đã tái hiện). `#onetrust-reject-all-handler` click được |
| V6 | URL có/không `?mid=` × 3 loại trang | ✅ Cả 6 đều load đúng trận 08.10.2026 6–0 `FINISHED`; có `mid` thì tiêu đề trang có tiền tố `JOH 6-0 SVA`, không có thì không. ⚠ *Suy luận, chưa tái hiện:* khi thiếu `mid` Flashscore phải tự suy ra trận từ cặp đội, nên với cặp đội có nhiều trận (lượt đi/về) có thể chọn nhầm — vì vậy thiết kế luôn giữ `mid` (U8) |
| V7 | Stats: 7 URL tab × 2 đội | ✅ 7/7 load. Header (sau khi chèn `Position`) **khớp từng tab** với header demo (Top Stats 10 cột, Shots 12, Attack 8, Passes 10, Defense 11, Goalkeeping 9, General 9). Combobox `["ALL","JOH","SVA"]`; chọn đội ngay trong trang cho dữ liệu đúng (Top Stats 16+16 dòng; Goalkeeping 1+1). ~7 s/tab (trình duyệt MCP) |
| V8 | `JS_EXTRACT` nguyên văn của `flashscore_summary.py` | ❌ Trả **2 sự kiện** (vd "13' Goal Sieng C. 1-0" — thực tế phút 13 là thẻ vàng của Sieng C.), `side` rỗng. Nguyên nhân: hàng sự kiện nay nằm trong `<ol class="smv__period-list" aria-label="1st Half">`; code cũ duyệt `root.children` nên mỗi hiệp bị coi là **một** hàng |
| V9 | Extractor timeline mới (Phụ lục D.1) | ✅ **21/21**: 6 Goal, 5 Yellow card, 10 Substitution; home 14 / away 7; kiến tạo, tỉ số `1-0…6-0`, hiệp `1st half`/`2nd half` đúng |
| V10 | Selector lineups cũ | ❌ `.section` = 0, `.lf_field` = 0, `.lf_formation` = 0, `.lf_sidesBox` = 0, `[data-analytics-context="widget-formation"]` = 0 ⇒ 4/5 ảnh `None`, ảnh `coaches` rơi vào fallback chụp viewport (sai nội dung) *(kết luận từ đọc code + số đếm selector, không chạy script)* |
| V11 | DOM lineups mới | ✅ Ổn định theo `data-testid`: `wcl-lineupsGroup` ×4 (Substituted players / Starting Lineups / Substitutes / Coaches), `wcl-lineupsField`; class có hậu tố hash (`wcl-side_YylQz`) ⇒ phải dùng `[class*="…"]` |
| V12 | Hướng sân Formation theo viewport | ✅ **Ngang** ở 1440/1100/900 px; **dọc** ở 760/600/420 px. Ảnh demo cũ là sân dọc 682×1184 ⇒ `parseFormation` (tách đội theo `y < H/2`) không dùng được với ảnh ngang |
| V13 | PoC lineups có cấu trúc + ghép theo id | ✅ 11+11 đá chính, 12+11 dự bị, 5+5 thay người, 2 HLV, 22 cầu thủ sơ đồ (hàng `[1,3,4,2,1]` / `[1,4,2,3,1]`, nhãn `3 - 4 - 2 - 1` / `4 - 2 - 3 - 1`). 22/22 đá chính + 10/10 vào sân + 22/22 sơ đồ ⊂ roster stats theo id, **0** sai lệch tên. 13 dự bị chưa ra sân không có trong roster (đúng kỳ vọng) |
| V14 | Cấu trúc khối "Substituted players" | ✅ Id cầu thủ **vào** ở container `wcl-lineupsParticipantsSubstitution-*`; cầu thủ **ra** ở khối thứ hai với `[class*="wcl-subName_"]`, phút ở `[class*="wcl-minute_"]` |
| V15 | Logo đội trong dòng stats | ✅ Logo trong ô cầu thủ (`SlUDTKeM-d29rUy0U.png`) trùng logo header đội nhà ⇒ có thể xác minh thứ tự đội |
| V16 | Môi trường Python | ✅ Python 3.14.0 · playwright 1.60.0 · openpyxl 3.1.5 · pillow 12.1.1 · aiohttp 3.14.3 · requests 2.32.5 · lxml 6.0.2 · pytesseract 0.3.13; Chromium + headless shell đã cài. **Chưa có** Flask/FastAPI/uvicorn/pytest |
| V17 | CSS `.section-sub` và `.card-head .eyebrow` | ✅ `display:none` ⇒ dòng phụ đề "recognised from the lineup sheet…" của Match story **không hiển thị** ⇒ không cần sửa copy ở đó |
| V18 | Quét mọi tham chiếu tới phần tử upload trong HTML | ✅ Danh sách đầy đủ ở §7.5 — đây là "bán kính ảnh hưởng" của việc thay UI |

### 2.1 Chưa kiểm chứng lúc thiết kế — kết quả kiểm ở Phase 4

| ID | Nội dung | Kết quả Phase 4 (2026-10-09) |
| --- | --- | --- |
| U1 | Loại sự kiện hiếm: own goal, penalty, thẻ đỏ, thẻ vàng thứ hai, VAR, bàn bị huỷ — tên `data-testid`/class/`<title>` của icon | ✅ Đã quan sát trên ~50 trận (EPL, LaLiga, EFL Cup, DFB-Pokal, V.League 2, National League North): `footballOwnGoal-ico`, `penalty-goal`, `penalty-missed`, `redCard-ico`, `red-card-second`, `var` ("Goal Disallowed - offside"). Quy tắc phân loại cập nhật ở §6.5 và §13 |
| U2 | Trận có hiệp phụ / loạt luân lưu: `aria-label` của `<ol>`, cấu trúc hàng luân lưu | ✅ `Extra Time`, `Penalties`. Hàng luân lưu có ô thời gian là thứ tự lượt sút ("1"…"7") ⇒ bị loại khỏi timeline |
| U3 | Trận **không có** tab Player stats / không có lineups / có lineups nhưng không có sơ đồ | ✅ Giải nhỏ không có tab "Player stats" (và "Lineups") ⇒ `E_NO_PLAYER_STATS` sau ~8 s nhờ đọc thanh tab. ⚠ Chưa gặp trận có stats mà thiếu lineups/sơ đồ (đường xử lý đã có test bằng dữ liệu giả) |
| U4 | Trận đang diễn ra, chưa đá, hoãn, huỷ: chữ trạng thái và hành vi trang | ✅ Trận chưa đá (lấy động từ lịch Premier League) ⇒ `E_MATCH_NOT_FINISHED`. ⚠ Chưa gặp trận đang đá/hoãn/huỷ (cùng nhánh xử lý) |
| U5 | Chuỗi trạng thái cho trận hiệp phụ/luân lưu (`AFTER EXTRA TIME`, `AFTER PENALTIES`?) | ✅ Thấy `Finished`, `After Extra Time`, **`After 90 minutes`** (luân lưu ngay sau 90'). Tập "đã kết thúc" đã bổ sung |
| U6 | Hai đội trùng mã 3 ký tự trong combobox | ⚠ Chưa gặp; có nhánh xử lý `W_TEAM_CODE_COLLISION` |
| U7 | Hành vi khi Flashscore chặn/captcha; chạy song song nhiều page | ⚠ Không bị chặn trong suốt quá trình kiểm thử (~60 trận); song song nhiều page chưa làm (Phase 5) |
| U8 | Cặp đội có nhiều trận: hành vi khi bỏ `mid` | ✅ Thiếu `mid` vẫn chạy và có `W_NO_MID`. Phát hiện thêm: **thứ tự 2 đội trong URL không phải nhà/khách** (vd `alaves…/ath-bilbao…` cho trận Athletic Bilbao v Alaves) — crawler không dựa vào thứ tự này |

---

## 3. Kiến trúc đích

### 3.1 Tổng quan

```text
┌──────────────────────────────────── máy người dùng (Windows) ────────────────────────────────────┐
│                                                                                                  │
│  Trình duyệt                           server.py (ThreadingHTTPServer, 127.0.0.1:8778)           │
│  match_report.html                                                                               │
│    │ GET /  ───────────────────────────▶  GET  /                  → match_report.html            │
│    │ POST /api/matches {url} ──────────▶  POST /api/matches       → 202 {jobId}                  │
│    │ GET /api/matches/{id}  (1 s) ─────▶  GET  /api/matches/{id}  → status / progress / JSON     │
│    ▼                                      GET  /api/health                                       │
│  state.data · summary ·                            │ hàng đợi (1 job / lần)                      │
│  lineupText · lineupImages                         ▼                                             │
│  → App.enter() → Render (không đổi)         worker thread ─ Playwright (sync) ─ Chromium         │
│                                                                                      │ headless  │
└──────────────────────────────────────────────────────────────────────────────────────┬───────────┘
                                                                                       ▼
                                                                               www.flashscore.com
```

### 3.2 Phương án đã cân nhắc

#### Cách lấy dữ liệu

| Phương án | Mô tả | Ưu | Nhược | Quyết định |
| --- | --- | --- | --- | --- |
| **A. Backend local + Playwright đọc DOM** | Mở trang như người dùng, đọc bảng/timeline/lineups | Tái dùng logic đã kiểm chứng (stats); dữ liệu đúng như người dùng thấy; không phụ thuộc API ngầm | ~45–60 s/trận; cần Chromium; phụ thuộc DOM (selector drift) | ✅ **Chọn** |
| B. Gọi feed nội bộ `global.flashscore.ninja/2/x/feed/…` | HTTP trực tiếp, không cần trình duyệt | Rất nhanh (vài giây) | Định dạng riêng (chưa có parser); header chữ ký `x-fsign` có thể đổi; rủi ro điều khoản dịch vụ có thể cao hơn; bỏ toàn bộ logic DOM đã kiểm chứng | Không chọn *(có thể xem lại như tối ưu hiệu năng ở tương lai)* |
| C. 100% phía trình duyệt, không backend | Trang HTML tự `fetch` | Không cần server | HTML thô không có dữ liệu (V1); trình duyệt không chạy được Chromium; buộc quay về B ngay trong trình duyệt | Loại |

#### Framework server

| Lựa chọn | Dependency mới | Nhận xét | Quyết định |
| --- | --- | --- | --- |
| stdlib `http.server` (`ThreadingHTTPServer`) | 0 | Gần như `python -m http.server` đang dùng; ~150 dòng; đủ cho 1 người dùng local | ✅ **Chọn** |
| aiohttp (đã cài sẵn) | 0 nhưng không được khai báo | Async + Playwright sync cần executor; phụ thuộc gói cài ngẫu nhiên trên máy | Không |
| FastAPI + uvicorn | ≥ 3 | Tiện (schema/validation/docs) nhưng thừa cho phạm vi này và kéo thêm nhiều dependency vào dự án hiện chỉ có Playwright/openpyxl/Pillow | Không *(nâng cấp sau nếu API lớn lên)* |

### 3.3 Cấu trúc thư mục (chỉ **thêm** file mới; file cũ giữ nguyên trừ Phase 3)

```text
Automation Football Dashboard/
├── CLAUDE.md                                  (mới — tài liệu dự án)
├── docs/detailed-design-url-ingestion.md      (mới — tài liệu này)
├── match_report.html                          (Phase 3 — đúng 7 điểm sửa, §7.1)
├── flashscore_scraper.py · _summary.py · _lineups.py   🔒 legacy, KHÔNG sửa
├── .claude/launch.json                        (Phase 2 — thêm mục "app", giữ nguyên "static")
├── server.py                                  (mới — HTTP server + job runner)
├── crawler/
│   ├── __init__.py        crawl(), CrawlError
│   ├── __main__.py        CLI: python -m crawler <link> [--out result.json]
│   ├── run.py             điều phối, tiến độ 10 bước, ngân sách 150 s, FS_DEBUG
│   ├── urls.py            parse / validate / dựng URL tab (giữ mid)
│   ├── browser.py         context, xử lý cookie, chặn tài nguyên, goto có retry + ánh xạ lỗi
│   ├── header.py          tên đội, ngày, trạng thái, tỉ số, logo
│   ├── player_stats.py    7 tab × 2 đội
│   ├── timeline.py        sự kiện (extractor mới)
│   ├── lineups.py         lineups có cấu trúc + hình học sơ đồ
│   ├── assemble.py        ghép JSON theo hợp đồng + cross-check + warnings
│   └── errors.py          mã lỗi / cảnh báo
├── tests/                 unittest (stdlib) — xem §13.3
│   ├── _support.py · legacy_xlsx.py
│   ├── fixtures/          fragment HTML/JSON chụp từ trang thật (9 trận)
│   ├── golden/            demo_views.json — snapshot DOM của luồng demo (chụp từ baseline)
│   ├── unit/   ·   e2e/   ·   live/      (live chỉ chạy khi FS_LIVE=1)
│   └── output/            file tạm, PDF, ảnh chụp (bỏ qua trong git)
├── tools/
│   ├── html_guard.py · verify_frozen.py · check_diff_budget.py
│   ├── golden_demo.py     --write (từ baseline git) | --check | --stability
│   └── capture_fixtures.py
├── .gitignore
└── requirements.txt       playwright==1.60.0 (runtime) · openpyxl, pillow (legacy + test)
```

### 3.4 Luồng xử lý

```text
Người dùng        match_report.html          server.py                worker thread           Flashscore
   │ dán URL, Enter     │                          │                         │                     │
   │───────────────────▶│ kiểm tra nhẹ (client)    │                         │                     │
   │                    │ POST /api/matches ──────▶│ validate + dựng lại URL │                     │
   │                    │◀──── 202 {jobId} ────────│ enqueue                 │                     │
   │                    │ poll GET …/{id} (1 s) ──▶│                         │ launch Chromium     │
   │  overlay           │◀── running + progress ───│                         │ header+timeline ───▶│
   │  "Reading …"       │                          │                         │ stats × 7 tab ─────▶│
   │                    │                          │                         │ lineups ───────────▶│
   │                    │◀── done + result ────────│◀── JSON + warnings ─────│ đóng browser        │
   │                    │ gán state.* → App.enter()│                         │                     │
   │◀──── dashboard ────│                          │                         │                     │
```

### 3.5 Mô hình luồng và vòng đời trình duyệt

- Đối tượng Playwright **sync** không an toàn đa luồng ⇒ **một worker thread duy nhất** sở hữu `sync_playwright()`; mỗi job: `launch → context → pages → close` (cô lập, không rò rỉ giữa các job).
- Luồng xử lý HTTP chỉ đọc/ghi `JobStore` (dict + `threading.Lock`).
- **Không dùng asyncio** ⇒ tránh xung đột event-loop trên Windows khi Playwright sinh subprocess.
- Hàng đợi: tối đa 1 job đang chạy + 1 chờ; thêm nữa ⇒ `429 E_BUSY`.
- Timeout: toàn job 150 s · mỗi điều hướng 30 s · mỗi selector 15 s · 1 lần retry khi hết thời gian điều hướng.
- Tắt server (Ctrl+C) ⇒ đóng browser đang chạy.

---

## 4. Đặc tả API

### 4.1 Endpoint

| Phương thức & đường dẫn | Mục đích | Phản hồi |
| --- | --- | --- |
| `GET /` , `GET /match_report.html` | Phục vụ web (chỉ whitelist 2 đường dẫn này — không liệt kê thư mục) | 200 `text/html; charset=utf-8` |
| `POST /api/matches` | Tạo job. Body: `{"url": "<link trận>"}` (`Content-Type: application/json`, ≤ 2 KB) | `202 {"jobId","status":"queued"}` · `400 E_URL_INVALID` · `429 E_BUSY` |
| `GET /api/matches/{jobId}` | Trạng thái / tiến độ / kết quả | `200` (xem bên dưới) · `404` nếu không có job |
| `GET /api/health` | Kiểm tra server + Playwright | `200 {"ok":true,"playwright":"1.60.0"}` |

Ví dụ (rút gọn):

```jsonc
// POST /api/matches
{ "url": "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n" }
// 202
{ "jobId": "7f3a9c1e", "status": "queued" }

// GET /api/matches/7f3a9c1e  (đang chạy)
{ "jobId": "7f3a9c1e", "status": "running",
  "progress": { "phase": "player_stats", "done": 3, "total": 10, "message": "Reading player stats · Attack (3/7)…" } }

// GET /api/matches/7f3a9c1e  (xong)
{ "jobId": "7f3a9c1e", "status": "done", "progress": { "done": 10, "total": 10 },
  "warnings": [], "result": { /* §5.1 */ } }

// GET /api/matches/7f3a9c1e  (lỗi)
{ "jobId": "7f3a9c1e", "status": "error",
  "error": { "code": "E_MATCH_NOT_FINISHED", "message": "This match has not finished yet.", "hint": "Try again after full time." } }
```

### 4.2 Tiến độ

10 bước: `header+timeline` (1) → `player_stats` (7, mỗi tab một bước) → `lineups` (1) → `assemble` (1). Thông điệp hiển thị trên overlay có sẵn: `Opening match page…` → `Reading player stats · <Tab> (n/7)…` → `Reading line-ups…` → `Drawing the dashboard…` (chuỗi cuối do `App` tự đặt).

### 4.3 Mã lỗi và cảnh báo

| Mã lỗi | HTTP | Khi nào |
| --- | --- | --- |
| `E_URL_INVALID` | 400 | Không phải URL trận bóng đá `flashscore.com` (host, đường dẫn, môn thể thao) |
| `E_BUSY` | 429 | Đang có job đang chạy và 1 job chờ |
| `E_MATCH_NOT_FOUND` | 404 | Trang 404 / không có `.duelParticipant` |
| `E_MATCH_NOT_FINISHED` | 422 | Trạng thái không thuộc tập "đã kết thúc" (✅ `Finished`, `After Extra Time`, `After 90 minutes`; phòng hờ `After Penalties`, `After 120 minutes`, `AET`, `AP`) |
| `E_NO_PLAYER_STATS` | 422 | Thanh tab của trận không có "Player stats" (báo ngay), hoặc bảng rỗng ở cả `top` và `general` (stats là **bắt buộc**, như luồng cũ) |
| `E_NETWORK` | 502 | *(thêm khi triển khai)* Không kết nối được flashscore.com (`net::ERR_*`) |
| `E_BLOCKED` | 502 | Captcha / 403 / 429 / bị chặn |
| `E_TIMEOUT` | 504 | Quá thời gian toàn job |
| `E_INTERNAL` | 500 | Lỗi không lường trước (kèm `jobId` để tra log) |

Mã do chính server trả (không đến từ crawler): `E_FORBIDDEN` (403 — `Host`/`Origin` lạ), `E_UNSUPPORTED_MEDIA_TYPE` (415 — không phải JSON), `E_BAD_REQUEST` (400/413 — body thiếu/quá lớn), `E_NOT_FOUND` (404 — endpoint lạ), `E_JOB_NOT_FOUND` (404 — job đã hết hạn).

Cảnh báo (không chặn kết quả; xuất hiện trong `warnings[]`):

| Mã | Ý nghĩa |
| --- | --- |
| `W_NO_MID` | URL không có `?mid=` — Flashscore chọn trận mặc định; hãy kiểm tra tên/ngày trận |
| `W_TIMELINE_EMPTY` | Trận có bàn thắng nhưng không đọc được sự kiện nào |
| `W_TIMELINE_SCORE_MISMATCH` | Số bàn trong timeline ≠ tỉ số header |
| `W_SCORE_MISMATCH` | Tổng `Goals`(+`Own goals`) của stats ≠ tỉ số header |
| `W_NO_LINEUPS` / `W_LINEUPS_PARTIAL` / `W_NO_FORMATION` | Thiếu toàn bộ / một phần lineups / sơ đồ |
| `W_ROSTER_MISMATCH` | Có cầu thủ đá chính không nằm trong roster stats |
| `W_TEAM_ORDER_SWAPPED` | Thứ tự đội ở combobox bị đảo so với header và đã được tự sửa |
| `W_TEAM_CODE_COLLISION` | Hai đội trùng mã 3 ký tự; mã được đổi thành `HOME`/`AWAY` (chỉ là khoá nội bộ) |
| `W_STATS_TAB_EMPTY` | Một tab stats không đọc được (sau 1 lần retry) |

### 4.4 Bảo mật (server chạy local nhưng có thể điều khiển trình duyệt trên máy bạn)

- Chỉ bind `127.0.0.1`; **không** bật CORS ⇒ trang web khác không thể đọc phản hồi của API.
- `POST /api/matches` **bắt buộc** `Content-Type: application/json` (khác ⇒ `415`). Nhờ đó trang bên ngoài không thể kích hoạt job bằng form hoặc `text/plain` (loại request "đơn giản" không cần preflight); request JSON cross-origin thì bị preflight chặn vì server không trả header CORS.
- Kiểm tra `Host` ∈ {`127.0.0.1:<port>`, `localhost:<port>`} (chống DNS rebinding) và, nếu có `Origin`, phải cùng origin (khác ⇒ `403`).
- URL người dùng **không bao giờ được chuyển tiếp nguyên văn**: parse → kiểm tra allowlist → **dựng lại** từ các thành phần (không SSRF).
- Giới hạn kích thước body, 1 job chạy cùng lúc, timeout cứng, không thực thi lệnh shell, không ghi file trừ thư mục `debug/` khi bật `FS_DEBUG=1`.
- Static: chỉ phục vụ whitelist (khác `python -m http.server` đang phơi cả thư mục).

---

## 5. Hợp đồng dữ liệu

### 5.1 Hình dạng `result`

```jsonc
{
  "schemaVersion": 1,
  "matchId": "vLuGlk0n",
  "sourceUrl": "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n",
  "fetchedAt": "2026-10-09T07:40:00Z",

  "stats": {                                   // → state.data   (BẮT BUỘC)
    "matchTitle": "Johor DT  vs  Svay Rieng",
    "matchDate": "",
    "home": "JOH", "away": "SVA",
    "teams": {
      "JOH": { "Top Stats": { "headers": ["Player","Position","Rating", "…"],
                              "rows": [ { "Player": "Aiman A.", "Position": "Wingback", "Rating": "9.0", "Total shots": "4", "Accurate passes": "23/30 (77%)", "…": "…" } ] },
               "Shots": {}, "Attack": {}, "Passes": {}, "Defense": {}, "Goalkeeping": {}, "General": {} },
      "SVA": { "…": "…" }
    }
  },

  "summary": {                                 // → state.summary (có thể null)
    "events": [ { "minute": "39'", "half": "1st half", "side": "home", "team": "Johor DT",
                  "type": "Goal", "player": "Aiman A.", "detail": "Marcos Guilherme", "score": "1 - 0" } ],
    "homeLogo": "data:image/png;base64,…", "awayLogo": "data:image/png;base64,…",
    "finalScore": { "h": 6, "a": 0 }
  },

  "lineups": {                                 // → state.lineupText (có thể null) — §5.3
    "formation":   { "players": [ { "num": "16", "name": "Hazmi S.", "ok": true, "side": "home", "x": 0.5, "y": 0.1 } ], "w": 100, "h": 176 },
    "starting_xi": [ { "homeNum": "16", "awayNum": "27", "home": { "name": "Hazmi S.", "ok": true }, "away": { "name": "Vireak D.", "ok": true } } ],
    "substituted": { "home": [ { "on": "Aketxe A.", "off": "Stoichkov", "min": "67" } ], "away": [] },
    "substitutes": [ { "homeNum": "47", "awayNum": "18", "home": { "name": "Aketxe A.", "ok": true }, "away": { "name": "Aim S.", "ok": true } } ],
    "coaches":     { "home": { "name": "Xisco", "ok": true }, "away": { "name": "McConkey M.", "ok": true } }
  },

  "lineupImages": { "formation": "data:image/png;base64,…", "starting_xi": "…", "substitutes": "…", "coaches": "…" },   // → state.lineupImages — §5.4
  "warnings": [ { "code": "W_NO_MID", "message": "…" } ]
}
```

### 5.2 Ánh xạ luồng xlsx → JSON (parity)

| Trường `state` | Luồng cũ (xlsx) | Luồng mới (JSON) | Ghi chú parity |
| --- | --- | --- | --- |
| `data.matchTitle` | Ô `B2` sheet `Summary`: `"{home}  vs  {away}"` (**2 dấu cách**) | Cùng định dạng | `Render` tách bằng `/\s+vs\s+/i` nên an toàn |
| `data.matchDate` | Luôn `""` (tiêu đề không có ngoặc) | `""` mặc định | **C3** — ngày giờ có sẵn trên trang nhưng web cũ chưa bao giờ hiển thị |
| `data.home / away` | Mã 3 ký tự theo thứ tự sheet | Cùng; xác minh bằng logo; xử lý trùng mã | Chỉ là khoá tra cứu, không hiển thị |
| `data.teams[c][tab]` | `{headers, rows}` từ sheet `"c - tab"` | Cùng | Mọi giá trị là **string**; ô trống = `"-"`; `headers[0..1] = Player, Position` |
| Tab đọc lỗi | Sheet "Không có dữ liệu" ⇒ `headers:["Không có dữ liệu"]` (tật của parser cũ) | `{headers:[], rows:[]}` + `W_STATS_TAB_EMPTY` | `renderStatTeam` xử lý `!rows.length` ⇒ `emptyTab` |
| `summary.events[*]` | Sheet `Timeline` | Cùng 8 khoá `minute, half, side, team, type, player, detail, score` | `type` ∈ {`Goal`, `Own goal`, `Penalty goal`, `Substitution`, `Yellow card`, `Red card`, `Second yellow (→ red)`, `VAR`, `Card`} (giữ nhãn cũ — `Render` so khớp bằng regex trên các nhãn này) |
| `summary.homeLogo/awayLogo` | Ảnh nhúng `image1/image2` | Data URL tải bằng `ctx.request.get` | Data URL ⇒ html2canvas/PDF không bị "tainted" |
| `summary.finalScore` | `"Final score: a - b"` | `{h,a}` từ `.detailScore__wrapper` | Không dùng để vẽ — scorebar tự tính từ stats |
| `lineupImages` | PNG thật | Placeholder 1×1 (§5.4) | |
| `lineupText` | Kết quả OCR | Dữ liệu cấu trúc (§5.3) | Cùng shape với `LineupOCR.compute()` |

### 5.3 `lineups` — cùng shape với kết quả OCR

| Trường | Nguồn DOM (Phụ lục D.2) | Quy tắc |
| --- | --- | --- |
| `starting_xi[i]` | Nhóm "Starting Lineups": `home[i]` ghép `away[i]` | Giống hàng hiển thị trên Flashscore; `homeNum/awayNum` từ `wcl-number_`; nếu một bên ngắn hơn ⇒ ô trống `{name:"",ok:false}` |
| `substitutes[i]` | Nhóm "Substitutes" | Như trên (số lượng 2 đội có thể khác nhau: 12 vs 11) |
| `substituted.{home,away}[]` | Nhóm "Substituted players" | `{on, off, min}`; `min` bỏ dấu `'` (renderer tự thêm), giữ dạng `45+2` |
| `coaches` | Nhóm "Coaches" | 1 người/đội |
| `formation.players[]` | `fp-formation_` home/away × `fp-row_` × `fp-player_` | `{num, name, ok, side, x, y}` (hình học ở dưới) |
| `name` | — | **Luôn dùng tên từ danh sách** (`Hazmi S.`), **không** dùng nhãn rút gọn trên sân (`Hazmi`/`Marcos …`) — vì `ratingFor()` tra rating bằng so khớp tên **chính xác** với cột `Player` của stats. Ghép theo `id` rồi lấy tên từ roster stats |
| `ok` | — | `true` cho mọi tên lấy từ DOM (xem C4 — hệ quả: dự bị chưa ra sân và HLV không còn bị làm mờ như khi OCR) |

**Hình học sơ đồ** (đo ở viewport **420×900** ⇒ sân dọc, đội nhà trên — ✅ V12/V13)

| Thành phần | Quy tắc |
| --- | --- |
| `w`, `h` | Hằng số `100`, `176` (khớp `viewBox` của `pitchSVG` trong `LineupOCR`) — renderer đặt `aspect-ratio: w/h` |
| `x` | Giá trị đo được: `(tâm − trái_sân) / rộng_sân`, làm tròn 3 chữ số. Hàng 4 người đo được `[0.195, 0.398, 0.602, 0.805]` ⇒ cách ~106 px ở `max-width:520px`, đủ rộng cho nhãn 100 px. Renderer tự kẹp vào [8%, 92%] |
| Thứ tự trong hàng | **Sắp theo `x` tăng dần** — thứ tự DOM của đội khách là phải→trái (đã quan sát) nên không được tin thứ tự DOM |
| `y` — đội nhà | Hàng GK→tiền đạo, `n` hàng, `ri` = chỉ số hàng từ 0: `y = 0.10 + 0.33·t` với `t = ri/(n−1)` (nếu `n = 1` lấy `t = 0.5`) |
| `y` — đội khách | Hàng GK→tiền đạo trong DOM; đặt tiền đạo ở trên: `y = 0.57 + 0.33·t` với `t = (n−1−ri)/(n−1)` ⇒ GK ở `0.90` (đối xứng với đội nhà, đúng quy ước của `parseFormation` hiện tại) |
| Điều kiện dùng | Cần ≥ 4 cầu thủ, nếu không `formation = null` và **không** đưa khoá `formation` vào `lineupImages` ⇒ thẻ Formation không hiển thị |

### 5.4 `lineupImages` chỉ là "công tắc hiển thị"

`renderOverall()` ([:1477](../match_report.html#L1477)) quyết định có dựng từng thẻ Match story hay không bằng `state.lineupImages[key]`; `LineupOCR.run()` ([:1373](../match_report.html#L1373)) thoát sớm nếu `state.lineupText` đã có. Để dùng dữ liệu cấu trúc mà **không sửa** hai hàm đó:

- Với mỗi khối có dữ liệu (`formation`, `starting_xi`, `substitutes`, `coaches`; `substituted` để tương thích), backend đặt `lineupImages[key]` = **PNG trong suốt 1×1** (data URL ~100 byte). Placeholder này **không bao giờ được hiển thị** vì `fillAll(state.lineupText)` vẽ từ dữ liệu cấu trúc.
- **Bất biến:** `lineupImages[key]` tồn tại ⇔ `lineups[key]` khác `null`. Nhờ đó nhánh fallback "dùng ảnh" của renderer không bao giờ bị kích hoạt với ảnh trống.
- Không chụp ảnh thật ⇒ tiết kiệm ~10 s và ~1 MB payload.

### 5.5 Khác biệt hành vi so với luồng xlsx/OCR (để bạn xem và phản đối nếu cần)

1. **Timeline đầy đủ và đúng** (nếu chạy lại script cũ hôm nay sẽ chỉ ra 1 sự kiện/hiệp).
2. **Lineups chính xác tuyệt đối** thay vì OCR; hàng Starting XI/Bench giống thứ tự trên Flashscore.
3. **Dự bị chưa ra sân và HLV không còn "mờ"** (`ok:true` — C4).
4. **Không tải Tesseract.js** trong luồng URL ⇒ nhanh hơn, hoạt động cả khi CDN Tesseract chậm.
5. Logo lấy từ ảnh header (tải riêng) thay vì ảnh nhúng trong xlsx.
6. Tab đọc lỗi cho `{headers:[],rows:[]}` thay vì tật `headers:["Không có dữ liệu"]`.
7. `matchDate` mặc định vẫn `""` để giống hệt luồng cũ (C3).

---

## 6. Thiết kế crawler

Nguyên tắc chung (rút từ việc scraper cũ bị hỏng):

- **S1** Ưu tiên `data-testid` → BEM ổn định (`smv__*`, `duelParticipant__*`, `participant__*`, `detailScore__*`) → `[class*="…"]`. **Không bao giờ** dùng nguyên văn class có hậu tố hash (`wcl-side_YylQz`).
- **S2** Mọi extractor trả về **số lượng** để tự kiểm tra; số lượng bất thường ⇒ cảnh báo, không im lặng.
- **S3** Đọc DOM trong trang bằng `page.evaluate` (một lần/khối) thay vì nhiều lệnh `locator` — nhanh và nguyên tử.
- **S4** Chờ bằng điều kiện (`wait_for_selector`, `wait_for`), không `sleep` cố định (trừ chờ bảng đổi đội, có vòng kiểm tra).
- **S5** Mọi bước có `try/except` riêng và quy tắc "bắt buộc / mềm" (§6.7).

### 6.1 URL (`crawler/urls.py`)

- Chấp nhận: `https://(www.)flashscore.com/match/football/<slug>-<id>/<slug>-<id>/` + tuỳ chọn `summary/...` + tuỳ chọn `?mid=<id>` + tuỳ chọn `#fragment` (bỏ). `<id>` = `[A-Za-z0-9]{6,12}` (ví dụ `AVV6BGlb`, `vLuGlk0n`).
- Kết quả: `MatchRef(team1, team2, mid)` với `ref.url("summary/lineups")` ⇒ `{base}summary/lineups/?mid=…`. **Giữ `mid`** (V6); thiếu `mid` ⇒ vẫn chạy + `W_NO_MID`. ⚠ Thứ tự 2 đội trong URL **không phải** nhà/khách (§2.1 U8) — nhà/khách luôn lấy từ header.
- Từ chối (`E_URL_INVALID`): host khác, `http://`, đường dẫn không bắt đầu `/match/football/`, môn khác.
- URL luôn được **dựng lại** từ các thành phần.

Bảng test tối thiểu: URL của bạn; thiếu `mid`; có `/summary/lineups/`; có `#fragment`; `http://`; host lạ; môn khác (`/match/tennis/…`); khoảng trắng/xuống dòng thừa; chuỗi rỗng.

### 6.2 Trình duyệt (`crawler/browser.py`)

| Mục | Quy tắc |
| --- | --- |
| Khởi chạy | `chromium.launch(headless=True)` (script lineups cũ dùng `headless=False`; V4 chứng minh headless đọc được cả 3 trang) |
| Context | UA Chrome như legacy · `locale="en-GB"` · timezone cố định (chỉ quan trọng nếu hiển thị ngày — C3) |
| Viewport | **1280×900** cho trang chính + stats; **420×900** riêng cho trang lineups (sân dọc, V12) |
| Chặn tài nguyên | `**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}` + `**/ads/**`, `**/analytics/**`, `**/gtm/**` như legacy. Logo tải riêng bằng `ctx.request.get` (không đi qua `page.route`) |
| Cookie | Chờ tối đa 6 s nút `#onetrust-reject-all-handler` (dự phòng `#onetrust-accept-btn-handler`) bằng `locator.wait_for(state="visible")`, click, rồi kiểm tra `#onetrust-consent-sdk` không còn chặn. Dự phòng cuối: ẩn overlay bằng CSS. **Không** dùng `is_visible(timeout=…)` (không chờ — V5). Chọn Reject mặc định (C5) |
| Timeout mặc định | 30 s mỗi điều hướng, 15 s mỗi selector |

### 6.3 Header + logo (`crawler/header.py`)

| Trường | Selector (✅) |
| --- | --- |
| Tên đội nhà / khách | `.duelParticipant__home .participant__participantName` / `.duelParticipant__away …` (`.first` — có 2 phần tử vì header cố định) |
| Ngày giờ | `.duelParticipant__startTime` (vd `08.10.2026 19:00`) |
| Tỉ số | `.detailScore__wrapper` → regex `(\d+)\D+(\d+)` |
| Trạng thái | `.detailScore__status` (✅ `FINISHED`) |
| Logo | `.duelParticipant__home img.participant__image` → `src` (thêm `https:` nếu bắt đầu bằng `//`) → `ctx.request.get` → `data:<mime>;base64,…` |

Lỗi: không có tên đội ⇒ `E_MATCH_NOT_FOUND`; trạng thái không thuộc tập "đã kết thúc" ⇒ `E_MATCH_NOT_FINISHED`.

### 6.4 Player stats (`crawler/player_stats.py`)

```text
TABS = top, shots, attack, passes, defense, goalkeeping, general        (nhãn: Top Stats, Shots, …, General — như legacy)
for i, tab in enumerate(TABS):
    goto  {base}summary/player-stats/{tab}/?mid=…
    chờ   [data-testid="wcl-table"]  (15 s)        # i == 0 mà không có ⇒ E_NO_PLAYER_STATS
    if i == 0:
        teams = đọc combobox [role="option"] bỏ "ALL", lấy nhãn = token cuối, giữ 2 đội đầu
        kiểm tra: đúng 2 nhãn, khác nhau (trùng ⇒ đặt nhãn "HOME"/"AWAY", chọn đội theo thứ tự option + W_TEAM_CODE_COLLISION)
        xác minh thứ tự: logo trong ô cầu thủ của đội teams[0] == logo header đội nhà (V15); sai ⇒ đảo + W_TEAM_ORDER_SWAPPED
    for team in teams:                                # ĐỔI ĐỘI NGAY TRONG TRANG — không goto lại
        mở combobox → click option có text == nhãn
        chờ bảng đổi (≤ 5 s): tập player-id khác tập của đội kia/trước đó
        headers, rows, ids = read_table()
    kiểm tra: ids(đội 1) ∩ ids(đội 2) = ∅
```

`read_table()` (giữ ngữ nghĩa legacy): `headers = ["Player","Position", *th[1:]]` (`th[0]` là nút lọc đội, hiển thị "ALL"/mã đội); mỗi dòng `{header: giá trị}` theo thứ tự header; ô trống ⇒ `"-"`; ô cầu thủ: dòng 1 = tên, dòng 2 = vị trí; `player-id` từ `data-analytics-player-id` (chỉ dùng nội bộ để ghép lineups, **không** đưa vào payload). Dùng `inner_text()` + `strip()` y như legacy để chuỗi **giống từng byte** (cần cho test parity).

Fail-soft: tab lỗi sau 1 retry ⇒ `{headers:[],rows:[]}` + `W_STATS_TAB_EMPTY`; nếu cả `top` và `general` rỗng ⇒ `E_NO_PLAYER_STATS`.

### 6.5 Timeline (`crawler/timeline.py`) — extractor mới (Phụ lục D.1)

Chạy trên **trang chính** (cùng lần `goto` với header ⇒ không tốn thêm điều hướng).

| Trường | Nguồn DOM (✅) |
| --- | --- |
| `half` | `aria-label` của `<ol class="smv__period-list">` (`1st Half`/`2nd Half`) → `1st half`/`2nd half`/`Extra time`/`Penalties` |
| `side` | Class `smv__homeParticipant` / `smv__awayParticipant` của `<li>` |
| `minute` | `[class*="timeBox"]` (vd `39'`, `45+2'`) |
| `type` | Có điểm số ⇒ `Own goal` (icon `footballOwnGoal-ico` hoặc chữ "own goal") / `Penalty goal` (icon `penalty-goal` hoặc chữ "penalt") / `Goal`; ≥ 2 tên hoặc icon `substitution` ⇒ `Substitution`; icon `penalty-missed` ⇒ `Penalty missed` *(nhãn mới; trước đây rơi vào `Card`)*; icon `var` ⇒ `VAR`; còn lại theo icon: `yellowRedCard`/`red-card-second` → `Second yellow (→ red)`, `redCard`/`red-card` → `Red card`, `yellowCard` → `Yellow card`, khác → `Card` |
| `player` | Tên đầu tiên ngoài khối kiến tạo; với thay người là cầu thủ **vào**; với VAR là tên trong khối `smv__assist` |
| `detail` | Goal: tên kiến tạo (`smv__assist`, bỏ ngoặc) · Card: lý do (`smv__subIncident`) · Sub: `Out: <tên ra>` · VAR: quyết định (vd "Goal Disallowed - offside") · Penalty missed: rỗng |
| `score` | Regex `(\d+)\s*[-:]\s*(\d+)` trên chữ của hàng |
| Loạt luân lưu | Hàng thuộc `<ol aria-label="Penalties">` **bị bỏ**: ô thời gian là thứ tự lượt sút ("1"…), đưa vào sẽ thành marker sai ở phút 1–7; dashboard hiện tại không có chỗ hiển thị kết quả luân lưu (đổi UI ⇒ cần phê duyệt) |

Kiểm tra chéo: số `Goal`+`Penalty goal`+`Own goal` phải bằng tổng tỉ số header, nếu không `W_TIMELINE_SCORE_MISMATCH`. Hàng đọc được nhưng 0 sự kiện trong trận có bàn thắng ⇒ `W_TIMELINE_EMPTY`.

✅ U1/U2 đã kiểm chứng ở Phase 4 (§2.1); mỗi loại sự kiện có fixture và test offline riêng (`tests/unit/test_timeline_rare_events.py`).

### 6.6 Lineups (`crawler/lineups.py`) — dữ liệu có cấu trúc (D3)

1. Trang `…/summary/lineups/?mid=…` ở viewport 420×900; chờ `[data-testid="wcl-lineupsGroup"]` (10 s). Không có ⇒ `lineups = null` + `W_NO_LINEUPS`.
2. Chạy extractor D.2 → thô: 4 nhóm theo tiêu đề (en-GB, chữ thường: `substituted players`, `starting lineups`, `substitutes`, `coaches`) + sơ đồ. Nếu tiêu đề không khớp (đổi locale) ⇒ phân loại theo cấu trúc: nhóm có `wcl-lineupsParticipantsSubstitution-*` = thay người; nhóm đầu có ≥ 9 người/đội = đá chính; nhóm sau = dự bị; nhóm 1 người/đội không có số áo = HLV.
3. Ghép theo `player-id` với roster stats (`id → tên`); xây `lineups` theo §5.3; hình học theo §5.3.
4. Kiểm tra: đá chính 11/11 (lệch ⇒ `W_LINEUPS_PARTIAL`); id đá chính ⊂ roster (lệch ⇒ `W_ROSTER_MISMATCH`); id đá chính đội nhà ⊂ stats đội nhà (nếu thuộc đội kia ⇒ đảo + `W_TEAM_ORDER_SWAPPED`).

### 6.7 Điều phối và quy tắc lỗi

```text
run_job(ref):
  ctx = new_context()
  page = new_page(1280x900); goto base; xử lý cookie
  info     = header(page)                         # BẮT BUỘC
  summary  = timeline(page) + logos               # MỀM
  tabs     = thanh tab của trận                   # không có "Player stats" ⇒ E_NO_PLAYER_STATS ngay
  stats    = player_stats(page, ref)              # BẮT BUỘC (top|general)
  lineups  = lineups(new_page(420x900), roster)   # MỀM; không có tab "Lineups" ⇒ bỏ qua + W_NO_LINEUPS
  return assemble(info, stats, summary, lineups)  # cross-check → warnings
```

| Nguồn | Lỗi thì | Lý do |
| --- | --- | --- |
| Header | Dừng — `E_MATCH_NOT_FOUND` / `E_MATCH_NOT_FINISHED` / `E_BLOCKED` | Không biết trận nào |
| Player stats | Dừng — `E_NO_PLAYER_STATS` / `E_TIMEOUT` | Dashboard cần stats (như luồng cũ) |
| Timeline | Tiếp tục, `summary` có thể `null` + cảnh báo | Luồng cũ coi là tuỳ chọn |
| Lineups | Tiếp tục, `lineups = null`, `lineupImages = {}` + cảnh báo | Luồng cũ coi là tuỳ chọn |

**Kiểm tra chéo trong `assemble()`** (chỉ sinh cảnh báo, không bao giờ làm hỏng kết quả):

| Kiểm tra | Cảnh báo khi lệch |
| --- | --- |
| Số `Goal`+`Penalty goal`+`Own goal` của timeline = tổng tỉ số header | `W_TIMELINE_SCORE_MISMATCH` |
| `Σ Goals(đội A) + Σ Own goals(đội B)` của stats = tỉ số header cho từng đội (đúng công thức mà `Render.scorebar` đang dùng) | `W_SCORE_MISMATCH` |
| Đá chính 11/11; id đá chính ⊂ roster stats | `W_LINEUPS_PARTIAL` / `W_ROSTER_MISMATCH` |
| Mã đội, thứ tự đội khớp logo header | `W_TEAM_ORDER_SWAPPED` |

Khi `FS_DEBUG=1`: lưu HTML của bước lỗi vào `debug/<jobId>/<bước>.html` (thay cho file `_DEBUG.html` của script cũ).

### 6.8 Hiệu năng (đo ở V4/V7)

| Bước | Thời gian |
| --- | --- |
| Khởi động Chromium + context | ~1 s |
| Header + timeline + logo | ~3 s |
| Stats: 7 tab × (load + đổi 2 đội) | ~5,7 s × 7 ≈ 40 s |
| Lineups | ~4 s |
| **Tổng** | **≈ 45–60 s** *(ước tính lúc thiết kế)*. **Đo thật khi triển khai: 31–61 s** cho 6 trận khác nhau, một lần 75 s khi Flashscore chậm. Script stats cũ đo được ~125 s cho cùng trận #1 (test parity) |

Tối ưu về sau (ngoài phạm vi v1, cần phê duyệt): chạy song song ≤ 3 page ⇒ ≈ 20 s; cache kết quả theo `matchId` ngắn hạn.

---

## 7. Thay đổi front-end (`match_report.html`)

Đây là **phase duy nhất sửa file hiện có** (Phase 3). Số dòng dưới đây theo **baseline** (SHA-256 ở phụ lục B) và sẽ dịch chuyển sau khi sửa — vì vậy công cụ kiểm tra dùng *chuỗi đánh dấu*, không dùng số dòng (§9.2).

### 7.1 Change surface — danh sách ĐẦY ĐỦ những gì được phép sửa

| ID | Vùng (baseline) | Loại | Nội dung | Lý do |
| --- | --- | --- | --- | --- |
| E1 | HTML [:511](../match_report.html#L511) | Sửa chữ | Đoạn mô tả trong `.upload-hero`: bỏ "Drop in your two Flashscore exports…" → "Paste a Flashscore match link…" | Chữ cũ nhắc tới upload |
| E2 | HTML [:514–547](../match_report.html#L514) và [:550](../match_report.html#L550) | **Thay** | (a) `.drop-grid` (3 ô upload) → khối `#urlForm` gồm `<label>` ẩn, input `#flashUrl`, dòng gợi ý, dòng lỗi `#urlError`. (b) Trong `.upload-cta`: nút `#btnBuild` ("Build dashboard") → `#btnGenerate` ("Generate report", cùng class `btn btn-primary`, `onclick="App.buildFromUrl()"`, `disabled`). **Giữ** `.upload-cta` và nút demo (:551) | D1 |
| E3 | CSS, ngay trước `</style>` ([:479](../match_report.html#L479)) | **Thêm** | Quy tắc `.url-form`, `.url-input`, `.url-hint`, `.url-error` dùng token có sẵn (`--panel`, `--border`, `--good`, `--bad`). Không sửa quy tắc nào hiện có | Giao diện ô URL |
| E4 | JS [:1000–1018](../match_report.html#L1000) và [:1091](../match_report.html#L1091) | **Xoá** + thêm | Xoá `setupDropzones`, `wireDrop`, `handleFile` (kèm dòng chú thích `/* dropzones */`) và listener `DOMContentLoaded→setupDropzones`; thêm `setupUrlForm`, `setUrlError` (+ listener mới) | Các phần tử đích không còn tồn tại ⇒ nếu giữ sẽ ném `TypeError` ngay khi tải trang |
| E5 | JS [:1022–1041](../match_report.html#L1022) | **Thay** | `App.build()` → `App.buildFromUrl()`; thêm đối tượng `Api` (fetch + polling) ngay trước `const App` | D1 |
| E6 | JS [:1072–1075](../match_report.html#L1072) | **Sửa** | Trong `App.reset()`: bỏ 4 dòng tham chiếu `.drop-zone`, `nameStats/…`, `fileStats/…`, `btnBuild`; thêm xoá `#flashUrl` và `#urlError` | Nếu giữ ⇒ "New match" ném `TypeError: Cannot set properties of null` |
| E7 | JS [:1497](../match_report.html#L1497) | Sửa chữ | Trong `renderOverall`, chuỗi empty-state "Add the **lineups** export to see…" → "Line-ups are not available for this match." | Chữ cũ tham chiếu tới upload; chỉ đổi 1 chuỗi, không đổi logic |

**Tuỳ chọn — chỉ làm nếu bạn đồng ý (C2):** O1 chữ footer web [:566](../match_report.html#L566) "Data from Flashscore exports"; O2 chữ footer PDF [:2444](../match_report.html#L2444) (nằm trong vùng đóng băng).

**Phase 5 (đã duyệt 2026-10-13) mở rộng Change surface thêm E8–E14** — gỡ mã xlsx mồ côi, O1/O2 thành E13/E14; chi tiết ở §13.5.

**🔒 Vùng đóng băng — giữ nguyên từng byte** (kiểm bằng hash — §9.2):

| Vùng | Baseline |
| --- | --- |
| Toàn bộ CSS hiện có | :12–478 |
| Dữ liệu demo `window.__DEMO_STATS`, `window.__DEMO_IMAGES` | :579–580 |
| `JSZipLite` | :589–772 |
| Hằng `TABS`, `U`, `toast`, `showLoading`, `hideLoading`, `destroyCharts` | :791–845 |
| `App.loadDemo`, `enter`, `setTeam`, `setTab`, `exportPDF` | :1042–1063, :1078–1088 |
| `LineupOCR` (cần cho demo) | :1102–1382 |
| `Render` (trừ **duy nhất** dòng 1497 của E7) | :1387–1496 và :1498–2301 |
| `Exporter` | :2310–2451 |
| Parser xlsx `readWorkbook … parseSummaryWorkbook` (còn lại như mã mồ côi cho tới Phase 5) | :848–998 |

### 7.2 Giao diện mới

```text
┌─────────────────────────────────────────────────────────────────┐
│     90 minutes · 22 players · one story                         │
│     Turn match data into tactical insight                       │
│     Paste a Flashscore match link and get a full performance    │
│     dashboard for both teams — ready to read or export.         │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ https://www.flashscore.com/match/football/…             │   │
│   └─────────────────────────────────────────────────────────┘   │
│   Works with finished football matches. Keep the ?mid= part     │
│   of the link if it has one.                                    │
│   ⚠ (dòng báo lỗi — aria-live="polite", ẩn khi rỗng)            │
│                                                                 │
│                    [  Generate report  ]                        │
│       or explore with sample data (Korea vs Czech Republic)     │
└─────────────────────────────────────────────────────────────────┘
```

Bố cục giữ đúng nhịp của màn hình hiện tại (hero → nội dung → `.upload-cta` gồm nút chính + link demo) nên tái dùng CSS `.upload-cta`/`.btn-primary`/`.demo-link` sẵn có; chỉ ô nhập và hai dòng chữ là CSS mới (E3).

Trạng thái: **idle** (nút bật khi chuỗi bắt đầu bằng `https://…flashscore.com/match/football/`) → **loading** (overlay có sẵn, thông điệp theo tiến độ) → **error** (dòng lỗi inline màu `--bad` + toast lỗi) → **success** (`App.enter()`). Enter trong ô nhập = bấm nút; tự `trim()` khi dán; `<label>` ẩn cho trình đọc màn hình; ≤ 600 px: ô nhập chiếm toàn chiều rộng.

### 7.3 Logic JS mới (giả mã — bám phong cách code hiện có)

```js
const FLASH_URL_RE = /^https:\/\/(www\.)?flashscore\.com\/match\/football\//i;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const Api = {
  async start(url){
    let r;
    try { r = await fetch('/api/matches', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ url }) }); }
    catch(e){ throw new Error('Cannot reach the local server. Run "python server.py" and open http://127.0.0.1:8778'); }
    const j = await r.json().catch(() => null);
    if(!r.ok || !j) throw new Error((j && j.error && j.error.message) || ('Server error ' + r.status + ' — is this page served by server.py?'));
    return j.jobId;
  },
  async wait(jobId, onProgress){
    const t0 = Date.now();
    for(;;){
      const r = await fetch('/api/matches/' + jobId);
      const j = await r.json().catch(() => null);
      if(!r.ok || !j) throw new Error('Lost contact with the local server (HTTP ' + r.status + ').');
      if(j.progress) onProgress(j.progress);
      if(j.status === 'done') return j;
      if(j.status === 'error') throw new Error(j.error.message);
      if(Date.now() - t0 > 180000) throw new Error('Timed out while reading the match.');
      await sleep(1000);
    }
  },
};

// trong const App = { … }:
async buildFromUrl(){
  const url = document.getElementById('flashUrl').value.trim();
  if(!FLASH_URL_RE.test(url)){ setUrlError('Paste a Flashscore football match link.'); return; }
  setUrlError(''); showLoading('Opening match page…');
  try{
    const jobId = await Api.start(url);
    const res   = await Api.wait(jobId, p => showLoading(p.message));
    const out   = res.result;
    state.data = out.stats;              state.summary = out.summary || null;
    state.lineupImages = out.lineupImages || {};   state.lineupText = out.lineups || null;
    showLoading('Drawing the dashboard…'); await sleep(120);
    App.enter();
    if((res.warnings || []).length) toast(res.warnings[0].message);
  }catch(e){ console.error(e); hideLoading(); setUrlError(e.message); toast(e.message, true); }
},
```

`setupUrlForm()`: gắn `input` ⇒ bật/tắt `#btnGenerate`, `keydown Enter` ⇒ `App.buildFromUrl()`. `setUrlError(msg)`: đặt chữ cho `#urlError` (ẩn khi rỗng). Cả hai là hàm mới, không đụng tới hàm cũ.

### 7.4 Những gì **không** đụng tới (và vì sao)

- `LineupOCR`: demo vẫn đưa ảnh vào OCR; xoá nó làm hỏng demo.
- `Render`, `Exporter`: luồng URL cho ra `state` cùng hình dạng ⇒ dashboard/PDF chạy y hệt.
- Nút demo + `window.__DEMO_*`: không có yêu cầu gỡ (C1).
- `state.statsFile/lineupFile/summaryFile` ([:781](../match_report.html#L781)) và dòng đầu của `App.reset` ([:1065](../match_report.html#L1065)): vô hại, giữ để giảm số điểm sửa.

### 7.5 Bán kính ảnh hưởng của việc thay UI (kết quả quét thật — V18)

| Loại | Tham chiếu tới phần tử/hàm upload | Xử lý |
| --- | --- | --- |
| CSS | `.drop-grid`, `.drop-zone*`, `.drop-icon*` (:116–140) | Để nguyên (mã mồ côi vô hại) — Phase 5 mới gỡ |
| HTML | 3 ô upload (:514–547), `#btnBuild` (:550) | Thay (E2) |
| JS | `setupDropzones/wireDrop/handleFile` (:1001–1018), `App.build` (:1022–1041), `App.reset` (:1072–1075), listener (:1091) | Xoá/sửa (E4–E6) |
| **Mồ côi sau Phase 3** | `JSZipLite`, `readWorkbook`, `parseStatsSheet/Workbook`, `parseLineupWorkbook`, `relTarget`, `normalizePath`, `bytesToDataURL`, `parseSummaryWorkbook`, và thẻ `<script>` SheetJS (:7) — chỉ được các hàm trên dùng | **Giữ nguyên** cho tới Phase 5 (cần phê duyệt) |

---

## 8. Kế hoạch triển khai — các bước điều chỉnh

Mỗi phase có **cổng ra**; chưa qua cổng thì không bắt đầu phase sau. Phase 1–2 chỉ thêm file mới nên rollback = xoá thư mục/file thêm vào. Phase 3 rollback = khôi phục bản baseline của `match_report.html`.

### Phase 0 — Safety net (không đổi sản phẩm)

| Bước | Việc | Tiêu chí hoàn thành |
| --- | --- | --- |
| 0.1 | Tạo điểm khôi phục: **khuyến nghị** `git init` + commit baseline (cần bạn đồng ý — C6); nếu không, bản sao ngoài thư mục dự án. Đối chiếu SHA-256 phụ lục B | Khôi phục được file đúng hash |
| 0.2 | Nếu dùng git: `.gitignore` cho `__pycache__/`, `.playwright-mcp/`, `debug/` | — |
| 0.3 | Viết harness **golden snapshot** cho luồng demo (§9.3) trên HTML gốc | Chạy 2 lần liên tiếp cho kết quả giống hệt |
| 0.4 | Viết `tools/verify_frozen.py` và `tools/check_diff_budget.py` (§9.2) | Chạy được trên HTML gốc (0 khác biệt) |

**G0:** harness xanh trên HTML gốc · công cụ chạy được · bạn xác nhận điểm khôi phục.

### Phase 1 — Crawler core (chỉ file mới)

| Bước | Việc | Tiêu chí hoàn thành |
| --- | --- | --- |
| 1.1 | `urls.py` + bảng test §6.1 | Tất cả case đạt |
| 1.2 | `browser.py` (headless, cookie bằng `wait_for`, chặn tài nguyên) | Không còn lỗi "intercepts pointer events" |
| 1.3 | `header.py` + logo | Trận #1: `Johor DT`/`Svay Rieng`, `6 - 0`, `FINISHED`, 2 logo |
| 1.4 | `player_stats.py` + fixture + **test parity** với `flashscore_scraper.py` (hàm legacy được import trong test, không sửa) | `stats` khớp 100% từng ô với xlsx legacy |
| 1.5 | `timeline.py` (D.1) + fixture offline (`page.set_content`) | Trận #1: 21 sự kiện (6/5/10), cross-check tỉ số đạt |
| 1.6 | `lineups.py` (D.2 + hình học) + fixture + test hình học bằng dữ liệu giả | Trận #1: 11/11, 12/11, 5/5, HLV, 22 cầu thủ sơ đồ; 0 `W_ROSTER_MISMATCH` |
| 1.7 | `assemble.py`, `errors.py` + kiểm tra schema | JSON đúng §5.1 |
| 1.8 | CLI `python -m crawler <url> --out result.json` | Chạy tay được; in cảnh báo |

**G1:** CLI trận #1 → JSON đạt schema + giá trị kỳ vọng (phụ lục C) + parity stats 100% + hash 3 script legacy không đổi.

### Phase 2 — Local server

| Bước | Việc | Tiêu chí hoàn thành |
| --- | --- | --- |
| 2.1 | `server.py`: static whitelist, `JobStore`, worker thread, polling | POST → poll → `done` với trận #1 |
| 2.2 | Ánh xạ lỗi §4.3; kiểm tra `Host`/`Origin`; giới hạn body | Test: URL xấu → 400; job thứ 2 → 429; `Origin` lạ → 403 |
| 2.3 | `.claude/launch.json`: **thêm** mục `app` (port 8778), giữ `static` | `static` vẫn chạy như cũ |
| 2.4 | Test API bằng script (`urllib`) + mô phỏng timeout/lỗi | Đạt |

**G2:** các test trên xanh; `GET /` trả đúng file baseline (hash khớp).

### Phase 3 — Front-end (phase duy nhất sửa `match_report.html`)

| Bước | Việc | Tiêu chí hoàn thành |
| --- | --- | --- |
| 3.1 | Chạy G0 một lần nữa ngay trước khi sửa | Xanh |
| 3.2 | E3 (CSS thêm) → E2/E1 (HTML) → E4–E6 (JS) → E7 (chuỗi) | — |
| 3.3 | `check_diff_budget` | Danh sách thay đổi **khớp đúng** §7.1, không dòng nào ngoài |
| 3.4 | `verify_frozen` | Mọi vùng đóng băng trùng hash |
| 3.5 | Golden snapshot luồng demo | **Không đổi** |
| 3.6 | e2e với API giả lập (dựng JSON từ `__DEMO_STATS`) | DOM Overall + 5 tab × 3 chế độ đội trùng golden (trừ khối Match story) |
| 3.7 | e2e thật trên trận #1 | Dashboard, mọi tab, Export PDF chạy |
| 3.8 | Checklist thủ công R-01…R-20 (§9.7) | Đạt hết |

**G3:** 3.3–3.8 đạt. Nếu có bất kỳ chênh lệch nào so với §7.1 ⇒ dừng, hỏi bạn.

### Phase 4 — Hardening và nghiệm thu

| Bước | Việc | Tiêu chí hoàn thành |
| --- | --- | --- |
| 4.1 | Bộ trận tham chiếu ≥ 6, phủ: thẻ đỏ/thẻ vàng thứ hai, penalty, own goal, VAR, hiệp phụ, luân lưu, không lineups, không player stats, có lineups không có sơ đồ (U1–U8) | Extractor đúng hoặc tạo cảnh báo hợp lý; cập nhật §6.5 |
| 4.2 | Diễn tập lỗi: URL sai, tắt mạng, trận chưa đá, bị chặn (giả lập), timeout | Thông báo rõ, UI không treo |
| 4.3 | Đo thời gian thật trên máy bạn | ≤ 60 s/trận |
| 4.4 | Cập nhật `CLAUDE.md` và tài liệu này theo hiện thực | Khớp code |
| 4.5 | Nghiệm thu với 3 trận thật do bạn chọn | Bạn xác nhận |

**G4:** nghiệm thu xong.

### Phase 5 — Tuỳ chọn, **cần phê duyệt riêng**

- 5.1 Gỡ mã mồ côi: parser xlsx, `JSZipLite`, thẻ SheetJS, CSS `.drop-*`.
- 5.2 Chuyển 3 script legacy vào `legacy/` hoặc gỡ.
- 5.3 Chạy song song ≤ 3 page, cache theo `matchId`.
- 5.4 Đổi chữ footer web/PDF (O1/O2).

---

## 9. Kiểm thử và chống hồi quy

### 9.1 Các lớp kiểm thử

| Lớp | Kiểm gì | Cần mạng | Khi nào chạy |
| --- | --- | --- | --- |
| Frozen + diff-budget | Chỉ những vùng trong §7.1 bị đổi | Không | Mỗi lần sửa HTML |
| Golden snapshot (demo) | DOM render của luồng demo không đổi | CDN thư viện | Trước/sau Phase 3 |
| Unit | `urls`, phân loại sự kiện, hình học sơ đồ, `assemble`/schema | Không | Mỗi commit |
| Fixture (offline) | Extractor JS chạy trên HTML đã lưu qua `page.set_content()` | Không | Mỗi commit |
| Parity | Stats mới ≡ xlsx legacy cho cùng trận | Có | Phase 1 + 4 |
| e2e (API giả lập) | Luồng URL → dashboard, không phụ thuộc Flashscore | CDN | Phase 3 |
| e2e thật + canary | Pipeline thật trên bộ trận tham chiếu | Có | Phase 4, trước mỗi release, định kỳ hằng tuần |

### 9.2 Frozen-region và diff-budget

- Mỗi vùng đóng băng được xác định bằng **chuỗi mở/đóng** trong HTML (vd `const JSZipLite = (()=>{` … `})();`), trích từ file baseline và file hiện tại rồi so SHA-256. Dùng chuỗi đánh dấu thay vì số dòng để chịu được dịch dòng.
- `check_diff_budget`: so baseline với hiện tại theo dòng; mỗi khối thay đổi phải thuộc **một trong 7 mã E1–E7** (xác định bằng chuỗi neo). Khối nào không thuộc ⇒ **fail**. Kết quả in ra để bạn đối chiếu bằng mắt với §7.1.
- Hai dòng khổng lồ (579–580) được so bằng hash, không in ra.

### 9.3 Golden snapshot của luồng demo

Playwright mở HTML gốc → bấm demo → với mỗi `team ∈ {all, home, away}` × `tab ∈ {overall, shots, attack, passes, defense, goalkeeping}` ghi: `innerHTML` của `#tc-<tab>` (bỏ các slot `#lc-*` vì OCR bất đồng bộ), `#scorebar`, `#tabNav`, và với mỗi biểu đồ trong `state.charts`: `type` + `JSON.stringify(data)`. Lưu `tests/golden/demo.json`. Tab `overall` chỉ chụp một lần (không phụ thuộc chế độ đội). Sau Phase 3 chạy lại — **phải giống hệt**. (Luồng URL được kiểm riêng ở 3.6.)

### 9.4 Parity xlsx ↔ JSON (stats)

Cho cùng một trận (chạy liền nhau để dữ liệu không đổi): chạy hàm legacy của `flashscore_scraper.py` để sinh workbook → đọc bằng `openpyxl` → áp ngữ nghĩa của `parseStatsSheet` (tìm hàng chứa `Player`, bỏ header rỗng, ô trống → `"-"`) → so với `result["stats"]` bằng `==`. Kỳ vọng: **0 khác biệt**. Chỉ stats có parity vì 2 script kia đã hỏng.

### 9.5 Fixture (offline)

Lưu fragment từ trang thật: bảng stats (`wcl-table`), `.smv__verticalSections`, widget lineups. Test = `page.set_content(<fragment>)` rồi chạy extractor và so với JSON kỳ vọng. Riêng **hình học sơ đồ** cần CSS thật nên: test thuật toán `y`/thứ tự `x` bằng dữ liệu giả; còn số đo thật do canary live kiểm.

### 9.6 Canary live

Bộ trận tham chiếu nằm trong `tests/live/test_live_reference.py` (khi triển khai đặt thẳng trong test thay vì file JSON riêng): kiểm những điều ổn định (mã đội, đủ 7 tab, số bàn, loại sự kiện phải có, 11 người đá chính, 22 cầu thủ sơ đồ, 0 cảnh báo), không so giá trị chính xác vì Flashscore có thể hiệu chỉnh. Chạy `FS_LIVE=1 python -m unittest discover -s tests/live -t .` theo yêu cầu/định kỳ để phát hiện *selector drift* sớm — chính là loại lỗi đã làm hỏng 2/3 script cũ.

### 9.7 Checklist thủ công

| ID | Bước | Kỳ vọng |
| --- | --- | --- |
| R-01 | Mở `http://127.0.0.1:8778/` | Có hero, ô URL, nút Generate, link demo; **không còn** 3 ô upload; console không lỗi |
| R-02 | Bấm demo | Dashboard Korea vs Czech Republic; scorebar có tên + tỉ số; không toast lỗi |
| R-03 | Overall (demo) | Head-to-head 12 hàng, radar, 8 thẻ best/worst; Match story hiện sau OCR — **không đổi** so với trước |
| R-04 | 5 tab × All/Home/Away (demo) | Mọi tổ hợp render; Goalkeeping Home/Away có hồ sơ thủ môn; Passes/Shots có scatter |
| R-05 | Bấm tiêu đề cột bảng | Sắp xếp tăng/giảm đúng |
| R-06 | Export PDF (demo) | Tải `MatchReport_*.pdf`: cover, header band, footer, nhiều trang |
| R-07 | "New match" | Về màn hình URL, ô URL rỗng, **không lỗi console** (kiểm tra E6) |
| R-08 | Dán link trận #1 → Generate | Overlay chạy theo bước, 45–60 s, vào dashboard JOH–SVA tỉ số 6–0 |
| R-09 | Overall (URL) | Scorebar có logo + 6 bàn thắng dưới Johor DT; timeline 21 marker (hover có tooltip); Formation 22 chấm có rating; Starting XI 11 hàng; Bench; Coaches |
| R-10 | Tab stats (URL) | Bảng đủ cột/hàng (Top Stats 16 dòng mỗi đội), rating badge, số liệu khớp trang Flashscore |
| R-11 | Export PDF (URL) | PDF có đủ tab, gồm Match story |
| R-12 | Dán chuỗi không phải link Flashscore | Báo lỗi inline, **không gọi server** |
| R-13 | Tắt server rồi Generate | Thông báo "Cannot reach the local server…" |
| R-14 | Link trận chưa kết thúc | `E_MATCH_NOT_FINISHED` hiển thị rõ |
| R-15 | Link trận không có player stats | `E_NO_PLAYER_STATS` hiển thị rõ |
| R-16 | Link không có `?mid=` | Toast `W_NO_MID`, dashboard vẫn dựng |
| R-17 | Màn hình ≤ 600 px | Form dùng được, không tràn ngang |
| R-18 | Mở `match_report.html` bằng `file://` | Demo vẫn chạy; Generate báo không kết nối được server |
| R-19 | Chạy trận A → "New match" → trận B | Không rò state (biểu đồ, `lineupText`) |
| R-20 | Ba tab trình duyệt cùng gửi | Tab thứ hai được xếp hàng (1 chạy + 1 chờ — §3.5), tab thứ ba nhận `E_BUSY` *(sửa lại cho khớp §3.5 khi triển khai)* |

---

## 10. Rủi ro

| # | Rủi ro | Khả năng | Ảnh hưởng | Giảm thiểu |
| --- | --- | --- | --- | --- |
| K1 | Flashscore đổi DOM (đã xảy ra) | Cao | Trung bình | S1–S5; fixture + canary; cảnh báo thay vì rỗng im lặng; debug snapshot |
| K2 | Flashscore chặn/captcha/giới hạn tốc độ | Thấp–TB | Cao | 1 job tuần tự, không song song ở v1; `E_BLOCKED` + hướng dẫn; UA/locale thật |
| K3 | Điều khoản dịch vụ Flashscore | TB | Cao | Chỉ dùng cá nhân/nội bộ, tốc độ thấp, không lưu/phát hành lại dữ liệu; bạn nên đọc điều khoản trước khi dùng rộng *(tôi chưa đối chiếu nội dung điều khoản)* |
| K4 | Hồi quy ở front-end | TB | Cao | Change surface hẹp, diff-budget, hash đóng băng, golden snapshot, checklist R-01…R-20 |
| K5 | Chưa có git ⇒ không khôi phục được | Cao | Cao | Phase 0.1 bắt buộc có điểm khôi phục trước khi sửa |
| K6 | Trận thiếu dữ liệu (giải nhỏ: không player stats/lineups) | TB | TB | Stats bắt buộc ⇒ lỗi rõ; timeline/lineups mềm ⇒ web hiển thị khối trống như hôm nay |
| K7 | Sự kiện hiếm/hiệp phụ/luân lưu chưa quan sát (U1–U2) | TB | Thấp–TB | Giữ phân loại theo chữ; kiểm ở Phase 4; sự kiện lạ → `Card` (như script cũ) |
| K8 | Trùng mã đội / sai thứ tự đội | Thấp | TB | Xác minh bằng logo + roster; xử lý trùng mã |
| K9 | Mất đồng bộ tên giữa stats và lineups | Thấp (đã thấy 0 sai lệch) | TB | Ghép theo id; tên lấy từ roster stats |
| K10 | Sự cố luồng/event-loop trên Windows | Thấp | TB | 1 worker thread, không asyncio |
| K11 | Server local bị trang web khác lạm dụng | Thấp | TB | Bind localhost, không CORS, kiểm `Host`/`Origin` |
| K12 | Sửa nhầm file HTML 1,18 MB | TB | Cao | Chỉ dùng thao tác thay thế theo chuỗi neo duy nhất; không ghi lại cả file; diff-budget; không in dòng 579–580 |
| K13 | Phiên bản Playwright/Python đổi | Thấp | Thấp | Ghim `playwright==1.60.0` (bản đã kiểm chứng) trong `requirements.txt` |

---

## 11. Mục cần bạn xác nhận (đã chọn sẵn mặc định)

Không cần trả lời nếu đồng ý mặc định — tôi sẽ làm theo cột "Mặc định".

| ID | Câu hỏi | Mặc định | Nếu đổi |
| --- | --- | --- | --- |
| C1 | Giữ nút demo "explore with sample data"? | **Giữ** (bạn chỉ yêu cầu thay 3 ô upload) | Gỡ demo ⇒ thêm điểm sửa HTML/JS; `LineupOCR` vẫn nên giữ tới Phase 5 |
| C2 | Đổi chữ "Data from Flashscore exports" ở footer web (:566) và footer PDF (:2444)? | **Không đổi** (thuần giao diện; PDF thuộc vùng đóng băng) | +2 chuỗi; cần duyệt |
| C3 | Hiển thị ngày giờ trận (`matchDate`)? | **Để rỗng** như luồng cũ (web cũ luôn rỗng) | Điền `08.10.2026 19:00` ⇒ scorebar + bìa PDF hiện ngày; cần đặt múi giờ cố định cho trình duyệt |
| C4 | Tên lineups lấy từ DOM đánh `ok:true` hết (dự bị chưa ra sân và HLV không còn chữ mờ)? | **Có** | `ok:false` cho người không có trong roster stats để giữ hiệu ứng mờ |
| C5 | Banner cookie: Reject all hay Accept (như script cũ)? | **Reject all**, dự phòng Accept | Không ảnh hưởng dữ liệu |
| C6 | `git init` + commit baseline ở Phase 0? | **Khuyến nghị làm** | Nếu không: bản sao thủ công ngoài thư mục dự án |
| C7 | Phase 5 (dọn mã mồ côi, gỡ script legacy) | **Chưa làm** | — |
| C8 | Cổng `8778` và mục `app` trong `launch.json` | **Có** | Đổi cổng bằng biến môi trường `FS_PORT` |
| C9 | Thêm `requirements.txt` (+ `pytest` chỉ cho dev) | **Có** | — |
| C10 | Trận có hiệp phụ/luân lưu | **Hỗ trợ nếu extractor đọc được**, kiểm ở Phase 4 | Nếu không đọc được: cảnh báo, hiển thị phần còn lại |

---

## 12. Phụ lục

### Phụ lục A — Bảng selector đã kiểm chứng (2026-10-09)

| Khối | Selector / thao tác | Ghi chú |
| --- | --- | --- |
| Header | `.duelParticipant__home .participant__participantName` · `.duelParticipant__away …` · `.duelParticipant__startTime` · `.detailScore__wrapper` · `.detailScore__status` · `.duelParticipant__home img.participant__image` | BEM, ổn định; dùng `.first` |
| Stats | URL `…/summary/player-stats/{top\|shots\|attack\|passes\|defense\|goalkeeping\|general}/?mid=…` · bảng `[data-testid="wcl-table"]` · `th` trong `[data-testid="wcl-tableHead"]` · hàng `[data-testid="wcl-tableBodyRow"]` · ô `[data-testid="wcl-tableBodyCell"]` · ô cầu thủ `[data-testid="wcl-playerCell"]` (+ `data-analytics-player-id`) · lọc đội `[data-testid="wcl-selectButton"]` → `[role="option"]` | `th[0]` = nút lọc đội |
| Timeline | `.smv__verticalSections` › `ol.smv__period-list[aria-label]` › `li[class*="smv__participantRow"]` (`smv__homeParticipant`/`smv__awayParticipant`) › `.smv__incident` › `[class*="timeBox"]`, `svg`, `[class*="playerName"]`, `[class*="smv__assist"]`, `[class*="smv__subIncident"]` | Goal: `data-testid="wcl-icon-incidents-goal-soccer"`; Sub: `…-substitution`; Thẻ vàng: `svg.card-ico.yellowCard-ico` + `<title>` lý do |
| Lineups | `[data-testid="wcl-lineupsGroup"]` › `[data-testid="wcl-headerSection-text"]` · `[class*="wcl-side_"]` · `[data-testid^="wcl-lineupsParticipantGeneral"]` (+ id, `wcl-number_`, `wcl-name_`, `wcl-roles_`) · `[data-testid^="wcl-lineupsParticipantsSubstitution"]` (`wcl-substitute_`, `wcl-subName_`, `wcl-minute_`) | Class có hậu tố hash ⇒ chỉ dùng `[class*=…]` |
| Sơ đồ | `[data-testid="wcl-lineupsField"]` · `[class*="fp-formation_"][class*="fp-home_"\|"fp-away_"]` › `[class*="fp-row_"]` › `[class*="fp-player_"]` · nhãn `[class*="fp-headerFormation_"] > span` (3 phần tử: nhà, "Formation", khách) · rating `[data-testid="wcl-badgeRating"]` | Sân dọc khi viewport ≤ ~760 px, ngang khi ≥ ~900 px |
| Cookie | `#onetrust-reject-all-handler`, `#onetrust-accept-btn-handler`, overlay `#onetrust-consent-sdk` | Hiện sau ~1 s |

### Phụ lục B — Baseline SHA-256

Tính ngày 2026-10-09, trước mọi thay đổi (chỉ có 2 file mới được tạo: `CLAUDE.md` và tài liệu này).

| File | Kích thước (byte) | SHA-256 |
| --- | --- | --- |
| `match_report.html` | 1 177 721 | `B47EE9FBB0B646B094E3CBC4AE69BCAB8D83FB4A53F75340DABCA83BE83AC63F` |
| `flashscore_scraper.py` | 18 789 | `C051E03C76E7C6811A46EDCFBE1BF68A31291071C0DD4182D6E0772F6A0874FA` |
| `flashscore_summary.py` | 18 821 | `4AE50B8C015D8B257E8CA59431F2420D4441146EF6AA49954D5D3D0E66C03B2B` |
| `flashscore_lineups.py` | 14 394 | `8742A321D12F894E704FCD8BC951D7A5B93E2A509E50CB5664AF805C5EB8F0D9` |
| `.claude/launch.json` | 196 | `5D52CA5B2DD759B288A8601EEE4745A9C4F4A57DAF8DA292E3326FBFED47F3B0` |

Kiểm lại bằng PowerShell: `Get-FileHash "match_report.html" -Algorithm SHA256`.

### Phụ lục C — Trận tham chiếu #1 (kỳ vọng quan sát ngày 2026-10-09)

URL: `https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n` — ASEAN Club Championship, **Johor DT 6–0 Svay Rieng**, `FINISHED`, hiển thị `08.10.2026 19:00` (theo múi giờ trình duyệt).

| Hạng mục | Kỳ vọng |
| --- | --- |
| Mã đội | `JOH` (nhà), `SVA` (khách) |
| Top Stats | 16 + 16 dòng; 10 header = `Player`, `Position` + 8 cột stat (`Rating` … `Duels`) |
| Goalkeeping | 1 + 1 (Hazmi S. / Vireak D.) |
| Timeline | 21 sự kiện: 6 `Goal` (39' Aiman A. ←Marcos Guilherme 1–0 · 51' Marcos Guilherme ←Jairo 2–0 · 61' Medina K. ←Aiman A. 3–0 · 70' Zahedi S. ←Aketxe A. 4–0 · 78' Amirruddin D. 5–0 · 86' Amirruddin D. 6–0), 5 `Yellow card` (13' Sieng C., 33' Mateus Barbosa [khách]; 33' Stoichkov, 66' Lowry S., 74' Akapo C. [nhà]), 10 `Substitution` (5 mỗi đội); home 14 / away 7 |
| Lineups | Đá chính 11/11 · dự bị 12/11 · thay người 5/5 · sơ đồ `3 - 4 - 2 - 1` vs `4 - 2 - 3 - 1` (hàng `[1,3,4,2,1]` / `[1,4,2,3,1]`) · HLV `Xisco` / `McConkey M.` · 22 cầu thủ trên sơ đồ |
| Ghép id | 22/22 đá chính, 10/10 vào sân, 22/22 sơ đồ ⊂ roster; 13 dự bị chưa ra sân không có trong roster |
| Cảnh báo kỳ vọng | Không có |

### Phụ lục D — Extractor tham chiếu (đã chạy thật trên trận #1)

> **Từ v1.1, nguồn chuẩn là code:** `JS_TIMELINE` trong [crawler/timeline.py](../crawler/timeline.py) và `JS_LINEUPS` trong [crawler/lineups.py](../crawler/lineups.py). Hai khối dưới đây là **bản v1.0 lúc thiết kế**, giữ lại để đối chiếu. Bản triển khai khác ở các điểm sau:
>
> - **D.1:** bỏ hàng loạt luân lưu; nhận phản lưới nhà qua icon `owngoal` và penalty qua icon `penalty-goal`; thêm nhãn `Penalty missed`; nhận thẻ vàng thứ hai qua `red-card-second`; VAR lấy tên cầu thủ từ khối `smv__assist` và quyết định VAR vào `detail` (§6.5).
> - **D.2:** `groups` là danh sách `{head, sides}` (giữ thứ tự, cho phép phân loại theo cấu trúc khi tiêu đề lạ); mỗi phần tử có `kind: "general" | "sub"`.

#### D.1 Timeline — chạy trên trang chính, viewport bất kỳ

```js
() => {
  const T = e => e ? (e.textContent || '').replace(/\s+/g, ' ').trim() : '';
  const root = document.querySelector('.smv__verticalSections') || document.querySelector('[class*="verticalSections"]');
  if (!root) return { events: [], rows: 0 };
  const normHalf = s => {
    const u = (s || '').toUpperCase();
    if (/1ST/.test(u)) return '1st half';
    if (/2ND/.test(u)) return '2nd half';
    if (/EXTRA/.test(u)) return 'Extra time';
    if (/PENAL/.test(u)) return 'Penalties';
    return '';
  };
  const rows = Array.from(root.querySelectorAll('li[class*="smv__participantRow"]'));
  const events = [];
  for (const li of rows) {
    const ol = li.closest('ol');
    const half = normHalf(ol && ol.getAttribute('aria-label'));
    const cls = String(li.className);
    const side = /smv__homeParticipant/.test(cls) ? 'home' : /smv__awayParticipant/.test(cls) ? 'away' : '';
    const minute = T(li.querySelector('[class*="timeBox"]'));

    const assistEl = li.querySelector('[class*="smv__assist"]');
    const inAssist = el => !!assistEl && assistEl.contains(el);
    const names = Array.from(li.querySelectorAll('[class*="playerName"]')).filter(e => !inAssist(e)).map(T).filter(Boolean);

    const svg = li.querySelector('svg');
    const sig = (((svg && svg.getAttribute('class')) || '') + ' ' + ((svg && svg.getAttribute('data-testid')) || '')).toLowerCase();
    const title = T(li.querySelector('svg title')).toLowerCase();
    const body = T(li).replace(minute, '').trim();
    const lower = body.toLowerCase();
    const sm = body.match(/(\d+)\s*[-:]\s*(\d+)/);
    const score = sm ? (sm[1] + ' - ' + sm[2]) : '';
    const parens = (body.match(/\(([^)]+)\)/g) || []).map(s => s.replace(/[()]/g, '').trim());
    const reasonEl = li.querySelector('[class*="smv__subIncident"]');

    const isSub = names.length >= 2 || /substitution/.test(sig) || /substitution/.test(title);
    let type, player = names[0] || '', detail = '';
    if (score) {
      if (/own goal/.test(lower)) type = 'Own goal';
      else if (/penalt/.test(lower)) type = 'Penalty goal';
      else type = 'Goal';
      const ass = (assistEl && T(assistEl)) || parens.find(p => !/own goal|penalt/i.test(p)) || '';
      detail = ass.replace(/^\(|\)$/g, '').trim();
    } else if (isSub) {
      type = 'Substitution';
      if (names[1]) detail = 'Out: ' + names[1];
    } else {
      if (/yellowred/.test(sig)) type = 'Second yellow (→ red)';
      else if (/redcard|red-card/.test(sig)) type = 'Red card';
      else if (/yellowcard|yellow-card/.test(sig)) type = 'Yellow card';
      else if (/\bvar\b/.test(sig)) type = 'VAR';
      else type = 'Card';
      detail = (reasonEl ? T(reasonEl) : (parens[0] || '')).replace(/^\(|\)$/g, '').trim();
    }
    if (!player && !minute) continue;
    events.push({ half, minute, side, type, player, detail, score });
  }
  return { rows: rows.length, events };
}
```

Kết quả trên trận #1: `rows = 21`, `events = 21` (6 Goal · 5 Yellow card · 10 Substitution), `side` home 14 / away 7, `Goal` cuối `86' Amirruddin D. 6 - 0`.

#### D.2 Lineups — chạy ở viewport 420×900 (sân dọc)

```js
() => {
  const T = e => e ? (e.textContent || '').replace(/\s+/g, ' ').trim() : '';
  const pidOf = e => {
    const x = e && (e.matches('[data-analytics-player-id]') ? e : e.querySelector('[data-analytics-player-id]'));
    return x ? x.getAttribute('data-analytics-player-id') : null;
  };
  const out = { groups: {}, formation: null };

  // 1) list groups: substituted players / starting lineups / substitutes / coaches
  document.querySelectorAll('[data-testid="wcl-lineupsGroup"]').forEach(g => {
    const head = T(g.querySelector('[data-testid="wcl-headerSection-text"]')).toLowerCase();
    const sides = [...g.querySelectorAll('[class*="wcl-side_"]')];
    out.groups[head] = sides.map(sideEl => [...sideEl.children].map(item => {
      const sub = item.querySelector('[data-testid^="wcl-lineupsParticipantsSubstitution"]');
      if (sub) {                                              // ON player + OFF player + minute
        const offName = sub.querySelector('[class*="wcl-subName_"]');
        return {
          onId: pidOf(sub), onName: T(sub.querySelector('[class*="wcl-substitute_"] [class*="wcl-name_"]')),
          rating: T(sub.querySelector('[data-testid="wcl-badgeRating"]')) || null,
          offId: pidOf(offName && offName.closest('[data-analytics-player-id]')), offName: T(offName),
          minute: T(sub.querySelector('[class*="wcl-minute_"]')),
        };
      }
      const gen = item.querySelector('[data-testid^="wcl-lineupsParticipantGeneral"]');
      if (!gen) return null;
      return {
        id: pidOf(gen), num: T(gen.querySelector('[class*="wcl-number_"]')) || null,
        name: T(gen.querySelector('[class*="wcl-name_"]')), role: T(gen.querySelector('[class*="wcl-roles_"]')) || null,
      };
    }).filter(Boolean));
  });

  // 2) formation: rows are ordered GK -> forwards; x/y normalised to the pitch box
  const field = document.querySelector('[data-testid="wcl-lineupsField"]');
  if (field) {
    const fb = field.getBoundingClientRect();
    const read = side => {
      const root = document.querySelector('[class*="fp-formation_"][class*="fp-' + side + '_"]');
      return root ? [...root.querySelectorAll('[class*="fp-row_"]')].map(row =>
        [...row.querySelectorAll('[class*="fp-player_"]')].map(pl => {
          const b = pl.getBoundingClientRect();
          return { id: pidOf(pl), num: T(pl.querySelector('[class*="wcl-participantNumber_"]')),
                   x: +(((b.left + b.width / 2) - fb.left) / fb.width).toFixed(3),
                   y: +(((b.top + b.height / 2) - fb.top) / fb.height).toFixed(3) };
        })) : [];
    };
    out.formation = {
      label: [...document.querySelectorAll('[class*="fp-headerFormation_"] > span')].map(T),
      home: read('home'), away: read('away'),
    };
  }
  return out;
}
```

Kết quả trên trận #1: nhóm `["substituted players","starting lineups","substitutes","coaches"]`; đá chính `[11,11]`; dự bị `[12,11]`; thay người `[5,5]`; HLV `Xisco` / `McConkey M.`; nhãn sơ đồ `["3 - 4 - 2 - 1","Formation","4 - 2 - 3 - 1"]`; hàng `home [1,3,4,2,1]` / `away [1,4,2,3,1]`. (2 phần tử không có `id` là 2 HLV — đúng kỳ vọng.)

Ví dụ ghép: `{"onId":"CGbL8vih","onName":"Aketxe A.","rating":"7.6","offId":"Kneifk5H","offName":"Stoichkov","minute":"67'"}` ⇒ `substituted.home[0] = {on:"Aketxe A.", off:"Stoichkov", min:"67"}`.

### Phụ lục E — Thuật ngữ

| Từ | Nghĩa |
| --- | --- |
| `mid` | Tham số `?mid=` trong URL Flashscore, xác định đúng một trận cụ thể giữa hai đội |
| Selector drift | Trang đích đổi DOM làm selector cũ không còn khớp |
| Golden snapshot | Bản chụp kết quả render "đúng" làm chuẩn để phát hiện thay đổi ngoài ý muốn |
| Diff-budget | Ngân sách thay đổi: chỉ những khối sửa nằm trong danh sách cho phép mới được xuất hiện trong diff |
| Frozen region | Vùng mã không được thay đổi (kiểm bằng hash) |
| Fixture | Mẩu HTML/JSON lưu từ trang thật để test offline |

---

## 13. Ghi nhận khi triển khai (2026-10-09)

### 13.1 Kết quả theo phase

| Phase | Kết quả | Bằng chứng |
| --- | --- | --- |
| 0 | `git init` + commit baseline `d4a4da6` (người dùng đồng ý; `core.autocrlf=false`, blob trùng từng byte với file gốc). Golden snapshot luồng demo: 16 view, 24 biểu đồ, chụp 2 lần giống hệt | `tools/golden_demo.py --stability`, `tests/unit/test_html_guard.py` (chứng minh công cụ bắt được sửa ngoài phạm vi) |
| 1 | `crawler/` + CLI. Trận #1 xong sau 31,5 s, mọi giá trị khớp phụ lục C. **Stats giống hệt 100%** luồng xlsx cũ (chạy chính script legacy) | `tests/live/test_parity_legacy_stats.py`, `tests/unit/test_extractors_offline.py` |
| 2 | `server.py`; smoke thật qua server 31,7 s, tiến độ cập nhật đủ 10 bước | `tests/e2e/test_server_api.py` (7), `tests/live/test_live_server.py` |
| 3 | Đúng 7 điểm sửa E1–E7; diff-budget ✓; 16/16 vùng đóng băng ✓; golden luồng demo ✓; luồng URL với dữ liệu demo cho dashboard trùng golden; dán link thật → dashboard sau 43 s | `tools/*`, `tests/e2e/test_url_flow.py` (11), `tests/live/test_live_ui.py` |
| 4 | U1–U8 (§2.1). Bộ 5 trận tham chiếu + 3 kịch bản lỗi chạy thật đều đạt. Match story của demo **chạy OCR thật** trước/sau khi sửa cho `lineupText` và nội dung 4 ô giống hệt | `tests/live/test_live_reference.py`, `tests/unit/test_timeline_rare_events.py` |
| 4.5 | Chờ người dùng nghiệm thu bằng trận của mình | — |

### 13.2 Điểm lệch / bổ sung so với v1.0

Tất cả thuộc phần mới (crawler, server, ô URL); không đụng tính năng cũ.

1. **Test dùng `unittest` của stdlib** thay vì pytest: không phải cài thêm gói vào máy (pytest vẫn chạy được các test này).
2. **Thêm mã lỗi `E_NETWORK`** (mất mạng). Server có thêm các mã riêng (§4.3).
3. **Timeline phân loại theo icon thật (U1):**
   - bỏ hàng loạt luân lưu;
   - thêm nhãn `Penalty missed`;
   - sửa thẻ vàng thứ hai, phản lưới nhà, penalty và VAR (§6.5).

   `Render` hiển thị nhãn mới bằng icon mặc định "•" và tooltip "Penalty missed — <tên>", không cần sửa `Render`.
4. **Tập trạng thái "đã kết thúc" thêm `After 90 minutes`** (U5).
5. **Báo `E_NO_PLAYER_STATS` ngay qua thanh tab** (~8 s thay vì ~30 s). Bỏ qua lineups khi trận không có tab Lineups (§6.7).
6. **`MatchRef` dùng `team1`/`team2`**, vì thứ tự đội trong URL không phải nhà/khách (U8).
7. **`JS_LINEUPS` trả `groups` dạng danh sách** (Phụ lục D).
8. **R-20 sửa cho khớp §3.5:** nhận 2 job (1 chạy + 1 chờ), job thứ 3 nhận `E_BUSY`.
9. **Bộ trận tham chiếu đặt thẳng trong test** thay vì file JSON riêng.
10. **Giữ nguyên:**
    - 3 script legacy và `__pycache__` gốc (test tắt ghi `.pyc`);
    - mọi vùng đóng băng của HTML;
    - mặc định C1–C5: demo giữ; footer "Data from Flashscore exports" chưa đổi; `matchDate` rỗng; `ok:true`; cookie "Reject all".

### 13.3 Bộ kiểm thử

| Lệnh (chạy ở thư mục gốc) | Nội dung | Thời gian |
| --- | --- | --- |
| `python -m unittest discover -s tests/unit -t .` | 51 test offline: URL, lineups/toạ độ, ghép + kiểm tra chéo, extractor trên fixture, sự kiện hiếm, ánh xạ lỗi điều hướng, công cụ bảo vệ HTML | ~8 s |
| `python -m unittest discover -s tests/e2e -t .` | 21 test giao diện + server với runner giả: golden luồng demo, PDF (demo và luồng URL), New match, luồng URL, các thông báo lỗi, `file://`, API | ~2–3 phút; cần mạng cho CDN; `FS_SKIP_PDF=1` bỏ test PDF |
| `FS_LIVE=1 python -m unittest discover -s tests/live -t .` | 7 test chạm flashscore.com: parity với script legacy, server thật, giao diện thật, bộ trận tham chiếu, trận chưa đá, giải không có stats, link thiếu `mid` | ~10 phút |
| `python tools/verify_frozen.py` · `python tools/check_diff_budget.py` · `python tools/golden_demo.py --check` | Cổng bảo vệ `match_report.html` | ~10 s |

### 13.4 Hạn chế đã biết

- **Kết quả loạt luân lưu không hiển thị:** dashboard hiện tại không có chỗ; thêm sẽ là thay đổi UI, cần phê duyệt.
- **Chưa gặp trên trang thật:**
  - trận có stats nhưng thiếu lineups/sơ đồ;
  - hai đội trùng mã;
  - bị chặn/captcha.

  Đã có đường xử lý và test bằng dữ liệu giả cho các trường hợp này.
- **Thời gian:** ~23–29 s/trận với tải song song mặc định (§13.5); có lúc 40–75 s khi Flashscore chậm.

### 13.5 Phase 5 (2026-10-13)

Người dùng duyệt cả 4 mục; chọn **xoá hẳn** 3 script cũ, chữ chân trang **"Data from Flashscore"**, không commit.

| Mục | Đã làm | Kiểm chứng |
| --- | --- | --- |
| Gỡ mã đọc xlsx mồ côi trong `match_report.html` | E8 thẻ SheetJS · E9 CSS `.drop-*` · E10 khối `JSZipLite` · E11 parser xlsx (`readWorkbook` … `parseSummaryWorkbook`, `relTarget`, `normalizePath`, `bytesToDataURL`), trường `statsFile/lineupFile/summaryFile`, 2 chú thích · E12 dòng đầu `App.reset` (~360 dòng bị gỡ, file còn 2 096 dòng) | `check_diff_budget` khớp E1–E14 · `verify_frozen` 14/14 vùng (bỏ 2 vùng đã gỡ: `JSZipLite`, parser xlsx) · golden luồng demo 16 view giống hệt |
| Xử lý 3 script cũ | Xoá `flashscore_scraper.py`, `flashscore_summary.py`, `flashscore_lineups.py`; xoá theo test parity (`tests/live/test_parity_legacy_stats.py`, `tests/legacy_xlsx.py`) và file `.pyc` mồ côi trong `__pycache__` gốc; bỏ `openpyxl` khỏi `requirements.txt`. Mã cũ vẫn xem được ở commit baseline `d4a4da6` | Parity đã chứng minh 100% ở Phase 1 (§13.1) trước khi xoá |
| Chạy song song | `FS_PARALLEL` (mặc định 3, tối đa 7, `1` = tuần tự như cũ): trang lineups bắt đầu tải ngay sau header; 7 tab player stats tải theo lô 3 trang (phát lệnh điều hướng `wait_until="commit"` cho cả lô rồi đọc từng trang — vẫn một thread Playwright sync) | Kết quả song song **giống hệt** tuần tự (so `stats/summary/lineups/lineupImages/warnings`). Đo xen kẽ 3 lần trận Malaga–Villarreal: song song 23–29 s, tuần tự 28–32 s; mức 7 không nhanh hơn mức 3 ⇒ giữ 3 |
| Chữ chân trang | E13 chân trang web, E14 chân trang mỗi trang PDF: "Data from Flashscore" | Test PDF (demo và luồng URL) đạt |

Cổng sau Phase 5: `python -m unittest discover -s tests -t .` 73 đạt / 6 bỏ qua (live); `FS_LIVE=1` 6/6 test live đạt (bộ 5 trận tham chiếu, trận chưa đá, giải không có stats, link thiếu `mid`, server thật, giao diện thật).
