"""Bảo vệ match_report.html khỏi thay đổi ngoài phạm vi (design doc §7.1, §9.2).

Hai lớp kiểm tra, cả hai so file hiện tại với bản baseline trong git (root commit):

1. Vùng đóng băng (frozen regions): mỗi vùng xác định bằng chuỗi mở/đóng, so SHA-256.
2. Diff-budget: mọi khối thay đổi phải nằm trong một "cửa sổ" được phép E1–E7.

Dùng chuỗi đánh dấu thay vì số dòng để chịu được việc dịch dòng sau khi sửa.
"""
from __future__ import annotations

import difflib
import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML_NAME = "match_report.html"

# Dòng E7 (chuỗi empty-state duy nhất được phép đổi bên trong Render).
E7_OLD = "          <div>Add the <strong>lineups</strong> export to see formation, line-ups and substitutions here.</div>"
E7_NEW = "          <div>Line-ups are not available for this match.</div>"


def _replace(old: str, new: str):
    return lambda text: text.replace(old, new)


def _cut(start: str, end: str):
    """Bỏ đoạn từ `start` tới hết `end` (nếu có) — mô phỏng một lần gỡ code đã được duyệt."""
    def apply(text: str) -> str:
        i = text.find(start)
        if i < 0:
            return text
        j = text.find(end, i)
        return text if j < 0 else text[:i] + text[j + len(end):]
    return apply


@dataclass(frozen=True)
class Region:
    name: str
    start: str          # chuỗi mở (bao gồm)
    end: str            # chuỗi đóng (bao gồm), tìm sau chuỗi mở
    edits: tuple = ()   # các sửa đổi đã duyệt bên trong vùng — áp cho cả baseline lẫn hiện tại trước khi so


FROZEN_REGIONS = [
    Region("head + CDN scripts", "<!DOCTYPE html>", "<style>\n:root{",
           (_replace('<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>\n', ""),)),
    Region("CSS hiện có", "<style>\n:root{",
           ".pdf-rendering .tab-content{display:block !important;page-break-after:always}\n",
           (_cut(".drop-grid{display:grid;", ".drop-zone.loaded .tag{color:var(--good)}\n\n"),)),
    Region("header HTML", "<!-- ============ HEADER ============ -->",
           '<section class="upload-screen" id="uploadScreen">'),
    Region("upload hero (kicker + h2)", '<div class="upload-hero">',
           "<h2>Turn match data into<br><em>tactical insight</em></h2>"),
    Region("nút demo", '<button class="demo-link" onclick="App.loadDemo()">',
           "or explore with sample data (Korea vs Czech Republic)</button>"),
    Region("dashboard + overlay + toast", "<!-- ============ DASHBOARD ============ -->",
           '<div class="toast" id="toast"></div>',
           (_replace("Data from Flashscore exports ·", "Data from Flashscore ·"),)),
    Region("demo data", '<script id="demoData">', "\n</script>"),
    Region("state / TABS / U / UI helpers", "const state = {",
           "function destroyCharts(){Object.values(state.charts).forEach(c=>{try{c.destroy()}catch(e){}});state.charts={};}",
           (_replace("  statsFile:null, lineupFile:null, summaryFile:null,\n", ""),
            _replace("from summary_*.xlsx", "from the crawler (server.py)"))),
    Region("App.loadDemo + enter", "  async loadDemo(){",
           "    hideLoading(); window.scrollTo(0,0);\n  },"),
    Region("App.setTeam / setTab / exportPDF", "  setTeam(team){",
           "  async exportPDF(){ await Exporter.run(); },\n};"),
    Region("LineupOCR", "const LineupOCR = (()=>{", "  return { run, loadingHTML };\n})();"),
    Region("Render (trừ dòng E7)", "const Render = (()=>{",
           "  return { scorebar, tabs, activeTab, _names:TEAM_FULL };\n})();", (_replace(E7_OLD, E7_NEW),)),
    Region("Exporter (trừ chữ chân trang PDF)", "const Exporter = (()=>{", "  return { run };\n})();",
           (_replace("data from Flashscore exports'", "data from Flashscore'"),)),
    Region("đuôi file", "  return { run };\n})();\n\n</script>", "</html>\n"),
]
# Phase 5 (đã duyệt 2026-10-13) gỡ hẳn: JSZipLite và parser xlsx ⇒ không còn là vùng đóng băng.


# Cửa sổ được phép sửa trong baseline (design doc §7.1). Mỗi cửa sổ là một dải dòng
# [đầu, cuối] (0-based, bao gồm) tìm bằng chuỗi đánh dấu; "insert_only" = chỉ được chèn.
@dataclass(frozen=True)
class Window:
    eid: str
    first: str                 # dòng đầu chứa chuỗi này
    last: str | None = None    # dòng cuối chứa chuỗi này (None = cùng dòng đầu)
    last_offset: int = 0       # lùi/tiến dòng cuối (vd -1 = dòng trước dòng đánh dấu)
    insert_only: bool = False  # chỉ cho phép chèn ngay trước dòng `first`
    first_offset: int = 0      # lùi/tiến dòng đầu


EDIT_WINDOWS = [
    # Phase 3 (luồng URL)
    Window("E1", "<p>Drop in your two Flashscore exports"),
    Window("E2", '<div class="drop-grid">', '<div class="upload-cta">', last_offset=-1),
    Window("E2", 'id="btnBuild"'),
    Window("E3", "</style>", insert_only=True),
    Window("E4", "/* ---------- dropzones ---------- */",
           "/* ---------- build / reset / navigation ---------- */", last_offset=-1),
    Window("E4", "document.addEventListener('DOMContentLoaded',setupDropzones);"),
    Window("E5", "  async build(){", "  async loadDemo(){", last_offset=-1),
    Window("E6", "document.querySelectorAll('.drop-zone')", "document.getElementById('btnBuild').disabled=true;"),
    Window("E7", "Add the <strong>lineups</strong> export"),
    # Phase 5 (dọn mã mồ côi + chữ chân trang)
    Window("E8", "ajax/libs/xlsx/0.18.5/xlsx.full.min.js"),
    Window("E9", ".drop-grid{display:grid;", ".upload-cta{text-align:center}", last_offset=-1),
    Window("E10", "JSZipLite — minimal ZIP reader", "  return { load:loadPrimed };", first_offset=-2, last_offset=5),  # +2: <script> + "/* ===" của khối sau (difflib căn lệch)
    Window("E11", "APP — core: state, parsing, file handling, navigation"),
    Window("E11", "statsFile:null, lineupFile:null, summaryFile:null,"),
    Window("E11", "from summary_*.xlsx"),
    Window("E11", "/* ---------- stats workbook parsing ---------- */", "/* ---------- dropzones ---------- */", last_offset=-1),
    Window("E12", "state.statsFile=state.lineupFile=state.summaryFile=state.data=null;"),
    Window("E13", "Data from Flashscore exports · <span"),
    Window("E14", "data from Flashscore exports',pageW"),
]


def utf8_stdout() -> None:
    """Console Windows/pipe mặc định cp1252 — in tiếng Việt và ✓/✗ sẽ lỗi nếu không đổi."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True).stdout


def baseline_rev() -> str:
    """Root commit = baseline đã commit ở Phase 0.1."""
    return git("rev-list", "--max-parents=0", "HEAD").decode().split()[0]


def load_baseline(rev: str | None = None) -> str:
    return git("show", f"{rev or baseline_rev()}:{HTML_NAME}").decode("utf-8")


def load_current() -> str:
    return (ROOT / HTML_NAME).read_bytes().decode("utf-8")


def extract(text: str, region: Region) -> str | None:
    i = text.find(region.start)
    if i < 0:
        return None
    j = text.find(region.end, i + len(region.start))
    if j < 0:
        return None
    chunk = text[i:j + len(region.end)]
    for edit in region.edits:
        chunk = edit(chunk)
    return chunk


def sha(text: str | None) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else "(không tìm thấy)"


def check_frozen(base: str, cur: str) -> list[tuple[str, bool, str]]:
    out = []
    for region in FROZEN_REGIONS:
        b, c = extract(base, region), extract(cur, region)
        if b is None:
            out.append((region.name, False, "không tìm thấy vùng trong BASELINE (định nghĩa sai)"))
        elif c is None:
            out.append((region.name, False, "không tìm thấy chuỗi đánh dấu trong file hiện tại"))
        else:
            ok = b == c
            out.append((region.name, ok, f"{len(b)} ký tự" if ok else f"KHÁC: baseline {sha(b)[:12]} ≠ hiện tại {sha(c)[:12]}"))
    return out


def _line_index(lines: list[str], needle: str, start: int = 0) -> int:
    for k in range(start, len(lines)):
        if needle in lines[k]:
            return k
    raise ValueError(f"không tìm thấy dòng chứa: {needle!r}")


def resolve_windows(base_lines: list[str]) -> list[tuple[str, int, int, bool]]:
    """→ [(eid, đầu, cuối, insert_only)] theo chỉ số dòng 0-based của baseline."""
    out = []
    for w in EDIT_WINDOWS:
        a = _line_index(base_lines, w.first) + w.first_offset
        if w.insert_only:
            out.append((w.eid, a, a, True))
            continue
        b = a if w.last is None else _line_index(base_lines, w.last, a - w.first_offset) + w.last_offset
        out.append((w.eid, a, b, False))
    return out


@dataclass
class Hunk:
    tag: str
    i1: int
    i2: int
    j1: int
    j2: int
    eid: str | None
    removed: list[str]
    added: list[str]


def diff_budget(base: str, cur: str) -> tuple[bool, list[Hunk]]:
    a, b = base.split("\n"), cur.split("\n")
    windows = resolve_windows(a)
    hunks: list[Hunk] = []
    ok = True
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        eid = None
        if tag == "insert":
            for wid, first, last, insert_only in windows:
                if (insert_only and i1 == first) or (not insert_only and first <= i1 <= last + 1):
                    eid = wid
                    break
        else:
            # Mọi dòng baseline bị sửa/xoá phải nằm trong một cửa sổ được phép (khối có thể trải qua
            # nhiều cửa sổ liền kề, vd E11 + E4) hoặc là dòng trống ở biên.
            ids = []
            for k in range(i1, i2):
                covering = [wid for wid, first, last, insert_only in windows if not insert_only and first <= k <= last]
                if covering:
                    ids.append(covering[0])
                elif a[k].strip():
                    ids = None
                    break
            if ids:
                eid = "+".join(dict.fromkeys(ids))
            elif ids is not None and not any(x.strip() for x in b[j1:j2]):
                eid = "(chỉ dòng trống)"
        if eid is None:
            ok = False
        hunks.append(Hunk(tag, i1, i2, j1, j2, eid, a[i1:i2], b[j1:j2]))
    return ok, hunks
