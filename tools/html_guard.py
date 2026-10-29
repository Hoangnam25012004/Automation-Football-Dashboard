"""Bảo vệ match_report.html khỏi thay đổi ngoài phạm vi.

Cấu hình hiện tại: thiết kế lại dashboard (design doc dashboard-redesign §10). Baseline = tag git
`redesign-baseline` (commit mốc sau Phase 0–5 của luồng URL); cấu hình E1–E14 cũ (so với root commit)
nằm trong lịch sử git.

Hai lớp kiểm tra, cả hai so file hiện tại với baseline trong git:

1. Vùng đóng băng (frozen regions): mỗi vùng xác định bằng chuỗi mở/đóng, so SHA-256.
2. Diff-budget: mọi khối thay đổi phải nằm trong một "cửa sổ" được phép RD1–RD8 (RD8: cloud design §11).

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
BASELINE_TAG = "redesign-baseline"

# RD7: hai dòng duy nhất được thêm vào App (luồng URL mang theo teamStats/meta; reset xoá chúng).
RD7_BUILD = "      state.teamStats=res.teamStats||null; state.meta=res.meta||null;   // schemaVersion 2 (redesign §3.4)\n"
RD7_RESET = "    state.teamStats=null; state.meta=null;\n"


def _replace(old: str, new: str):
    return lambda text: text.replace(old, new)


@dataclass(frozen=True)
class Region:
    name: str
    start: str          # chuỗi mở (bao gồm)
    end: str            # chuỗi đóng (bao gồm), tìm sau chuỗi mở
    edits: tuple = ()   # các sửa đổi đã duyệt bên trong vùng — áp cho cả baseline lẫn hiện tại trước khi so


FROZEN_REGIONS = [
    Region("head + CDN scripts", "<!DOCTYPE html>", "<style>\n"),
    Region("màn hình nhập URL", "<!-- ============ UPLOAD SCREEN ============ -->", "</section>"),
    Region("loading overlay + toast", '<div class="loading-overlay" id="loading">', '<div class="toast" id="toast"></div>'),
    Region("demo data", '<script id="demoData">', "\n</script>"),
    Region("core: state / TABS / U / ô URL / Api / App", "const state = {",
           "document.addEventListener('DOMContentLoaded',setupUrlForm);",
           (_replace(RD7_BUILD, ""), _replace(RD7_RESET, ""))),
    Region("LineupOCR", "const LineupOCR = (()=>{", "  return { run, loadingHTML };\n})();"),
]


# Cửa sổ được phép sửa trong baseline (design doc dashboard-redesign §10.1). Mỗi cửa sổ là một dải dòng
# [đầu, cuối] (0-based, bao gồm) tìm bằng chuỗi đánh dấu; "insert_only" = chỉ được chèn trước dòng đầu.
@dataclass(frozen=True)
class Window:
    eid: str
    first: str                 # dòng đầu chứa chuỗi này
    last: str | None = None    # dòng cuối chứa chuỗi này (None = cùng dòng đầu)
    last_offset: int = 0       # lùi/tiến dòng cuối (vd -1 = dòng trước dòng đánh dấu)
    insert_only: bool = False  # chỉ cho phép chèn ngay trước dòng `first`
    first_offset: int = 0      # lùi/tiến dòng đầu


EDIT_WINDOWS = [
    Window("RD1", "<style>", "</style>"),                                                      # CSS
    Window("RD5", "<!-- ============ HEADER ============ -->", "<!-- ============ UPLOAD SCREEN", last_offset=-1),
    Window("RD4", "<!-- ============ DASHBOARD ============ -->", "</main>"),                  # markup dashboard
    Window("RD2", "APP — Render module", "return { scorebar, tabs, activeTab, _names:TEAM_FULL };",
           first_offset=-1, last_offset=1),                                                   # Render → Views…
    Window("RD3", "APP — PDF Exporter", "  return { run };", first_offset=-1, last_offset=1),  # Exporter → Report
    Window("RD7", "state.lineupText=res.lineups||null;", insert_only=True, first_offset=1),
    Window("RD7", "state.lineupImages={}; state.lineupText=null; state.summary=null;", insert_only=True, first_offset=1),
    # RD8 (cloud design §11, Q-E a): khối <script> "cloud mode" chèn ngay trước </body>, không sửa dòng cũ nào
    Window("RD8", "</body>", first_offset=-2),   # -2: difflib có thể gióng khối chèn trước </script> của khối Report
]


def utf8_stdout() -> None:
    """Console Windows/pipe mặc định cp1252 — in tiếng Việt và ✓/✗ sẽ lỗi nếu không đổi."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True).stdout


def baseline_rev() -> str:
    """Tag `redesign-baseline` (commit mốc trước khi thiết kế lại dashboard)."""
    return git("rev-parse", BASELINE_TAG + "^{commit}").decode().strip()


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
