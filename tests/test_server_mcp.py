"""Tests du protocole MCP (JSON-RPC sur stdio).

On pilote le serveur comme le ferait un hote MCP : on ecrit des trames
sur stdin, on lit les reponses sur stdout. Le transport HTTP est reel
(les outils de lecture tapent l'API), mais aucune ecriture n'est faite
ici hors bac a sable.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
SERVER = os.path.join(ROOT, "src", "server.py")
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
import local_config  # noqa: E402

REFERENCE = local_config.reference_project_id()


class MCPSession:
    """Client MCP minimal : une requete, une reponse."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, SERVER], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1, cwd=ROOT)
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read()
            raise AssertionError("pas de reponse du serveur. stderr=%s" % err[:500])
        return json.loads(line)

    def tool(self, name, arguments=None):
        r = self.call("tools/call", {"name": name, "arguments": arguments or {}})
        assert "result" in r, "erreur outil %s : %s" % (name, r.get("error"))
        content = r["result"]["content"][0]["text"]
        return json.loads(content), r["result"].get("isError", False)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


@pytest.fixture(scope="module")
def mcp():
    s = MCPSession()
    s.call("initialize", {"protocolVersion": "2024-11-05",
                          "capabilities": {},
                          "clientInfo": {"name": "pytest", "version": "1"}})
    yield s
    s.close()


def test_initialize_renvoie_le_nom_du_serveur():
    s = MCPSession()
    r = s.call("initialize", {"protocolVersion": "2024-11-05",
                              "capabilities": {},
                              "clientInfo": {"name": "pytest", "version": "1"}})
    assert r["result"]["serverInfo"]["name"] == "freedcamp"
    assert "tools" in r["result"]["capabilities"]
    s.close()


def test_tools_list_expose_tous_les_outils(mcp):
    r = mcp.call("tools/list")
    noms = {t["name"] for t in r["result"]["tools"]}
    attendus = {
        "fc_whoami", "fc_projects", "fc_groups", "fc_lists", "fc_tasks",
        "fc_task_get", "fc_milestones", "fc_users",
        "fc_task_create", "fc_task_update", "fc_task_status_set",
        "fc_task_assign", "fc_task_delete", "fc_list_create",
        "fc_list_archive", "fc_milestone_create", "fc_milestone_update",
        "fc_comment_add", "fc_project_create", "fc_project_archive",
    }
    assert attendus <= noms, "outils manquants : %s" % (attendus - noms)


def test_chaque_outil_a_un_schema_valide(mcp):
    r = mcp.call("tools/list")
    for t in r["result"]["tools"]:
        assert t.get("description"), "%s sans description" % t["name"]
        schema = t.get("inputSchema")
        assert schema and schema.get("type") == "object", t["name"]
        assert "properties" in schema, t["name"]


def test_whoami(mcp):
    data, err = mcp.tool("fc_whoami")
    assert err is False
    assert data["authenticated"] is True


def test_projects_liste(mcp):
    data, err = mcp.tool("fc_projects")
    assert err is False
    assert data, "aucun projet accessible"


@pytest.mark.skipif(not REFERENCE, reason="pas de projet de reference")
def test_tasks_lecture_projet_reference(mcp):
    data, err = mcp.tool("fc_tasks", {"project_id": REFERENCE,
                                      "status": "open", "limit": 5})
    assert err is False
    assert len(data) <= 5
    assert all(t["status_title"] != "Completed" for t in data)


@pytest.mark.skipif(not REFERENCE, reason="pas de projet de reference")
def test_milestones_projet_reference(mcp):
    data, err = mcp.tool("fc_milestones", {"project_id": REFERENCE})
    assert err is False
    assert data, "aucun jalon dans le projet de reference"


def test_outil_inconnu_renvoie_une_erreur(mcp):
    r = mcp.call("tools/call", {"name": "fc_inexistant", "arguments": {}})
    assert "error" in r or r["result"].get("isError") is True


def test_argument_manquant_message_clair(mcp):
    r = mcp.call("tools/call", {"name": "fc_tasks", "arguments": {}})
    texte = json.dumps(r)
    assert "project_id" in texte


def test_date_invalide_rejetee_avec_explication(mcp):
    r = mcp.call("tools/call", {"name": "fc_task_update",
                                "arguments": {"task_id": "1",
                                              "due_date": "15/03/2027"}})
    texte = json.dumps(r).lower()
    assert "aaaa-mm-jj" in texte or "due_date" in texte


def test_erreur_api_ne_fuit_pas_le_secret(mcp):
    r = mcp.call("tools/call", {"name": "fc_task_get",
                                "arguments": {"task_id": "999999999999"}})
    conf = json.loads(local_config.credentials_path().read_text(encoding="utf-8"))
    assert conf["api_secret"] not in json.dumps(r)
