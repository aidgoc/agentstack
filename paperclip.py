"""
Paperclip API client for AgentStack.

Wraps the Paperclip REST API to provide company orchestration:
companies, agents, tasks (issues), goals, approvals, costs, and activity.
"""

import os
import requests

PAPERCLIP_URL = os.getenv("PAPERCLIP_URL", "http://127.0.0.1:3100")
API = f"{PAPERCLIP_URL}/api"
TIMEOUT = 10


def _get(path, params=None):
    r = requests.get(f"{API}{path}", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _post(path, data=None):
    r = requests.post(f"{API}{path}", json=data or {}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _patch(path, data):
    r = requests.patch(f"{API}{path}", json=data, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _delete(path):
    r = requests.delete(f"{API}{path}", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# ── Companies ────────────────────────────────────────

def list_companies():
    return _get("/companies")


def create_company(name, description=""):
    return _post("/companies", {"name": name, "description": description})


def get_company(company_id):
    return _get(f"/companies/{company_id}")


def get_company_stats():
    return _get("/companies/stats")


# ── Agents ───────────────────────────────────────────

VALID_ROLES = ["ceo", "cto", "cmo", "cfo", "engineer", "designer", "pm", "qa", "devops", "researcher", "general"]


def list_agents(company_id):
    return _get(f"/companies/{company_id}/agents")


def create_agent(company_id, name, short_name, role="general", title="", system_prompt=""):
    data = {
        "name": name,
        "shortName": short_name,
        "role": role if role in VALID_ROLES else "general",
        "title": title or name,
        "systemPrompt": system_prompt,
    }
    return _post(f"/companies/{company_id}/agents", data)


def get_agent(agent_id):
    return _get(f"/agents/{agent_id}")


def update_agent(agent_id, **fields):
    return _patch(f"/agents/{agent_id}", fields)


# ── Issues (Tasks) ───────────────────────────────────

def list_issues(company_id, status=None, assignee_agent_id=None):
    params = {}
    if status:
        params["status"] = status
    if assignee_agent_id:
        params["assigneeAgentId"] = assignee_agent_id
    return _get(f"/companies/{company_id}/issues", params)


def create_issue(company_id, title, description="", priority="medium", assignee_agent_id=None):
    data = {"title": title, "description": description, "priority": priority, "status": "todo"}
    if assignee_agent_id:
        data["assigneeAgentId"] = assignee_agent_id
    return _post(f"/companies/{company_id}/issues", data)


def get_issue(issue_id):
    return _get(f"/issues/{issue_id}")


def update_issue(issue_id, **fields):
    return _patch(f"/issues/{issue_id}", fields)


def add_comment(issue_id, body):
    return _post(f"/issues/{issue_id}/comments", {"body": body})


def list_comments(issue_id):
    return _get(f"/issues/{issue_id}/comments")


# ── Goals ────────────────────────────────────────────

def list_goals(company_id):
    return _get(f"/companies/{company_id}/goals")


def create_goal(company_id, title, description=""):
    return _post(f"/companies/{company_id}/goals", {"title": title, "description": description})


# ── Approvals ────────────────────────────────────────

def list_approvals(company_id, status=None):
    params = {"status": status} if status else {}
    return _get(f"/companies/{company_id}/approvals", params)


def approve(approval_id):
    return _post(f"/approvals/{approval_id}/approve")


def reject(approval_id):
    return _post(f"/approvals/{approval_id}/reject")


# ── Costs ────────────────────────────────────────────

def get_costs(company_id):
    return _get(f"/companies/{company_id}/costs")


# ── Activity ─────────────────────────────────────────

def get_activity(company_id, limit=20):
    return _get(f"/companies/{company_id}/activity", {"limit": limit})


# ── Dashboard ────────────────────────────────────────

def get_dashboard(company_id):
    return _get(f"/companies/{company_id}/dashboard")


# ── Health ───────────────────────────────────────────

def health():
    return _get("/health")


# ── Helpers for Telegram formatting ──────────────────

def fmt_issue(issue):
    """Format an issue for Telegram display."""
    status_icons = {
        "todo": "[ ]", "in_progress": "[~]", "in_review": "[?]",
        "done": "[x]", "cancelled": "[-]", "backlog": "[.]",
    }
    priority_icons = {"urgent": "!!!", "high": "!!", "medium": "!", "low": "."}
    s = status_icons.get(issue.get("status", ""), "[ ]")
    p = priority_icons.get(issue.get("priority", ""), "")
    ident = issue.get("identifier", "")
    title = issue.get("title", "")
    assignee = ""
    if issue.get("assigneeAgentId"):
        assignee = f" @agent"
    return f"{s} {ident} {p} {title}{assignee}"


def fmt_agent(agent):
    """Format an agent for Telegram display."""
    status_icons = {"idle": "(-)", "active": "(*)", "terminated": "(x)", "pending_approval": "(?)"}
    s = status_icons.get(agent.get("status", ""), "(?)")
    return f"{s} {agent['name']} [{agent.get('role', '')}] - {agent.get('title', '')}"
