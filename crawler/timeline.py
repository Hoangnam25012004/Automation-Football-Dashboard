"""Timeline sự kiện của trận (design doc §6.5, extractor tham chiếu ở Phụ lục D.1).

Khác JS_EXTRACT của flashscore_summary.py: các hàng sự kiện nay nằm trong
<ol class="smv__period-list" aria-label="1st Half">, nên duyệt từng <li> thay vì root.children.
Nhãn `type` giữ bộ nhãn cũ vì Render của web so khớp bằng regex trên các nhãn này; thêm
"Penalty missed" (trước đây rơi vào "Card"). Hàng của loạt luân lưu (period "Penalties") bị bỏ:
ô thời gian của chúng là thứ tự lượt sút, đưa vào sẽ thành marker sai ở phút 1–7.
Tín hiệu icon đã kiểm chứng (10/2026): goal-soccer, footballOwnGoal-ico, penalty-goal, penalty-missed,
yellowCard-ico, redCard-ico, red-card-second, substitution, var.
"""
from __future__ import annotations

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .header import MatchInfo

JS_TIMELINE = r"""() => {
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
    if (half === 'Penalties') continue;     // loạt luân lưu: ô thời gian là thứ tự lượt sút, không phải phút
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
      if (/owngoal/.test(sig) || /own goal/.test(lower)) type = 'Own goal';
      else if (/penalty-goal/.test(sig) || /penalt/.test(lower)) type = 'Penalty goal';
      else type = 'Goal';
      const ass = (assistEl && T(assistEl)) || parens.find(p => !/own goal|penalt/i.test(p)) || '';
      detail = ass.replace(/^\(|\)$/g, '').trim();
    } else if (isSub) {
      type = 'Substitution';
      if (names[1]) detail = 'Out: ' + names[1];
    } else if (/penalty-missed/.test(sig) || /penalty missed/.test(lower)) {
      type = 'Penalty missed';
    } else if (/\bvar\b/.test(sig)) {
      // VAR: quyết định là chữ thường của hàng ("Goal Disallowed - offside"), cầu thủ nằm trong khối smv__assist
      type = 'VAR';
      const who = assistEl ? T(assistEl) : '';
      if (!player) player = who.replace(/^\(|\)$/g, '').trim();
      detail = (who ? body.replace(who, '') : body).replace(/\s+/g, ' ').trim();
    } else {
      if (/yellowred|red-card-second/.test(sig)) type = 'Second yellow (→ red)';
      else if (/redcard|red-card/.test(sig)) type = 'Red card';
      else if (/yellowcard|yellow-card/.test(sig)) type = 'Yellow card';
      else type = 'Card';
      detail = (reasonEl ? T(reasonEl) : (parens[0] || '')).replace(/^\(|\)$/g, '').trim();
    }
    if (!player && !minute) continue;
    events.push({ half, minute, side, type, player, detail, score });
  }
  return { rows: rows.length, events };
}"""

GOAL_TYPES = {"Goal", "Penalty goal", "Own goal"}


def read_timeline(page, info: MatchInfo) -> tuple[list[dict], int]:
    """→ (sự kiện theo đúng 8 khoá của sheet Timeline cũ, số hàng sự kiện tìm thấy trong DOM)."""
    try:
        page.wait_for_selector(".smv__verticalSections", timeout=8_000)
    except PlaywrightTimeout:
        return [], 0
    raw = page.evaluate(JS_TIMELINE)
    events = []
    for ev in raw["events"]:
        team = info.home if ev["side"] == "home" else info.away if ev["side"] == "away" else ""
        events.append({"minute": ev["minute"], "half": ev["half"], "side": ev["side"], "team": team,
                       "type": ev["type"], "player": ev["player"], "detail": ev["detail"], "score": ev["score"]})
    return events, raw["rows"]
