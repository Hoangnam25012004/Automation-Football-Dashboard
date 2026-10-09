"""
Flashscore Player Stats Scraper v4
====================================
Cách dùng:
  1. Cài thư viện (chỉ 1 lần):
       pip install playwright openpyxl
       playwright install chromium

  2. Chạy:
       python flashscore_scraper.py

  Output: .xlsx chia theo 2 đội (Home / Away) × 7 tabs
  Mỗi sheet có cột: Player | Position | [stats...]
"""

import re
import time
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ─── Config ──────────────────────────────────────────────────────────────────

TABS = ["top", "shots", "attack", "passes", "defense", "goalkeeping", "general"]
TAB_LABELS = {
    "top": "Top Stats", "shots": "Shots", "attack": "Attack",
    "passes": "Passes", "defense": "Defense",
    "goalkeeping": "Goalkeeping", "general": "General",
}

COLOR_HOME  = "1A3A5C"   # xanh đậm
COLOR_AWAY  = "5C1A1A"   # đỏ đậm
COLOR_FG    = "FFFFFF"
COLOR_ODD   = "F2F7FC"
COLOR_EVEN  = "FFFFFF"
COLOR_TITLE = "2E75B6"


# ─── URL helpers ─────────────────────────────────────────────────────────────

def normalize_match_url(url):
    m = re.search(r"(https://www\.flashscore\.com/match/football/[^/]+/[^/]+/)", url)
    return m.group(1) if m else url.rstrip("/") + "/"

def build_tab_url(base_url, tab):
    return f"{base_url}summary/player-stats/{tab}/"


# ─── Match info ──────────────────────────────────────────────────────────────

def extract_match_info(page):
    info = {"home": "Home", "away": "Away", "date": ""}
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
    return info


# ─── Team filter (combobox) ──────────────────────────────────────────────────

def open_combobox(page):
    try:
        btn = page.locator('[data-testid="wcl-selectButton"]').first
        btn.click(timeout=5000)
        time.sleep(0.8)
        return True
    except Exception:
        return False


def get_listbox_items(page):
    for sel in [
        '[role="option"]',
        '[role="listbox"] li',
        'ul[role="listbox"] > li',
        '[class*="teamSelector"] li',
        '[class*="selectList"] li',
    ]:
        items = page.locator(sel).all()
        if items:
            return items
    return []


def detect_team_filters(page):
    """
    Phát hiện options từ combobox filter.
    Trả về list [{"label": "ENG", "full_text": "England ENG"}, ...]
    BỎ "ALL" — chỉ lấy 2 đội.
    """
    results = []
    try:
        if not open_combobox(page):
            return []

        try:
            page.wait_for_selector('[role="option"], [role="listbox"]', timeout=3000)
        except Exception:
            pass

        items = get_listbox_items(page)
        for item in items:
            try:
                txt = item.inner_text(timeout=1000).strip()
                if not txt:
                    continue
                parts = txt.split()
                label = parts[-1] if parts else txt
                # Bỏ qua "ALL"
                if label.upper() == "ALL":
                    continue
                results.append({"label": label, "full_text": txt})
            except Exception:
                continue

        page.keyboard.press("Escape")
        time.sleep(0.3)

    except Exception as e:
        print(f"  ⚠ detect_team_filters lỗi: {e}")

    return results


def select_team(page, team_info):
    """Chọn 1 team từ combobox. Trả về True nếu thành công."""
    try:
        if not open_combobox(page):
            return False

        try:
            page.wait_for_selector('[role="option"], [role="listbox"]', timeout=3000)
        except Exception:
            pass

        items = get_listbox_items(page)
        target = team_info["label"].upper()
        full   = team_info["full_text"].upper()

        for item in items:
            try:
                txt = item.inner_text(timeout=1000).strip().upper()
                if txt == target or txt == full or txt.endswith(target):
                    item.click(timeout=3000)
                    time.sleep(1.5)
                    return True
            except Exception:
                continue

        page.keyboard.press("Escape")
        time.sleep(0.3)
        return False

    except Exception as e:
        print(f"    ⚠ select_team '{team_info['label']}' lỗi: {e}")
        return False


# ─── Table reader ────────────────────────────────────────────────────────────

def read_table(page):
    """
    Đọc bảng stats hiện tại.
    Trả về:
      headers: ["Player", "Position", "Rating", "Total shots", ...]
      rows:    [["Kane H.", "Striker", "7.9", "3", ...], ...]
    """
    headers = []
    rows    = []

    # ── Headers từ <thead> ────────────────────────────────────────────────────
    try:
        thead = page.locator('[data-testid="wcl-tableHead"]').first
        th_list = thead.locator("th").all()

        # th đầu tiên = cột player (thường rỗng hoặc tên đội)
        # → đổi thành "Player" và thêm "Position" ngay sau
        for i, th in enumerate(th_list):
            txt = th.inner_text().strip()
            if i == 0:
                headers.append("Player")
                headers.append("Position")   # thêm cột Position ở vị trí 2
            else:
                headers.append(txt if txt else f"Col{i}")
    except Exception:
        pass

    if not headers:
        headers = ["Player", "Position"]

    # ── Rows từ <tbody> ───────────────────────────────────────────────────────
    try:
        tbody = page.locator('[data-testid="wcl-tableBody"]').first
        for tr in tbody.locator('[data-testid="wcl-tableBodyRow"]').all():
            cells = []

            # --- Cột 1: Player name ---
            # --- Cột 2: Position    ---
            try:
                pc    = tr.locator('[data-testid="wcl-playerCell"]').first
                lines = [l.strip() for l in pc.inner_text().strip().split("\n") if l.strip()]
                cells.append(lines[0] if lines else "")       # Player
                cells.append(lines[1] if len(lines) > 1 else "")  # Position
            except Exception:
                try:
                    first_td = tr.locator('[data-testid="wcl-tableBodyCell"]').first
                    lines    = [l.strip() for l in first_td.inner_text().strip().split("\n") if l.strip()]
                    cells.append(lines[0] if lines else "")
                    cells.append(lines[1] if len(lines) > 1 else "")
                except Exception:
                    cells.extend(["", ""])

            # --- Cột 3+: Stat cells (bỏ td đầu tiên = player cell) ---
            try:
                stat_tds = tr.locator('[data-testid="wcl-tableBodyCell"]').all()
                for td in stat_tds[1:]:
                    txt = td.inner_text().strip()
                    cells.append(txt if txt else "-")
            except Exception:
                pass

            if any(c for c in cells if c not in ("", "-")):
                rows.append(cells)

    except Exception as e:
        print(f"      ⚠ read_table lỗi: {e}")

    # Fallback: đọc thẳng <table>
    if not rows:
        try:
            for i, tr in enumerate(page.locator('[data-testid="wcl-table"] tr').all()):
                texts = [td.inner_text().strip() for td in tr.locator("td, th").all()]
                if not any(texts):
                    continue
                if i == 0 and len(headers) == 0:
                    headers = ["Player", "Position"] + texts[1:]
                else:
                    rows.append(texts)
        except Exception:
            pass

    return headers, rows


def scrape_tab(page, base_url, tab, team_info):
    """Navigate đến tab, chọn filter team, đọc bảng."""
    url = build_tab_url(base_url, tab)
    page.goto(url, wait_until="domcontentloaded", timeout=30000)

    try:
        page.wait_for_selector('[data-testid="wcl-table"]', timeout=15000)
    except PlaywrightTimeout:
        return [], []

    time.sleep(1.5)

    ok = select_team(page, team_info)
    if not ok:
        print(f"      ⚠ Không filter được '{team_info['label']}'", end=" ")
    time.sleep(1.0)

    return read_table(page)


# ─── Excel writer ────────────────────────────────────────────────────────────

def write_sheet(wb, sheet_name, tab_label, headers, rows, match_info, hcolor):
    ws = wb.create_sheet(sheet_name)
    ws.sheet_view.showGridLines = False

    # Tiêu đề
    ws["A1"] = f"{match_info['home']} vs {match_info['away']}  |  {tab_label}"
    ws["A1"].font = Font(bold=True, size=13, color=COLOR_TITLE, name="Arial")
    ws.row_dimensions[1].height = 24

    ws["A2"] = f"{match_info.get('date', '')}  —  {sheet_name}"
    ws["A2"].font = Font(size=9, color="888888", name="Arial", italic=True)
    ws.row_dimensions[2].height = 16

    if not rows:
        ws["A4"] = "Không có dữ liệu"
        ws["A4"].font = Font(italic=True, color="999999", name="Arial")
        return

    # Header row (row 4)
    h_font   = Font(bold=True, color=COLOR_FG, name="Arial", size=10)
    h_fill   = PatternFill("solid", start_color=hcolor)
    h_align  = Alignment(horizontal="center", vertical="center", wrap_text=True)
    h_border = Border(
        bottom=Side(style="medium", color="FFFFFF"),
        right=Side(style="thin", color="FFFFFF"),
    )

    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=ci, value=h)
        cell.font = h_font; cell.fill = h_fill
        cell.alignment = h_align; cell.border = h_border
    ws.row_dimensions[4].height = 30

    # Data rows
    for ri, row_data in enumerate(rows, 5):
        fill   = PatternFill("solid", start_color=COLOR_ODD if ri % 2 else COLOR_EVEN)
        bdr    = Border(bottom=Side(style="thin", color="E0E0E0"),
                        right=Side(style="thin", color="E8E8E8"))
        for ci, val in enumerate(row_data, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.fill = fill
            cell.font = Font(name="Arial", size=10)
            # Cột 1 (Player) và cột 2 (Position) căn trái, còn lại căn giữa
            cell.alignment = Alignment(
                horizontal="left" if ci <= 2 else "center",
                vertical="center")
            cell.border = bdr

        # Pad nếu thiếu cột
        for ci in range(len(row_data) + 1, len(headers) + 1):
            cell = ws.cell(row=ri, column=ci, value="-")
            cell.fill = fill
            cell.font = Font(name="Arial", size=10, color="AAAAAA")
            cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.row_dimensions[ri].height = 20

    # Column widths
    for ci, h in enumerate(headers, 1):
        vals = [str(h)] + [str(r[ci-1]) if ci-1 < len(r) else "" for r in rows]
        ws.column_dimensions[get_column_letter(ci)].width = min(
            max(len(v) for v in vals) + 4, 35)

    ws.freeze_panes = "A5"
    if headers and rows:
        ws.auto_filter.ref = f"A4:{get_column_letter(len(headers))}{4+len(rows)}"


def write_excel(all_data, match_info, teams, output_path):
    wb = Workbook()
    wb.remove(wb.active)

    # Summary sheet
    ws = wb.create_sheet("Summary")
    ws.sheet_view.showGridLines = False
    ws["B2"] = f"{match_info['home']}  vs  {match_info['away']}"
    ws["B2"].font = Font(bold=True, size=16, color=COLOR_TITLE, name="Arial")
    ws["B3"] = match_info.get("date", "")
    ws["B3"].font = Font(size=11, color="666666", name="Arial")
    ws["B4"] = f"Home: {match_info['home']}  |  Away: {match_info['away']}"
    ws["B4"].font = Font(size=10, color="444444", name="Arial")
    ws["B6"] = f"Crawled: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws["B6"].font = Font(italic=True, size=9, color="999999", name="Arial")
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 55

    ri = 8
    team_colors = [COLOR_HOME, COLOR_AWAY]
    for ti, t in enumerate(teams):
        label_cell = ws.cell(ri, 2, f"▶ {t['label']}  ({t['full_text']})")
        label_cell.font = Font(bold=True, size=11, name="Arial",
                               color=team_colors[ti] if ti < 2 else "000000")
        ri += 1
        for tab in TABS:
            n = len(all_data.get(t["label"], {}).get(tab, ([], []))[1])
            ws.cell(ri, 2, f"    • {TAB_LABELS[tab]}: {n} cầu thủ").font = Font(size=10, name="Arial")
            ri += 1
        ri += 1

    # Data sheets: (team × tab)
    for ti, t in enumerate(teams):
        hcolor = team_colors[ti] if ti < 2 else COLOR_HOME
        for tab in TABS:
            headers, rows = all_data.get(t["label"], {}).get(tab, ([], []))
            sname = f"{t['label']} - {TAB_LABELS[tab]}"[:31]
            write_sheet(wb, sname, TAB_LABELS[tab], headers, rows, match_info, hcolor)

    wb.save(output_path)
    print(f"\n✅ Đã lưu: {output_path}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Flashscore Player Stats Scraper  v4")
    print("=" * 60)

    url = input("\nNhập link Flashscore match:\n> ").strip()
    if not url:
        url = "https://www.flashscore.com/match/football/england-j9N9ZNFA/new-zealand-rLctHkpU/summary/player-stats/top/"

    base_url   = normalize_match_url(url)
    all_data   = {}
    match_info = {"home": "Home", "away": "Away", "date": ""}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-GB",
        )
        page = ctx.new_page()
        page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())
        page.route("**/ads/**",       lambda r: r.abort())
        page.route("**/analytics/**", lambda r: r.abort())
        page.route("**/gtm/**",       lambda r: r.abort())

        # Load trang đầu
        print(f"\nBase URL: {base_url}")
        print("Đang load trang...")
        page.goto(build_tab_url(base_url, "top"), wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Cookie banner
        for sel in ["#onetrust-accept-btn-handler", "#didomi-notice-agree-button",
                    ".cookie-accept", "[data-testid='accept-cookies']"]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    btn.click(); time.sleep(0.5); break
            except Exception:
                pass

        match_info = extract_match_info(page)
        print(f"Trận: {match_info['home']} vs {match_info['away']}  ({match_info['date']})")

        # Detect teams (chỉ lấy 2 đội, bỏ ALL)
        print("\nĐang detect filter teams...")
        try:
            page.wait_for_selector('[data-testid="wcl-table"]', timeout=10000)
        except Exception:
            pass
        time.sleep(1)

        teams = detect_team_filters(page)
        print(f"Tìm thấy: {[t['full_text'] for t in teams]}")

        # Fallback nếu detect thất bại
        if len(teams) < 2:
            home_code = match_info["home"][:3].upper()
            away_code = match_info["away"][:3].upper()
            teams = [
                {"label": home_code, "full_text": match_info["home"]},
                {"label": away_code, "full_text": match_info["away"]},
            ]
            print(f"⚠ Dùng mặc định: {[t['label'] for t in teams]}")

        # Chỉ lấy 2 đội đầu (home + away)
        teams = teams[:2]
        total = len(teams) * len(TABS)
        done  = 0

        for team in teams:
            all_data[team["label"]] = {}
            print(f"\n── {team['full_text']} ({team['label']}) ──────────────────────")
            for tab in TABS:
                done += 1
                print(f"  [{done}/{total}] {TAB_LABELS[tab]} ...", end=" ", flush=True)
                try:
                    headers, rows = scrape_tab(page, base_url, tab, team)
                    all_data[team["label"]][tab] = (headers, rows)
                    print(f"✓ {len(rows)} cầu thủ, {len(headers)} cột")
                except Exception as e:
                    print(f"✗ {e}")
                    all_data[team["label"]][tab] = ([], [])

        browser.close()

    home  = re.sub(r"[^\w]", "_", match_info["home"])[:15]
    away  = re.sub(r"[^\w]", "_", match_info["away"])[:15]
    ts    = datetime.now().strftime("%Y%m%d_%H%M")
    fname = f"flashscore_{home}_vs_{away}_{ts}.xlsx"
    out   = str(Path.home() / "Downloads" / fname)

    write_excel(all_data, match_info, teams, out)
    print(f"File: {out}")


if __name__ == "__main__":
    main()
