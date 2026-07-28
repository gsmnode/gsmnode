#!/usr/bin/env sh
#
# Publish "Phone App/" to its own public GitHub repo.
#
# gsmnode is a monorepo — six surfaces, of which this is one. The Phone App gets
# a repository of its own so it can be cloned, watched and released on its own,
# with pubspec.yaml at the root, rather than making people check out the whole
# tree. This splits the folder out into its own commit history — where
# pubspec.yaml is at the top level — and pushes that to GitHub.
#
# The monorepo stays the source of truth. Nothing here is a fork: the split is
# recomputed from scratch every run, so the public repo is always exactly what
# this folder contains.
#
# First run, once:
#   git remote add github-phone-app https://github.com/gsmnode/phone-app.git
#
# Then, from the repo root:
#   sh scripts/publish-phone-app.sh
#
# A different remote or branch can be passed as the first and second argument.
#
set -eu

PREFIX="Phone App"
REMOTE="${1:-github-phone-app}"
BRANCH="${2:-main}"

cd "$(dirname "$0")/.."

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
	echo "No '$REMOTE' remote. Add it first:" >&2
	echo "  git remote add $REMOTE https://github.com/gsmnode/phone-app.git" >&2
	exit 1
fi

# A dirty tree would publish something that is not in any commit.
if ! git diff-index --quiet HEAD -- "$PREFIX"; then
	echo "'$PREFIX' has uncommitted changes. Commit them first." >&2
	exit 1
fi

echo "Splitting '$PREFIX' …"
split_ref=$(git subtree split --prefix="$PREFIX")

echo "Pushing $split_ref -> $REMOTE/$BRANCH"
git push "$REMOTE" "$split_ref:refs/heads/$BRANCH"

version=$(sed -n 's/^version: *\([^+[:space:]]*\).*/\1/p' "$PREFIX/pubspec.yaml")

echo
echo "Done. To cut a GitHub release (with the APK attached, if one was built):"
echo "  gh release create v$version --repo gsmnode/phone-app --generate-notes"
echo "Keep the tag and the pubspec 'version' in step."
