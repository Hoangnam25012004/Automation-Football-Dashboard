"""Chạy crawler bằng tay:  python -m crawler <link trận Flashscore> [--out result.json]"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .errors import CrawlError
from .run import crawl


def _summary(result: dict) -> list[str]:
    stats = result["stats"]
    lines = [f"Trận: {stats['matchTitle']}  ({stats['home']} / {stats['away']})"]
    for code in (stats["home"], stats["away"]):
        counts = ", ".join(f"{tab} {len(td['rows'])}" for tab, td in stats["teams"][code].items())
        lines.append(f"  {code}: {counts}")
    summary = result["summary"] or {}
    events = summary.get("events") or []
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    lines.append(f"Timeline: {len(events)} sự kiện {by_type}  · logo: "
                 f"{'✓' if summary.get('homeLogo') else '✗'}/{'✓' if summary.get('awayLogo') else '✗'}")
    lu = result["lineups"]
    if lu:
        xi = lu.get("starting_xi") or []
        bench = lu.get("substitutes") or []
        subs = lu.get("substituted") or {}
        fm = lu.get("formation") or {}
        coaches = lu.get("coaches") or {}
        lines.append(f"Lineups: đá chính {len(xi)} hàng · dự bị {len(bench)} hàng · thay người "
                     f"{len(subs.get('home', []))}+{len(subs.get('away', []))} · sơ đồ {len(fm.get('players', []))} cầu thủ · "
                     f"HLV {coaches.get('home', {}).get('name', '—')} / {coaches.get('away', {}).get('name', '—')}")
    else:
        lines.append("Lineups: không có")
    for w in result["warnings"]:
        lines.append(f"⚠ {w['code']}: {w['message']}" + (f" ({w['detail']})" if w.get("detail") else ""))
    return lines


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m crawler",
                                 description="Crawl một trận Flashscore → JSON (cùng định dạng với API của server.py).")
    ap.add_argument("url", help="link trận, vd https://www.flashscore.com/match/football/<home>/<away>/?mid=<id>")
    ap.add_argument("--out", help="ghi kết quả JSON ra file")
    args = ap.parse_args()

    t0 = time.monotonic()
    try:
        result = crawl(args.url, progress=lambda p: print(f"[{p['done']}/{p['total']}] {p['message']}", flush=True))
    except CrawlError as exc:
        print(f"✗ {exc.code}: {exc.message} — {exc.hint}")
        return 2
    print(f"✓ Xong sau {time.monotonic() - t0:.1f} s")
    print("\n".join(_summary(result)))
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Đã ghi {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
