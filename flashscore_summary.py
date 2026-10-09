"""
Flashscore Match Summary (Timeline) Scraper v1
==============================================
Lấy dòng thời gian (timeline) của trận đấu: bàn thắng, thẻ phạt, thay người…
giống tab "SUMMARY" trên Flashscore.

Cách dùng:
  1. Cài thư viện (chỉ 1 lần):
       pip install playwright openpyxl pillow
       playwright install chromium
       (pillow: để nhúng logo 2 đội vào file Excel)

  2. Chạy:
       python flashscore_summary.py
       (dán link Flashscore của trận đấu)

  Output: .xlsx gồm
    - Sheet "Summary"  : thông tin trận + tỉ số cuối
    - Sheet "Timeline" : mỗi sự kiện 1 dòng
        Minute | Half | Side | Team | Type | Player | Detail | Score

  Nếu không đọc được sự kiện nào, tool sẽ lưu kèm 1 file .html (vùng timeline)
  để gửi lại cho mình chỉnh selector cho đúng.
"""

import io
import re
import time
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage

# ─── Config / màu ──────────────────────────────────────────────────────────────
COLOR_HOME  = "1A3A5C"
COLOR_AWAY  = "5C1A1A"
COLOR_FG    = "FFFFFF"
COLOR_ODD   = "F2F7FC"
COLOR_EVEN  = "FFFFFF"
COLOR_TITLE = "2E75B6"


def normalize_match_url(url):
    m = re.search(r"(https://www\.flashscore\.com/match/football/[^/]+/[^/]+/)", url)
    return m.group(1) if m else url.rstrip("/") + "/"


# ─── Match info (home/away/date/score) ──────────────────────────────────────────

def extract_match_info(page):
    info = {"home": "Home", "away": "Away", "date": "", "score": ""}
    try:
        info["home"] = page.locator(
            ".duelParticipant__home .participant__participantName"
        ).first.inner_text(timeout=5000).strip()
        info["away"] = page.locator(
            ".duelParticipant__away .participant__participantName"
        ).first.inner_text(timeout=5000).strip()
    except Exception:
        pass
    try:
        info["date"] = page.locator(
            ".duelParticipant__startTime"
        ).first.inner_text(timeout=3000).strip()
    except Exception:
        pass
    # Tỉ số cuối: vùng .detailScore__wrapper thường là "1 - 1"
    for sel in [".detailScore__wrapper", "[class*='detailScore']"]:
        try:
            raw = page.locator(sel).first.inner_text(timeout=2000).strip()
            m = re.search(r"(\d+)\D+(\d+)", raw)
            if m:
                info["score"] = f"{m.group(1)} - {m.group(2)}"
                break
        except Exception:
            continue
    return info


# ─── Team logos ─────────────────────────────────────────────────────────────────

def extract_logos(page, ctx):
    """Lấy URL + bytes logo của 2 đội. Ảnh bị chặn khi load trang nên ta đọc
    thuộc tính src từ DOM rồi tải riêng qua ctx.request (không bị route chặn)."""
    out = {"home": {"url": None, "data": None}, "away": {"url": None, "data": None}}
    sides = [("home", ".duelParticipant__home"), ("away", ".duelParticipant__away")]
    for side, root in sides:
        url = None
        # 1) thẻ <img>
        for q in [f"{root} img.participant__image", f"{root} img"]:
            try:
                u = page.locator(q).first.get_attribute("src", timeout=2500)
                if u:
                    url = u; break
            except Exception:
                continue
        # 2) fallback: background-image
        if not url:
            try:
                url = page.evaluate(
                    """(sel)=>{const e=document.querySelector(sel+" [class*='participant__image'], "+sel+" [class*='logo']");
                        if(!e) return null; const b=getComputedStyle(e).backgroundImage||'';
                        const m=b.match(/url\\([\"']?([^\"')]+)/); return m?m[1]:null;}""", root)
            except Exception:
                url = None
        if url and url.startswith("//"):
            url = "https:" + url
        out[side]["url"] = url
        if url:
            try:
                resp = ctx.request.get(url, timeout=10000)
                if resp.ok:
                    out[side]["data"] = resp.body()
            except Exception as e:
                print(f"  ⚠ tải logo {side} lỗi: {e}")
    return out


# ─── Timeline extraction (chạy thẳng trong trang) ───────────────────────────────
# Walk các phần tử của vùng timeline theo đúng thứ tự, vừa đi vừa nhớ hiệp đấu,
# phân loại sự kiện theo class của <svg> icon + text trong dòng.
JS_EXTRACT = r"""
() => {
  const out = [];
  const sampleHTML = [];
  const containerSel = [
    '.smv__verticalSections',
    '[class*="verticalSections"]',
    '.detailMS__incidentsWrapper',
    '[class*="incidentsWrapper"]'
  ];
  let root = null;
  for (const s of containerSel) { const e = document.querySelector(s); if (e) { root = e; break; } }
  if (!root) return { events: [], html: '', sample: '' };

  const txt = el => el ? (el.textContent || '').replace(/\s+/g, ' ').trim() : '';
  let half = '';
  const classifyHalf = t => {
    const u = t.toUpperCase();
    if (u.includes('1ST')) return '1st half';
    if (u.includes('2ND')) return '2nd half';
    if (u.includes('EXTRA')) return 'Extra time';
    if (u.includes('PENAL')) return 'Penalties';
    return half;
  };

  const rows = Array.from(root.children);
  for (const row of rows) {
    const cls = (row.className || '').toString();
    const hasPlayer = row.querySelector('[class*="playerName"]');

    // ── Tiêu đề hiệp đấu (không có cầu thủ) ──
    if (!hasPlayer && /HALF|EXTRA TIME|PENAL|FULL TIME/i.test(txt(row))) {
      half = classifyHalf(txt(row));
      continue;
    }
    if (!hasPlayer) continue;

    if (sampleHTML.length < 10) sampleHTML.push(row.outerHTML);

    const incident = row.querySelector('[class*="incident"]') || row;
    const side   = /home/i.test(cls) ? 'home' : /away/i.test(cls) ? 'away' : '';
    const minute = txt(row.querySelector('[class*="timeBox"]'));
    const svg    = row.querySelector('svg');
    const sc     = ((svg && svg.getAttribute('class')) || '').toLowerCase();

    // tên cầu thủ — loại bỏ tên nằm trong phần assist (kiến tạo)
    const assistEls = Array.from(row.querySelectorAll('[class*="assist"]'));
    const inAssist  = el => assistEls.some(a => a.contains(el));
    const nameEls   = Array.from(row.querySelectorAll('[class*="playerName"]')).filter(e => !inAssist(e));
    const names     = nameEls.map(txt).filter(Boolean);

    // text của dòng, bỏ phút, để dò tỉ số + ngoặc đơn
    const body  = txt(row).replace(minute, '').trim();
    const lower = body.toLowerCase();
    const sm    = body.match(/(\d+)\s*[-:]\s*(\d+)/);
    const score = sm ? (sm[1] + ' - ' + sm[2]) : '';
    const parens = (body.match(/\(([^)]+)\)/g) || []).map(s => s.replace(/[()]/g, '').trim());

    // dấu hiệu thay người: 2 cầu thủ, hoặc icon/phần tử sub
    const subEl = row.querySelector('[class*="ubstitut"], [class*="ncidentSub"]');
    const isSub = names.length >= 2 || /substitut/.test(sc) || !!subEl;

    let type, player = names[0] || '', detail = '';
    if (score) {                                   // có tỉ số ⇒ bàn thắng
      if (/own goal/.test(lower)) type = 'Own goal';
      else if (/penalt/.test(lower)) type = 'Penalty goal';
      else type = 'Goal';
      const ass = (assistEls[0] && txt(assistEls[0])) ||
                  parens.find(p => !/own goal|penalt/i.test(p)) || '';
      detail = ass.replace(/^\(|\)$/g, '').trim();
    } else if (isSub) {                            // thay người
      type = 'Substitution';
      const outName = names[1] || txt(subEl);
      if (outName) detail = 'Out: ' + outName;
    } else {                                       // thẻ phạt
      if (/yellowred/.test(sc)) type = 'Second yellow (→ red)';
      else if (/redcard|red-card/.test(sc)) type = 'Red card';
      else if (/yellowcard|yellow-card/.test(sc)) type = 'Yellow card';
      else if (/\bvar\b/.test(sc)) type = 'VAR';
      else type = 'Card';
      detail = parens[0] || '';                    // lý do: Holding, Tripping…
    }

    if (!player && !minute) continue;
    out.push({ half, minute, side, type, player, detail, score });
  }

  // luôn trả về vài dòng HTML mẫu để chỉnh selector khi cần
  return { events: out, html: out.length ? '' : root.outerHTML.slice(0, 200000),
           sample: sampleHTML.join('\n\n') };
}
"""


def scrape_summary(page):
    try:
        page.wait_for_selector(
            ".smv__verticalSections, [class*='verticalSections'], [class*='incidentsWrapper']",
            timeout=15000)
    except PlaywrightTimeout:
        print("  ⚠ Không thấy vùng timeline (có thể trận chưa có sự kiện hoặc layout khác).")
    time.sleep(1.2)
    try:
        return page.evaluate(JS_EXTRACT)
    except Exception as e:
        print(f"  ⚠ Lỗi đọc timeline: {e}")
        return {"events": [], "html": ""}


# ─── Excel writer ───────────────────────────────────────────────────────────────

def write_excel(events, match_info, output_path):
    wb = Workbook()
    wb.remove(wb.active)

    # ── Summary sheet ──
    ws = wb.create_sheet("Summary")
    ws.sheet_view.showGridLines = False
    ws["B2"] = f"{match_info['home']}  vs  {match_info['away']}"
    ws["B2"].font = Font(bold=True, size=16, color=COLOR_TITLE, name="Arial")
    ws["B3"] = f"Final score:  {match_info.get('score', '') or '-'}"
    ws["B3"].font = Font(bold=True, size=12, color="333333", name="Arial")
    ws["B4"] = match_info.get("date", "")
    ws["B4"].font = Font(size=10, color="666666", name="Arial")
    ws["B5"] = f"Home: {match_info['home']}   |   Away: {match_info['away']}"
    ws["B5"].font = Font(size=10, color="444444", name="Arial")
    ws["B7"] = f"Events: {len(events)}"
    ws["B7"].font = Font(size=10, name="Arial")
    ws["B8"] = f"Crawled: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws["B8"].font = Font(italic=True, size=9, color="999999", name="Arial")
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 55

    # ── Logos (nhúng ảnh nếu tải được, kèm URL dạng text) ──
    def embed_logo(data, anchor, px=72):
        if not data:
            return False
        try:
            im = XLImage(io.BytesIO(data)); im.width = px; im.height = px; im.anchor = anchor
            ws.add_image(im); return True
        except Exception as e:
            print(f"  ⚠ nhúng logo lỗi (cần Pillow?): {e}"); return False

    ws["B11"] = "Logos"
    ws["B11"].font = Font(bold=True, size=11, color=COLOR_TITLE, name="Arial")
    ws["B12"] = match_info["home"]; ws["E12"] = match_info["away"]
    for cell in ("B12", "E12"):
        ws[cell].font = Font(bold=True, size=10, name="Arial")
    embed_logo(match_info.get("home_logo"), "B13")
    embed_logo(match_info.get("away_logo"), "E13")
    ws.row_dimensions[13].height = 58
    if match_info.get("home_logo_url"):
        ws["B19"] = f"Home logo: {match_info['home_logo_url']}"
        ws["B19"].font = Font(size=8, color="888888", name="Arial")
    if match_info.get("away_logo_url"):
        ws["B20"] = f"Away logo: {match_info['away_logo_url']}"
        ws["B20"].font = Font(size=8, color="888888", name="Arial")
    for col in ("C", "D", "E"):
        ws.column_dimensions[col].width = 14

    # ── Timeline sheet ──
    ws = wb.create_sheet("Timeline")
    ws.sheet_view.showGridLines = False
    ws["A1"] = f"{match_info['home']} vs {match_info['away']}  —  Match timeline"
    ws["A1"].font = Font(bold=True, size=13, color=COLOR_TITLE, name="Arial")
    ws.row_dimensions[1].height = 24

    headers = ["Minute", "Half", "Side", "Team", "Type", "Player", "Detail", "Score"]
    h_font   = Font(bold=True, color=COLOR_FG, name="Arial", size=10)
    h_align  = Alignment(horizontal="center", vertical="center", wrap_text=True)
    h_border = Border(bottom=Side(style="medium", color="FFFFFF"),
                      right=Side(style="thin", color="FFFFFF"))
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=3, column=ci, value=h)
        c.font = h_font
        c.fill = PatternFill("solid", start_color=COLOR_TITLE)
        c.alignment = h_align
        c.border = h_border
    ws.row_dimensions[3].height = 26

    if not events:
        ws["A5"] = "Không đọc được sự kiện nào (xem file .html kèm theo)."
        ws["A5"].font = Font(italic=True, color="C0392B", name="Arial")
    else:
        for ri, ev in enumerate(events, 4):
            side = ev.get("side", "")
            team = match_info["home"] if side == "home" else match_info["away"] if side == "away" else ""
            row_vals = [
                ev.get("minute", ""), ev.get("half", ""),
                side.capitalize(), team, ev.get("type", ""),
                ev.get("player", ""), ev.get("detail", ""), ev.get("score", ""),
            ]
            fill_color = COLOR_ODD if ri % 2 else COLOR_EVEN
            for ci, val in enumerate(row_vals, 1):
                c = ws.cell(row=ri, column=ci, value=val)
                c.fill = PatternFill("solid", start_color=fill_color)
                c.font = Font(name="Arial", size=10,
                              color=COLOR_HOME if (ci == 3 and side == "home")
                              else COLOR_AWAY if (ci == 3 and side == "away") else "000000",
                              bold=(ci == 5))
                c.alignment = Alignment(horizontal="left" if ci in (4, 6, 7) else "center",
                                        vertical="center")
            ws.row_dimensions[ri].height = 18

    widths = [9, 10, 7, 20, 16, 22, 26, 9]
    for ci, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = "A4"

    wb.save(output_path)
    print(f"\n✅ Đã lưu: {output_path}")


# ─── Main ────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Flashscore Match Summary (Timeline)  v1")
    print("=" * 60)

    url = input("\nNhập link Flashscore match:\n> ").strip()
    if not url:
        url = "https://www.flashscore.com/match/football/belgium-GbB957na/egypt-bejDn7NN/"

    base_url = normalize_match_url(url)
    print(f"\nURL: {base_url}\n")

    match_info = {"home": "Home", "away": "Away", "date": "", "score": ""}
    events, debug_html = [], ""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
            viewport={"width": 1280, "height": 900},
            locale="en-GB",
        )
        page = ctx.new_page()
        page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())
        page.route("**/ads/**",       lambda r: r.abort())
        page.route("**/analytics/**", lambda r: r.abort())

        print("Đang load trang...")
        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            try:
                page.goto(base_url, wait_until="commit", timeout=20000)
            except Exception:
                pass
        time.sleep(3)

        # Cookie banner
        for sel in ["#onetrust-accept-btn-handler", "#didomi-notice-agree-button",
                    "button:has-text('Accept all')", "button:has-text('Accept')"]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1500):
                    btn.click(); time.sleep(0.8); break
            except Exception:
                pass
        time.sleep(1.5)

        match_info = extract_match_info(page)
        print(f"Trận: {match_info['home']} vs {match_info['away']}  "
              f"({match_info['score'] or '?'})  {match_info['date']}")

        logos = extract_logos(page, ctx)
        match_info["home_logo"]     = logos["home"]["data"]
        match_info["away_logo"]     = logos["away"]["data"]
        match_info["home_logo_url"] = logos["home"]["url"]
        match_info["away_logo_url"] = logos["away"]["url"]
        print(f"Logo: home {'✓' if match_info['home_logo'] else '✗'}, "
              f"away {'✓' if match_info['away_logo'] else '✗'}")

        print("\nĐang đọc timeline...")
        res = scrape_summary(page)
        events = res.get("events", [])
        debug_html = res.get("sample", "") or res.get("html", "")
        print(f"  → {len(events)} sự kiện.")

        browser.close()

    home = re.sub(r"[^\w]", "_", match_info["home"])[:15]
    away = re.sub(r"[^\w]", "_", match_info["away"])[:15]
    ts   = datetime.now().strftime("%Y%m%d_%H%M")
    out  = str(Path.home() / "Downloads" / f"summary_{home}_vs_{away}_{ts}.xlsx")

    write_excel(events, match_info, out)

    # Lưu HTML mẫu nếu phân loại còn nghi ngờ (chưa rõ loại, hoặc thay người thiếu cầu thủ ra)
    uncertain = (not events) or any(
        (ev.get("type") in ("Card", "VAR", "")) or
        (ev.get("type") == "Substitution" and not ev.get("detail"))
        for ev in events)
    if uncertain and debug_html:
        dbg = out.replace(".xlsx", "_DEBUG.html")
        Path(dbg).write_text(debug_html, encoding="utf-8")
        print(f"⚠ Một vài sự kiện chưa chắc chắn. Đã lưu HTML mẫu (10 dòng đầu):\n   {dbg}")
        print("   → Nếu loại sự kiện / cầu thủ ra sân chưa đúng, gửi file này cho mình để chỉnh selector.")
    print(f"File: {out}")


if __name__ == "__main__":
    main()
