# Publishing

How this folder becomes `github.com/gsmnode/gsmnode-unraid`, and how people
find it from Unraid.

Unraid installs a plugin from a URL that must serve the `.plg` and nothing else,
and Community Applications reads the same URL. gsmnode is a monorepo — seven
surfaces, of which this is one — so the plugin is split out into a repository of
its own rather than moved. `gsmnode.plg` sits at the root of this folder, which
is the root of that repository, which makes the install URL:

```
https://raw.githubusercontent.com/gsmnode/gsmnode-unraid/main/gsmnode.plg
```

That URL is baked into the plugin as its `pluginURL`, which is where **Update**
looks. Moving the repository breaks updates for everyone who already installed
it, so pick the name once.

## One-time GitHub setup

1. Create **`gsmnode/gsmnode-unraid`**, public. Ideally with nothing added
   — no README, no `.gitignore`, no license — because this folder supplies all
   three.

   If GitHub's "Add a license" or "Add a README" box was ticked, the repository
   already has an `Initial commit` that shares no history with the split, and
   the first push is rejected as non-fast-forward. Replace it once:

   ```sh
   git fetch github-gsmnode-unraid main                    # look at what is there first
   git subtree split --prefix="Unraid Plugin" \
     | xargs -I{} git push --force github-gsmnode-unraid {}:refs/heads/main
   ```

   Only ever for that first push, and only after confirming the commit being
   discarded is GitHub's generated one and nothing else.
2. Set the repository **description**. Community Applications shows it. Suggested:
   *"Unraid notification agent for gsmnode — send Unraid notifications as SMS
   through an Android phone."*
3. Add **topics**: `unraid`, `unraid-plugin`, `notifications`, `sms`, `gsm`,
   `sms-gateway`, `android`.
4. Leave **Issues enabled** — the plugin's `support` attribute points at the
   monorepo's, but people will open them here regardless.

## Publish

From the monorepo root, once:

```sh
git remote add github-gsmnode-unraid https://github.com/gsmnode/gsmnode-unraid.git
```

Then, whenever this folder changes and is committed:

```sh
sh scripts/publish-unraid-plugin.sh
```

That recomputes the split from scratch and pushes it, so the public repository
is always exactly what this folder contains. Because the split is deterministic,
repeated runs fast-forward rather than conflict — *unless* commits were made on
GitHub directly (a merged pull request, say), which have no counterpart here.
Merge those into the monorepo first; otherwise the push is rejected, and forcing
it would drop them.

## Cut a release

Unraid compares the `version` entity in the installed `.plg` against the one it
fetches from `pluginURL`, and offers an update when the fetched one sorts higher.
Nothing else is consulted — no tags, no GitHub releases.

So a release is: bump the version, rebuild, commit, push.

1. Edit `source/gsmnode.plg.in`:
   - `<!ENTITY version "YYYY.MM.DD">` — the date format Unraid sorts by.
   - Add a `###YYYY.MM.DD` section at the top of `<CHANGES>`. That is what the
     Plugins tab shows when someone asks what an update did.
2. Rebuild and check it:

   ```sh
   sh scripts/build-plg.sh
   python -m unittest discover tests
   ```

   The tests fail if `gsmnode.plg` is stale, if the changelog does not name the
   new version, or if the version is not in the date format.
3. Commit, then `sh scripts/publish-unraid-plugin.sh`.

A GitHub release is optional and changes nothing about updates, but tagging is
worth it so an install URL can be pinned to a commit if one ever needs to be:

```sh
gh release create 2026.07.24 --repo gsmnode/gsmnode-unraid --generate-notes
```

## Get it into Community Applications

CA is where Unraid users actually look. It is fed by the
[Community Applications Appfeed](https://github.com/Squidly271/AppFeed), and a
plugin joins it through a template.

1. Publish, and confirm the raw URL above serves the `.plg` and that installing
   from it works on a real server.
2. Write a CA template — an XML file naming the plugin, its `pluginURL`, an icon
   URL, a category (`Productivity:` / `Tools:Utilities`) and the description.
3. Open a pull request against the Appfeed repository adding it.

Until that merges, the raw URL in the README installs it fine — that is the
normal way Unraid plugins are shared, and it needs nothing from anyone.

## Test it on a real server first

Nothing here can be verified from the monorepo. Before publishing a version:

1. Copy `gsmnode.plg` onto the server's flash drive, and install it by path
   rather than URL — **Plugins → Install Plugin** takes
   `/boot/config/plugins/gsmnode.plg`. That installs the file you built, not
   whatever GitHub is serving.
2. Check the row appears under **Settings → Notifications → Notification
   Agents**, with its icon.
3. Fill it in, **Apply**, **Test** — an SMS should arrive.
4. Reboot, and check the row is still there. That is the one thing only a real
   server proves: `/usr/local/emhttp` is a RAM disk, and the row coming back
   depends on Unraid reinstalling the plugin at boot.
5. Uninstall, and check the agent is gone from **Notification Agents** too.
