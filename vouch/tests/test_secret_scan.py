"""DL-06: the secret scanner finds a planted fake key, in the tree and in git history, and stays
quiet on a clean tree. Planted values are fake and assembled at runtime so this file holds none."""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import secret_scan  # noqa: E402

FAKE_AWS = "AKIA" + "Z" * 16
FAKE_HMAC_LINE = "VOUCH_N8N_HMAC_SECRET=" + "q7" * 20


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "PATH": __import__("os").environ["PATH"]})


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "README.md").write_text("clean\n")
    (tmp_path / ".env.example").write_text("VOUCH_N8N_HMAC_SECRET=<generate-a-long-random-string>\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "clean")
    return tmp_path


def test_clean_tree_has_no_findings(repo):
    assert secret_scan.main(["--path", str(repo), "--history"]) == 0


def test_planted_key_in_tree_is_found(repo):
    (repo / "config.py").write_text(f'KEY = "{FAKE_AWS}"\n')
    _git(repo, "add", ".")
    assert secret_scan.main(["--path", str(repo)]) == 1


def test_key_removed_from_tree_is_still_found_in_history(repo):
    (repo / "settings.env").write_text(FAKE_HMAC_LINE + "\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "oops")
    (repo / "settings.env").write_text("VOUCH_N8N_HMAC_SECRET=\n")
    _git(repo, "commit", "-q", "-am", "remove")
    assert secret_scan.main(["--path", str(repo)]) == 0
    assert secret_scan.main(["--path", str(repo), "--history"]) == 1


def test_this_repository_is_clean():
    assert secret_scan.main(["--path", str(REPO)]) == 0


def test_allow_list_skips_only_the_named_commit_and_file(repo):
    for name in ("settings.env", "other.env"):
        (repo / name).write_text(FAKE_HMAC_LINE + "\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "two files")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    found = secret_scan.scan_history(repo, allow={(head[:8], "settings.env")})
    assert len(found) == 1 and "other.env" in found[0]
