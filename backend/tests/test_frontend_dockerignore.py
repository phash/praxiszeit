"""Gesamtreview B8: ``frontend/.dockerignore`` haelt Host-Reste aus dem Build.

Parallelpfad zu ``backend/.dockerignore`` (test_backend_dockerignore.py). Das
Frontend-Dockerfile installiert zuerst lock-treu (``npm ci``) und kopiert
danach mit ``COPY . .`` den ganzen Ordner. Ohne diese Datei kam dabei das
Host-``node_modules`` mit (rund 355 MB) und ueberschrieb die eben
installierten Pakete — ``COPY`` fuehrt Verzeichnisse zusammen. Ein nach einem
Abhaengigkeits-Bump noch nicht aktualisiertes Host-``node_modules`` (``git
pull`` ohne ``npm install``) landete so ueber ``docker compose build
frontend`` in ``dist``, auch Laufzeitpakete wie axios; teils als Gemisch, weil
Dateien, die es nur in der neuen Version gibt, stehen blieben. Dazu kamen
``dist/``, Agenten-Notizen (``.claude``) und das leere, root-eigene
``frontend/backend`` (Rest eines Docker-Mounts aus dem falschen cwd).

Die Tests brauchen das Repo-Wurzelverzeichnis (``../frontend``) und
ueberspringen sich im reinen Backend-Container, wie test_491_deploy_pull.py.
Ausgewertet wird mit dem Docker-Nachbau aus test_backend_dockerignore.py.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.test_backend_dockerignore import _excluded, _rules

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
DOCKERIGNORE = FRONTEND / ".dockerignore"

pytestmark = pytest.mark.skipif(
    not (FRONTEND / "Dockerfile").is_file(),
    reason=f"frontend/ nicht erreichbar unter {FRONTEND} (Backend-Container ohne Repo)",
)


@pytest.fixture(scope="module")
def rules():
    assert DOCKERIGNORE.is_file(), f"{DOCKERIGNORE} fehlt"
    return _rules(DOCKERIGNORE)


# Je Regel mindestens ein Beispiel (test_jede_regel_hat_ein_beispiel). Der
# Docker-Bundle-Test in test_491_deploy_pull.py prueft dieselben Pfade gegen
# die tar-Ausschluesse von tools/build-release.sh.
HOST_RESTE = [
    "node_modules/axios/package.json",
    "node_modules/.vite/deps/react.js",
    "dist/index.html",
    "dist/assets/index-3f9c2a1b.js",
    ".claude/agent-memory/notizen.md",
    "backend",
    "backend/app/main.py",
    ".env",
    ".env.local",
    ".env.production",
    "coverage/index.html",
    "test-results/.last-run.json",
]

# Alles, was `npm ci` + `npm run build` (tsc && vite build) und die
# nginx-Stufe lesen.
BENOETIGT = [
    "Dockerfile",
    "nginx.conf",
    "index.html",
    "package.json",
    "package-lock.json",
    "vite.config.ts",
    "tsconfig.json",
    "tsconfig.node.json",
    "postcss.config.js",
    "eslint.config.js",
    "src/main.tsx",
    "src/test/setup.ts",
    "public/icon-192.png",
    "public/help/HANDBUCH-ADMIN.md",
]


@pytest.mark.parametrize("path", HOST_RESTE)
def test_host_reste_bleiben_draussen(rules, path):
    assert _excluded(path, rules), path


@pytest.mark.parametrize("path", BENOETIGT)
def test_benoetigte_dateien_bleiben_drin(rules, path):
    assert not _excluded(path, rules), path


@pytest.mark.parametrize("path", BENOETIGT)
def test_benoetigte_dateien_gibt_es(path):
    """Die Liste darf nicht veralten: eine umbenannte Konfigurationsdatei
    (vite.config.ts -> .mts) wuerde sonst nie gegen die Regeln geprueft."""
    assert (FRONTEND / path).is_file(), path


def test_jede_regel_hat_ein_beispiel(rules):
    for negate, rx in rules:
        if negate:
            continue
        assert any(_excluded(p, [(False, rx)]) for p in HOST_RESTE), (
            f"Regel {rx.pattern} hat kein Beispiel in HOST_RESTE")


def test_kein_quelltext_und_keine_oeffentlichen_dateien_werden_ausgeschlossen(rules):
    """Gegen den echten Baum: jede Datei unter src/ und public/ (Handbuch-
    Spiegel, Schriften, Icons) muss im Build ankommen."""
    geprueft = 0
    for top in ("src", "public"):
        for dirpath, _dirnames, filenames in os.walk(FRONTEND / top):
            for name in filenames:
                rel = (Path(dirpath) / name).relative_to(FRONTEND).as_posix()
                assert not _excluded(rel, rules), rel
                geprueft += 1
    assert geprueft > 100  # falscher Pfad darf kein „alles gut" ergeben

