"""
FCU Bid Scanner — HTML dashboard generator
Renders a full interactive bid dashboard matching the FCU design system.
"""

import os
import re
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Score + Trade helpers
# ---------------------------------------------------------------------------

TRADE_RULES = [
    (["carpet"], "Carpet"),
    (["window covering", "blinds", "shades", "curtain", "shade"], "Window Coverings"),
    (["resilient", "lvt", "vct", "vinyl plank", "vinyl tile"], "Resilient Flooring"),
    (["tile", "ceramic", "porcelain"], "Tile"),
    (["epoxy"], "Epoxy Flooring"),
    (["hardwood", "wood floor"], "Wood Flooring"),
    (["flooring", "floor covering", "floor installation", "floor replacement"], "Flooring"),
]


def detect_trade(title: str, keyword: str = "") -> str:
    text = (title + " " + keyword).lower()
    for keywords, trade in TRADE_RULES:
        if any(k in text for k in keywords):
            return trade
    return "Flooring / Coverings"


def calculate_score(bid: dict) -> int:
    score = 40

    # Relevance
    if bid.get("is_relevant"):
        score += 20

    # Urgency
    days = _days_until(bid.get("due_date"))
    if days is not None:
        if 0 <= days <= 3:
            score += 20
        elif 0 <= days <= 7:
            score += 15
        elif 0 <= days <= 14:
            score += 10
        elif days < 0:
            score -= 20  # past due

    # High-value agency keywords
    title_low = bid.get("title", "").lower()
    if any(k in title_low for k in ["lausd", "los angeles unified", "la unified", "county of los angeles"]):
        score += 10
    elif any(k in title_low for k in ["los angeles", "long beach", "pasadena", "glendale", "burbank"]):
        score += 5

    return max(0, min(99, score))


def _days_until(d) -> int | None:
    if not d:
        return None
    return (d - date.today()).days


def _score_color(score: int) -> str:
    if score >= 70:
        return "#c9a84c"   # gold
    elif score >= 55:
        return "#e8a030"   # amber
    elif score >= 40:
        return "#8e8e93"   # gray
    else:
        return "#636366"   # dim


# ---------------------------------------------------------------------------
# Dashboard HTML template
# ---------------------------------------------------------------------------

TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FCU Bid Dashboard — {scan_date}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --charcoal: #1a1a1a;
  --charcoal-light: #2a2a2a;
  --charcoal-mid: #3a3a3a;
  --gold: #c9a84c;
  --gold-dim: #b8963a;
  --cream: #f5f0e8;
  --cream-dark: #e4ddd0;
  --white: #ffffff;
  --green: #34c759;
  --red: #ff3b30;
  --blue: #007aff;
  --blue-dim: rgba(0,122,255,0.12);
  --gray: #8e8e93;
  --gray-light: #c7c7cc;
  --font: 'Plus Jakarta Sans', -apple-system, sans-serif;
  --mono: 'IBM Plex Mono', monospace;
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  font-family: var(--font);
  background: var(--cream);
  color: var(--charcoal);
  min-height: 100vh;
  font-size: 14px;
}}

/* ── Header ── */
.header {{
  background: var(--charcoal);
  color: var(--cream);
  padding: 0 28px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
}}
.header-brand {{
  display: flex;
  align-items: center;
  gap: 10px;
}}
.header-logo {{
  width: 30px;
  height: 30px;
  background: var(--gold);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12px;
  color: var(--charcoal);
  letter-spacing: -0.3px;
  flex-shrink: 0;
}}
.header-title {{
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.3px;
}}
.header-count {{
  font-family: var(--mono);
  font-size: 12px;
  color: var(--gray);
}}

/* ── Stats row ── */
.stats {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border-bottom: 1px solid var(--cream-dark);
  background: var(--white);
}}
.stat-box {{
  padding: 20px 24px;
  border-right: 1px solid var(--cream-dark);
}}
.stat-box:last-child {{ border-right: none; }}
.stat-num {{
  font-size: 36px;
  font-weight: 700;
  letter-spacing: -1.5px;
  line-height: 1;
  margin-bottom: 4px;
  color: var(--charcoal);
}}
.stat-label {{
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--gray);
  font-family: var(--mono);
}}

/* ── Filter bar ── */
.filters {{
  background: var(--white);
  border-bottom: 1px solid var(--cream-dark);
  padding: 12px 28px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}}
.filter-search {{
  flex: 1;
  min-width: 200px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--cream);
  border: 1px solid var(--cream-dark);
  padding: 8px 12px;
}}
.filter-search svg {{
  flex-shrink: 0;
  opacity: 0.4;
}}
.filter-search input {{
  border: none;
  background: transparent;
  font-family: var(--font);
  font-size: 13px;
  color: var(--charcoal);
  outline: none;
  width: 100%;
}}
.filter-search input::placeholder {{ color: var(--gray); }}
.filter-label {{
  font-size: 12px;
  font-weight: 600;
  color: var(--gray);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  font-family: var(--mono);
  white-space: nowrap;
}}
.filter-select {{
  border: 1px solid var(--cream-dark);
  background: var(--cream);
  font-family: var(--font);
  font-size: 13px;
  color: var(--charcoal);
  padding: 8px 28px 8px 12px;
  outline: none;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%238e8e93'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
}}

/* ── Tab bar ── */
.tabs {{
  background: var(--white);
  border-bottom: 1px solid var(--cream-dark);
  padding: 0 28px;
  display: flex;
  gap: 0;
}}
.tab {{
  padding: 12px 20px;
  font-size: 13px;
  font-weight: 600;
  color: var(--gray);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  white-space: nowrap;
  user-select: none;
}}
.tab.active {{
  color: var(--charcoal);
  border-bottom-color: var(--charcoal);
}}

/* ── Table ── */
.table-wrap {{
  overflow-x: auto;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  background: var(--white);
  min-width: 900px;
}}
thead tr {{
  background: var(--charcoal);
  color: var(--cream);
}}
th {{
  padding: 10px 16px;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
}}
th:hover {{ color: var(--gold); }}
th.sorted {{ color: var(--gold); }}
th .sort-arrow {{ margin-left: 4px; opacity: 0.5; }}
th.sorted .sort-arrow {{ opacity: 1; }}

td {{
  padding: 13px 16px;
  border-bottom: 1px solid var(--cream-dark);
  vertical-align: middle;
}}
tr:hover td {{ background: rgba(201,168,76,0.04); }}
tr.hidden {{ display: none; }}

/* ── Score badge ── */
.score-badge {{
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 500;
  color: var(--white);
  flex-shrink: 0;
}}

/* ── Bid/Agency cell ── */
.bid-title {{
  font-size: 14px;
  font-weight: 600;
  color: var(--charcoal);
  line-height: 1.3;
  margin-bottom: 3px;
}}
.bid-agency {{
  font-family: var(--mono);
  font-size: 11px;
  color: var(--gray);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}}

/* ── Due date ── */
.due-normal {{ color: var(--charcoal); font-family: var(--mono); font-size: 12px; }}
.due-soon {{ color: #e8a030; font-family: var(--mono); font-size: 12px; font-weight: 500; }}
.due-urgent {{ color: var(--red); font-family: var(--mono); font-size: 12px; font-weight: 500; }}
.due-expired {{ color: var(--gray); font-family: var(--mono); font-size: 12px; text-decoration: line-through; }}

/* ── Status badge ── */
.badge {{
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  white-space: nowrap;
}}
.badge-new {{ background: var(--blue-dim); color: var(--blue); }}
.badge-soon {{ background: rgba(255,59,48,0.1); color: var(--red); }}

/* ── Source tag ── */
.source-tag {{
  font-family: var(--mono);
  font-size: 11px;
  color: var(--blue);
  white-space: nowrap;
}}

/* ── Trade tag ── */
.trade-tag {{
  font-size: 12px;
  color: var(--gray);
  white-space: nowrap;
}}
.trade-tag.flooring {{ color: var(--gold-dim); font-weight: 500; }}

/* ── Empty state ── */
.empty-row td {{
  text-align: center;
  padding: 48px;
  color: var(--gray);
  font-size: 14px;
  font-family: var(--mono);
}}

/* ── Footer ── */
.footer {{
  padding: 20px 28px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--gray-light);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  border-top: 1px solid var(--cream-dark);
}}

@media (max-width: 768px) {{
  .stats {{ grid-template-columns: repeat(2, 1fr); }}
  .header {{ padding: 0 16px; }}
  .filters {{ padding: 10px 16px; }}
  .tabs {{ padding: 0 16px; }}
}}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div class="header-brand">
    <div class="header-logo">FCU</div>
    <span class="header-title">Bid Dashboard</span>
  </div>
  <span class="header-count" id="display-count">{total_bids} of {total_bids} bids</span>
</div>

<!-- Stats -->
<div class="stats">
  <div class="stat-box">
    <div class="stat-num">{total_bids}</div>
    <div class="stat-label">Total Bids</div>
  </div>
  <div class="stat-box">
    <div class="stat-num">{new_count}</div>
    <div class="stat-label">New</div>
  </div>
  <div class="stat-box">
    <div class="stat-num">{due_7_count}</div>
    <div class="stat-label">Due in 7 Days</div>
  </div>
  <div class="stat-box">
    <div class="stat-num">{relevant_count}</div>
    <div class="stat-label">Flooring Relevant</div>
  </div>
</div>

<!-- Filters -->
<div class="filters">
  <span class="filter-label">Search</span>
  <div class="filter-search">
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <circle cx="6" cy="6" r="5" stroke="#1a1a1a" stroke-width="1.5"/>
      <path d="M10 10l3 3" stroke="#1a1a1a" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
    <input type="text" id="search-input" placeholder="title, agency, trade..." oninput="applyFilters()">
  </div>
  <span class="filter-label">Trade</span>
  <select class="filter-select" id="trade-filter" onchange="applyFilters()">
    <option value="">All Trades</option>
    {trade_options}
  </select>
  <span class="filter-label">Due</span>
  <select class="filter-select" id="due-filter" onchange="applyFilters()">
    <option value="">Any Date</option>
    <option value="7">Next 7 days</option>
    <option value="14">Next 14 days</option>
    <option value="30">Next 30 days</option>
  </select>
  <span class="filter-label">Source</span>
  <select class="filter-select" id="source-filter" onchange="applyFilters()">
    <option value="">All Sources</option>
    <option value="bidnet direct">BidNet Direct</option>
    <option value="sam.gov">SAM.gov</option>
    <option value="planetbids">PlanetBids</option>
    <option value="cal eprocure">Cal eProcure</option>
    <option value="opengov">OpenGov</option>
    <option value="bid locker">Bid Locker</option>
    <option value="quality bidders">Quality Bidders</option>
    <option value="socal plan room">SoCal Plan Room</option>
    <option value="crisp plan room">Crisp Plan Room</option>
    <option value="caltrans ccop">Caltrans CCOP</option>
  </select>
</div>

<!-- Tabs -->
<div class="tabs">
  <div class="tab active" data-tab="all" onclick="switchTab(this)">All (<span class="tab-count-all">{total_bids}</span>)</div>
  <div class="tab" data-tab="flooring" onclick="switchTab(this)">Flooring (<span class="tab-count-flooring">{relevant_count}</span>)</div>
  <div class="tab" data-tab="expiring" onclick="switchTab(this)">Expiring Soon (<span id="tab-count-expiring">{due_7_count}</span>)</div>
</div>

<!-- Table -->
<div class="table-wrap">
<table id="bids-table">
  <thead>
    <tr>
      <th style="width:52px;" onclick="sortTable('score')">SCORE <span class="sort-arrow">↕</span></th>
      <th onclick="sortTable('title')">BID / AGENCY <span class="sort-arrow">↕</span></th>
      <th style="width:60px;">STATE</th>
      <th style="width:160px;" onclick="sortTable('trade')">TRADE <span class="sort-arrow">↕</span></th>
      <th style="width:80px;">VALUE</th>
      <th style="width:130px;" onclick="sortTable('due')" class="sorted">DUE DATE <span class="sort-arrow">↑</span></th>
      <th style="width:80px;">STATUS</th>
      <th style="width:140px;">SOURCE</th>
    </tr>
  </thead>
  <tbody id="bids-tbody">
{table_rows}
  </tbody>
</table>
</div>

<!-- Footer -->
<div class="footer">
  <span>FCU Bid Dashboard · Generated {generated_at} · Sources: {sources_summary}</span>
  <span>Verify all bids on source portals before submitting.</span>
</div>

<script>
const allRows = Array.from(document.querySelectorAll('#bids-tbody tr[data-bid]'));
let currentTab = 'all';
let sortCol = 'due';
let sortDir = 1;

function switchTab(el) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  currentTab = el.dataset.tab;
  applyFilters();
}}

function applyFilters() {{
  const q = document.getElementById('search-input').value.toLowerCase();
  const trade = document.getElementById('trade-filter').value.toLowerCase();
  const dueMax = parseInt(document.getElementById('due-filter').value) || null;
  const source = document.getElementById('source-filter').value.toLowerCase();
  const today = new Date(); today.setHours(0,0,0,0);

  let visible = 0;
  allRows.forEach(row => {{
    const title = (row.dataset.title || '').toLowerCase();
    const rowTrade = (row.dataset.trade || '').toLowerCase();
    const rowSource = (row.dataset.source || '').toLowerCase();
    const relevant = row.dataset.relevant === '1';
    const daysVal = parseInt(row.dataset.days);

    let show = true;
    if (q && !title.includes(q)) show = false;
    if (trade && !rowTrade.includes(trade)) show = false;
    if (source && !rowSource.includes(source)) show = false;
    if (dueMax !== null && (isNaN(daysVal) || daysVal < 0 || daysVal > dueMax)) show = false;
    if (currentTab === 'flooring' && !relevant) show = false;
    if (currentTab === 'expiring' && (isNaN(daysVal) || daysVal < 0 || daysVal > 7)) show = false;

    row.classList.toggle('hidden', !show);
    if (show) visible++;
  }});

  document.getElementById('display-count').textContent = visible + ' of {total_bids} bids';
}}

function sortTable(col) {{
  if (sortCol === col) sortDir *= -1;
  else {{ sortCol = col; sortDir = 1; }}

  const tbody = document.getElementById('bids-tbody');
  const rows = Array.from(tbody.querySelectorAll('tr[data-bid]'));

  rows.sort((a, b) => {{
    let av, bv;
    if (col === 'score') {{ av = parseInt(a.dataset.score)||0; bv = parseInt(b.dataset.score)||0; }}
    else if (col === 'due') {{ av = parseInt(a.dataset.days ?? 9999); bv = parseInt(b.dataset.days ?? 9999); }}
    else if (col === 'trade') {{ av = a.dataset.trade||''; bv = b.dataset.trade||''; return sortDir * av.localeCompare(bv); }}
    else {{ av = (a.dataset.title||''); bv = (b.dataset.title||''); return sortDir * av.localeCompare(bv); }}
    return sortDir * (av - bv);
  }});

  rows.forEach(r => tbody.appendChild(r));

  document.querySelectorAll('th').forEach(th => th.classList.remove('sorted'));
  document.querySelectorAll('th .sort-arrow').forEach(s => s.textContent = '↕');
  const thIndex = {{score:0, title:1, trade:3, due:5}}[col];
  if (thIndex !== undefined) {{
    const th = document.querySelectorAll('th')[thIndex];
    th.classList.add('sorted');
    th.querySelector('.sort-arrow').textContent = sortDir === 1 ? '↑' : '↓';
  }}
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def _build_row(bid: dict) -> str:
    score = calculate_score(bid)
    score_color = _score_color(score)
    trade = detect_trade(bid.get("title", ""), bid.get("search_keyword", ""))
    days = _days_until(bid.get("due_date"))

    # Due date cell
    due_str = bid["due_date"].strftime("%b %d, %Y") if bid.get("due_date") else bid.get("due_date_raw") or "TBD"
    if days is None:
        due_class, due_extra = "due-normal", ""
    elif days < 0:
        due_class, due_extra = "due-expired", "<br><small>Expired</small>"
    elif days <= 3:
        due_class, due_extra = "due-urgent", f"<br><small>{days}d left</small>"
    elif days <= 7:
        due_class, due_extra = "due-soon", f"<br><small>{days}d left</small>"
    else:
        due_class, due_extra = "due-normal", f"<br><small>{days}d</small>"

    # Status badge
    if days is not None and days < 0:
        status_html = '<span class="badge badge-soon">Expired</span>'
    else:
        status_html = '<span class="badge badge-new">New</span>'

    # Trade tag
    is_flooring = bid.get("is_relevant", False)
    trade_class = "trade-tag flooring" if is_flooring else "trade-tag"
    trade_label = f'<span class="{trade_class}">{trade}</span>'

    # Title — truncate
    title = bid.get("title", "Unknown")[:80] + ("…" if len(bid.get("title", "")) > 80 else "")
    agency = bid.get("agency") or "California"

    # days dataset attribute
    days_attr = str(days) if days is not None else ""
    relevant_attr = "1" if bid.get("is_relevant") else "0"
    title_data = bid.get("title", "").replace('"', '&quot;')
    trade_data = trade.replace('"', '&quot;')
    bid_url = bid.get("url") or "#"
    bid_source = bid.get("source", "BidNet Direct")

    source_data = bid_source.replace('"', '&quot;').lower()
    return f"""    <tr data-bid="1" data-score="{score}" data-days="{days_attr}" data-relevant="{relevant_attr}" data-title="{title_data}" data-trade="{trade_data}" data-source="{source_data}">
      <td><div class="score-badge" style="background:{score_color}">{score}</div></td>
      <td><div class="bid-title">{title}</div><div class="bid-agency">{agency}</div></td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--gray)">CA</td>
      <td>{trade_label}</td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--gray)">—</td>
      <td><span class="{due_class}">{due_str}{due_extra}</span></td>
      <td>{status_html}</td>
      <td><a class="source-tag" href="{bid_url}" target="_blank">{bid_source}</a></td>
    </tr>"""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_report(bids: list[dict], output_path: str) -> str:
    today = date.today()
    now = datetime.now()

    relevant_count = sum(1 for b in bids if b.get("is_relevant"))
    due_7_count = sum(
        1 for b in bids
        if b.get("due_date") and 0 <= _days_until(b["due_date"]) <= 7
    )
    new_count = len(bids)  # all freshly scanned

    # Sort: by score desc, then due date asc
    sorted_bids = sorted(
        bids,
        key=lambda b: (-calculate_score(b), b.get("due_date") or date(9999, 1, 1)),
    )

    # Build rows
    rows_html = "\n".join(_build_row(b) for b in sorted_bids)
    if not rows_html:
        rows_html = '    <tr class="empty-row"><td colspan="8">No bids found. Run the scanner again or expand your keywords.</td></tr>'

    # Build trade filter options
    trades = sorted(set(detect_trade(b.get("title",""), b.get("search_keyword","")) for b in bids))
    trade_options = "\n    ".join(f'<option value="{t.lower()}">{t}</option>' for t in trades)

    # Sources summary for footer
    source_counts: dict[str, int] = {}
    for b in bids:
        s = b.get("source", "BidNet Direct")
        source_counts[s] = source_counts.get(s, 0) + 1
    sources_summary = " · ".join(f"{s} ({n})" for s, n in sorted(source_counts.items()))

    html = TEMPLATE.format(
        scan_date=today.strftime("%B %d, %Y"),
        total_bids=len(bids),
        new_count=new_count,
        due_7_count=due_7_count,
        relevant_count=relevant_count,
        trade_options=trade_options,
        table_rows=rows_html,
        generated_at=now.strftime("%Y-%m-%d %H:%M"),
        sources_summary=sources_summary,
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path
