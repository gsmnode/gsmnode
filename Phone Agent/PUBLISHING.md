# Publishing

How this folder becomes `github.com/gsmnode/phone-agent`.

gsmnode is a monorepo — six surfaces, of which this is one — so the Phone Agent
is split out into a repository of its own rather than moved. That repo is a
public mirror people can clone, watch and release on their own, with
`pubspec.yaml` at the root. The monorepo stays the source of truth.

## One-time GitHub setup

1. Create **`gsmnode/phone-agent`**, public. Ideally with nothing added — no
   README, no `.gitignore`, no license — because this folder supplies all three.

   If GitHub's "Add a license" or "Add a README" box was ticked, the repository
   already has an `Initial commit` that shares no history with the split, and
   the first push is rejected as non-fast-forward. Replace it once:

   ```sh
   git fetch github-phone-agent main                        # look at what is there first
   git subtree split --prefix="Phone Agent" \
     | xargs -I{} git push --force github-phone-agent {}:refs/heads/main
   ```

   Only ever for that first push, and only after confirming the commit being
   discarded is GitHub's generated one and nothing else.
2. Set the repository **description**. Suggested:
   *"gsmnode gateway agent for Android — turns a phone into the SMS/MMS and call
   endpoint the API Server drives."*
3. Add **topics**: `gsmnode`, `flutter`, `android`, `sms`, `mms`, `gsm`,
   `sms-gateway`.

## Publish

From the monorepo root, once:

```sh
git remote add github-phone-agent https://github.com/gsmnode/phone-agent.git
```

Then, whenever this folder changes and is committed:

```sh
sh scripts/publish-phone-agent.sh
```

That recomputes the split from scratch and pushes it, so the public repository
is always exactly what this folder contains. Because the split is deterministic,
repeated runs fast-forward rather than conflict — *unless* commits were made on
GitHub directly (a merged pull request, say), which have no counterpart here.
Merge those into the monorepo first; otherwise the push is rejected, and forcing
it would drop them.

Note the `android_overlay/` folder travels with the split, so the native SMS/MMS
and call bridge is reproducible from the published repo exactly as it is here —
see the README's *Set up* section.

## Build a production version

The app is Flutter. From this folder:

```sh
flutter build apk --release        # build/app/outputs/flutter-apk/app-release.apk
flutter build appbundle --release  # build/app/outputs/bundle/release/app-release.aab
```

An APK is what people sideload from a GitHub release; an AAB (App Bundle) is
what Google Play requires.

### Release signing

Release builds are signed with your own upload key when
`android/key.properties` is present, and fall back to debug signing when it is
not (so `flutter run --release` works out of the box). A debug-signed APK is
fine for sideloading; Google Play rejects it.

To sign for real:

1. Generate an upload keystore **once**, keep it outside the repo and back it
   up — losing it means you can no longer update the Play listing:

   ```sh
   keytool -genkey -v -keystore gsmnode-upload.jks \
     -keyalg RSA -keysize 2048 -validity 10000 -alias upload
   ```
2. Copy `android/key.properties.example` to `android/key.properties` and fill
   in the passwords, alias and `storeFile` path.

`key.properties`, `*.jks` and `*.keystore` are gitignored — never commit them,
this repo is public.

## Publish to Google Play

1. Build a signed AAB (`flutter build appbundle --release`).
2. In the Play Console, create the app under the `app.gsmnode.phoneagent`
   application id, complete the store listing, and upload the `.aab` — roll out
   to an internal-testing track first.

## Cut a release

The app's version is `version` in `pubspec.yaml` (`major.minor.patch+build`).

1. Bump `version` in `pubspec.yaml`.
2. Commit, then `sh scripts/publish-phone-agent.sh`.
3. Tag the pushed commit on GitHub and publish a release from it, attaching the
   built APK if there is one:

   ```sh
   gh release create v1.0.0 --repo gsmnode/phone-agent --generate-notes
   ```

   Keep the tag and the pubspec `version` in step.
