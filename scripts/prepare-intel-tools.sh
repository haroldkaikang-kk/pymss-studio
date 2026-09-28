#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
DEST="$ROOT/intel-build/bin"
WORK="$ROOT/intel-build/audio-tools"
mkdir -p "$DEST" "$WORK"
export MACOSX_DEPLOYMENT_TARGET=12.0

download_checked() {
  local url="$1" hash="$2" destination="$3"
  curl --fail --location --silent --show-error --retry 5 --max-time 300 -o "$destination" "$url"
  [[ "$(shasum -a 256 "$destination" | awk '{print $1}')" == "$hash" ]] || {
    echo "Checksum mismatch: $url" >&2; exit 1;
  }
}

for name in ffmpeg ffprobe; do
  if [[ "$name" == ffmpeg ]]; then
    hash=7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4
  else
    hash=2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd
  fi
  download_checked "https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/$name.zip" "$hash" "$WORK/$name.zip"
  mkdir -p "$WORK/$name"
  ditto -x -k "$WORK/$name.zip" "$WORK/$name"
  source="$(find "$WORK/$name" -type f -name "$name" -print -quit)"
  install -m 755 "$source" "$DEST/$name"
done

# The upstream prebuilt aria2 requires macOS 15. Build against Apple's system
# libraries to avoid carrying Homebrew libraries with newer deployment targets.
ARIA_URL=https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0.tar.xz
ARIA_SHA=60a420ad7085eb616cb6e2bdf0a7206d68ff3d37fb5a956dc44242eb2f79b66b
download_checked "$ARIA_URL" "$ARIA_SHA" "$WORK/aria2.tar.xz"
tar -xJf "$WORK/aria2.tar.xz" -C "$WORK"
SDK="$(xcrun --sdk macosx --show-sdk-path)"
(
  cd "$WORK/aria2-1.37.0"
  export CC="$(xcrun -f clang)" CXX="$(xcrun -f clang++)"
  export CFLAGS="-O2 -arch x86_64 -mmacosx-version-min=12.0 -isysroot $SDK"
  export CXXFLAGS="$CFLAGS" LDFLAGS="-arch x86_64 -mmacosx-version-min=12.0 -isysroot $SDK"
  export PKG_CONFIG_LIBDIR="$WORK/empty-pkgconfig"
  export ZLIB_CFLAGS="-isysroot $SDK" ZLIB_LIBS=-lz
  export EXPAT_CFLAGS="-isysroot $SDK" EXPAT_LIBS=-lexpat
  export SQLITE3_CFLAGS="-isysroot $SDK" SQLITE3_LIBS=-lsqlite3
  ./configure --disable-nls --with-appletls --without-openssl --without-gnutls \
    --without-libgcrypt --without-libnettle --without-libgmp --without-libssh2 \
    --without-libcares --without-libxml2 --with-libexpat --with-sqlite3
  make -j "$(sysctl -n hw.logicalcpu)"
  install -m 755 src/aria2c "$DEST/aria2c"
  cp COPYING "$DEST/ARIA2-COPYING.txt"
)
for name in ffmpeg ffprobe aria2c; do
  codesign --force --sign - --timestamp=none "$DEST/$name"
  "$DEST/$name" --version >/dev/null 2>&1 || "$DEST/$name" -version >/dev/null
done
python3 scripts/audit-intel-macos.py "$DEST" > intel-build/audio-tools-audit.json
cat > "$DEST/THIRD_PARTY_TOOLS.txt" <<EOF
FFmpeg and ffprobe 9.0.2: https://ffmpeg.martin-riedl.de/
Project and license: https://ffmpeg.org/legal.html
aria2 1.37.0 built for x86_64 macOS 12.0 using AppleTLS, system zlib,
Expat and SQLite. Source: $ARIA_URL
Source SHA-256: $ARIA_SHA
License: ARIA2-COPYING.txt (GPL v2 or later).
EOF
