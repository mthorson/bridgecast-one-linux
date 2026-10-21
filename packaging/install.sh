#!/bin/sh
set -eu

bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
data_dir=${XDG_DATA_HOME:-"$HOME/.local/share"}
app_dir=$data_dir/bridgecast-one-linux
desktop_dir=$data_dir/applications

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import PyQt6.QtCore' >/dev/null 2>&1; then
    printf '%s\n' 'Python 3 with PyQt6 is required. Install it with your distribution package manager or pip.' >&2
    exit 1
fi
if ! command -v amidi >/dev/null 2>&1; then
    printf '%s\n' 'The ALSA amidi command is required. Install your distribution’s alsa-utils package.' >&2
    exit 1
fi
if ! python3 -c 'import ctypes.util, sys; sys.exit(0 if ctypes.util.find_library("asound") else 1)' >/dev/null 2>&1; then
    printf '%s\n' 'The libasound shared library is required. Install your distribution’s ALSA library package.' >&2
    exit 1
fi

mkdir -p "$app_dir/assets" "$desktop_dir"
install -m 644 "$bundle_dir/bridgecast_gui.py" "$bundle_dir/bridgecast_protocol.py" "$bundle_dir/bridgecast_qt.py" "$app_dir/"
install -m 644 "$bundle_dir/assets/"*.png "$app_dir/assets/"

cat > "$desktop_dir/bridgecast-one-linux.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=BRIDGE CAST ONE for Linux
Comment=Configure the BRIDGE CAST ONE device mixer
Exec=python3 "$app_dir/bridgecast_gui.py"
Icon=$app_dir/assets/bridgecast-linux-icon.png
Terminal=false
Categories=AudioVideo;Audio;
EOF

printf 'Installed BRIDGE CAST ONE for Linux in %s\n' "$app_dir"
printf 'Desktop launcher: %s\n' "$desktop_dir/bridgecast-one-linux.desktop"
