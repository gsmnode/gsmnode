# Publishing

How this folder becomes `github.com/gsmnode/phone-app`.

gsmnode is a monorepo — six surfaces, of which this is one — so the Phone App is
split out into a repository of its own rather than moved. That repo is a public
mirror people can clone, watch and release on their own, with `pubspec.yaml` at
the root. The monorepo stays the source of truth.

## One-time GitHub setup

1. Create **`gsmnode/phone-app`**, public. Ideally with nothing added — no
   README, no `.gitignore`, no license — because this folder supplies all three.

   If GitHub's "Add a license" or "Add a README" box was ticked, the repository
   already has an `Initial commit` that shares no history with the split, and
   the first push is rejected as non-fast-forward. Replace it once:

   ```sh
   git fetch github-phone-app main                        # look at what is there first
   git subtree split --prefix="Phone App" \
     | xargs -I{} git push --force github-phone-app {}:refs/heads/main
   ```

   Only ever for that first push, and only after confirming the commit being
   discarded is GitHub's generated one and nothing else.
2. Set the repository **description**. Suggested:
   *"gsmnode console for Android — a mobile mirror of the Web App: send SMS, MMS
   and calls, and manage devices, users and integrations."*
3. Add **topics**: `gsmnode`, `flutter`, `android`, `sms`, `mms`, `gsm`,
   `sms-gateway`.

## Publish

From the monorepo root, once:

```sh
git remote add github-phone-app https://github.com/gsmnode/phone-app.git
```

Then, whenever this folder changes and is committed:

```sh
sh scripts/publish-phone-app.sh
```

That recomputes the split from scratch and pushes it, so the public repository
is always exactly what this folder contains. Because the split is deterministic,
repeated runs fast-forward rather than conflict — *unless* commits were made on
GitHub directly (a merged pull request, say), which have no counterpart here.
Merge those into the monorepo first; otherwise the push is rejected, and forcing
it would drop them.

## Cut a release

The app's version is `version` in `pubspec.yaml` (`major.minor.patch+build`).

1. Bump `version` in `pubspec.yaml`.
2. Commit, then `sh scripts/publish-phone-app.sh`.
3. Tag the pushed commit on GitHub and publish a release from it, attaching the
   built APK if there is one:

   ```sh
   gh release create v1.0.0 --repo gsmnode/phone-app --generate-notes
   ```

   Keep the tag and the pubspec `version` in step.
