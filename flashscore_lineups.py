"""
Flashscore Lineups Scraper v5 — Clean Element Screenshots to Excel
===================================================================
pip install playwright openpyxl pillow
playwright install chromium
python flashscore_lineups.py
"""

import re, time, io
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, PatternFill, Alignment

C_TITLE = "2E75B6"

def normalize_match_url(url):
    m = re.search(r"(https://www\.flashscore\.com/match/football/[^/]+/[^/]+/)", url)
    return m.group(1) if m else url.rstrip("/") + "/"

# ─── Screenshot helpers ───────────────────────────────────────────────────────

def get_section_screenshot(page, heading_keyword):
    """
    Tìm section chứa heading_keyword, chụp toàn bộ section đó.
    Trả về bytes hoặc None.
    """
    try:
        # Tìm tất cả các section div
        sections = page.locator(".section").all()
        for section in sections:
            try:
                text = section.inner_text(timeout=1000).strip().upper()
                if heading_keyword.upper() in text:
                    section.scroll_into_view_if_needed(timeout=3000)
                    time.sleep(0.5)
                    return section.screenshot()
            except Exception:
                continue
    except Exception:
        pass
    return None


def get_formation_screenshot(page):
    """Chụp riêng phần formation pitch."""
    # Thử các selector theo thứ tự
    for sel in [
        ".lf_field",
        '[data-analytics-context="widget-formation"]',
        ".lf_formation",
        ".lf_sidesBox",
    ]:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                el.scroll_into_view_if_needed(timeout=3000)
                time.sleep(0.5)
                return el.screenshot()
        except Exception:
            continue
    return None


def get_lineup_widget_screenshot(page):
    """Chụp toàn bộ lineup widget (fallback)."""
    for sel in [
        '[data-analytics-context="widget-lineups"]',
        ".lf_lineUp",
        ".lf__lineUp",
    ]:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                el.scroll_into_view_if_needed(timeout=3000)
                time.sleep(0.5)
                return el.screenshot()
        except Exception:
            continue
    return None


def get_coaches_screenshot(page):
    """Chụp section coaches — thường nằm cuối trang."""
    # Thử via section
    img = get_section_screenshot(page, "COACHES")
    if img:
        return img
    # Fallback: scroll xuống cuối và chụp
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
    return page.screenshot(full_page=False)

# ─── Excel helpers ────────────────────────────────────────────────────────────

def add_sheet_with_image(wb, sheet_name, title, img_bytes, match_label,
                         target_width=800):
    """
    Tạo sheet với tiêu đề và ảnh được scale cân đối về target_width px.
    """
    ws = wb.create_sheet(sheet_name)
    ws.sheet_view.showGridLines = False

    # Row 1: match label
    ws["A1"] = match_label
    ws["A1"].font = Font(bold=True, size=12, color=C_TITLE, name="Arial")
    ws.row_dimensions[1].height = 22

    # Row 2: section title
    ws["A2"] = title
    ws["A2"].font = Font(bold=True, size=11, color="222222", name="Arial")
    ws.row_dimensions[2].height = 20

    # Row 3: spacer
    ws.row_dimensions[3].height = 6

    if not img_bytes:
        ws["A4"] = "⚠ Không chụp được screenshot"
        ws["A4"].font = Font(italic=True, color="999999", name="Arial")
        ws.column_dimensions["A"].width = 50
        return

    # Load ảnh và scale
    img_stream = io.BytesIO(img_bytes)
    xl_img = XLImage(img_stream)

    orig_w = xl_img.width
    orig_h = xl_img.height

    if orig_w > 0:
        scale = target_width / orig_w
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
    else:
        new_w, new_h = target_width, 400

    xl_img.width  = new_w
    xl_img.height = new_h
    xl_img.anchor = "A4"
    ws.add_image(xl_img)

    # Set column width (Excel units ≈ 7px per unit)
    ws.column_dimensions["A"].width = new_w / 7 + 2

    # Set row 4 height đủ chứa ảnh (Excel points ≈ 0.75 * px)
    ws.row_dimensions[4].height = new_h * 0.75 + 10


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Flashscore Lineups → Excel  v5")
    print("=" * 60)

    url = input("\nNhập link Flashscore match:\n> ").strip()
    if not url:
        url = "https://www.flashscore.com/match/football/england-j9N9ZNFA/new-zealand-rLctHkpU/summary/lineups/"

    base_url = normalize_match_url(url)
    target   = f"{base_url}summary/lineups/"
    print(f"\nURL: {target}\n")

    screenshots = {}
    match_label = "Flashscore Lineups"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
            viewport={"width": 1100, "height": 900},
            locale="en-GB",
            device_scale_factor=2,  # retina → ảnh sắc nét gấp đôi
        )
        page = ctx.new_page()

        print("Đang load trang...")
        try:
            page.goto(target, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            try:
                page.goto(target, wait_until="commit", timeout=20000)
            except Exception:
                pass

        time.sleep(4)

        # Cookie
        for sel in ["#onetrust-accept-btn-handler", "#didomi-notice-agree-button",
                    "button:has-text('Accept all')", "button:has-text('Accept')"]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1500):
                    btn.click(); time.sleep(1); break
            except Exception:
                pass

        time.sleep(2)

        # Match label
        try:
            home = page.locator(
                ".duelParticipant__home .participant__participantName"
            ).first.inner_text(timeout=5000).strip()
            away = page.locator(
                ".duelParticipant__away .participant__participantName"
            ).first.inner_text(timeout=5000).strip()
            date = page.locator(
                ".duelParticipant__startTime"
            ).first.inner_text(timeout=3000).strip()
            match_label = f"{home} vs {away}  ({date})"
        except Exception:
            pass
        print(f"Trận: {match_label}\n")

        # ── Ẩn sticky header + cookie + ads trước khi chụp ────────────────
        try:
            page.evaluate("""
                const hide = [
                    // Score header sticky (che nội dung khi scroll)
                    '.duelParticipant', '.duelParticipant__container',
                    '.detailOver', '.detail__detailOver',
                    '[class*="duelParticipant"]',
                    '[class*="stickyBlock"]', '[class*="sticky"]',
                    // Cookie / ads
                    '#onetrust-consent-sdk', '#didomi-host',
                    '[id*="cookie"]', '[id*="Cookie"]',
                    '[class*="Cookie"]', '[class*="gdpr"]',
                    '[class*="banner"]', '.ad-container',
                ];
                hide.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        el.style.setProperty('display', 'none', 'important');
                    });
                });
                // Gỡ position fixed/sticky của mọi element
                document.querySelectorAll('*').forEach(el => {
                    const pos = getComputedStyle(el).position;
                    if (pos === 'fixed' || pos === 'sticky') {
                        el.style.setProperty('position', 'relative', 'important');
                    }
                });
            """)
        except Exception:
            pass
        time.sleep(0.5)

        # ── 1. Formation ─────────────────────────────────────────────────────
        print("[1/5] Chụp Formation...")
        img = get_formation_screenshot(page)
        screenshots["formation"] = img
        print(f"      {'✓' if img else '✗'}")

        # ── 2. Starting Lineups ──────────────────────────────────────────────
        print("[2/5] Chụp Starting Lineups...")
        img = get_section_screenshot(page, "STARTING LINEUPS")
        screenshots["starting"] = img
        print(f"      {'✓' if img else '✗'}")

        # ── 3. Substituted Players ───────────────────────────────────────────
        print("[3/5] Chụp Substituted Players...")
        img = get_section_screenshot(page, "SUBSTITUTED PLAYERS")
        screenshots["substituted"] = img
        print(f"      {'✓' if img else '✗'}")

        # ── 4. Substitutes ───────────────────────────────────────────────────
        print("[4/5] Chụp Substitutes...")
        img = get_section_screenshot(page, "SUBSTITUTES")
        # "SUBSTITUTED PLAYERS" cũng chứa "SUBSTITUTES" → cần tìm đúng section
        # Nếu bị trùng, thử tìm section có text CHÍNH XÁC là "SUBSTITUTES"
        if not img:
            try:
                sections = page.locator(".section").all()
                for section in sections:
                    try:
                        # Lấy heading text (thường là element đầu tiên)
                        heading = section.locator(
                            '[class*="headerSection"], [class*="sectionHeader"], h3, h4'
                        ).first
                        htxt = heading.inner_text(timeout=800).strip().upper()
                        if htxt == "SUBSTITUTES":
                            section.scroll_into_view_if_needed(timeout=3000)
                            time.sleep(0.5)
                            img = section.screenshot()
                            break
                    except Exception:
                        continue
            except Exception:
                pass
        screenshots["substitutes"] = img
        print(f"      {'✓' if img else '✗'}")

        # ── 5. Coaches ───────────────────────────────────────────────────────
        print("[5/5] Chụp Coaches...")
        img = get_coaches_screenshot(page)
        screenshots["coaches"] = img
        print(f"      {'✓' if img else '✗'}")

        browser.close()

    # ── Ghi Excel ─────────────────────────────────────────────────────────────
    print("\nĐang ghi Excel...")
    wb = Workbook()
    wb.remove(wb.active)

    # Summary
    ws = wb.create_sheet("Summary", 0)
    ws.sheet_view.showGridLines = False
    ws["A1"] = "LINEUPS"
    ws["A1"].font = Font(bold=True, size=18, color=C_TITLE, name="Arial")
    ws["A2"] = match_label
    ws["A2"].font = Font(size=13, color="333333", name="Arial")
    ws["A3"] = f"Crawled: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws["A3"].font = Font(size=9, italic=True, color="888888", name="Arial")
    ws["A5"] = "Sheets:"
    ws["A5"].font = Font(bold=True, size=10, name="Arial")
    for i, name in enumerate(["Formation","Starting XI","Substituted","Substitutes","Coaches"], 1):
        ws.cell(5+i, 1, f"  {i}. {name}").font = Font(size=10, name="Arial")
    ws.column_dimensions["A"].width = 60
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 22

    # Các sheet ảnh — target_width=800 cho ảnh cân đối
    sections = [
        ("Formation",   "formation",   "⚽  FORMATION  —  Sơ đồ đội hình"),
        ("Starting XI", "starting",    "📋  STARTING LINEUPS  —  Cầu thủ xuất phát"),
        ("Substituted", "substituted", "🔄  SUBSTITUTED PLAYERS  —  Thay người"),
        ("Substitutes", "substitutes", "🪑  SUBSTITUTES  —  Cầu thủ dự bị"),
        ("Coaches",     "coaches",     "👔  COACHES  —  Huấn luyện viên"),
    ]

    for sheet_name, key, title in sections:
        img_bytes = screenshots.get(key)
        # Formation dùng width lớn hơn vì nội dung rộng
        w = 900 if key == "formation" else 750
        add_sheet_with_image(wb, sheet_name, title, img_bytes, match_label,
                             target_width=w)
        print(f"  ✓ Sheet '{sheet_name}'" if img_bytes else f"  ✗ Sheet '{sheet_name}' (no image)")

    # Lưu
    try:
        home_p = re.sub(r"[^\w]", "_", match_label.split(" vs ")[0])[:15]
        away_p = re.sub(r"[^\w]", "_", match_label.split(" vs ")[1].split("(")[0].strip())[:15]
    except Exception:
        home_p, away_p = "Home", "Away"

    ts    = datetime.now().strftime("%Y%m%d_%H%M")
    fname = f"lineups_{home_p}_vs_{away_p}_{ts}.xlsx"
    out   = str(Path.home() / "Downloads" / fname)
    wb.save(out)
    print(f"\n✅ Đã lưu: {out}")

if __name__ == "__main__":
    main()
