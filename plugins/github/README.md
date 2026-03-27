# GitHub Plugin

Talk to GitHub in natural language. Uses stdlib `urllib` only.

## Setup

```yaml
# config.yaml
jarvis:
  github:
    token: ghp_your_token_here   # or set JARVIS_GITHUB_TOKEN env var
    user: shahil-sk              # default owner for short repo names
```

Or:
```bash
export JARVIS_GITHUB_TOKEN=ghp_your_token
export JARVIS_GITHUB_USER=shahil-sk
```

## What You Can Say

```
show my repos
show repo jarvis
list open issues in jarvis
create issue in jarvis: auth bug on login page
close issue 3 in jarvis
show open PRs in jarvis
latest commits on jarvis
branches in jarvis
search github for fast sqlite orm python
```

## Token Scopes Needed
- `repo` — for private repos, issues, PRs
- `public_repo` — for public repos only
