#!/usr/bin/env bash
# Rewrites Git history to remove a personal e-mail address.
# Tested on a mirror clone of this repository: gmail hits 0, final tree identical.
# NOTHING is pushed by this script. Read the output, then push manually (step 6 in the guide).
set -euo pipefail

REPO_URL="https://github.com/karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture.git"
WORK="$HOME/history-rewrite"
BAD_EMAIL="kareemrabie2020@gmail.com"
GOOD_NAME="Karim Rabie"
GOOD_EMAIL="139635577+karimrabiee@users.noreply.github.com"

FILTER_PYTHON="/mnt/c/Users/karee/AppData/Local/Microsoft/WindowsApps/python.exe"

if [[ ! -f "$FILTER_PYTHON" ]]; then
    FILTER_PYTHON="$(command -v python3 || command -v python || true)"
fi

if [[ -z "$FILTER_PYTHON" ]] || ! "$FILTER_PYTHON" -m git_filter_repo -h >/dev/null 2>&1; then
    echo "git-filter-repo is not available to the selected Python interpreter."
    echo "Check Python paths from PowerShell and Git Bash."
    exit 1
fi

git-filter-repo() {
    "$FILTER_PYTHON" -m git_filter_repo "$@"
}

rm -rf "$WORK" && mkdir -p "$WORK" && cd "$WORK"

# 0. Backup (a full mirror you can always push back)
git clone --mirror "$REPO_URL" backup.git
cp -r backup.git rewrite.git
cd rewrite.git

cat > ../mailmap.txt <<MAP
$GOOD_NAME <$GOOD_EMAIL> <$BAD_EMAIL>
$GOOD_NAME <139635577+kareemrabiee@users.noreply.github.com>
MAP
echo "$BAD_EMAIL==>REDACTED" > ../replace.txt

# 1. Rewrite authors/committers, file contents and commit messages
git filter-repo --mailmap ../mailmap.txt --replace-text ../replace.txt --replace-message ../replace.txt --force

# 2. Verify
echo "--- identities after rewrite"
git log --all --format='%an <%ae> | %cn <%ce>' | sort | uniq -c
echo "--- files in any commit still containing the e-mail (expect 0)"
for c in $(git rev-list --all); do git grep -lI "$BAD_EMAIL" "$c" 2>/dev/null || true; done | wc -l
echo "--- main tree identical to the original? (expect no diff output)"
cd .. && git clone -q backup.git cmp_old && git clone -q rewrite.git cmp_new
diff -rq --exclude=.git cmp_old cmp_new && echo "IDENTICAL"
echo
echo "Rewrite is ready in: $WORK/rewrite.git  (backup in $WORK/backup.git)"
echo "Nothing was pushed."
