#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
version=$(sed -n 's/^APP_VERSION = "\([^"]*\)"$/\1/p' "$repo_dir/bridgecast_qt.py")
if [[ -z "$version" ]]; then
    printf '%s\n' 'Could not read APP_VERSION from bridgecast_qt.py' >&2
    exit 1
fi

tag="v$version"
git -C "$repo_dir" rev-parse --verify "refs/tags/$tag" >/dev/null
build_dir=$(mktemp -d)
trap 'rm -rf -- "$build_dir"' EXIT
bundle_name="bridgecast-one-linux-$version"
bundle_dir="$build_dir/$bundle_name"
mkdir -p "$bundle_dir" "$repo_dir/dist"

git -C "$repo_dir" archive "$tag" \
    bridgecast_gui.py bridgecast_protocol.py bridgecast_qt.py README.md requirements.txt assets \
    | tar -x -C "$bundle_dir"
install -m 755 "$repo_dir/packaging/install.sh" "$bundle_dir/install.sh"

timestamp=$(git -C "$repo_dir" show -s --format=%ct "$tag^{commit}")
output="$repo_dir/dist/$bundle_name-linux.tar.gz"
tar -C "$build_dir" --sort=name --owner=0 --group=0 --numeric-owner --mtime="@$timestamp" \
    -cf - "$bundle_name" | gzip -n > "$output"
sha256sum "$output"

if command -v makepkg >/dev/null 2>&1; then
    arch_dir="$build_dir/arch"
    mkdir -p "$arch_dir"
    cp "$output" "$arch_dir/"
    archive_sha=$(sha256sum "$output" | cut -d ' ' -f 1)
    sed -e "s/@VERSION@/$version/g" -e "s/@SHA256@/$archive_sha/g" \
        "$repo_dir/packaging/arch/PKGBUILD.in" > "$arch_dir/PKGBUILD"
    (cd "$arch_dir" && makepkg --cleanbuild --noconfirm)
    cp "$arch_dir"/bridgecast-one-linux-"$version"-1-any.pkg.tar.zst "$repo_dir/dist/"
    sha256sum "$repo_dir/dist/bridgecast-one-linux-$version-1-any.pkg.tar.zst"
fi
