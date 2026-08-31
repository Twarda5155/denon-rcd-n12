#!/usr/bin/env python
"""
commits_per_day.py
==================

Count *your* commits per calendar day across all GitHub repositories you can
see (including private ones), by walking each repository's default branch via
the GitHub GraphQL API.

Authentication piggybacks on the GitHub CLI, so no token handling is needed:
    gh auth login          # once
    gh auth status         # verify

Usage
-----
    python commits_per_day.py --days 365 \
        --email you@example.com --email you@work.example.com

    python commits_per_day.py --since 2026-01-01 --out OUTPUT/commits.csv --plot

Notes / caveats
---------------
* Only the DEFAULT branch of each repo is traversed. Commits living only on
  unmerged feature branches are not counted (GitHub's own contribution graph
  behaves the same way).
* Commits are bucketed by the *local* date of `committedDate`, so the totals
  match what you'd expect from your own timezone rather than UTC.
* Filtering is by author email, not by linked account. That means commits made
  with an email GitHub does not know about are still counted here -- which is
  exactly what you want when auditing attribution problems.
* Forks are skipped by default (--include-forks to keep them).
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from collections import Counter

import requests

GQL_ENDPOINT = "https://api.github.com/graphql"

REPOS_QUERY = """
query($cursor: String) {
  viewer {
    login
    repositories(
      first: 100
      after: $cursor
      affiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]
      orderBy: {field: PUSHED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        isFork
        isArchived
        isEmpty
        defaultBranchRef { name }
      }
    }
  }
}
"""

HISTORY_QUERY = """
query($owner: String!, $name: String!, $since: GitTimestamp!,
      $emails: [String!], $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(since: $since, author: {emails: $emails},
                  first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes { committedDate }
          }
        }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# GitHub plumbing
# ---------------------------------------------------------------------------

def gh_token() -> str:
    """Borrow the token the GitHub CLI already holds."""
    try:
        out = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        sys.exit("gh CLI not found. Install with:  winget install GitHub.cli")
    except subprocess.CalledProcessError:
        sys.exit("gh is not authenticated. Run:  gh auth login")
    return out.stdout.strip()


def gql(session: requests.Session, query: str, variables: dict) -> dict:
    resp = session.post(
        GQL_ENDPOINT,
        json={"query": query, "variables": variables},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


def list_repositories(session: requests.Session, include_forks: bool,
                      include_archived: bool) -> tuple[str, list[str]]:
    repos: list[str] = []
    login = ""
    cursor = None
    while True:
        data = gql(session, REPOS_QUERY, {"cursor": cursor})
        viewer = data["viewer"]
        login = viewer["login"]
        page = viewer["repositories"]
        for node in page["nodes"]:
            if node["isEmpty"] or node["defaultBranchRef"] is None:
                continue
            if node["isFork"] and not include_forks:
                continue
            if node["isArchived"] and not include_archived:
                continue
            repos.append(node["nameWithOwner"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return login, repos


def commit_dates(session: requests.Session, name_with_owner: str,
                 since_iso: str, emails: list[str]) -> list[dt.date]:
    owner, name = name_with_owner.split("/", 1)
    dates: list[dt.date] = []
    cursor = None
    while True:
        data = gql(session, HISTORY_QUERY, {
            "owner": owner, "name": name, "since": since_iso,
            "emails": emails, "cursor": cursor,
        })
        target = (data["repository"] or {}).get("defaultBranchRef") or {}
        target = target.get("target") or {}
        history = target.get("history")
        if not history:
            break
        for node in history["nodes"]:
            stamp = node["committedDate"].replace("Z", "+00:00")
            dates.append(dt.datetime.fromisoformat(stamp).astimezone().date())
        if not history["pageInfo"]["hasNextPage"]:
            break
        cursor = history["pageInfo"]["endCursor"]
    return dates


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=365,
                   help="look back this many days (default: 365)")
    g.add_argument("--since", type=str,
                   help="explicit start date, YYYY-MM-DD")
    p.add_argument("--email", action="append", dest="emails", default=[],
                   help="author email to count; repeat for several. "
                        "Defaults to your git config user.email.")
    p.add_argument("--per-repo", action="store_true",
                   help="also print a per-repository breakdown")
    p.add_argument("--include-forks", action="store_true")
    p.add_argument("--include-archived", action="store_true")
    p.add_argument("--fill-gaps", action="store_true",
                   help="emit rows for days with zero commits too")
    p.add_argument("--out", type=str, help="write CSV to this path")
    p.add_argument("--plot", type=str, nargs="?", const="commits_per_day.png",
                   help="save a bar chart PNG (needs matplotlib)")
    return p.parse_args()


def default_emails() -> list[str]:
    try:
        out = subprocess.run(["git", "config", "--global", "user.email"],
                             capture_output=True, text=True, check=True)
        value = out.stdout.strip()
        return [value] if value else []
    except Exception:
        return []


def main() -> None:
    args = parse_args()

    emails = args.emails or default_emails()
    if not emails:
        sys.exit("No author email. Pass --email or set git config user.email.")

    if args.since:
        start = dt.date.fromisoformat(args.since)
    else:
        start = dt.date.today() - dt.timedelta(days=args.days)
    since_iso = dt.datetime.combine(
        start, dt.time.min).astimezone().isoformat()

    session = requests.Session()
    session.headers.update({
        "Authorization": f"bearer {gh_token()}",
        "Accept": "application/vnd.github+json",
    })

    login, repos = list_repositories(session, args.include_forks,
                                     args.include_archived)
    print(f"Account : {login}")
    print(f"Emails  : {', '.join(emails)}")
    print(f"Since   : {start.isoformat()}")
    print(f"Repos   : {len(repos)}\n")

    totals: Counter[dt.date] = Counter()
    per_repo: Counter[str] = Counter()

    for i, repo in enumerate(repos, 1):
        print(f"  [{i:>3}/{len(repos)}] {repo}", end="\r", flush=True)
        try:
            dates = commit_dates(session, repo, since_iso, emails)
        except Exception as exc:                      # keep going on one bad repo
            print(f"\n  ! {repo}: {exc}")
            continue
        totals.update(dates)
        per_repo[repo] += len(dates)

    print(" " * 78, end="\r")

    if not totals:
        print("No commits found for those emails in that window.")
        print("Tip: run  git log --all --format='%ae' | sort -u  in a repo "
              "to see which emails your commits actually carry.")
        return

    days = sorted(totals)
    if args.fill_gaps:
        span = (days[-1] - days[0]).days
        days = [days[0] + dt.timedelta(d) for d in range(span + 1)]

    rows = [(d, totals.get(d, 0)) for d in days]
    active = [c for _, c in rows if c]

    print(f"{'date':<12}{'commits':>8}")
    print("-" * 20)
    for d, c in rows:
        print(f"{d.isoformat():<12}{c:>8}")

    print("-" * 20)
    print(f"{'total':<12}{sum(active):>8}")
    print(f"{'active days':<12}{len(active):>8}")
    print(f"{'mean/active':<12}{sum(active) / len(active):>8.2f}")
    print(f"{'busiest':<12}{max(rows, key=lambda r: r[1])[0].isoformat():>8}")

    if args.per_repo:
        print("\nPer repository")
        print("-" * 50)
        for repo, n in per_repo.most_common():
            if n:
                print(f"{repo:<40}{n:>8}")

    if args.out:
        import csv
        import os
        parent = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(parent, exist_ok=True)
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["date", "commits"])
            writer.writerows([(d.isoformat(), c) for d, c in rows])
        print(f"\nCSV written: {args.out}")

    if args.plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            sys.exit("matplotlib not installed:  mamba install matplotlib")
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.bar([d for d, _ in rows], [c for _, c in rows], width=1.0)
        ax.set_ylabel("commits")
        ax.set_title(f"Commits per day - {login} (since {start})")
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(args.plot, dpi=150)
        print(f"Chart written: {args.plot}")


if __name__ == "__main__":
    main()
