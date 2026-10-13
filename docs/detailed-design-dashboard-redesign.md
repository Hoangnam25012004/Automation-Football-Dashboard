# Detailed Design — Thiết kế lại Dashboard & Match Report (PDF) cho Performance Analyst và Coach

| Thuộc tính | Giá trị |
| --- | --- |
| Trạng thái | **v0.1 — Bản thiết kế, CHỜ DUYỆT.** Chưa sửa dòng code nào. Mọi mục đánh dấu 🟡 ở [§14](#14-quyết-định-cần-bạn-duyệt) cần bạn chọn/đồng ý trước khi triển khai |
| Ngày | 2026-10-13 |
| Phạm vi | Thiết kế lại **toàn bộ giao diện dashboard** và **file PDF match report** trong `match_report.html`, hướng tới Performance Analyst và Coach, phân tích **sau trận**, **trung lập 2 đội**, theme **nền trắng – nhấn đỏ**, giao diện **tiếng Anh** |
| Không thuộc phạm vi | Phân tích trước trận và trong trận (live); chế độ "đội của tôi"; đa ngôn ngữ; tài khoản/lưu trữ lịch sử nhiều trận |
| Tài liệu liên quan | [CLAUDE.md](../CLAUDE.md) · [detailed-design-url-ingestion.md](detailed-design-url-ingestion.md) (luồng crawl hiện tại, Change surface E1–E14) |
| Ký hiệu | ✅ đã kiểm chứng trên dữ liệu/trang thật ngày 2026-10-13 · ⚠ giả định, phải xác nhận khi triển khai · 🔒 không được đổi · 🟡 cần bạn duyệt |

---

## 0. Tóm tắt

### 0.1 Yêu cầu

Thiết kế lại dashboard và PDF để **Performance Analyst** và **Coach**:

- nhìn ra **insight** nhanh;
- có **đầy đủ thông tin** để ra quyết định;
- **đánh giá được hiệu suất từng cầu thủ**.

Yêu cầu về giao diện:

- theme **đỏ – trắng**;
- **đồng nhất** cỡ chữ, font và màu chữ ở mọi hạng mục.

Ràng buộc:

- không gây bug cho chức năng khác;
- không đổi tính năng khác khi chưa được phép;
- có điểm chưa rõ thì hỏi lại.

### 0.2 Quyết định đã chốt (AskUserQuestion, 2026-10-13)

| # | Câu hỏi | Bạn chọn | Hệ quả thiết kế |
| --- | --- | --- | --- |
| R1 | Giai đoạn hỗ trợ | **Chỉ sau trận** | Giữ quy tắc chỉ nhận trận đã kết thúc (`E_MATCH_NOT_FINISHED`). Không có chế độ live, không có màn hình pre-match. "Giữa trận" được phục vụ gián tiếp bằng **so sánh hiệp 1 ↔ hiệp 2** (§5.3), dùng khi review lại các quyết định ở giờ nghỉ |
| R2 | Góc nhìn | **Trung lập 2 đội** | Mọi view đặt 2 đội ngang hàng. Insight viết theo ngôi thứ ba ("Johor DT created…"). Bộ lọc All / Home / Away chỉ dùng để lọc danh sách cầu thủ |
| R3 | Theme | **Nền trắng, nhấn đỏ** | Bộ token màu mới ở §7.1; PDF nền trắng, in tiết kiệm mực |
| R4 | Ngôn ngữ UI/PDF | **Tiếng Anh** | Nhãn giữ đúng thuật ngữ Flashscore (`Expected goals (xG)`, `Duels won`…) |

### 0.3 Giải pháp trong 8 dòng

1. **Một lớp tính toán mới, tách khỏi phần hiển thị: `Metrics`.** Lớp này gộp 7 tab stats thành **1 hồ sơ/cầu thủ**, tính tổng đội, chỉ số dẫn xuất, quy đổi per-90 và nhóm vị trí. Đây là các hàm thuần, kiểm thử được.
2. **Một lớp insight: `Insights`.** Gồm khoảng 20 luật có ngưỡng rõ ràng, sinh 4–6 câu nhận định kèm số liệu. Câu nào cũng truy ngược được về số gốc; không có câu chung chung.
3. **Dashboard 8 tab** theo câu hỏi của Analyst/Coach: Summary · Team · Attack · Passing · Defending · Goalkeeping · Players · Line-ups (§5).
4. **Đánh giá cầu thủ theo vai trò** (GK / DEF / MID / FWD):
   - rating Flashscore;
   - chỉ số per-90;
   - xếp hạng trong trận;
   - các thẻ Strength / Concern;
   - sự kiện của cầu thủ (bàn, thẻ, vào/ra sân).
5. **Design system đỏ–trắng.** Một font (Inter, số `tabular-nums`), một thang cỡ chữ 7 bậc, màu chữ 3 cấp, token màu duy nhất ở `:root`. Chart.js nhận theme từ một chỗ duy nhất (không còn màu cứng trong JS).
6. **PDF dựng riêng cho in ấn** (không còn chụp màn hình từng tab):
   - trang A4 dọc, nền trắng, header/footer và số trang thống nhất;
   - 2 preset: **Coach brief** (~4 trang) và **Full analyst report** (~10–14 trang, có phụ lục bảng player stats);
   - hiện tại PDF dài 21–24 trang, nặng 7–11 MB, nền tối.
7. **🟡 Bổ sung dữ liệu (cần duyệt).**
   - Crawl thêm tab **STATS cấp đội** cho 3 phạm vi Overall / 1st half / 2nd half (✅ 45 chỉ số/phạm vi). Có possession **thật**, corners, free kicks, big chances, hit woodwork, goal kicks.
   - Lấy thêm **ngày, giải/vòng, trọng tài, sân** từ header.
   - Thiếu dữ liệu nào thì dashboard tự lùi về số suy ra từ player stats và ghi nhãn "derived".
8. **Chống hồi quy.** Các hợp đồng hành vi được giữ cố định (§10.2):
   - ô URL, API, demo + OCR, New match, Export, sort bảng;
   - `LineupOCR`, dữ liệu demo, luồng URL (E1–E7) **vẫn đóng băng** 🔒.

   Chỉ `Render`, `Exporter` và CSS được mở khoá (🟡). Golden snapshot v2 và bộ test mới được dựng trước khi sửa.

### 0.4 Vì sao cần thiết kế lại — những vấn đề đo được trên bản hiện tại

| # | Vấn đề (✅ đo trên mã/dữ liệu thật) | Ảnh hưởng tới Analyst/Coach |
| --- | --- | --- |
| P1 | **"Possession" hiện là số suy ra** = tỉ lệ đường chuyền *thành công* của 2 đội ([match_report.html](../match_report.html), hàm `overallHeadline`). Ví dụ Malaga–Villarreal: tỉ lệ đường chuyền thành công 283 / 539 ⇒ **34% – 66%**, trong khi Flashscore ghi **37% – 63%** | Một chỉ số "headline" sai lệch 3 điểm %, không có nhãn cảnh báo ⇒ có thể dẫn tới kết luận sai |
| P2 | Không có câu nhận định nào; người xem phải tự đọc 12 thanh so sánh, radar và 6 tab | Coach không có thời gian tự rút insight |
| P3 | Đánh giá cầu thủ chỉ dựa vào **rating** (thẻ best/worst) và bảng riêng lẻ theo từng tab. Không có per-90, không theo vai trò, không gộp hồ sơ | Không trả lời được câu "cầu thủ X chơi tốt/kém ở mặt nào, so với người cùng vị trí ra sao" |
| P4 | Không có số liệu theo hiệp, corners, free kicks, big chances (player stats không có các chỉ số này) | Thiếu dữ liệu cho phần review chiến thuật và set-piece |
| P5 | **PDF = chụp màn hình** 6 tab × 3 phạm vi, cắt ngang nội dung khi quá dài. Đo được: **21 trang / 6,9 MB** (trận Johor), **24 trang / 11 MB** (demo). Nền xanh đậm | Khó đọc, in tốn mực, nhiều trang lặp lại, không có tóm tắt cho Coach |
| P6 | Giao diện không đồng nhất. Dùng 3 font (Bebas Neue, Inter, JetBrains Mono) với hơn 15 cỡ chữ rời rạc. Màu viết cứng trong JS (`rgba(59,130,246,…)`, `#072019`…). Đội nhà xanh dương, đội khách đỏ (xung đột với theme đỏ mới) | Trái yêu cầu "đồng nhất size, font, color" |
| P7 | Line-ups chôn ở cuối tab Overall | Khó tìm khi cần đối chiếu sơ đồ |

### 0.5 Roadmap

| Phase | Nội dung | Sửa file nào | Điều kiện qua phase |
| --- | --- | --- | --- |
| R0 | Safety net v2: commit mốc hiện tại 🟡, dựng test hợp đồng hành vi, test số liệu `Metrics` trên 3 trận | `tests/`, `tools/` | Test mới xanh **trên mã cũ** |
| R1 | 🟡 Crawler: team stats 3 phạm vi + metadata header (`schemaVersion` 2, tương thích ngược) | `crawler/`, `server.py` (không đổi) | Unit + live xanh; trận Johor ≤ 75 s |
| R2 | `Theme` + `Metrics` + `Insights` (chưa đổi giao diện) | `match_report.html` (thêm module) | Test số liệu khớp Flashscore |
| R3 | Dashboard mới (8 view) + design system | `match_report.html` | Hợp đồng hành vi xanh; review giao diện |
| R4 | PDF mới (2 preset) | `match_report.html` | PDF test xanh; review bản in |
| R5 | Nghiệm thu, cập nhật golden v2, CLAUDE.md và tài liệu | docs, tests | Bạn nghiệm thu |

---

## 1. Hiện trạng (as-is)

### 1.1 Dữ liệu web đang nhận (không đổi — hợp đồng `state`)

| Đối tượng | Nội dung | Số lượng (trận Johor, ✅) |
| --- | --- | --- |
| `state.data.teams[CODE]` | 7 tab: `Top Stats`, `Shots`, `Attack`, `Passes`, `Defense`, `Goalkeeping`, `General` | 16 cầu thủ/đội (GK tab: 1) |
| `state.summary.events` | `{minute, half, side, team, type, player, detail, score}` | 21 sự kiện |
| `state.lineupText` | sơ đồ (x, y), đá chính, dự bị, thay người (`on/off/min`), HLV | 11+11, 12+11 |

**Các cột hiện có** (✅ trận Johor và demo; tên cột giống hệt Flashscore):

| Tab | Cột |
| --- | --- |
| Top Stats | Rating, Total shots, Expected goals (xG), Accurate passes, Touches, Touches in opposition box, Successful dribbles, Duels |
| Shots | Total shots, Goals, xG, xG on target (xGOT), Shots on target, Shots off target, Blocked shots, Shots inside the box, Shots outside the box, Headed shots |
| Attack | Touches in opposition box, Successful dribbles, Big chances missed, Touches, Fouls suffered, Offsides |
| Passes | Accurate passes, Big chances created, Key passes, Assists, Expected assists (xA), Accurate passes in final third, Accurate long passes, Accurate crosses |
| Defense | Duels won, Aerial duels won, Ground duels won, Tackles won, Fouls committed, Interceptions, Clearances, Errors leading to goal, Errors leading to shot |
| Goalkeeping | Goalkeeper saves, Goals conceded, Goals prevented, xGOT faced, Punches, Throws, Act as sweeper |
| General | Rating, Minutes played, Goals, Own goals, Assists, Yellow cards, Red cards |

Các sự thật đã kiểm chứng (✅) mà `Metrics` dựa vào:

- **Tên cầu thủ là duy nhất trong mỗi đội**, ở cả 4 bộ dữ liệu: Johor ×3 lần crawl và demo.
- **Mọi tab có cùng tập cầu thủ** (riêng tab Goalkeeping chỉ có GK) ⇒ gộp hồ sơ theo khoá `(team, Player)` là an toàn.
- **Tổng theo cầu thủ khớp với số cấp đội của Flashscore.**
  - Trận Johor: Passes 290/366 và 299/366; shots 25/7; fouls 17/10.
  - xG lệch tối đa 0,02 do làm tròn: 4,81 so với 4,79.
- **Giá trị `Position`** gặp trong dữ liệu: Goalkeeper, Centre back, Defender, Fullback, Wingback, Midfielder, Attacking midfielder, Winger, Forward, Striker.

### 1.2 Giao diện hiện tại (sẽ được thay)

- Thanh tỉ số; toggle All / Home / Away; 6 tab:
  - **Overall**: head-to-head 12 chỉ số, radar, 8 thẻ best/worst, timeline, Match story;
  - **Shots**, **Attack**, **Passes**, **Defense**, **Goalkeeping**: thẻ leader, chart, bảng sort được.
- Theme xanh sân cỏ tối.
- PDF: trang bìa, rồi `html2canvas` từng tab × 3 phạm vi.

### 1.3 Thành phần **giữ nguyên** 🔒 và lý do

| Thành phần | Lý do |
| --- | --- |
| Luồng URL (E1–E7): `#flashUrl`, `#btnGenerate`, `#urlError`, `setupUrlForm`, `Api`, `App.buildFromUrl`, `App.reset` | Đã nghiệm thu; e2e `test_url_flow` phụ thuộc vào các id này |
| `server.py`, hợp đồng API, mã lỗi | Không liên quan tới giao diện |
| `LineupOCR` (toàn bộ logic, id `lc-*`, các class `fm-*`, `ln-*`, `sub-*`) | Demo vẫn cần OCR (CLAUDE.md §7). Thiết kế mới **chỉ đổi CSS** của các class này, không đổi JS sinh ra chúng |
| Dữ liệu demo (`__DEMO_STATS`, `__DEMO_IMAGES`, `__DEMO_SUMMARY`) | Nút demo vẫn phải hoạt động y như cũ |
| `U` (parseFraction, num, rankVal, esc, fmt) | Được `LineupOCR` dùng. `ratingClass` giữ nguyên ngưỡng, chỉ đổi màu qua CSS |
| `state` shape, `App.enter/setTeam/setTab/exportPDF/loadDemo` (chữ ký hàm) | Là "API" mà test và các module khác gọi tới |

---

## 2. Người dùng và câu hỏi cần trả lời

### 2.1 Persona

| Persona | Bối cảnh dùng | Cần gì | Định dạng ưa thích |
| --- | --- | --- | --- |
| **Head Coach / Assistant Coach** | Họp debrief 24–48 h sau trận; chọn đội hình trận sau | Tóm tắt 1 trang: trận đấu diễn ra thế nào, vì sao thắng/thua, ai chơi tốt/kém, cần chỉnh gì | PDF **Coach brief** in giấy, xem trên tablet |
| **Performance Analyst** | Phân tích sâu, chuẩn bị video session, báo cáo cho staff | Toàn bộ số liệu, so sánh theo pha, theo hiệp, theo vai trò; bảng đầy đủ để trích dẫn | Dashboard web + PDF **Full analyst report** |

### 2.2 Câu hỏi → view trả lời (truy vết yêu cầu)

| # | Câu hỏi của Coach/Analyst | View | Dữ liệu |
| --- | --- | --- | --- |
| Q1 | Kết quả có phản ánh đúng thế trận? (thắng xứng đáng hay may mắn) | Summary: xG vs Goals, xGOT, Goals prevented, insight I01–I04 | player stats (+ team stats) |
| Q2 | Thế trận thay đổi thế nào giữa 2 hiệp, sau các lần thay người? | Summary/Team: Half-by-half, timeline | 🟡 team stats theo hiệp, events |
| Q3 | Đội nào kiểm soát bóng, tiến lên 1/3 cuối hiệu quả hơn? | Team (In possession), Passing | Passes, team stats |
| Q4 | Tạo cơ hội bằng cách nào, chất lượng cơ hội ra sao? | Attack: shot profile, xG/shot, big chances | Shots, Attack, team stats |
| Q5 | Phòng ngự: đối đầu, tranh chấp tay đôi, lỗi dẫn tới bàn thua? | Defending | Defense |
| Q6 | Thủ môn cứu thua hơn/kém kỳ vọng? | Goalkeeping | Goalkeeping |
| Q7 | Set-piece và restart (phạt góc, phạt trực tiếp, ném biên) | Team (Set pieces & restarts) | 🟡 team stats |
| Q8 | Kỷ luật (thẻ, phạm lỗi) | Summary/Team | General, Defense, events |
| Q9 | Cầu thủ nào nổi bật / đáng lo, ở mặt nào? | Players: hồ sơ, xếp hạng theo vai trò, Strength/Concern | gộp 7 tab |
| Q10 | Cầu thủ vào sân thay người có tác động không? | Players (badge Sub), Line-ups | lineups.substituted, General |
| Q11 | Đội hình và sơ đồ thực tế? | Line-ups | lineupText |

---

## 3. Dữ liệu

### 3.1 Nguồn hiện có — đủ để làm toàn bộ thiết kế (không phụ thuộc R1)

Toàn bộ dashboard **chạy được** chỉ với dữ liệu hiện tại (luồng URL và demo). Các phần cần dữ liệu mới (đánh dấu 🟡) sẽ **ẩn có chủ đích** kèm một dòng giải thích, không hiện ô trống.

### 3.2 🟡 Nguồn mới đề xuất — tab STATS cấp đội (đã kiểm chứng ✅ 2026-10-13)

| Thuộc tính | Sự thật |
| --- | --- |
| URL | `…/summary/stats/overall/?mid=…`, `…/summary/stats/1st-half/?mid=…`, `…/summary/stats/2nd-half/?mid=…` (giữ `?mid=`) |
| Selector hàng | `[data-testid="wcl-statistics"]`, `innerText` dạng `home \| label \| away` hoặc `home \| (pct) \| label \| (pct) \| away` |
| Số hàng | **45/phạm vi** ở cả Johor–Svay Rieng và Malaga–Villarreal (ở mỗi trận, 5 hàng đầu là khối "Top stats" lặp lại) |
| Nhóm | Top stats · Shots · Attack · Passes · Defence · Goalkeeping (danh sách đủ ở [Phụ lục A](#phụ-lục-a--45-chỉ-số-cấp-đội-flashscore-2026-10-13)) |
| Chỉ số **chỉ có ở cấp đội** | Ball possession, Big chances, Hit the woodwork, Headed goals, Big chances scored, Corner kicks, Free kicks, Throw-ins, Goal kicks, Passes (tổng), Long passes, Final third passes, Crosses, Tackles (tổng) |
| ⚠ Possession giả | Trận Johor hiện **50% – 50%** ở cả 3 phạm vi dù số đường chuyền chênh nhau ⇒ nhiều khả năng giải này không có dữ liệu possession. Quy tắc: nếu Overall, 1st half và 2nd half đều đúng 50/50 thì đánh dấu `possessionReliable=false` và hiển thị "n/a" kèm chú thích |
| Chi phí | 1 trang + 2 lần bấm tab (hoặc 3 `goto`), ước tính +5–8 s mỗi trận (⚠ đo lại ở R1). Chạy song song với các trang hiện có (`FS_PARALLEL`) |
| Lỗi | Thiếu tab STATS ⇒ **cảnh báo** `W_NO_TEAM_STATS` (không chặn job). Dashboard dùng số suy ra từ player stats và gắn nhãn "derived" |

### 3.3 🟡 Metadata trận (header, đã kiểm chứng ✅ trên Malaga–Villarreal)

| Trường | Selector | Ví dụ | Dùng ở |
| --- | --- | --- | --- |
| `matchDate` | `.duelParticipant__startTime` | `18.09.2026 02:30` | Thanh tỉ số, bìa PDF. **Đã có sẵn trong hợp đồng** nhưng hiện để rỗng |
| `competition` | `[data-testid="wcl-breadcrumbs"]` | `LALIGA - ROUND 6` (bỏ tiền tố `FOOTBALL`, quốc gia tách riêng) | Thanh tỉ số, bìa PDF |
| `referee`, `venue` | Khối match information (`REFEREE: … VENUE: …`) | `Ortiz M. (Esp)`, `Estadio La Rosaleda` | Bìa PDF (nếu có) |

⚠ Lần chạy thử trên trận Johor không đọc được header vì trang chưa render xong trong thời gian chờ của script khảo sát. Phải kiểm lại ở R1 trên đủ 9 trận fixture. Thiếu trường nào thì để rỗng và **không** sinh cảnh báo (đây là dữ liệu trang trí).

### 3.4 Hợp đồng dữ liệu mở rộng (tương thích ngược)

```js
result = {
  schemaVersion: 2,                       // 1 → 2; front-end đọc được cả 1 và 2
  stats, summary, lineups, lineupImages, warnings,      // KHÔNG đổi
  teamStats: {                            // MỚI, có thể null
    overall:  { rows:[{key:"Ball possession", group:"Top stats", home:"37%", away:"63%",
                       homePct:null, awayPct:null}], possessionReliable:true },
    firstHalf:{ … }, secondHalf:{ … }     // từng phạm vi có thể null
  },
  meta: { competition:"LALIGA - ROUND 6", country:"SPAIN", referee:"Ortiz M. (Esp)",
          venue:"Estadio La Rosaleda", kickoff:"18.09.2026 02:30" }   // MỚI, các trường có thể ""
}
```

Front-end:

- gán `state.teamStats = res.teamStats || null` và `state.meta = res.meta || null`;
- gán `state.data.matchDate = meta.kickoff` (trường này đã có trong hợp đồng; hiện luôn rỗng);
- luồng demo đặt cả hai thành `null`.

Hai trường mới của `state` không ảnh hưởng `LineupOCR`.

---

## 4. Lớp tính toán: `Metrics` và `Insights`

### 4.1 Hồ sơ cầu thủ hợp nhất

`Metrics.players()` gộp 7 tab thành một danh sách `PlayerProfile` (khoá `team + Player`):

```js
{ team:"JOH", side:"home", name:"Aiman A.", position:"Wingback", group:"DEF",
  minutes:78, rating:9.0, started:true, subOn:null, subOff:"78",
  raw:{ "Total shots":"4", "Accurate passes":"23/30 (77%)", … },   // mọi cột của 7 tab, chuỗi gốc
  v:{ shots:4, xg:0.60, passAcc:23, passAtt:30, passPct:76.7, … }, // số đã parse
  p90:{ shots:4.62, … },                                           // chỉ khi minutes ≥ 30
  events:[{minute:"23'", type:"Goal"}, …],                         // từ summary theo tên
  rank:{ xg:{pos:2, of:11, scope:"DEF"} … },                       // xếp hạng trong trận
  tags:{ strengths:[…], concerns:[…] } }
```

| Quy tắc | Chi tiết |
| --- | --- |
| Nhóm vị trí | GK = Goalkeeper · DEF = Centre back, Defender, Fullback, Wingback · MID = Midfielder, Defensive midfielder, Central midfielder, Attacking midfielder · FWD = Winger, Forward, Striker · nhãn lạ ⇒ `OTHER` (log `console.warn` một lần, không lỗi) |
| Đá chính / vào sân | Lấy từ `lineupText.starting_xi` và `substituted`. Không có lineups ⇒ suy từ `minutes ≥ 85` (⚠ chỉ là ước lượng, chú thích "estimated") |
| Per-90 | `value / minutes × 90`, chỉ tính khi `minutes ≥ 30`. Dưới 30' hiện "—" kèm tooltip "Too few minutes for per-90". Tỉ lệ (%) không quy đổi |
| Phân số `"23/30 (77%)"` | Dùng `U.parseFraction` có sẵn ⇒ `made`, `att`, `pct` |
| `"-"` | = 0 khi cộng tổng, nhưng hiển thị "—" |
| Sự kiện của cầu thủ | So khớp `event.player` (và `detail` cho kiến tạo/cầu thủ ra sân) với tên trong roster. Luồng URL khớp tuyệt đối (CLAUDE.md §7: 0 lệch tên) |

### 4.2 Chỉ số đội (ưu tiên số Flashscore, lùi về số suy ra)

| Chỉ số | Nguồn ưu tiên (🟡 team stats) | Fallback (player stats) | Nhãn khi fallback |
| --- | --- | --- | --- |
| Goals | `summary.finalScore` | Σ Goals + Σ Own goals đối thủ (như hiện nay) | — |
| xG, xGOT, Shots, SoT, Off, Blocked, In/Out box | team stats | Σ cột tương ứng | — (khớp ±0,02) |
| Ball possession | team stats (nếu `possessionReliable`) | **Không suy ra.** Hiện "n/a" và **bỏ** proxy hiện tại (P1) 🟡 | "Possession not available" |
| Pass share | — | Σ Accurate passes / tổng 2 đội | Hiển thị **với tên thật** là "Share of completed passes" |
| Passes, Pass accuracy, Final third, Long, Crosses | team stats | Σ phân số Passes | "derived" nếu thiếu tổng số (player stats chỉ có số *accurate/attempt*, vẫn đủ) |
| Big chances, Corners, Free kicks, Throw-ins, Goal kicks, Hit woodwork | team stats | **Không có** ⇒ ẩn hàng | — |
| Duels won %, Tackles, Interceptions, Clearances, Fouls, Offsides, Cards | team stats / Σ | Σ | — |
| Goals prevented, Saves | team stats | Σ Goalkeeping | — |

**Kiểm tra chéo** (khi có cả hai nguồn), xếp theo mức chênh lệch:

| Chênh lệch | Chỉ số | Xử lý |
| --- | --- | --- |
| > 1 đơn vị | Shots, Passes, Fouls, Cards | Ghi `console.warn` |
| > 0,15 | xG | Ghi `console.warn` |

Khi chênh lệch, dashboard **luôn ưu tiên hiển thị số của Flashscore cấp đội**.

### 4.3 Chỉ số dẫn xuất (định nghĩa cố định, hiển thị kèm tooltip công thức)

| ID | Tên hiển thị | Công thức | Ý nghĩa cho Coach |
| --- | --- | --- | --- |
| D1 | xG per shot | xG / Total shots | Chất lượng trung bình mỗi cú sút |
| D2 | Finishing (G − xG) | Goals (không tính own goal) − xG | Dứt điểm vượt/thiếu kỳ vọng |
| D3 | Shot placement (xGOT − xG) | xGOT − xG (theo đội/cầu thủ) | Sút trúng vị trí khó hay dễ |
| D4 | On-target % | SoT / Shots | — |
| D5 | Box shot share | Shots inside box / Shots | Tạo cơ hội ở vị trí nguy hiểm |
| D6 | Final-third accuracy | Accurate final third (made/att) | Chất lượng tiến công |
| D7 | Long-ball accuracy | Accurate long passes | Phong cách triển khai |
| D8 | Cross accuracy | Accurate crosses | — |
| D9 | Duel / Aerial / Ground win % | made/att | Tranh chấp |
| D10 | Defensive actions | Tackles won + Interceptions + Clearances | Khối lượng phòng ngự |
| D11 | GK goals prevented | Goals prevented (Flashscore) | Thủ môn cứu thua hơn/kém kỳ vọng (xGOT faced − Goals conceded) |
| D12 | Discipline | Fouls, Yellow, Red | — |
| D13 | Sub impact | Đóng góp (G, A, xG, xA, rating) của cầu thủ vào sân | Q10 |
| D14 | Half delta 🟡 | Chỉ số hiệp 2 − hiệp 1 (xG, Shots, Possession, Final third passes) | Q2 |

Quy tắc hiển thị số:

| Loại số | Cách hiển thị | Ví dụ |
| --- | --- | --- |
| xG, xGOT, xA | 2 chữ số thập phân | — |
| Rating | 1 chữ số thập phân | — |
| Tỉ lệ | Số nguyên kèm % | — |
| Per-90 | 1 chữ số thập phân | — |
| Delta | Luôn có dấu | `+1.21`, `−0.40` |

### 4.4 `Insights` — luật sinh nhận định (trung lập, có số liệu)

Mỗi luật có `id`, `when` (điều kiện), `score` (độ quan trọng), `text` (mẫu câu).

Quy trình hiển thị:

1. Lấy 4–6 câu có `score` cao nhất.
2. Mỗi luật chỉ xuất hiện 1 lần.
3. Ưu tiên đa dạng chủ đề, mỗi nhóm tối đa 2 câu.

Quy tắc viết câu:

- Văn phong mô tả, không phán xét.
- Dùng động từ quan sát: *created, conceded, outperformed*.
- **Không** đưa ra khuyến nghị chiến thuật cụ thể. Phần khuyến nghị là việc của Coach; bản thiết kế chỉ chỉ ra *chỗ cần xem lại* ("Worth reviewing: …").

| ID | Nhóm | Điều kiện | Mẫu câu (ví dụ trận Johor) |
| --- | --- | --- | --- |
| I01 | Result vs performance | xG share ≥ 65% **hoặc** ≤ 35% | "Johor DT dominated chance quality: 4.79 xG vs 0.32 (94% of match xG)." |
| I02 | Result vs performance | Đội thắng có xG thấp hơn đội thua | "Svay Rieng won despite lower xG (0.8 vs 1.6) — clinical finishing and/or goalkeeping." |
| I03 | Finishing | \|G − xG\| ≥ 1.0 | "Johor DT outperformed their xG by +1.21 (6 goals from 4.79 xG)." |
| I04 | Goalkeeping | \|Goals prevented\| ≥ 0.7 | "Vireak D. conceded 1.74 more than expected from shots on target (goals prevented −1.74)." |
| I05 | Chance quality | xG/shot chênh ≥ 0.06 giữa 2 đội | "Johor DT's shots were higher quality: 0.19 xG per shot vs 0.05." |
| I06 | Chance creation | Big chances ≥ 3 **và** big chances missed ≥ 3 (🟡 team stats hoặc Σ Big chances missed) | "Johor DT missed 5 of 10 big chances." |
| I07 | Territory | Touches in opp. box share ≥ 60% | "Johor DT had 64% of touches in the opposition box (28 vs 16)." |
| I08 | Possession 🟡 | Possession tin cậy, chênh ≥ 20 điểm, **và** đội ít bóng có xG cao hơn | "Villarreal controlled the ball (63%) …" / mẫu "less possession, more threat" |
| I09 | Build-up | Final-third accuracy chênh ≥ 12 điểm | — |
| I10 | Half shift 🟡 | \|xG H2 − xG H1\| ≥ 0.8 của một đội **hoặc** xG share đảo chiều | "Johor DT's threat grew after half-time: xG 1.65 → 3.13." |
| I11 | Substitutions | Cầu thủ vào sân có G/A **hoặc** rating ≥ 7.5 | "Aketxe A. (on 67') added a goal." |
| I12 | Defensive errors | Errors leading to goal ≥ 1 | "Svay Rieng made 2 errors leading to goals — worth reviewing on video." |
| I13 | Duels | Duel win % chênh ≥ 10 điểm | — |
| I14 | Aerial | Aerial win % chênh ≥ 15 điểm (tổng ≥ 10 lần) | — |
| I15 | Discipline | Red card, **hoặc** yellow ≥ 4, **hoặc** fouls chênh ≥ 8 | — |
| I16 | Set pieces 🟡 | Corners chênh ≥ 5 | — |
| I17 | Player of the match | Rating cao nhất (bằng nhau ⇒ G+A, rồi xG+xA) | "Player of the match: Aiman A. (9.0) — 1 goal, 1 assist." |
| I18 | Standout per side | Rating cao nhất của đội còn lại | — |
| I19 | Concern | Rating ≤ 6.0 với ≥ 45' | "Low rating: X (5.8, 90')." |
| I20 | Data quality | Có warning từ crawler **hoặc** possession không tin cậy | "Possession not provided by Flashscore for this match." (luôn ở cuối, màu trung tính) |

Ngưỡng là **hằng số ở một chỗ** (`INSIGHT_THRESHOLDS`) để Analyst chỉnh dễ dàng. 🟡 Ngưỡng ở trên là đề xuất ban đầu và sẽ được hiệu chỉnh trên 9 trận fixture ở R2.

### 4.5 Đánh giá cầu thủ theo vai trò

Mỗi nhóm vị trí có **bộ KPI hồ sơ** (6–8 chỉ số) dùng cho thẻ Strength/Concern, radar hồ sơ và PDF:

| Nhóm | KPI hồ sơ |
| --- | --- |
| GK | Goalkeeper saves, Goals prevented, xGOT faced, Goals conceded, Accurate long passes %, Punches, Act as sweeper |
| DEF | Duels won %, Aerial duels won %, Tackles won, Interceptions, Clearances, Accurate passes %, Accurate passes in final third, Errors leading to shot/goal *(ngược)* |
| MID | Accurate passes (made, %), Key passes, xA, Accurate passes in final third, Successful dribbles, Duels won %, Tackles won + Interceptions |
| FWD | Goals, xG, Shots on target, xGOT, Touches in opposition box, Successful dribbles, Key passes, Big chances missed *(ngược)* |

**Xếp hạng trong trận.**

- Với mỗi KPI, xếp hạng cầu thủ **trong cùng nhóm vị trí, của cả 2 đội**, chỉ tính người có ≥ 30'.
- Dùng per-90 cho chỉ số khối lượng và giá trị gốc cho tỉ lệ.
- Hiển thị dạng "#2 of 9 DEF". **Không** gọi là percentile vì mẫu chỉ khoảng 4–10 người.
- Tỉ lệ (%) chỉ xếp hạng khi số lần thử ≥ 5, ví dụ duels ≥ 5, passes ≥ 10. Tránh trường hợp 1/1 = 100% đứng đầu.

**Thẻ Strength / Concern.** Tối đa 3 thẻ mỗi loại.

- Strength: xếp hạng #1 của nhóm, **hoặc** vượt ngưỡng tuyệt đối. Ví dụ:
  - Key passes ≥ 3;
  - Duels won ≥ 70% với ≥ 8 lần;
  - Goals prevented ≥ +0.5.
- Concern: xếp cuối nhóm, **hoặc** chạm ngưỡng xấu. Ví dụ:
  - Errors leading to goal ≥ 1;
  - Pass accuracy < 70% với ≥ 20 đường chuyền;
  - Big chances missed ≥ 2;
  - thẻ đỏ.
- Ngưỡng nằm trong `PLAYER_TAG_RULES`.

**Rating.**

- Dùng **nguyên** rating của Flashscore, không tự chế điểm tổng hợp. Lý do: tránh tạo ra một con số "hộp đen" thứ hai mâu thuẫn với nguồn.
- Thang màu rating đổi sang theme mới (§7.1). Ngưỡng `U.ratingClass` **giữ nguyên** 🔒.

---

## 5. Kiến trúc thông tin của dashboard

### 5.1 Khung chung

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│▌Match Performance                                [New match]  [Export PDF ▾] │ ← header trắng, vạch đỏ 4px trên cùng
├──────────────────────────────────────────────────────────────────────────────┤
│  LALIGA · ROUND 6 · 18.09.2026                                    FULL TIME    │ ← eyebrow 12px (🟡 meta)
│  [logo] Malaga            1  –  3            Villarreal [logo]                 │ ← match header
│         ⚽ Player 34'                    ⚽ Player 12', 55', 78'                │
│  xG 0.57 – 3.20 · Shots 5 – 16 · Possession 37% – 63%                         │ ← 3 KPI phụ
├──────────────────────────────────────────────────────────────────────────────┤
│  Summary  Team  Attack  Passing  Defending  Goalkeeping  Players  Line-ups     │ ← tab gạch chân đỏ
├──────────────────────────────────────────────────────────────────────────────┤
│  [nội dung tab]                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

| Thành phần | Quy định |
| --- | --- |
| Header | Giữ nguyên hai nút `#btnReset` ("New match") và `#btnExport` ("Export PDF") cùng id và hành vi. Export mở menu nhỏ chọn preset (§8.1) 🟡 |
| Team filter | Toggle `All / Home / Away` **chỉ hiện ở các tab có danh sách cầu thủ** (Attack, Passing, Defending, Players). Giữ `App.setTeam` và class `.toggle-pill` để test cũ vẫn chạy được |
| Màu đội | Home = **Red** `--home`, Away = **Graphite** `--away` (§7.1). Cả hai luôn đi kèm **tên hoặc mã đội**, không dựa vào màu đơn thuần |
| Bố cục | Lưới 12 cột, `max-width:1280px`. Breakpoint: 1280 · 1024 · 768 · 420. Ở 420px mọi lưới thành 1 cột, bảng cuộn ngang trong khung riêng (không cuộn cả trang) |
| Trạng thái rỗng | Mọi card thiếu dữ liệu hiện 1 dòng `caption` giải thích (ví dụ "Half-by-half stats are not available for this match."). Không để trống, không hiện số 0 giả |

### 5.2 Tab **Summary** — "Trận đấu này kể câu chuyện gì?" (Q1, Q2, Q8, Q9)

```text
┌ Key insights ─────────────────────────────┐ ┌ Result vs performance ───────────────┐
│ • Johor DT dominated chance quality: …     │ │        Goals   xG    xGOT   GP(GK)    │
│ • Johor DT outperformed xG by +1.21 …      │ │ JOH      6    4.79   4.26   +0.32     │
│ • Svay Rieng made 2 errors leading to …    │ │ SVA      0    0.32   0.32   −1.74     │
│ • Player of the match: Aiman A. (9.0) …    │ │ [bar xG vs Goals từng đội]            │
└────────────────────────────────────────────┘ └───────────────────────────────────────┘
┌ Team comparison (12 chỉ số, 4 nhóm) ──────────────────────────────────────────────┐
│ ATTACK      Shots · On target · xG · Big chances🟡 · Box touches                    │
│ POSSESSION  Possession🟡 · Passes · Pass accuracy · Final-third accuracy             │
│ DEFENCE     Duels won % · Tackles won · Interceptions                               │
│ DISCIPLINE  Fouls · Yellow · Red                                                    │
│ (thanh 2 phía; ô của đội trội hơn in đậm — không đổi màu)                           │
└──────────────────────────────────────────────────────────────────────────────────────┘
┌ Match timeline (giữ logic hiện có, restyle) ────────────────────────────────────────┐
┌ Half by half 🟡 ───────────────────┐ ┌ Top performers ──────────────────────────────┐
│ xG, Shots, Possession, FT passes   │ │ POTM · Best per team · Concerns (rating ≤6.0) │
│ H1 vs H2, 2 đội (bảng + mũi tên)   │ │ thẻ: tên · vị trí · phút · rating · G/A       │
└────────────────────────────────────┘ └────────────────────────────────────────────────┘
```

- **Bỏ** radar "Performance radar" ở Summary. Radar dạng "share" khó đọc với Coach; so sánh dạng thanh 2 phía trực quan hơn. Radar chuyển xuống hồ sơ cầu thủ, nơi nó hữu ích.
- **Bỏ** 8 thẻ best/worst, thay bằng "Top performers" gọn hơn và có ngữ cảnh: phút thi đấu, G/A.

### 5.3 Tab **Team** — "Hai đội chơi như thế nào theo từng pha?" (Q2, Q3, Q7)

| Card | Nội dung | Ghi chú |
| --- | --- | --- |
| In possession | Passes, Accurate %, Long passes (acc %), Final third passes (acc %), Crosses (acc %), Key passes, xA | Bảng 2 cột + thanh |
| Chance creation | Shots, Box shot share, xG/shot, Big chances, Big chances missed, Touches in box | |
| Out of possession | Duels won %, Aerial %, Ground %, Tackles (won %), Interceptions, Clearances, Errors → shot/goal | |
| Set pieces & restarts 🟡 | Corner kicks, Free kicks, Throw-ins, Goal kicks, Offsides | Ẩn khi không có team stats |
| Half by half 🟡 | Ma trận chỉ số × (H1, H2, Δ) × 2 đội; chart cột nhóm xG/Shots theo hiệp | Q2 — "giữa trận" nhìn lại |
| Momentum by events | Timeline thu gọn đánh dấu bàn thắng, thẻ, thay người, kết hợp xG theo hiệp 🟡 | Không có dữ liệu theo phút ⇒ **không** vẽ đường momentum giả |

### 5.4 Tab **Attack** (Q4)

- Thanh KPI đội: Shots · On target % · xG · xG/shot · xGOT − xG · Big chances missed.
- **Shot profile** (cột chồng 100%) cho mỗi đội: On target / Off target / Blocked; Inside box / Outside box / Headed.
- **Shooting map theo cầu thủ** (scatter có sẵn, restyle). Trục x = Shots, trục y = xG, kích thước điểm = Goals. Hai đường tham chiếu là trung bình trận.
- **Finishing table**: Player · Team · Shots · SoT · Goals · xG · G − xG · xGOT. Sắp theo xG.
- **Attacking involvement**: Touches in box, Successful dribbles (%), Fouls suffered, Offsides. Top 8 theo team filter.

### 5.5 Tab **Passing** (Q3)

- KPI đội: Accurate passes % · Final-third % · Long-ball % · Cross % · Key passes · xA.
- **Volume vs accuracy** (scatter có sẵn, restyle). Gắn nhãn tên cầu thủ có ≥ 20 đường chuyền.
- **Creators**: Key passes, Big chances created, xA, Assists. Bar ngang top 8.
- **Progression**: Accurate passes in final third (made/att), Accurate long passes, Accurate crosses.

### 5.6 Tab **Defending** (Q5, Q8)

- KPI đội: Duels won % · Aerial % · Ground % · Tackles won · Interceptions · Clearances · Errors → goal.
- **Duel map**: mỗi cầu thủ một hàng. Thanh thắng/thua cho aerial và ground, sắp theo tổng lần tranh chấp.
- **Defensive actions**: Tackles won + Interceptions + Clearances theo cầu thủ (bar chồng).
- **Discipline**: Fouls committed, cards, phút nhận thẻ (từ timeline).

### 5.7 Tab **Goalkeeping** (Q6)

Giữ ý tưởng "keeper profile" hiện có, restyle, mỗi đội một thẻ:

- Saves, Goals conceded, xGOT faced, **Goals prevented** (nổi bật, có dấu ±), Punches, Throws, Act as sweeper, Accurate long passes.
- Donut "Saves vs Conceded".
- Có 2 thủ môn ra sân thì hiện cả hai.

### 5.8 Tab **Players** — trung tâm đánh giá cầu thủ (Q9, Q10)

```text
[Team: All|Home|Away]  [Group: All|GK|DEF|MID|FWD]  [Per 90 ☐]  [Min. minutes: 0|30|60]   🔍 search
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ #  Player        Team Pos        Min  Rating  G  A  xG   xA   Key  Pass%  Duel%  Def. │ ← bảng tổng hợp
│ 1  Aiman A.  ▸   JOH  Wingback   78   9.0     1  1  0.60 0.21  2   77%    56%    3    │   sort mọi cột
│ …                                                                                    │   badge: ⓢ sub, 🟨, 🟥
└──────────────────────────────────────────────────────────────────────────────────────┘
Bấm ▸ mở Player profile (panel ngay dưới hàng, không dùng modal):
┌ Aiman A. · Johor DT · Wingback (DEF) · 78' · Rating 9.0 ───────────────────────────────┐
│ Events: ⚽ 23' · 🅰 41' · ▼ 78'                                                         │
│ Strengths: #1 of 9 DEF in xG · 4 shots …     Concerns: —                               │
│ [Radar KPI hồ sơ: cầu thủ vs trung bình nhóm DEF trận này]  [Bảng KPI: value · p90 · rank] │
│ All stats ▾ (7 nhóm, đầy đủ cột gốc)                                                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Bảng tổng hợp có 14 cột cố định** (như hình), dùng chung cho mọi nhóm vị trí ⇒ dễ quét.
  - `Def.` = Tackles won + Interceptions + Clearances.
  - `Duel%` = Duels won %.
- **Per 90** chỉ đổi các cột khối lượng (G, A, xG, xA, Key, Def.). Cột tỉ lệ và Rating giữ nguyên.
- **Bảng đầy đủ theo từng tab Flashscore** (thứ người dùng gọi là "bảng player stats"): nằm trong khối "All stats" của hồ sơ, và có ở các tab Attack/Passing/Defending/Goalkeeping (bảng sort được, giữ hành vi `wireSort` hiện có).
- Vị trí của **Top Stats** và **General** trong giao diện mới:
  - các cột thuộc Top Stats/General được gộp vào bảng tổng hợp;
  - khối "All stats" vẫn liệt kê đủ 7 nhóm cột gốc.
- Không có tab nào bị mất dữ liệu so với hiện tại. Tóm tắt nơi hiển thị từng tab Flashscore xem ở §10.3.

### 5.9 Tab **Line-ups** (Q11)

- Chuyển nguyên "Match story" sang đây. **Giữ** các id `lc-formation`, `lc-starting`, `lc-substitutes`, `lc-coaches` mà `LineupOCR` điền vào 🔒.
- Bổ sung card **Substitutions** dùng `lineupText.substituted`: phút, ▲ vào, ▼ ra, rating người vào sân. Card này hiện chưa hiển thị dù dữ liệu đã có; key `substituted` có sẵn trong `LineupOCR.failAll`.
- Restyle sân sang nền trắng, line xám, cầu thủ:
  - đội nhà: chấm đỏ;
  - đội khách: chấm graphite;
  - badge rating theo thang mới.
- ⚠ **Luồng demo** gọi `LineupOCR.run()` khi `state.currentTab==='overall'` (`run()` chỉ fill khi đang ở tab Overall). Thiết kế mới phải đảm bảo id tab chứa Line-ups không làm hỏng điều kiện này. Hai cách:
  - (a) giữ id nội bộ của tab Summary là `'overall'` **và** đặt Line-ups trong tab Summary;
  - (b) 🟡 **thêm 1 dòng** cho phép điều kiện nhận `'lineups'`. Cách này **phải sửa `LineupOCR`**, một vùng đang đóng băng.

  **Đề xuất (c):** giữ id tab `'overall'` cho **tab Line-ups** và đặt label "Line-ups". Tab Summary dùng id mới `'summary'` làm tab mặc định. Như vậy:
  - `LineupOCR` không đổi byte nào;
  - OCR demo chạy khi người dùng mở tab Line-ups;
  - tab Line-ups hiện `loadingHTML()` có sẵn trong lúc chờ OCR.

  Quyết định này ghi ở §14, mục 🟡 Q-F.

  Hệ quả của (c) và cách xử lý:

  | Tình huống | Xử lý |
  | --- | --- |
  | `App.reset()` (đóng băng) đặt `currentTab='overall'`, nên trận kế tiếp sẽ mở ở tab Line-ups | Vỏ `Render.tabs()` (chỉ được `App.enter` gọi) đặt `state.currentTab='summary'` ⇒ mọi trận mới luôn mở ở Summary |
  | OCR demo xong khi người dùng đang ở tab khác | `run()` không fill. Lần mở tab Line-ups sau đó gọi lại `run()`, lúc này đã có `state.lineupText` (cache) ⇒ fill ngay |
  | PDF cần trang Line-ups | `Report` đặt tạm `currentTab='overall'`, `await LineupOCR.run()`, rồi dựng trang; giống cách `Exporter` hiện tại chuyển tab và khôi phục sau khi xuất |

---

## 6. Hồ sơ hiển thị cho từng thành phần chung

| Component | Mô tả | Dùng ở |
| --- | --- | --- |
| `KpiTile` | label (caption) · value (kpi) · delta/ghi chú | Match header, thanh KPI các tab |
| `CompareRow` | giá trị home · label · giá trị away · thanh 2 phía (home đỏ, away graphite); bên trội hơn in đậm | Summary, Team |
| `InsightList` | bullet đỏ 6px, câu ≤ 160 ký tự, số in đậm | Summary, PDF |
| `PlayerChip` | tên · mã đội (màu) · vị trí · phút · rating badge | Top performers, Line-ups |
| `RatingBadge` | ô bo 4px, chữ 12/600, nền theo thang rating mới | mọi nơi |
| `DataTable` | header sticky, sort, số canh phải `tabular-nums`, hàng sọc rất nhạt, hàng đội nhà/khách có vạch màu 3px bên trái | Players, các tab |
| `Card` | nền trắng, viền `--line`, bo 8px, padding 16/20, tiêu đề H3 + eyebrow phải | mọi nơi |
| `EmptyNote` | caption xám, icon thông tin | khi thiếu dữ liệu |

---

## 7. Design system đỏ – trắng

### 7.1 Token màu (`:root`, thay thế toàn bộ token cũ 🟡)

| Token | Giá trị | Dùng cho | Tương phản trên nền trắng |
| --- | --- | --- | --- |
| `--brand` | `#C8102E` | Vạch đỏ header, tab active, nút primary, bullet insight, tiêu đề section (vạch trái) | 5.9 : 1 ✅ AA |
| `--brand-strong` | `#A00D25` | Hover/active nút | 8.1 : 1 |
| `--brand-tint` | `#FDECEF` | Nền hàng chọn, nền nhãn nhẹ | — |
| `--home` | `#C8102E` (= brand) | Dữ liệu đội nhà (thanh, chấm, đường) | 5.9 : 1 |
| `--home-tint` | `rgba(200,16,46,.12)` | Vùng tô radar/area đội nhà | — |
| `--away` | `#1F2937` | Dữ liệu đội khách | 14.7 : 1 |
| `--away-tint` | `rgba(31,41,55,.12)` | Vùng tô đội khách | — |
| `--ink` | `#111827` | **Màu chữ cấp 1**: tiêu đề, số KPI, giá trị bảng | 17.7 : 1 |
| `--ink-2` | `#374151` | **Màu chữ cấp 2**: thân bài, nhãn | 10.3 : 1 |
| `--ink-3` | `#6B7280` | **Màu chữ cấp 3**: caption, eyebrow, trục chart | 4.8 : 1 ✅ AA |
| `--line` | `#E5E7EB` | Viền card, kẻ bảng, grid chart | — |
| `--surface` | `#FFFFFF` | Card, trang PDF | — |
| `--canvas` | `#F7F7F8` | Nền trang web | — |
| `--pos` | `#15803D` | Delta tốt / rating cao (chỉ cho *ngữ nghĩa*, không cho đội) | 5.0 : 1 |
| `--neg` | `#B45309` | Concern / delta xấu — **dùng hổ phách, không dùng đỏ** để không lẫn với đội nhà và brand | 5.0 : 1 |

Ba quy tắc màu:

1. **Đỏ không bao giờ mang nghĩa "xấu"**: đỏ = brand hoặc đội nhà.
2. Mọi phần tử theo đội đều có tên hoặc mã đội đi kèm.
3. Màu chữ chỉ được chọn trong `--ink`, `--ink-2`, `--ink-3`, `--brand` (link/nhấn) và `#FFFFFF` (chữ trên nút đỏ).

Ở bản in đen trắng, đỏ (độ sáng ~45%) và graphite (~20%) vẫn phân biệt được.

**Thang rating** (giữ ngưỡng của `U.ratingClass`, chỉ đổi màu):

| Class | Ngưỡng | Nền / chữ |
| --- | --- | --- |
| `rating-elite` | ≥ 9.0 | `#14532D` / trắng |
| `rating-great` | 7.5–8.9 | `#15803D` / trắng |
| `rating-good` | 7.0–7.4 | `#DCFCE7` / `#14532D` |
| `rating-avg` | 6.5–6.9 | `#F3F4F6` / `#374151` |
| `rating-poor` | 6.0–6.4 | `#FEF3C7` / `#92400E` |
| `rating-bad` | < 6.0 | `#B45309` / trắng |
| `rating-na` | — | `#F3F4F6` / `#6B7280` |

### 7.2 Typography — **một font, một thang cỡ chữ**

- Font duy nhất là **Inter**, các weight 400 / 500 / 600 / 700, nạp từ Google Fonts như hiện nay.
- **Bỏ** Bebas Neue và JetBrains Mono.
- Mọi con số dùng `font-variant-numeric: tabular-nums` để các cột thẳng hàng.

| Token | Cỡ / line-height | Weight | Màu | Dùng cho |
| --- | --- | --- | --- | --- |
| `--fs-score` | 40 / 44 | 700 | `--ink` | Tỉ số |
| `--fs-h1` | 22 / 28 | 700 | `--ink` | Tên đội ở header, tiêu đề trang PDF |
| `--fs-h2` | 18 / 24 | 700 | `--ink` | Tiêu đề section (vạch đỏ 3px bên trái) |
| `--fs-h3` | 14 / 20 | 600 | `--ink` | Tiêu đề card |
| `--fs-kpi` | 24 / 28 | 700 | `--ink` | Giá trị KPI |
| `--fs-body` | 14 / 20 | 400 | `--ink-2` | Thân bài, insight, ô bảng |
| `--fs-caption` | 12 / 16 | 500 | `--ink-3` | Eyebrow (UPPERCASE, letter-spacing .06em), chú thích, trục chart, legend |

- **Cỡ tối thiểu 12px** trên web.
- Mobile (≤ 420px): chỉ `--fs-score` (32) và `--fs-h1` (18) được thu nhỏ, còn lại giữ nguyên.
- Chart.js dùng đúng `--fs-caption` (12px, `--ink-3`) cho trục, tick và legend; tooltip dùng `--fs-body`.

### 7.3 Spacing, hình khối, chuyển động

| Hạng mục | Quy định |
| --- | --- |
| Spacing | 4 · 8 · 12 · 16 · 24 · 32 · 48 |
| Bo góc | Card 8 · badge 4 · nút 6 |
| Đổ bóng | Card `0 1px 2px rgba(17,24,39,.06)`, không dùng bóng đậm |
| Animation | Chart.js tắt animation khi export PDF (`animation:false`) để chụp ổn định (thay cho `setTimeout(420)` hiện tại); trên web giữ 300 ms |
| Icon | SVG nét 1.5px, `currentColor`. Bộ ký hiệu sự kiện (⚽, thẻ, ▲▼) giữ như hiện có để timeline và OCR không đổi nghĩa |

### 7.4 Theme cho Chart.js — một nguồn duy nhất

`Theme.applyChartDefaults()` đặt các giá trị sau:

- `Chart.defaults.font`, `color`;
- `plugins.tooltip`, `scale.grid` từ CSS variables, đọc bằng `getComputedStyle(document.documentElement)`.

Toàn bộ chart mới **không** chứa màu cứng; màu đội lấy qua `Theme.team('home'|'away', alpha)`. Đây là điều kiện để đạt yêu cầu "đồng nhất".

### 7.5 Truy cập

- Tương phản AA cho mọi chữ: xem cột tương phản ở bảng §7.1.
- Tab dùng `role="tablist"`, focus nhìn thấy được (viền 2px `--brand`).
- Bảng có `<th scope="col">`; nút sort có `aria-sort`.

---

## 8. Match report PDF

### 8.1 Hai preset 🟡

| Preset | Đối tượng | Trang | Nội dung |
| --- | --- | --- | --- |
| **Coach brief** | Coach | 4 (cố định) | 1 Summary · 2 Team & half-by-half · 3 Players (2 đội, top 8 mỗi đội + concerns) · 4 Line-ups |
| **Full analyst report** (mặc định) | Analyst | ~10–14 | Coach brief + Attack · Passing · Defending & Goalkeeping · Player ratings từng đội (1 trang/đội) · **Phụ lục**: bảng player stats đầy đủ 2 đội (7 nhóm cột, ngắt trang theo hàng, lặp header) |

Nút **Export PDF** giữ nguyên id và vị trí. Bấm vào mở menu 2 lựa chọn. `App.exportPDF()` giữ chữ ký và mặc định chạy **Full analyst report**, để test e2e cũ (bấm nút → nhận file) vẫn đúng.

### 8.2 Bố cục trang (A4 dọc 210 × 297 mm)

```text
┌──────────────────────────────────────────────┐
│▌MATCH REPORT                Malaga 1–3 Villarreal │ ← header 14mm: vạch đỏ trái, H1 + tỉ số (phải)
│ LaLiga · Round 6 · 18.09.2026                │ ← caption
├──────────────────────────────────────────────┤
│                                              │
│   Nội dung trang (lề 12mm, lưới 2 cột)        │
│                                              │
├──────────────────────────────────────────────┤
│ Data from Flashscore · Generated 13.10.2026   Page 3 / 11 │ ← footer 10mm, caption
└──────────────────────────────────────────────┘
```

**Trang 1 — Summary** (nội dung quan trọng nhất của cả báo cáo):

- tỉ số, logo, người ghi bàn;
- 6 KPI;
- Key insights (≤ 6 câu);
- Result vs performance;
- Player of the match;
- Top performers / Concerns.

### 8.3 Cách dựng (thay `Exporter` 🟡)

| Bước | Chi tiết |
| --- | --- |
| 1 | Tạo container ẩn `#reportRoot` rộng **794px** (A4 ở 96 dpi), nằm ngoài màn hình (`position:fixed; left:-10000px`), dùng **cùng CSS** với dashboard (đảm bảo đồng nhất font, màu) |
| 2 | `Report.build(preset)` dựng **từng trang** thành một `<section class="pdf-page">` cao **1123px** cố định. Nội dung được thiết kế để vừa trang; riêng bảng phụ lục được chia hàng theo chiều cao đo thực tế (không cắt ngang chữ như `sliceTall` hiện tại) |
| 3 | Chart trong report tạo với `animation:false`, `devicePixelRatio:2` |
| 4 | Đếm tổng số trang ⇒ điền "Page x / N" vào footer HTML |
| 5 | `html2canvas(page,{scale:2, backgroundColor:'#FFFFFF'})` ⇒ `pdf.addImage(…,'JPEG',0.92)` full trang, mỗi section đúng 1 trang |
| 6 | Header/footer nằm **trong HTML** (cùng font Inter) thay vì `pdf.text` Helvetica ⇒ đồng nhất font giữa web và PDF |
| 7 | Tên file: `MatchReport_<Home>_<Away>_<yyyy-mm-dd>_<coach\|full>.pdf` |
| 8 | Dọn dẹp: huỷ chart report, xoá `#reportRoot`, khôi phục tab/đội đang xem như `Exporter` hiện tại |

**Mục tiêu đo được** (kiểm ở R4):

| Chỉ tiêu | Coach brief | Full report |
| --- | --- | --- |
| Số trang | 4 | ≤ 14 |
| Dung lượng | ≤ 2,5 MB | ≤ 6 MB |
| Thời gian xuất | ≤ 10 s | ≤ 25 s |

Thêm yêu cầu cho cả hai preset:

- không trang nào có nội dung bị cắt;
- chữ nhỏ nhất ≥ 8 pt khi in.

⚠ PDF dạng ảnh không cho chọn chữ. Muốn chọn và tìm kiếm được chữ trong PDF thì phải nhúng font Inter vào jsPDF và vẽ text vector; cách này tăng độ phức tạp đáng kể. Phương án này **không** được đề xuất cho bản này (ghi ở §13, R-7).

---

## 9. Kiến trúc front-end

Vẫn là **một file** `match_report.html`, không build step, không framework (CLAUDE.md §5). Mã mới được tổ chức thành module IIFE như phong cách hiện tại:

| Module | Trách nhiệm | Phụ thuộc | Kiểm thử |
| --- | --- | --- | --- |
| `Theme` | Đọc token CSS, cấu hình mặc định Chart.js, màu theo đội | Chart | e2e (style) |
| `Metrics` | Hồ sơ cầu thủ, tổng đội, ưu tiên team stats/fallback, per-90, xếp hạng, nhóm vị trí. **Hàm thuần** | `U`, `state` | **unit qua Playwright** (`page.evaluate`) trên 3 bộ dữ liệu (§11) |
| `Insights` | Luật I01–I20, chọn 4–6 câu | `Metrics` | unit như trên |
| `Views` (thay `Render`) | 8 tab + match header, dùng component §6 | `Metrics`, `Insights`, `Theme`, `LineupOCR` | e2e + golden v2 |
| `Report` (thay `Exporter`) | PDF 2 preset | `Views`, jsPDF, html2canvas | e2e PDF |

**Tương thích tên.**

- `Render` vẫn được export với 3 hàm `scorebar`, `tabs`, `activeTab` (được `App.enter/setTeam/setTab` gọi), cùng `_names`. Ba hàm này uỷ quyền sang `Views`.
- `Exporter.run` được giữ, uỷ quyền sang `Report.run('full')`.

Nhờ vậy `App` (đang đóng băng) **không phải sửa**.

`TABS` (đóng băng) được `App`, `Render` và `Exporter` cũ sử dụng. Thiết kế mới định nghĩa `VIEWS` riêng và không đọc `TABS`. 🟡 `TABS` có thể giữ nguyên (mã chết nhưng vô hại) hoặc gỡ ở bước dọn dẹp.

---

## 10. Phạm vi thay đổi và guardrails

### 10.1 Change surface 🟡 (cần bạn đồng ý mở khoá)

| ID | Vùng | Loại | Ghi chú |
| --- | --- | --- | --- |
| RD1 | Toàn bộ CSS cũ (vùng đóng băng "old CSS") | **Thay** | Theme mới §7. Giữ tên class mà `LineupOCR` sinh ra (`fm-*`, `ln-*`, `sub-*`, `lineup-*`, `rating-*`, `ocr-loading`, `spinner`) |
| RD2 | `Render` (trừ E7, nay chuyển vào view Line-ups) | **Thay** | Thành `Views` + vỏ tương thích `Render` |
| RD3 | `Exporter` (gồm E14 footer) | **Thay** | Thành `Report` + vỏ `Exporter.run` |
| RD4 | Markup `#dashboard` (scorebar, toggle, tab nav, footer-note) | **Sửa** | Giữ id: `scorebar`, `teamToggle`, `tabNav`, `tabContents`, `footMatch`, các `.toggle-pill[data-team]`, `.tab-btn[data-tab]` |
| RD5 | Header + màn hình nhập URL | **Restyle** (CSS) + đổi chữ thương hiệu | **Giữ** cấu trúc và id của E1–E2; không đổi hành vi |
| RD6 | Thêm `Theme`, `Metrics`, `Insights` | **Thêm** | Script block mới hoặc trong block Render |
| RD7 | `App.buildFromUrl` + `App.reset` | **Sửa 2 dòng mỗi hàm** | Gán/xoá `state.teamStats`, `state.meta`. Chỉ khi R1 được duyệt |

### 10.2 Hợp đồng hành vi phải giữ (test hoá ở R0, chạy trước và sau)

| # | Hành vi | Test |
| --- | --- | --- |
| B1 | Ô URL: validate, bật/tắt `#btnGenerate`, thông báo lỗi `#urlError` y nguyên chữ | `test_url_flow` (có sẵn) |
| B2 | Polling, thông điệp tiến độ, hiển thị lỗi server và cảnh báo (toast) | `test_url_flow` |
| B3 | Demo: bấm "explore with sample data" ⇒ dashboard Korea vs Czech Republic; OCR line-ups ra đúng tên (như golden hiện tại) | `test_demo_flow` + test OCR mới so khớp `lineupText` của demo với snapshot hiện tại |
| B4 | "New match" đưa về màn hình nhập, xoá state và chart | e2e có sẵn |
| B5 | Export PDF tạo file hợp lệ, không ném lỗi, khôi phục tab/đội đang xem | e2e PDF (mở rộng: kiểm số trang, preset) |
| B6 | Bảng sort được theo mọi cột (desc → asc), sort số theo `U.rankVal` | e2e mới |
| B7 | Không có lỗi JS trong console ở mọi tab × mọi team filter, ở 1280px và 420px | e2e mới (lặp toàn bộ tổ hợp) |
| B8 | Không có cuộn ngang toàn trang ở 420px | e2e mới |
| B9 | API/crawler không đổi hành vi ngoài phần R1 đã duyệt | toàn bộ unit/live hiện có |

### 10.3 Không mất dữ liệu — mọi cột hiện hiển thị vẫn có chỗ

| Dữ liệu hiện có | Nơi hiển thị mới |
| --- | --- |
| 12 chỉ số head-to-head | Summary (Team comparison) + Team |
| Radar đội | Thay bằng so sánh 2 phía (Summary). Radar chuyển sang hồ sơ cầu thủ |
| Best/worst theo rating | Top performers / Concerns |
| Timeline | Summary (giữ logic gom nhóm, tooltip) |
| Bảng 5 tab × đội | Bảng sort được trong Attack/Passing/Defending/Goalkeeping + "All stats" của Players + phụ lục PDF |
| Top Stats, General | Bảng tổng hợp Players |
| Match story | Tab Line-ups (+ card Substitutions mới) |

### 10.4 Công cụ bảo vệ cập nhật

| Công cụ | Thay đổi |
| --- | --- |
| `tools/html_guard.py` | Thêm cấu hình "redesign": vùng đóng băng mới gồm demo data, `LineupOCR`, `U`, `toast/showLoading/hideLoading/destroyCharts`, `setupUrlForm`, `setUrlError`, `Api`, `App.*`. 🟡 **Baseline so sánh mới** = commit mốc sau Phase 5 (R0). Nếu bạn không muốn commit: dùng hash nội dung lưu trong `tools/` |
| `tools/check_diff_budget.py` | Change surface RD1–RD7 thay E1–E14 (E1–E14 được nhập vào commit mốc) |
| `tools/golden_demo.py` | Snapshot v2 (tab mới, số chart mới) tạo **sau khi bạn nghiệm thu giao diện** ở R5. Trong lúc R3–R4 chưa nghiệm thu, golden v1 được thay bằng các test hợp đồng B1–B9 (golden v1 chắc chắn đỏ vì DOM đổi có chủ đích) |

---

## 11. Kế hoạch triển khai chi tiết

| Phase | Việc | Đầu ra | Kiểm tra |
| --- | --- | --- | --- |
| **R0** | (1) 🟡 Commit mốc toàn bộ thay đổi Phase 0–5. (2) Viết test B6–B8 và test OCR demo trên mã **hiện tại**. (3) Lưu 3 bộ dữ liệu cố định `tests/fixtures/results/{vLuGlk0n,GGiPsLP1,d8pxv90m}.json`: thường / VAR + pen / hiệp phụ + luân lưu. (4) Ghi kỳ vọng số liệu đội theo Flashscore | test mới xanh trên mã cũ | `unittest` xanh |
| **R1** 🟡 | `crawler/team_stats.py` (3 phạm vi, song song) + `header.py` đọc meta; `assemble` thêm `teamStats`, `meta`, `schemaVersion=2`; cảnh báo `W_NO_TEAM_STATS`; `tools/capture_fixtures.py` lưu thêm `team_stats_*.html`; test offline + live 9 trận | JSON mở rộng | unit, live; thời gian ≤ 75 s trận Johor |
| **R2** | `Theme`, `Metrics`, `Insights` (chưa đổi giao diện); test số liệu (§12.2) | module + test | test Metrics/Insights xanh |
| **R3** | `Views` 8 tab + CSS mới + vỏ `Render`; dọn CSS cũ | dashboard mới | B1–B9 xanh; screenshot 1280/420 cho bạn duyệt |
| **R4** | `Report` 2 preset + vỏ `Exporter` | PDF mới | mục tiêu §8.3; B5 |
| **R5** | Bạn nghiệm thu ⇒ golden v2, cập nhật guard, CLAUDE.md, tài liệu này (§ghi nhận) | — | toàn bộ checklist §12.4 |

Mỗi phase dừng lại báo cáo; **không** chuyển phase khi test đỏ.

---

## 12. Kiểm thử và nghiệm thu

### 12.1 Các lớp test

| Lớp | Mới / có sẵn | Nội dung |
| --- | --- | --- |
| unit Python | có sẵn + R1 | parser team stats (fixture HTML), meta, `possessionReliable`, schema v2 |
| unit JS (Playwright `page.evaluate`) | **mới** | `Metrics`, `Insights` trên 3 bộ dữ liệu + demo |
| e2e | có sẵn + mới | B1–B9, mọi tab × filter × 2 viewport, PDF 2 preset |
| live | có sẵn + R1 | team stats + meta trên trận tham chiếu |

### 12.2 Kỳ vọng số liệu (trích, trận Johor `vLuGlk0n`, ✅ Flashscore 2026-10-13)

| Chỉ số | Johor DT | Svay Rieng |
| --- | --- | --- |
| Goals | 6 | 0 |
| xG (team stats / Σ player) | 4.79 / 4.81 | 0.32 / 0.32 |
| Total shots | 25 | 7 |
| Accurate passes | 290/366 (79%) | 299/366 (82%) |
| Fouls | 17 | 10 |
| Goals prevented | 0.32 | −1.74 |
| xG theo hiệp (H1 → H2) | 1.65 → 3.13 | 0.06 → 0.26 |
| Possession | 50/50 ⇒ `possessionReliable=false` ⚠ | |

Kỳ vọng insight trên trận Johor (tập con, không phụ thuộc thứ tự): I01, I03, I04, I12, I17, I20 (possession).

Cần thêm 2 trận đối chứng:

- Malaga–Villarreal: possession thật 37/63, có VAR và penalty;
- Altglienicke–Wolfsburg: hiệp phụ và luân lưu, kiểm tra trục timeline > 90'.

### 12.3 Kiểm tra giao diện "đồng nhất" (tự động)

Script e2e duyệt mọi phần tử chữ hiển thị, lấy `getComputedStyle` và khẳng định:

- `font-family` chỉ là Inter (hoặc fallback);
- `font-size` ∈ {12, 14, 18, 22, 24, 40} px (mobile thêm 18, 32);
- `color` ∈ {ink, ink-2, ink-3, brand, #FFF, các màu chữ của thang rating};
- không phần tử chữ nào < 12px.

Đây là cách **đo** được yêu cầu "đồng nhất size, font, color".

### 12.4 Checklist nghiệm thu (bạn duyệt ở R5)

- [ ] `python -m unittest discover -s tests -t .` xanh; `FS_LIVE=1` live xanh
- [ ] Guard: diff budget RD1–RD7, vùng đóng băng mới, golden v2
- [ ] Chạy thật trận `vLuGlk0n` + Malaga + Altglienicke qua `python server.py`
- [ ] Demo: dashboard + OCR line-ups đúng như trước
- [ ] Coach brief 4 trang, Full report ≤ 14 trang, không cắt chữ, in đen trắng đọc được
- [ ] 1280 px và 420 px: không lỗi console, không cuộn ngang
- [ ] CLAUDE.md và tài liệu cập nhật

---

## 13. Rủi ro

| # | Rủi ro | Khả năng | Ảnh hưởng | Giảm thiểu |
| --- | --- | --- | --- | --- |
| R-1 | Thay `Render`/`Exporter`/CSS làm hỏng luồng demo/OCR | TB | Cao | Giữ `LineupOCR` đóng băng; giữ id `lc-*` và class; test OCR so khớp snapshot (B3) trước khi sửa |
| R-2 | Flashscore đổi DOM tab STATS | TB | TB | Thiếu dữ liệu chỉ sinh cảnh báo, dashboard lùi về số suy ra; live test canary |
| R-3 | Possession giả (50/50) bị coi là thật | Đã thấy | TB | Luật `possessionReliable` + nhãn "n/a" |
| R-4 | Insight sai ngữ cảnh (ngưỡng không hợp mọi giải) | TB | TB | Ngưỡng tập trung một chỗ; câu luôn kèm số; hiệu chỉnh trên 9 fixture ở R2; không có khuyến nghị chiến thuật tự động |
| R-5 | Xếp hạng trong trận trên mẫu nhỏ bị hiểu như percentile giải đấu | TB | Thấp | Ghi "#k of n DEF", yêu cầu số phút và số lần thử tối thiểu |
| R-6 | PDF nặng/chậm vì `html2canvas` | Thấp | TB | JPEG 0.92, trang cố định, tắt animation; đo theo §8.3 |
| R-7 | PDF dạng ảnh không chọn được chữ | Chắc chắn | Thấp | Chấp nhận (như hiện tại). Phương án vector để sau, cần duyệt riêng |
| R-8 | Thời gian crawl tăng | TB | Thấp | Song song với trang hiện có; ngân sách 150 s giữ nguyên; đo ở R1 |
| R-9 | Team color đỏ trùng brand khiến người xem nghĩ dashboard "nghiêng" đội nhà | Thấp | Thấp | Hai đội luôn có tên; chọn thay thế ở 🟡 Q-C nếu bạn muốn |

---

## 14. Quyết định cần bạn duyệt

Mỗi mục có **đề xuất mặc định** (★). Bạn chỉ cần trả lời những mục muốn khác.

| ID | Câu hỏi | Lựa chọn |
| --- | --- | --- |
| Q-A | Crawl thêm tab **STATS cấp đội** (Overall / 1st half / 2nd half) và **meta** (ngày, giải, trọng tài, sân)? Đụng `crawler/` và tăng ~5–8 s/trận | ★ Có (mở khoá Half-by-half, Set pieces, possession thật) · Không (dashboard chỉ dùng player stats; các card 🟡 ẩn) |
| Q-B | Mở khoá vùng đóng băng `Render`, `Exporter`, CSS cũ (RD1–RD7), giữ đóng băng `LineupOCR`, demo data, luồng URL | ★ Đồng ý · Không (khi đó chỉ làm được restyle hạn chế) |
| Q-C | Màu 2 đội | ★ Home đỏ `#C8102E` / Away graphite `#1F2937` · Home graphite / Away đỏ · Hai màu trung tính khác (navy/teal), đỏ chỉ dành cho brand |
| Q-D | "Possession" khi thiếu dữ liệu thật | ★ Hiện "n/a" và đổi proxy thành "Share of completed passes" (tên đúng) · Giữ proxy như hiện tại |
| Q-E | PDF | ★ 2 preset (Coach brief + Full analyst report, mặc định Full) · Chỉ 1 báo cáo Full |
| Q-F | Vị trí Line-ups | ★ Tab riêng "Line-ups" (dùng id nội bộ `'overall'` để không sửa `LineupOCR`) · Giữ ở cuối Summary như hiện nay |
| Q-G | Commit mốc trước khi bắt đầu (để guard so sánh với baseline mới) | ★ Có, commit toàn bộ Phase 0–5 · Không commit (guard dùng hash lưu file) |
| Q-H | Font | ★ Chỉ Inter · Giữ Bebas Neue cho tỉ số/tiêu đề lớn |

---

## Phụ lục A — 45 chỉ số cấp đội Flashscore (2026-10-13)

Thứ tự đúng như trên trang (✅ Johor–Svay Rieng, Malaga–Villarreal; giống nhau ở cả 3 phạm vi). Ký hiệu: `(pct)` = hàng có thêm tỉ lệ %; \* = **chỉ có ở cấp đội**.

| Nhóm | Chỉ số |
| --- | --- |
| Top stats (lặp) | Expected goals (xG) · Ball possession\* · Big chances\* · Touches in opposition box · Total shots |
| Shots | Expected goals (xG) · xG on target (xGOT) · Total shots · Shots on target · Shots off target · Blocked shots · Shots inside the box · Shots outside the box · Hit the woodwork\* · Headed goals\* |
| Attack | Touches in opposition box · Big chances scored\* · Big chances missed · Corner kicks\* · Free kicks\* · Offsides |
| Passes | Passes\* · Accurate passes (pct) · Long passes\* · Accurate long passes (pct) · Final third passes\* · Accurate final third passes (pct) · Crosses\* · Accurate crosses (pct) · Expected assists (xA) · Key passes · Throw-ins\* |
| Defence | Fouls · Duels won · Tackles\* · Tackles won (pct) · Interceptions · Clearances · Errors leading to shot · Errors leading to goal |
| Goalkeeping | Goalkeeper saves · xGOT faced · Goals conceded · Goals prevented · Goal kicks\* |

Ví dụ giá trị (Malaga – Villarreal, Overall):

- xG 0.57 – 3.20;
- Possession 37% – 63%;
- Big chances 0 – 7;
- Shots 5 – 16;
- Corners 4 – 8;
- Passes 350 – 600;
- Accurate passes 283 (81%) – 539 (90%).

## Phụ lục B — Ánh xạ vị trí → nhóm

| Position (Flashscore) | Nhóm |
| --- | --- |
| Goalkeeper | GK |
| Centre back, Defender, Fullback, Wingback | DEF |
| Midfielder, Defensive midfielder ⚠, Central midfielder ⚠, Attacking midfielder | MID |
| Winger, Forward, Striker | FWD |
| khác / rỗng | OTHER |

⚠ = chưa thấy trong dữ liệu đã thu, thêm phòng trước.

## Phụ lục C — Thuật ngữ

| Thuật ngữ | Nghĩa |
| --- | --- |
| xG / xGOT / xA | Expected goals / xG on target (chất lượng cú sút trúng đích) / Expected assists |
| Goals prevented | xGOT faced − Goals conceded của thủ môn (dương = cứu thua hơn kỳ vọng) |
| Per-90 | Chỉ số quy đổi trên 90 phút thi đấu |
| Derived | Số do dashboard tự tính từ player stats khi Flashscore không cung cấp số cấp đội |
| Coach brief / Full analyst report | Hai preset của PDF (§8.1) |
| POTM | Player of the match (rating cao nhất) |
