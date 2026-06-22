#!/usr/bin/env bash
# Validate a built praxiszeit-X.Y.Z-linux-x64.tar.gz against the distros we
# claim to support. Spins up minimal Docker containers (no praxiszeit setup),
# extracts the tarball, and verifies that the bundled PG binaries start.
#
# A pass means: postgres --version + initdb --version both succeed inside
# a clean install of each target distro. A fail blocks the release.
#
# Usage:
#   bash tools/validate-release.sh [path/to/tarball]
# Default: dist/praxiszeit-${APP_VERSION}-linux-x64.tar.gz (latest by mtime)

set -euo pipefail

cd "$(dirname "$0")/.."

TARBALL="${1:-}"
if [ -z "$TARBALL" ]; then
    TARBALL=$(ls -t dist/praxiszeit-*-linux-x64.tar.gz 2>/dev/null | head -1)
fi
if [ -z "$TARBALL" ] || [ ! -f "$TARBALL" ]; then
    echo "ERROR: kein Tarball gefunden. Erst 'bash tools/build-release.sh --linux-only' laufen lassen." >&2
    exit 1
fi

echo "==> Validiere $TARBALL"
TARBALL_ABS=$(readlink -f "$TARBALL")

# Distros wir wir unterstuetzen — alle haben glibc >= 2.34
DISTROS=(
    "ubuntu:24.04"
    "ubuntu:22.04"
    "debian:12"
    "rockylinux:9"
    # #177: Rolling-Distro. Arch/CachyOS liefern libxml2 nur noch als .so.16;
    # der Test beweist, dass das ins Bundle gelegte libxml2.so.2 den PG-Start
    # trotzdem traegt (System-libxml2 wird hier bewusst NICHT installiert).
    "archlinux:latest"
)

FAILED=()
for distro in "${DISTROS[@]}"; do
    echo
    echo "==> Test gegen $distro"
    # Distro-spezifisch: gleiche Pakete wie install.sh installieren würde.
    case "$distro" in
        ubuntu:*|debian:*)
            INSTALL_CMD='export DEBIAN_FRONTEND=noninteractive && apt-get update -qq && apt-get install -y -qq libxml2 libssl3 libgssapi-krb5-2 libzstd1 liblz4-1 libreadline8 libbrotli1 adduser >/dev/null'
            ;;
        rockylinux:*|almalinux:*|fedora:*)
            INSTALL_CMD='dnf install -y -q libxml2 openssl-libs krb5-libs libzstd lz4-libs readline libbrotli shadow-utils >/dev/null'
            ;;
        archlinux:*)
            # Bewusst OHNE libxml2: Arch liefert nur .so.16; das gebuendelte
            # libxml2.so.2 muss den PG-Start tragen (#177). shadow ist in base.
            INSTALL_CMD='pacman -Sy --noconfirm --needed openssl krb5 zstd lz4 readline brotli >/dev/null 2>&1'
            ;;
        *)
            INSTALL_CMD='true'
            ;;
    esac

    # In jedem Container:
    #   1. Runtime-Deps installieren (wie install.sh)
    #   2. unprivileged User anlegen (initdb verweigert root)
    #   3. Tarball extrahieren
    #   4. postgres + initdb starten unter dem unprivileged User
    if docker run --rm \
        -v "$TARBALL_ABS:/tarball.tgz:ro" \
        "$distro" \
        bash -c "
            set -e
            ${INSTALL_CMD}
            id pztest &>/dev/null || useradd -m -s /bin/bash pztest
            mkdir -p /opt/pz && cd /opt/pz
            tar xzf /tarball.tgz
            chown -R pztest:pztest /opt/pz

            echo \"  glibc: \$(ldd --version 2>&1 | head -1 | awk '{print \$NF}')\"

            su pztest -c 'LD_LIBRARY_PATH=/opt/pz/bin/postgresql/lib /opt/pz/bin/postgresql/bin/postgres --version'
            su pztest -c 'LD_LIBRARY_PATH=/opt/pz/bin/postgresql/lib /opt/pz/bin/postgresql/bin/initdb --version'

            # Vollstaendiger initdb-Cluster
            su pztest -c '
                export LD_LIBRARY_PATH=/opt/pz/bin/postgresql/lib
                mkdir -p /tmp/pgdata
                /opt/pz/bin/postgresql/bin/initdb -D /tmp/pgdata -U pgtest -E UTF8 --locale=C -A trust \
                    -c dynamic_library_path=/opt/pz/bin/postgresql/lib \
                    -L /opt/pz/bin/postgresql/share > /tmp/initdb.log 2>&1
            ' || {
                echo \"INITDB FAIL — log tail:\"
                tail -20 /tmp/initdb.log
                exit 1
            }
            echo '  OK: postgres + initdb laufen'
        " 2>&1 | sed 's/^/    /'; then
        echo "  ✓ $distro"
    else
        echo "  ✗ $distro"
        FAILED+=("$distro")
    fi
done

echo
echo "============================================="
if [ "${#FAILED[@]}" -eq 0 ]; then
    echo "✓ Alle ${#DISTROS[@]} Distros: postgres + initdb laufen"
    echo "  Tarball ist freigabefaehig."
    exit 0
else
    echo "✗ Failures: ${FAILED[*]}"
    echo "  Tarball NICHT freigabefaehig."
    exit 1
fi
