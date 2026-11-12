from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Optional
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from analyzer import AnalysisEngine
from exporter import Exporter
from git_manager import GitRepoManager
from parser import GitLogParser

app = FastAPI(title="GitScope Web API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tasks_db: Dict[str, Dict] = {}


class AnalyzeRequest(BaseModel):
    target: str
    since: Optional[str] = None
    until: Optional[str] = None


def run_analysis_task(task_id: str, target: str, since: Optional[str], until: Optional[str]):
    try:
        tasks_db[task_id]["status"] = "preparing"
        manager = GitRepoManager(target)
        repo_path = manager.prepare()
        repo_name = Path(repo_path).name
        existing_files = manager.get_existing_files()

        tasks_db[task_id]["status"] = "parsing"
        parser = GitLogParser(repo_path, since=since, until=until)
        commit_stream = parser.parse_commits()

        tasks_db[task_id]["status"] = "analyzing"
        engine = AnalysisEngine(
            repo_name=repo_name,
            repo_path=str(repo_path),
            since=since,
            until=until,
            existing_files=existing_files,
        )
        report = engine.analyze(commit_stream)

        tasks_db[task_id]["status"] = "completed"
        tasks_db[task_id]["report"] = report.model_dump()
        tasks_db[task_id]["html_report"] = Exporter.to_html(report)
    except Exception as e:
        tasks_db[task_id]["status"] = "failed"
        tasks_db[task_id]["error"] = str(e)


@app.post("/api/analyze")
def start_analysis(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    tasks_db[task_id] = {
        "status": "queued",
        "target": req.target,
        "report": None,
        "html_report": None,
        "error": None,
    }
    background_tasks.add_task(run_analysis_task, task_id, req.target, req.since, req.until)
    return {"task_id": task_id, "status": "queued"}


@app.get("/api/status/{task_id}")
def check_status(task_id: str):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    data = tasks_db[task_id]
    return {
        "task_id": task_id,
        "status": data["status"],
        "error": data.get("error"),
        "has_report": data.get("report") is not None,
    }


@app.get("/api/report/{task_id}")
def get_report(task_id: str):
    if task_id not in tasks_db or tasks_db[task_id]["status"] != "completed":
        raise HTTPException(status_code=404, detail="Report not ready")
    return tasks_db[task_id]["report"]


@app.get("/report/{task_id}", response_class=HTMLResponse)
def view_html_report(task_id: str):
    if task_id not in tasks_db or tasks_db[task_id]["status"] != "completed":
        raise HTTPException(status_code=404, detail="Report not ready")
    return HTMLResponse(content=tasks_db[task_id]["html_report"])


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>GitScope Dashboard</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0d1117; color: #c9d1d9; padding: 40px 20px; }
    .box { max-width: 600px; margin: 40px auto; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 24px; }
    h1 { color: #fff; font-size: 24px; margin-bottom: 16px; }
    input { width: 100%; box-sizing: border-box; padding: 10px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #fff; margin-bottom: 14px; }
    button { background: #238636; color: #fff; border: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; width: 100%; }
    button:hover { background: #2ea043; }
    #status-box { margin-top: 20px; display: none; padding: 12px; border-radius: 6px; font-size: 14px; }
    .loading { background: #1f2937; color: #58a6ff; border: 1px solid #30363d; }
    .success { background: #0d2818; color: #3fb950; border: 1px solid #238636; }
    .error { background: #3c1618; color: #f85149; border: 1px solid #da3633; }
  </style>
</head>
<body>
  <div class="box">
    <h1>GitScope Analysis Dashboard</h1>
    <p style="color:#8b949e; font-size:14px; margin-bottom:16px;">Analyze Git history for hotspots, ownership, coupling, and commit hygiene.</p>
    <label style="font-size:13px; font-weight:600;">Repository URL or Local Path:</label>
    <input type="text" id="target" placeholder="https://github.com/org/repo or ." value=".">
    <button onclick="startAnalysis()">Start Analysis</button>
    <div id="status-box"></div>
  </div>
  <script>
    async function startAnalysis() {
      const target = document.getElementById('target').value.trim();
      const statusBox = document.getElementById('status-box');
      statusBox.style.display = 'block';
      statusBox.className = 'loading';
      statusBox.innerText = 'Submitting task...';

      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: target })
      });
      const data = await res.json();
      const taskId = data.task_id;

      const poll = setInterval(async () => {
        const sRes = await fetch(`/api/status/${taskId}`);
        const sData = await sRes.json();
        if (sData.status === 'completed') {
          clearInterval(poll);
          statusBox.className = 'success';
          statusBox.innerHTML = `Analysis complete! <a href="/report/${taskId}" target="_blank" style="color:#58a6ff; font-weight:bold; text-decoration:underline;">Open Interactive Report</a>`;
        } else if (sData.status === 'failed') {
          clearInterval(poll);
          statusBox.className = 'error';
          statusBox.innerText = 'Error: ' + sData.error;
        } else {
          statusBox.innerText = 'Status: ' + sData.status + '...';
        }
      }, 1000);
    }
  </script>
</body>
</html>"""

