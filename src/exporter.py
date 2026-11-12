from __future__ import annotations

import json
from pathlib import Path
from models import ScopeReport


class Exporter:
    @staticmethod
    def to_json(report: ScopeReport, indent: int = 2) -> str:
        return report.model_dump_json(indent=indent)

    @staticmethod
    def to_markdown(report: ScopeReport, top_n: int = 15) -> str:
        md = []
        md.append(f"# GitScope Report: {report.repo_name}\n")
        md.append(f"- **Analyzed At:** {report.analyzed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if report.since or report.until:
            md.append(f"- **Time Range:** {report.since or 'Beginning'} -> {report.until or 'Latest'}")
        md.append(f"- **Total Commits Analyzed:** {report.total_commits}")
        md.append(f"- **Total Contributors:** {report.total_authors}")
        md.append(f"- **Commit Hygiene Score:** {report.hygiene.quality_score} / 100")
        md.append(f"- **Conventional Commits:** {report.hygiene.conventional_percentage}%\n")

        md.append("## Commit Hygiene & Quality Inspection\n")
        md.append(f"- **Overall Hygiene Score:** {report.hygiene.quality_score}/100")
        md.append(f"- **Conventional Commits Adherence:** {report.hygiene.conventional_count}/{report.hygiene.total_scanned} ({report.hygiene.conventional_percentage}%)")
        md.append(f"- **Vague Commit Messages Flagged:** {report.hygiene.vague_commits_count}")
        md.append(f"- **Ticket References Detected:** {report.hygiene.ticket_referenced_count}\n")

        md.append("### Contributor Hygiene Leaderboard\n")
        md.append("| Contributor | Commits | Conventional % | Vague Commits | Hygiene Score |")
        md.append("| :--- | :---: | :---: | :---: | :---: |")
        sorted_by_clean = sorted(report.contributors, key=lambda c: (c.hygiene.hygiene_score, c.total_commits), reverse=True)
        for c in sorted_by_clean:
            c_pct = round((c.hygiene.conventional_count / c.total_commits) * 100, 1) if c.total_commits > 0 else 0.0
            md.append(f"| **{c.name}** | {c.total_commits} | {c_pct}% | {c.hygiene.vague_count} | **{c.hygiene.hygiene_score}/100** |")
        md.append("\n")

        md.append("## Contributor Summary & Detailed Change Log\n")
        for c in report.contributors:
            md.append(f"### {c.name} ({c.email})")
            md.append(f"- **Summary:** {c.summary}")
            dirs = ", ".join(f"`{d}`" for d in c.primary_directories) if c.primary_directories else "root"
            files = ", ".join(f"`{f}`" for f in c.primary_files) if c.primary_files else "none"
            md.append(f"- **Key Modules:** {dirs}")
            md.append(f"- **Key Files:** {files}\n")

            if c.change_log:
                md.append("#### Changes Made by This Contributor:")
                md.append("| Commit | Date | Lines (+ / -) | Commit Message | Files Touched |")
                md.append("| :--- | :--- | :---: | :--- | :--- |")
                for item in c.change_log[:15]:
                    dt_str = item.timestamp.strftime("%Y-%m-%d")
                    files_str = ", ".join(f"`{Path(f).name}`" for f in item.files_changed[:3])
                    md.append(f"| `{item.commit_hash}` | {dt_str} | +{item.lines_added} / -{item.lines_deleted} | {item.message} | {files_str} |")
                md.append("\n")

        md.append("## Top File Hotspots\n")
        md.append("> **How to read this:** Files with high churn (frequent modifications and large line diffs) combined with a low bus factor (knowledge concentrated in 1 person) represent high risk areas for regressions and team bottlenecks.\n")
        md.append("| File Path | Status | Commits | Churn (+ / -) | Bus Factor | Risk Level | Primary Author |")
        md.append("| :--- | :---: | :--- | :--- | :--- | :--- | :--- |")

        for f in report.hotspots_files[:top_n]:
            top_author = f.top_contributors[0].name if f.top_contributors else "N/A"
            risk_badge = f"**{f.risk_level}**" if f.risk_level == "High" else f.risk_level
            status_badge = "Deleted" if f.is_deleted else "Active"
            md.append(
                f"| `{f.path}` | {status_badge} | {f.commits} | +{f.lines_added} / -{f.lines_deleted} | {f.bus_factor} | {risk_badge} | {top_author} |"
            )

        if report.coupled_files:
            md.append("\n## Temporal Coupling: Files That Change Together\n")
            md.append("> **How to read this:** Files that frequently co-change in the same commit signify hidden architectural dependencies.\n")
            md.append("| File A | File B | Co-Commits | Coupling % |")
            md.append("| :--- | :--- | :---: | :---: |")
            for cp in report.coupled_files[:top_n]:
                md.append(f"| `{cp.file_a}` | `{cp.file_b}` | {cp.together_commits} | {cp.coupling_percentage}% |")

        md.append("\n## Directory Ownership & Knowledge Distribution\n")
        md.append("> **How to read this:** Shows knowledge distribution by architectural component or module.\n")
        md.append("| Directory | Commits | Total Churn | Bus Factor | Key Contributors |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")

        for d in report.hotspots_directories[:top_n]:
            authors_str = ", ".join([f"{c.name} ({int(c.ownership_percentage * 100)}%)" for c in d.top_contributors[:3]])
            md.append(f"| `{d.path}` | {d.commits} | {d.total_churn} | {d.bus_factor} | {authors_str} |")

        md.append("\n---\n*Generated by GitScope*")
        return "\n".join(md)

    @staticmethod
    def to_badge_svg(label: str, value: str, color: str = "#238636") -> str:
        width = 110 + len(value) * 7
        mid_x = 75
        val_x = mid_x + ((width - mid_x) / 2)
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <mask id="a">
    <rect width="{width}" height="20" rx="3" fill="#fff"/>
  </mask>
  <g mask="url(#a)">
    <path fill="#555" d="M0 0h{mid_x}v20H0z"/>
    <path fill="{color}" d="M{mid_x} 0h{width - mid_x}v20H{mid_x}z"/>
    <path fill="url(#b)" d="M0 0h{width}v20H0z"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="38" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="38" y="14">{label}</text>
    <text x="{val_x}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{val_x}" y="14">{value}</text>
  </g>
</svg>"""

    @staticmethod
    def to_html(report: ScopeReport) -> str:
        report_data_json = report.model_dump_json()
        score = report.hygiene.quality_score
        badge_color = "#3fb950" if score >= 80 else ("#d29922" if score >= 60 else "#f85149")
        badge_svg = Exporter.to_badge_svg("gitscope score", f"{score}/100", badge_color)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GitScope Report - {report.repo_name}</title>
  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --text-muted: #8b949e;
      --accent: #58a6ff;
      --high: #f85149;
      --med: #d29922;
      --low: #3fb950;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 32px 24px;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    header {{ margin-bottom: 24px; border-bottom: 1px solid var(--border); padding-bottom: 16px; display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px; }}
    h1 {{ font-size: 28px; color: #fff; margin-bottom: 8px; }}
    .stats-bar {{ display: flex; gap: 16px; flex-wrap: wrap; margin-top: 12px; }}
    .stat-pill {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 16px;
      font-size: 14px;
    }}
    .stat-pill strong {{ color: var(--accent); }}
    .section {{ margin-top: 36px; }}
    h2 {{ font-size: 20px; color: #fff; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
    .controls-row {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }}
    .search-box {{
      width: 100%;
      max-width: 320px;
      padding: 8px 12px;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: #fff;
      font-size: 14px;
    }}
    .search-box:focus {{ outline: none; border-color: var(--accent); }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 14px; }}
    th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
    th {{ background: var(--card-bg); color: #fff; cursor: pointer; user-select: none; }}
    th:hover {{ color: var(--accent); }}
    tr:hover {{ background: rgba(255, 255, 255, 0.02); }}
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 600;
    }}
    .badge-high {{ background: rgba(248, 81, 73, 0.15); color: var(--high); border: 1px solid var(--high); }}
    .badge-med {{ background: rgba(210, 153, 34, 0.15); color: var(--med); border: 1px solid var(--med); }}
    .badge-low {{ background: rgba(63, 185, 80, 0.15); color: var(--low); border: 1px solid var(--low); }}
    .badge-del {{ background: rgba(139, 148, 158, 0.2); color: var(--text-muted); }}
    .badge-active {{ background: rgba(63, 185, 80, 0.15); color: var(--low); }}
    .cards-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
    }}
    .card h3 {{ color: #fff; font-size: 16px; margin-bottom: 4px; }}
    .card p {{ font-size: 13px; color: var(--text-muted); margin-bottom: 8px; }}
    .card .summary {{ font-size: 13px; color: var(--text); line-height: 1.5; margin-bottom: 12px; }}
    .change-list {{ margin-top: 10px; font-size: 12px; border-top: 1px solid var(--border); padding-top: 8px; }}
    .change-entry {{ padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }}
    .filter-tags {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .filter-tag {{
      cursor: pointer;
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 12px;
      border: 1px solid var(--border);
      background: var(--card-bg);
    }}
    .filter-tag.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    .treemap-container {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      background: var(--card-bg);
      padding: 12px;
      border-radius: 8px;
      border: 1px solid var(--border);
      min-height: 180px;
    }}
    .treemap-box {{
      padding: 10px;
      border-radius: 6px;
      color: #fff;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      overflow: hidden;
      font-size: 12px;
      transition: transform 0.15s;
    }}
    .treemap-box:hover {{ transform: scale(1.02); }}
    .treemap-high {{ background: #8e1519; border: 1px solid var(--high); }}
    .treemap-med {{ background: #744210; border: 1px solid var(--med); }}
    .treemap-low {{ background: #1c4b27; border: 1px solid var(--low); }}
    .badge-preview-box {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      padding: 12px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .badge-preview-box code {{ font-size: 12px; color: var(--accent); user-select: all; }}
    .pagination-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 14px;
      font-size: 13px;
      color: var(--text-muted);
    }}
    .page-btn {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 6px 14px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 13px;
    }}
    .page-btn:hover:not(:disabled) {{ background: var(--border); color: #fff; }}
    .page-btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}
    .page-size-select {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>GitScope Report: {report.repo_name}</h1>
        <div class="stats-bar">
          <div class="stat-pill">Analyzed: <strong>{report.analyzed_at.strftime('%Y-%m-%d %H:%M UTC')}</strong></div>
          <div class="stat-pill">Total Commits: <strong>{report.total_commits}</strong></div>
          <div class="stat-pill">Contributors: <strong>{report.total_authors}</strong></div>
          <div class="stat-pill">Conventional Adherence: <strong>{report.hygiene.conventional_percentage}%</strong></div>
          <div class="stat-pill">Hygiene Score: <strong style="color:{badge_color};">{report.hygiene.quality_score}/100</strong></div>
        </div>
      </div>
      <div>
        <div class="badge-preview-box">
          <div>{badge_svg}</div>
        </div>
      </div>
    </header>

    <div class="section">
      <h2>Interactive Hotspot Treemap (Size = Churn, Color = Risk)</h2>
      <div class="treemap-container" id="treemap-container"></div>
    </div>

    <div class="section">
      <h2>Commit Hygiene & Quality Inspection</h2>
      <div class="cards-grid">
        <div class="card">
          <h3>Commit Quality Score: {report.hygiene.quality_score}/100</h3>
          <p>Total Scanned: {report.hygiene.total_scanned} commits</p>
          <div class="summary">
            &bull; Conventional commits adherence: <strong>{report.hygiene.conventional_percentage}%</strong> ({report.hygiene.conventional_count}/{report.hygiene.total_scanned})<br>
            &bull; Vague messages flagged: <strong>{report.hygiene.vague_commits_count}</strong><br>
            &bull; Ticket references found: <strong>{report.hygiene.ticket_referenced_count}</strong>
          </div>
        </div>
        <div class="card" style="grid-column: span 2;">
          <h3>Contributor Hygiene Leaderboard (Cleanest vs Most Vague)</h3>
          <table>
            <thead>
              <tr>
                <th>Contributor</th>
                <th>Commits</th>
                <th>Conventional %</th>
                <th>Vague Commits</th>
                <th>Hygiene Score</th>
              </tr>
            </thead>
            <tbody id="hygiene-leaderboard-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="section">
      <h2>Contributor Breakdown & Work Summaries</h2>
      <div class="cards-grid" id="contributors-container"></div>
    </div>

    <div class="section">
      <h2>File Hotspots</h2>
      <div class="controls-row">
        <input type="text" id="hotspot-search" class="search-box" placeholder="Filter files or author...">
        <div class="filter-tags">
          <span class="filter-tag active" onclick="filterRisk('all', this)">All Risks</span>
          <span class="filter-tag" onclick="filterRisk('High', this)">High Risk</span>
          <span class="filter-tag" onclick="filterRisk('Medium', this)">Medium Risk</span>
          <span class="filter-tag" onclick="filterRisk('Low', this)">Low Risk</span>
        </div>
        <div>
          <label style="font-size:13px; color:var(--text-muted); margin-right:6px;">Page size:</label>
          <select id="page-size" class="page-size-select" onchange="changePageSize(this.value)">
            <option value="10">10</option>
            <option value="25" selected>25</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </div>
      </div>

      <table id="hotspots-table">
        <thead>
          <tr>
            <th onclick="sortHotspots('path')">File Path</th>
            <th onclick="sortHotspots('is_deleted')">Status</th>
            <th onclick="sortHotspots('commits')">Commits</th>
            <th onclick="sortHotspots('total_churn')">Churn (+/-)</th>
            <th onclick="sortHotspots('bus_factor')">Bus Factor</th>
            <th onclick="sortHotspots('risk_level')">Risk</th>
            <th onclick="sortHotspots('top_author')">Top Contributor</th>
          </tr>
        </thead>
        <tbody id="hotspots-tbody"></tbody>
      </table>

      <div class="pagination-bar">
        <span id="page-info">Showing 0-0 of 0</span>
        <div>
          <button id="btn-prev" class="page-btn" onclick="prevPage()">Previous</button>
          <span id="page-num" style="margin: 0 10px; font-weight:600; color:#fff;">1</span>
          <button id="btn-next" class="page-btn" onclick="nextPage()">Next</button>
        </div>
      </div>
    </div>

    <div class="section">
      <h2>Temporal Coupling: Files That Change Together</h2>
      <table id="coupling-table">
        <thead>
          <tr>
            <th>File A</th>
            <th>File B</th>
            <th>Shared Commits</th>
            <th>Coupling Degree</th>
          </tr>
        </thead>
        <tbody id="coupling-tbody"></tbody>
      </table>
    </div>
  </div>

  <script>
    const data = {report_data_json};

    function renderTreemap() {{
      const container = document.getElementById('treemap-container');
      const files = data.hotspots_files.slice(0, 15);
      if (files.length === 0) {{
        container.innerHTML = '<div style="color:var(--text-muted);">No files tracked.</div>';
        return;
      }}
      const totalChurn = files.reduce((acc, f) => acc + (f.total_churn || 1), 0);
      container.innerHTML = files.map(f => {{
        const weight = Math.max(8, Math.round(((f.total_churn || 1) / totalChurn) * 100));
        const riskClass = f.risk_level === 'High' ? 'treemap-high' : (f.risk_level === 'Medium' ? 'treemap-med' : 'treemap-low');
        const filename = f.path.split('/').pop();
        return `
          <div class="treemap-box ${{riskClass}}" style="flex: ${{weight}} 1 120px;" title="${{f.path}} (Churn: ${{f.total_churn}}, Risk: ${{f.risk_level}})">
            <strong>${{filename}}</strong>
            <span>${{f.total_churn}} lines</span>
          </div>
        `;
      }}).join('');
    }}

    function renderHygieneLeaderboard() {{
      const tbody = document.getElementById('hygiene-leaderboard-tbody');
      const sorted = [...data.contributors].sort((a, b) => b.hygiene.hygiene_score - a.hygiene.hygiene_score);
      tbody.innerHTML = sorted.map(c => {{
        const convPct = c.total_commits > 0 ? Math.round((c.hygiene.conventional_count / c.total_commits) * 100) : 0;
        const scoreClass = c.hygiene.hygiene_score >= 80 ? 'badge-low' : (c.hygiene.hygiene_score >= 60 ? 'badge-med' : 'badge-high');
        return `
          <tr>
            <td><strong>${{c.name}}</strong></td>
            <td>${{c.total_commits}}</td>
            <td>${{convPct}}%</td>
            <td>${{c.hygiene.vague_count}}</td>
            <td><span class="badge ${{scoreClass}}">${{c.hygiene.hygiene_score}}/100</span></td>
          </tr>
        `;
      }}).join('');
    }}

    function renderContributors() {{
      const container = document.getElementById('contributors-container');
      container.innerHTML = data.contributors.map(c => {{
        const changesHtml = (c.change_log || []).slice(0, 5).map(ch => `
          <div class="change-entry">
            <code>${{ch.commit_hash}}</code>: <strong>${{ch.message}}</strong> (+${{ch.lines_added}}/-${{ch.lines_deleted}})
          </div>
        `).join('');

        return `
          <div class="card">
            <h3>${{c.name}}</h3>
            <p>${{c.email}} &bull; ${{c.total_commits}} commits &bull; ${{c.total_churn}} churn</p>
            <div class="summary">${{c.summary}}</div>
            ${{changesHtml ? '<div class="change-list"><strong>Recent Changes:</strong>' + changesHtml + '</div>' : ''}}
          </div>
        `;
      }}).join('');
    }}

    let currentRiskFilter = 'all';
    let sortKey = 'commits';
    let sortAsc = false;
    let currentPage = 1;
    let pageSize = 25;

    function renderHotspots() {{
      const query = document.getElementById('hotspot-search').value.toLowerCase();
      const tbody = document.getElementById('hotspots-tbody');

      let list = data.hotspots_files.filter(f => {{
        const matchesSearch = f.path.toLowerCase().includes(query) ||
          (f.top_contributors[0] && f.top_contributors[0].name.toLowerCase().includes(query));
        const matchesRisk = currentRiskFilter === 'all' || f.risk_level === currentRiskFilter;
        return matchesSearch && matchesRisk;
      }});

      list.sort((a, b) => {{
        let valA = a[sortKey];
        let valB = b[sortKey];
        if (sortKey === 'top_author') {{
          valA = a.top_contributors[0] ? a.top_contributors[0].name : '';
          valB = b.top_contributors[0] ? b.top_contributors[0].name : '';
        }}
        if (valA < valB) return sortAsc ? -1 : 1;
        if (valA > valB) return sortAsc ? 1 : -1;
        return 0;
      }});

      const totalItems = list.length;
      const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
      if (currentPage > totalPages) currentPage = totalPages;

      const startIndex = (currentPage - 1) * pageSize;
      const endIndex = Math.min(startIndex + pageSize, totalItems);
      const pageSlice = list.slice(startIndex, endIndex);

      document.getElementById('page-info').innerText = totalItems === 0
        ? 'Showing 0 files'
        : `Showing ${{startIndex + 1}}-${{endIndex}} of ${{totalItems}} files`;
      document.getElementById('page-num').innerText = currentPage;
      document.getElementById('btn-prev').disabled = currentPage <= 1;
      document.getElementById('btn-next').disabled = currentPage >= totalPages;

      if (pageSlice.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text-muted); text-align:center;">No matching files found.</td></tr>';
        return;
      }}

      tbody.innerHTML = pageSlice.map(f => {{
        const riskClass = f.risk_level === 'High' ? 'badge-high' : (f.risk_level === 'Medium' ? 'badge-med' : 'badge-low');
        const statusBadge = f.is_deleted ? '<span class="badge badge-del">Deleted</span>' : '<span class="badge badge-active">Active</span>';
        const topAuth = f.top_contributors[0] ? f.top_contributors[0].name : 'N/A';
        return `
          <tr>
            <td><code>${{f.path}}</code></td>
            <td>${{statusBadge}}</td>
            <td>${{f.commits}}</td>
            <td>+${{f.lines_added}} / -${{f.lines_deleted}}</td>
            <td>${{f.bus_factor}}</td>
            <td><span class="badge ${{riskClass}}">${{f.risk_level}}</span></td>
            <td>${{topAuth}}</td>
          </tr>
        `;
      }}).join('');
    }}

    function filterRisk(risk, elem) {{
      currentRiskFilter = risk;
      currentPage = 1;
      document.querySelectorAll('.filter-tag').forEach(t => t.classList.remove('active'));
      elem.classList.add('active');
      renderHotspots();
    }}

    function sortHotspots(key) {{
      if (sortKey === key) {{
        sortAsc = !sortAsc;
      }} else {{
        sortKey = key;
        sortAsc = false;
      }}
      currentPage = 1;
      renderHotspots();
    }}

    function changePageSize(val) {{
      pageSize = parseInt(val, 10);
      currentPage = 1;
      renderHotspots();
    }}

    function prevPage() {{
      if (currentPage > 1) {{
        currentPage--;
        renderHotspots();
      }}
    }}

    function nextPage() {{
      currentPage++;
      renderHotspots();
    }}

    function renderCoupling() {{
      const tbody = document.getElementById('coupling-tbody');
      if (!data.coupled_files || data.coupled_files.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted); text-align:center;">No strong file coupling patterns detected.</td></tr>';
        return;
      }}
      tbody.innerHTML = data.coupled_files.map(cp => `
        <tr>
          <td><code>${{cp.file_a}}</code></td>
          <td><code>${{cp.file_b}}</code></td>
          <td>${{cp.together_commits}}</td>
          <td><span class="badge badge-med">${{cp.coupling_percentage}}%</span></td>
        </tr>
      `).join('');
    }}

    document.getElementById('hotspot-search').addEventListener('input', () => {{
      currentPage = 1;
      renderHotspots();
    }});

    renderTreemap();
    renderHygieneLeaderboard();
    renderContributors();
    renderHotspots();
    renderCoupling();
  </script>
</body>
</html>"""
