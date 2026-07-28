#!/usr/bin/env sh
#
# Publish "Unraid Plugin/" to the public GitHub repo Unraid installs from.
#
# Unraid installs a plugin from a URL that serves the .plg and nothing else, so
# gsmnode.plg has to sit at the root of a repository. This splits the folder out
# into its own commit history — where gsmnode.plg is at the top level — and
# pushes that to GitHub.
#
# The monorepo stays the source of truth. Nothing here is a fork: the split is
# recomputed from scratch every run, so the public repo is always exactly what
# this folder contains.
#
# First run, once:
#   git remote add github-gsmnode-unraid https://github.com/gsmnode/gsmnode-unraid.git
#
# Then, from the repo root:
#   sh scripts/publish-unraid-plugin.sh
#
# A different remote or branch can be passed as the first and second argument.
#
set -eu

PREFIX="Unraid Plugin"
REMOTE="${1:-github-gsmnode-unraid}"
BRANCH="${2:-main}"

cd "$(dirname "$0")/.."

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
	echo "No '$REMOTE' remote. Add it first:" >&2
	echo "  git remote add $REMOTE https://github.com/gsmnode/gsmnode-unraid.git" >&2
	exit 1
fi

# A dirty tree would publish something that is not in any commit.
if ! git diff-index --quiet HEAD -- "$PREFIX"; then
	echo "'$PREFIX' has uncommitted changes. Commit them first." >&2
	exit 1
fi

# The .plg is generated and committed, and it is the thing being published — so
# a stale one would ship the old agent to every server that updates.
echo "Checking the built plugin is current …"
sh "$PREFIX/scripts/build-plg.sh" >/dev/null
if ! git diff --quiet -- "$PREFIX/gsmnode.plg"; then
	git checkout -- "$PREFIX/gsmnode.plg"
	echo "gsmnode.plg is not what source/ builds. Rebuild and commit it first:" >&2
	echo "  sh \"$PREFIX/scripts/build-plg.sh\"" >&2
	exit 1
fi

echo "Splitting '$PREFIX' …"
split_ref=$(git subtree split --prefix="$PREFIX")

echo "Pushing $split_ref -> $REMOTE/$BRANCH"
git push "$REMOTE" "$split_ref:refs/heads/$BRANCH"

version=$(sed -n 's/.*<!ENTITY *version *"\([^"]*\)".*/\1/p' "$PREFIX/gsmnode.plg")

echo
echo "Done. Unraid offers version $version to anyone who already has it installed"
echo "as soon as GitHub serves the new file — no tag or release is needed."
echo
echo "To tag it anyway, so an install can be pinned to this commit:"
echo "  gh release create $version --repo gsmnode/gsmnode-unraid --generate-notes"
