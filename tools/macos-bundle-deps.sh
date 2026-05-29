#!/usr/bin/env bash
# macos-bundle-deps.sh — macht ein macOS-Release-Tarball self-contained.
#
# PROBLEM (#183): Die theseus-PostgreSQL-Binaries linken gegen Homebrew-OpenSSL
# (/opt/homebrew bzw. /usr/local .../openssl@3/lib/lib{ssl,crypto}.3.dylib) und
# teils gegen die Build-Runner-Pfade (/Users/runner/.../lib/...). Auf einem
# sauberen Kunden-Mac fehlen die → postgres startet nicht, Backups scheitern.
#
# Diese Lösung bündelt libssl.3/libcrypto.3 ins Paket (bin/postgresql/lib/) und
# schreibt ALLE betroffenen Load-Commands auf @loader_path um, danach wird jede
# geänderte Mach-O-Datei ad-hoc neu signiert (auf Apple Silicon Pflicht, sonst
# kill durch den Kernel).
#
# MUSS AUF macOS LAUFEN (braucht install_name_tool + codesign + Homebrew openssl@3
# auf der BUILD-Maschine; der Kunden-Mac braucht danach nichts mehr).
#
# Usage:
#   brew install openssl@3
#   bash tools/macos-bundle-deps.sh dist/praxiszeit-1.8.0-macos-arm64.tar.gz
#   bash tools/macos-bundle-deps.sh dist/praxiszeit-1.8.0-macos-x64.tar.gz
# Ergebnis: <tarball> wird IN PLACE ersetzt (Backup als <tarball>.orig).
set -euo pipefail

[ "$(uname -s)" = "Darwin" ] || { echo "FEHLER: nur auf macOS lauffähig (install_name_tool/codesign)." >&2; exit 1; }
command -v install_name_tool >/dev/null || { echo "FEHLER: install_name_tool fehlt (Xcode Command Line Tools)." >&2; exit 1; }
command -v codesign >/dev/null || { echo "FEHLER: codesign fehlt." >&2; exit 1; }

TARBALL="${1:?Usage: macos-bundle-deps.sh <macos-tarball.tar.gz>}"
[ -f "$TARBALL" ] || { echo "FEHLER: $TARBALL nicht gefunden." >&2; exit 1; }

OSSL_PREFIX="$(brew --prefix openssl@3 2>/dev/null || true)"
[ -n "$OSSL_PREFIX" ] && [ -d "$OSSL_PREFIX/lib" ] || {
    echo "FEHLER: openssl@3 nicht via Homebrew gefunden — 'brew install openssl@3'." >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
echo "==> Entpacke $TARBALL"
tar xzf "$TARBALL" -C "$WORK"

PGLIB="$WORK/bin/postgresql/lib"
[ -d "$PGLIB" ] || { echo "FEHLER: bin/postgresql/lib/ nicht im Tarball." >&2; exit 1; }

echo "==> Bündele OpenSSL aus $OSSL_PREFIX/lib"
for d in libssl.3.dylib libcrypto.3.dylib; do
    cp -f "$OSSL_PREFIX/lib/$d" "$PGLIB/$d"
    chmod u+w "$PGLIB/$d"
done

# IDs + Interdependenz der gebündelten OpenSSL-Libs auf @loader_path setzen.
install_name_tool -id "@loader_path/libcrypto.3.dylib" "$PGLIB/libcrypto.3.dylib"
install_name_tool -id "@loader_path/libssl.3.dylib"    "$PGLIB/libssl.3.dylib"
# libssl referenziert libcrypto über den Homebrew-Pfad → umbiegen:
_ssl_crypto_dep="$(otool -L "$PGLIB/libssl.3.dylib" | awk '/libcrypto\.3\.dylib/{print $1; exit}')"
[ -n "$_ssl_crypto_dep" ] && install_name_tool -change "$_ssl_crypto_dep" "@loader_path/libcrypto.3.dylib" "$PGLIB/libssl.3.dylib"

# Alle Mach-O-Dateien in bin/ + lib/ einsammeln und schlechte Deps umschreiben.
# (portabel für macOS-bash 3.2 — kein mapfile/readarray)
MACHO=()
while IFS= read -r f; do MACHO+=("$f"); done < <(
    find "$WORK/bin/postgresql/bin" "$PGLIB" -type f 2>/dev/null \
    | while read -r ff; do file "$ff" | grep -q 'Mach-O' && echo "$ff"; done
)

relto_lib() {  # @loader_path-relativer Pfad von Datei $1 ins lib/-Verzeichnis
    python3 -c "import os,sys;print(os.path.relpath(sys.argv[1], os.path.dirname(sys.argv[2])))" "$PGLIB" "$1"
}

echo "==> Schreibe Load-Commands um (${#MACHO[@]} Mach-O-Dateien)"
for f in "${MACHO[@]}"; do
    chmod u+w "$f"
    rel="$(relto_lib "$f")"           # z.B. "../lib" (bin/) oder "." (lib/)
    changed=0
    # Jede „schlechte" Dependency (Homebrew-OpenSSL, /usr/local, Build-Runner) -> @loader_path
    while read -r dep; do
        case "$dep" in
            /opt/homebrew/*|/usr/local/opt/*|/Users/runner/*)
                base="$(basename "$dep")"
                install_name_tool -change "$dep" "@loader_path/$rel/$base" "$f"
                changed=1
                ;;
        esac
    done < <(otool -L "$f" | tail -n +2 | awk '{print $1}')
    [ "$changed" = 1 ] && codesign --force --sign - "$f" >/dev/null 2>&1 || true
done

# Auch die frisch gebündelten OpenSSL-Libs signieren (IDs wurden geändert).
codesign --force --sign - "$PGLIB/libcrypto.3.dylib" "$PGLIB/libssl.3.dylib" >/dev/null 2>&1 || true

echo "==> Verifiziere: keine externen Pfade mehr"
BAD=0
for f in "${MACHO[@]}" "$PGLIB/libssl.3.dylib" "$PGLIB/libcrypto.3.dylib"; do
    if otool -L "$f" | tail -n +2 | awk '{print $1}' | grep -qE '^(/opt/homebrew|/usr/local/opt|/Users/runner)'; then
        echo "  ✗ $(basename "$f") referenziert noch externe Pfade:" >&2
        otool -L "$f" | grep -E '/opt/homebrew|/usr/local/opt|/Users/runner' >&2
        BAD=1
    fi
done
[ "$BAD" = 0 ] || { echo "FEHLER: externe Referenzen verbleiben — Tarball NICHT ersetzt." >&2; exit 1; }
echo "  ✓ alle Referenzen sind @loader_path oder /usr/lib-System-Libs"

echo "==> Verifiziere: postgres + initdb starten (--version)"
PG="$WORK/bin/postgresql"
DYLD_LIBRARY_PATH="$PG/lib" "$PG/bin/postgres" --version
DYLD_LIBRARY_PATH="$PG/lib" "$PG/bin/initdb" --version

echo "==> Packe neu (Backup: ${TARBALL}.orig)"
cp -f "$TARBALL" "${TARBALL}.orig"
( cd "$WORK" && tar -czf "$TARBALL.tmp" . )
mv -f "$TARBALL.tmp" "$TARBALL"
echo "✓ $TARBALL ist jetzt self-contained. SHA256SUMS neu erzeugen!"
