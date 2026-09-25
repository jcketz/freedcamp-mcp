"""Test de non-regression : les accents doivent survivre au transport stdio.

Sous Windows, stdout d'un sous-processus Python est en cp1252 par defaut.
Sans reconfiguration explicite en UTF-8, tout libelle accentue remonte
corrompu a l'hote MCP ("Interieur" -> "Int?rieur"), sans aucune erreur.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
SERVER = os.path.join(ROOT, "src", "server.py")
sys.path.insert(0, os.path.dirname(__file__))
import local_config  # noqa: E402

REFERENCE = local_config.reference_project_id()
pytestmark = pytest.mark.skipif(
    not REFERENCE, reason="aucun projet de reference declare")


@pytest.fixture(scope="module")
def proc():
    p = subprocess.Popen(
        [sys.executable, SERVER], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", bufsize=1, cwd=ROOT)
    p.stdin.write(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "pytest", "version": "1"}}}) + "\n")
    p.stdin.flush()
    p.stdout.readline()
    yield p
    try:
        p.stdin.close()
        p.wait(timeout=5)
    except Exception:
        p.kill()


def _call(proc, tool, arguments, msg_id=2):
    proc.stdin.write(json.dumps({
        "jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments}}) + "\n")
    proc.stdin.flush()
    r = json.loads(proc.stdout.readline())
    return json.loads(r["result"]["content"][0]["text"])


def test_accents_preserves_dans_les_libelles(proc):
    """Le projet de reference doit contenir des libelles accentues."""
    listes = _call(proc, "fc_lists", {"project_id": REFERENCE})
    titres = " ".join(x["title"] for x in listes)
    assert "\ufffd" not in titres, "caractere de remplacement : encodage casse"
    assert "Intérieur" in titres or "Extérieur" in titres, \
        "aucun accent retrouve : les libelles sont corrompus"


def test_accents_preserves_dans_les_taches(proc):
    taches = _call(proc, "fc_tasks",
                   {"project_id": REFERENCE, "limit": 30}, msg_id=3)
    blob = json.dumps(taches, ensure_ascii=False)
    assert "\ufffd" not in blob, "caractere de remplacement dans les taches"
    assert "é" in blob or "è" in blob, "aucun accent : encodage suspect"
