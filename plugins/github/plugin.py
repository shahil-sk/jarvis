"""GitHub plugin — repos, issues, PRs, commits, branches. Uses stdlib urllib only."""

import json
import os
import urllib.request
import urllib.error
from plugins.base import PluginBase
from core.config import get

_API = "https://api.github.com"


def _token() -> str:
    return (
        os.environ.get("JARVIS_GITHUB_TOKEN")
        or get("github", {}).get("token", "")
    )


def _default_user() -> str:
    return (
        os.environ.get("JARVIS_GITHUB_USER")
        or get("github", {}).get("user", "")
    )


def _gh(path: str, method: str = "GET", body: dict = None) -> dict | list:
    token = _token()
    if not token:
        raise RuntimeError("No GitHub token. Set JARVIS_GITHUB_TOKEN env var or config.yaml github.token")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept"       : "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent"   : "Jarvis/1.0",
    }
    data = json.dumps(body).encode() if body else None
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{_API}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read().decode(errors="replace"))
        raise RuntimeError(f"GitHub {e.code}: {err.get('message', e.reason)}")


def _repo_arg(repo: str, user: str = "") -> str:
    """Normalise repo to owner/repo form."""
    if "/" in repo:
        return repo
    owner = user or _default_user()
    if not owner:
        raise RuntimeError("Specify repo as owner/repo or set github.user in config.yaml")
    return f"{owner}/{repo}"


class Plugin(PluginBase):
    priority = 35

    def matches(self, text: str) -> bool:
        # Handled entirely by LLM intent router
        return False

    def run(self, text: str, memory) -> str:
        return "Use natural language — GitHub plugin is intent-routed."

    # ── repos ────────────────────────────────────────────────

    def list_repos(self, limit: int = 10) -> str:
        try:
            repos = _gh(f"/user/repos?sort=updated&per_page={limit}")
            lines = []
            for r in repos:
                priv = "🔒" if r["private"] else "👁️ "
                lines.append(f"{priv} {r['full_name']}  ★{r['stargazers_count']}  {r.get('language') or ''}")
            return "\n".join(lines) or "No repos found."
        except RuntimeError as e:
            return str(e)

    def get_repo(self, repo: str) -> str:
        try:
            r = _gh(f"/repos/{_repo_arg(repo)}")
            return (
                f"{r['full_name']}\n"
                f"  Stars   : {r['stargazers_count']}\n"
                f"  Forks   : {r['forks_count']}\n"
                f"  Lang    : {r.get('language','?')}\n"
                f"  Issues  : {r['open_issues_count']}\n"
                f"  Default : {r['default_branch']}\n"
                f"  URL     : {r['html_url']}"
            )
        except RuntimeError as e:
            return str(e)

    # ── issues ───────────────────────────────────────────────

    def list_issues(self, repo: str, state: str = "open") -> str:
        try:
            issues = _gh(f"/repos/{_repo_arg(repo)}/issues?state={state}&per_page=15")
            issues = [i for i in issues if "pull_request" not in i]  # exclude PRs
            if not issues:
                return f"No {state} issues in {repo}."
            lines = []
            for i in issues:
                lines.append(f"#{i['number']}  [{i['state']}]  {i['title']}")
            return "\n".join(lines)
        except RuntimeError as e:
            return str(e)

    def create_issue(self, repo: str, title: str, body: str = "") -> str:
        try:
            r = _gh(f"/repos/{_repo_arg(repo)}/issues",
                    method="POST", body={"title": title, "body": body})
            return f"Issue created: #{r['number']} — {r['title']}\n{r['html_url']}"
        except RuntimeError as e:
            return str(e)

    def close_issue(self, repo: str, number: int) -> str:
        try:
            r = _gh(f"/repos/{_repo_arg(repo)}/issues/{number}",
                    method="PATCH", body={"state": "closed"})
            return f"Issue #{r['number']} closed."
        except RuntimeError as e:
            return str(e)

    # ── pull requests ──────────────────────────────────────────

    def list_prs(self, repo: str, state: str = "open") -> str:
        try:
            prs = _gh(f"/repos/{_repo_arg(repo)}/pulls?state={state}&per_page=15")
            if not prs:
                return f"No {state} PRs in {repo}."
            lines = []
            for pr in prs:
                lines.append(f"#{pr['number']}  [{pr['state']}]  {pr['title']}  ← {pr['head']['ref']}")
            return "\n".join(lines)
        except RuntimeError as e:
            return str(e)

    # ── commits ───────────────────────────────────────────────

    def list_commits(self, repo: str, branch: str = "", limit: int = 10) -> str:
        try:
            path = f"/repos/{_repo_arg(repo)}/commits?per_page={limit}"
            if branch:
                path += f"&sha={branch}"
            commits = _gh(path)
            lines = []
            for c in commits:
                sha  = c["sha"][:7]
                msg  = c["commit"]["message"].splitlines()[0][:72]
                author = c["commit"]["author"]["name"]
                lines.append(f"{sha}  {author[:16]:<16}  {msg}")
            return "\n".join(lines)
        except RuntimeError as e:
            return str(e)

    # ── branches ──────────────────────────────────────────────

    def list_branches(self, repo: str) -> str:
        try:
            branches = _gh(f"/repos/{_repo_arg(repo)}/branches")
            return "\n".join(f"  {b['name']}" for b in branches) or "No branches."
        except RuntimeError as e:
            return str(e)

    # ── search ────────────────────────────────────────────────

    def search_repos(self, query: str, limit: int = 8) -> str:
        try:
            data = _gh(f"/search/repositories?q={urllib.parse.quote(query)}&per_page={limit}")
            items = data.get("items", [])
            lines = []
            for r in items:
                lines.append(f"★{r['stargazers_count']:<6} {r['full_name']}  {r.get('description','')[:60]}")
            return "\n".join(lines) or "No results."
        except RuntimeError as e:
            return str(e)
