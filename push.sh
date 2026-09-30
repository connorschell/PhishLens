#!/usr/bin/env bash
# Push PhishLens to GitHub using a token held in a local file, never on the
# command line and never written into .git/config.
#
# Setup once:  put a fine-grained GitHub token in .git_token in this directory.
#              That file is gitignored. See 00_Admin/git-remote-access.md.
# Usage:       ./push.sh [branch]      (default: main)
set -euo pipefail

cd "$(dirname "$0")"
BRANCH="${1:-main}"
TOKEN_FILE=".git_token"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "No $TOKEN_FILE found. See 00_Admin/git-remote-access.md." >&2
  exit 1
fi

TOKEN="$(tr -d ' \t\r\n' < "$TOKEN_FILE")"
if [[ -z "$TOKEN" ]]; then
  echo "$TOKEN_FILE is empty." >&2
  exit 1
fi

REMOTE="$(git remote get-url origin)"
AUTH="Authorization: Basic $(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)"

# The token goes in a request header, not the URL, so it cannot leak into
# error output, the reflog, or .git/config.
git -c http.extraheader="$AUTH" push "$REMOTE" "$BRANCH"
