#!/bin/bash
# F-025: Pre-commit hook that refuses to commit sensitive files.
#
# Install via:   scripts/install-git-hooks.sh
# Run manually:  scripts/pre-commit-hook.sh
#
# Blocks:
#   - .env in the repo root (always — even if added with `git add -f`)
#   - Files containing the string PraxisZeit2025! (the old hardcoded default)
#   - Files containing PostgreSQL connection strings with inline passwords
set -euo pipefail

# Files staged for commit
staged=$(git diff --cached --name-only --diff-filter=ACM)

exit_code=0

# --- Hard-block .env in repo root (gitignored, but `git add -f` bypasses ignore) ---
while IFS= read -r f; do
    case "$f" in
        ".env"|"backend/.env"|"frontend/.env")
            echo "error: $f must not be committed. Use .env.example for templates." >&2
            echo "       If you really need to commit this file, use 'git add -f' *after* removing secrets." >&2
            exit_code=1
            ;;
    esac
done <<<"$staged"

# --- Reject known hardcoded defaults ---
if [ -n "$staged" ]; then
    if echo "$staged" | xargs -r git show ":0:" 2>/dev/null | grep -q "PraxisZeit2025!" 2>/dev/null; then
        # Fallback: grep each staged blob
        while IFS= read -r f; do
            [ -z "$f" ] && continue
            if git show ":0:$f" 2>/dev/null | grep -q "PraxisZeit2025!"; then
                echo "error: $f still references the removed default password PraxisZeit2025!" >&2
                exit_code=1
            fi
        done <<<"$staged"
    fi
fi

# --- Reject inline DB connection strings with non-placeholder passwords ---
while IFS= read -r f; do
    [ -z "$f" ] && continue
    # Only scan text files
    case "$f" in
        *.md|*.txt|*.py|*.sh|*.bat|*.ts|*.tsx|*.js|*.jsx|*.yml|*.yaml|*.conf|*.sql|*.env*) ;;
        *) continue ;;
    esac
    if git show ":0:$f" 2>/dev/null | grep -E "postgresql://[^:]+:[^@/]{4,}@" | grep -vE "(CHANGE_ME|example|localhost|127\.0\.0\.1|\\\$\{|\\\$[A-Z]|<[^>]+>)" >&2; then
        echo "error: $f contains a postgresql:// URL with an inline password." >&2
        exit_code=1
    fi
done <<<"$staged"

if [ "$exit_code" -ne 0 ]; then
    echo "" >&2
    echo "Pre-commit hook rejected the commit. Fix the issues above or bypass (not recommended):" >&2
    echo "  git commit --no-verify" >&2
fi

exit "$exit_code"
