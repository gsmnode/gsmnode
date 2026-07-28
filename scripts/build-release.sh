#!/usr/bin/env sh
#
# Build signed release artifacts for the phone apps.
#
# For each app this produces both:
#   - an APK, for sideloading / attaching to a GitHub release
#   - an AAB (App Bundle), for uploading to Google Play
#
# Signing comes from each app's android/key.properties (see
# android/key.properties.example). If that file is absent the build falls back
# to debug signing — fine for sideloading, rejected by Google Play — and this
# script warns about it.
#
# From the repo root:
#   sh scripts/build-release.sh                 # both apps
#   sh scripts/build-release.sh "Phone Agent"   # one app
#
set -eu

cd "$(dirname "$0")/.."

build_app() {
	app="$1"

	if [ ! -d "$app" ]; then
		echo "No '$app' folder at the repo root." >&2
		exit 1
	fi

	version=$(sed -n 's/^version: *\(.*\)/\1/p' "$app/pubspec.yaml")
	echo "==> $app ($version)"

	if [ ! -f "$app/android/key.properties" ]; then
		echo "    WARNING: $app/android/key.properties not found — building with" >&2
		echo "    debug signing. Google Play will reject the AAB. See" >&2
		echo "    $app/android/key.properties.example to set up release signing." >&2
	fi

	( cd "$app" && flutter build apk --release && flutter build appbundle --release )

	echo "    APK: $app/build/app/outputs/flutter-apk/app-release.apk"
	echo "    AAB: $app/build/app/outputs/bundle/release/app-release.aab"
	echo
}

if [ "$#" -ge 1 ]; then
	build_app "$1"
else
	build_app "Phone Agent"
	build_app "Phone App"
fi

echo "Done."
