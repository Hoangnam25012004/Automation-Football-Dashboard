"""Ghép kết quả theo hợp đồng dữ liệu (design doc §5.1) + kiểm tra chéo (§6.7).

Kiểm tra chéo chỉ sinh cảnh báo, không bao giờ làm hỏng kết quả.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .errors import Warnings
from .header import MatchInfo
from .lineups import lineup_images
from .player_stats import StatsResult
from .timeline import GOAL_TYPES
from .urls import MatchRef

SCHEMA_VERSION = 1
_FRACTION = re.compile(r"^\s*(\d+)\s*/\s*(\d+)")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _num(value) -> float:
    """Cùng cách hiểu số với U.num của web: "-"/rỗng = 0, phân số "a/b (x%)" = a."""
    text = str(value or "").strip()
    if text in ("", "-"):
        return 0.0
    m = _FRACTION.match(text)
    if m:
        return float(m.group(1))
    m = _NUMBER.search(text.replace(",", ""))
    return float(m.group()) if m else 0.0


def _team_sum(stats: StatsResult, code: str, tab: str, column: str) -> float:
    rows = stats.teams.get(code, {}).get(tab, {}).get("rows", [])
    return sum(_num(r.get(column)) for r in rows)


def assemble(ref: MatchRef, info: MatchInfo, stats: StatsResult, events: list[dict], timeline_rows: int,
             logos: tuple[str | None, str | None], lineups: dict | None, warnings: Warnings) -> dict:
    h, a = info.score_home, info.score_away

    # Kiểm tra chéo 1: bàn thắng trong timeline = tỉ số header.
    if h is not None and a is not None:
        goals = sum(1 for e in events if e["type"] in GOAL_TYPES)
        if timeline_rows == 0 and h + a > 0:
            warnings.add("W_TIMELINE_EMPTY")
        elif timeline_rows and goals != h + a:
            warnings.add("W_TIMELINE_SCORE_MISMATCH", f"timeline {goals} goals, score {h}-{a}")

        # Kiểm tra chéo 2: Σ Goals(đội) + Σ Own goals(đối thủ) = tỉ số (công thức của Render.scorebar).
        hg = _team_sum(stats, stats.home, "General", "Goals") + _team_sum(stats, stats.away, "General", "Own goals")
        ag = _team_sum(stats, stats.away, "General", "Goals") + _team_sum(stats, stats.home, "General", "Own goals")
        if (int(hg), int(ag)) != (h, a):
            warnings.add("W_SCORE_MISMATCH", f"player stats {int(hg)}-{int(ag)}, score {h}-{a}")

    home_logo, away_logo = logos
    summary = None
    if events or home_logo or away_logo:
        summary = {"events": events, "homeLogo": home_logo, "awayLogo": away_logo,
                   "finalScore": {"h": h, "a": a} if h is not None and a is not None else None}

    return {
        "schemaVersion": SCHEMA_VERSION,
        "matchId": ref.mid or "",
        "sourceUrl": ref.url(),
        "fetchedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "stats": {
            "matchTitle": f"{info.home}  vs  {info.away}",    # 2 dấu cách như sheet Summary của luồng cũ
            "matchDate": "",                                     # C3: để rỗng như luồng cũ
            "home": stats.home,
            "away": stats.away,
            "teams": stats.teams,
        },
        "summary": summary,
        "lineups": lineups,
        "lineupImages": lineup_images(lineups),
        "warnings": warnings.items,
    }
