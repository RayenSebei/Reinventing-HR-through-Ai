"""DL-06: scan tracked files (and optionally the whole git history) for committed secrets.

Stdlib only. Patterns are specific to real credential formats to keep false alarms low.
Usage (repository root):  python -m tools.secret_scan [--history] [--path DIR]
Exit code 1 if anything is found. Output shows file and line, never the matched value.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    "private key block": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    "AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "OpenAI/Anthropic-style API key": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{24,}\b"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "Vouch secret set in a file": re.compile(
        r"\bVOUCH_(?:JWT_SECRET|N8N_HMAC_SECRET|OPENAI_API_KEY)\s*[=:]\s*['\"]?(?!<|\$|\{|['\"]?\s*$)[^\s'\"#]{8,}"),
}
SKIP_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".zip", ".db"}
SKIP_FILES = {"tools/secret_scan.py", "vouch/tests/test_secret_scan.py"}


def scan_text(text: str) -> list[tuple[int, str]]:
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for name, rx in PATTERNS.items():
            if rx.search(line):
                hits.append((i, name))
    return hits


def tracked_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=str(root), capture_output=True, text=True, check=True).stdout
        return [root / p for p in out.splitlines()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]


def scan_tree(root: Path) -> list[str]:
    found = []
    for f in tracked_files(root):
        rel = f.relative_to(root).as_posix()
        if f.suffix.lower() in SKIP_SUFFIXES or rel in SKIP_FILES or not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found += [f"{rel}:{ln}: {name}" for ln, name in scan_text(text)]
    return found


def scan_history(root: Path) -> list[str]:
    try:
        log = subprocess.run(["git", "log", "-p", "--all", "--no-color", "--format=commit %H"], cwd=str(root),
                             capture_output=True, text=True, errors="replace", check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ["git history not available"]
    found, commit, path = [], "?", "?"
    for line in log.splitlines():
        if line.startswith("commit "):
            commit = line[7:15]
        elif line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++") and path not in SKIP_FILES:
            for _, name in scan_text(line[1:]):
                found.append(f"history {commit} {path}: {name}")
    return sorted(set(found))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--path", default=str(Path(__file__).resolve().parents[1]))
    a = ap.parse_args(argv)
    root = Path(a.path)
    found = scan_tree(root) + (scan_history(root) if a.history else [])
    for f in found:
        print("SECRET?", f)
    print(f"secret scan: {len(found)} finding(s){' (tree + history)' if a.history else ' (tree)'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
