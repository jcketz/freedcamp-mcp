"""E2E du cycle complet d'ECRITURE via le protocole MCP.

Scenario realiste bout en bout, dans un projet jetable :
  creer projet > creer liste > creer tache > modifier > assigner >
  sous-tache > commenter > changer statut > supprimer > archiver.

Aucune ecriture hors du bac a sable.
"""
import datetime
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import local_config  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
SERVER = os.path.join(ROOT, "src", "server.py")


class MCP:
    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, SERVER], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1, cwd=ROOT)
        self._id = 0
        self._send("initialize", {"protocolVersion": "2024-11-05",
                                  "capabilities": {},
                                  "clientInfo": {"name": "e2e", "version": "1"}})

    def _send(self, method, params):
        self._id += 1
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": self._id,
             "method": method, "params": params}) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def call(self, _tool, **arguments):
        """_tool est prefixe : un argument d'outil peut s'appeler 'name'."""
        r = self._send("tools/call", {"name": _tool, "arguments": arguments})
        result = r.get("result") or {}
        payload = json.loads(result["content"][0]["text"])
        if result.get("isError"):
            raise AssertionError("%s a echoue : %s" % (_tool, payload))
        return payload

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


@pytest.fixture(scope="module")
def mcp():
    s = MCP()
    yield s
    s.close()


@pytest.fixture(scope="module")
def projet(mcp):
    groups = mcp.call("fc_groups")
    voulu = local_config.test_group_id()
    g = next((x for x in groups if str(x["group_id"]) == str(voulu)), None) \
        if voulu else groups[-1]
    assert g, "groupe de test %s introuvable" % voulu
    p = mcp.call("fc_project_create",
                 name="ZZ E2E %s" % datetime.datetime.now().strftime("%H%M%S"),
                 group_id=g["group_id"],
                 description="E2E jetable")
    yield p["project_id"]
    mcp.call("fc_project_archive", project_id=p["project_id"])


def test_cycle_complet(mcp, projet):
    # --- liste
    liste = mcp.call("fc_list_create", project_id=projet, title="Chantiers")
    assert liste["title"] == "Chantiers"
    assert liste["id"] in [x["id"] for x in mcp.call("fc_lists", project_id=projet)]

    # --- creation avec tous les champs
    t = mcp.call("fc_task_create", project_id=projet, title="Poser la trappe",
                 list_id=liste["id"], description="anti-renard",
                 due_date="2026-10-04", priority=2)
    assert t["title"] == "Poser la trappe"
    assert t["due_date"] == "2026-10-04", "echeance perdue a la creation"
    assert t["task_group_id"] == liste["id"]

    # --- modification : l'echeance doit VRAIMENT changer
    t2 = mcp.call("fc_task_update", task_id=t["id"], due_date="2026-11-08",
                  title="Poser la trappe (v2)")
    assert t2["due_date"] == "2026-11-08"
    assert t2["title"] == "Poser la trappe (v2)"

    # --- statut : mapping non standard
    assert mcp.call("fc_task_status_set", task_id=t["id"],
                    status="in_progress")["status_title"] == "In Progress"
    assert mcp.call("fc_task_status_set", task_id=t["id"],
                    status="completed")["status_title"] == "Completed"

    # --- assignation
    users = mcp.call("fc_users", project_id=projet)
    assert users
    a = mcp.call("fc_task_assign", task_id=t["id"], user_id=users[0]["user_id"])
    assert a["assigned_to_id"] == users[0]["user_id"]

    # --- sous-tache
    sous = mcp.call("fc_task_create", project_id=projet, title="Acheter grillage",
                    list_id=liste["id"], parent_id=t["id"])
    assert sous["parent_id"] == t["id"]

    # --- commentaire
    c = mcp.call("fc_comment_add", task_id=t["id"], text="Grillage commande")
    assert c["comments_count"] >= 1
    detail = mcp.call("fc_task_get", task_id=t["id"])
    assert any("grillage" in x["text"].lower() for x in detail["comments"])

    # --- filtrage client
    ouvertes = mcp.call("fc_tasks", project_id=projet, status="open")
    assert t["id"] not in [x["id"] for x in ouvertes], "terminee non filtree"
    trouvees = mcp.call("fc_tasks", project_id=projet, query="grillage")
    assert sous["id"] in [x["id"] for x in trouvees]

    # --- suppression
    mcp.call("fc_task_delete", task_id=sous["id"])
    restantes = [x["id"] for x in mcp.call("fc_tasks", project_id=projet,
                                           status="all")]
    assert sous["id"] not in restantes

    # --- archivage de liste
    l2 = mcp.call("fc_list_create", project_id=projet, title="A archiver")
    mcp.call("fc_list_archive", list_id=l2["id"])
    assert l2["id"] not in [x["id"] for x in mcp.call("fc_lists",
                                                      project_id=projet)]


def test_garde_fou_date_entiere_impossible(mcp, projet):
    """Le piege le plus couteux : un entier efface la date en silence."""
    liste = mcp.call("fc_lists", project_id=projet)[0]
    t = mcp.call("fc_task_create", project_id=projet, title="Garde-fou",
                 list_id=liste["id"])
    r = mcp._send("tools/call", {"name": "fc_task_update",
                                 "arguments": {"task_id": t["id"],
                                               "due_date": 1790000000}})
    assert r["result"]["isError"] is True, "un entier aurait du etre refuse"


@pytest.mark.skipif(not local_config.reference_project_id(),
                    reason="aucun projet de reference declare "
                           "(l'app Milestones ne s'active pas par API)")
def test_milestone_cycle(mcp):
    """Cycle jalon sur un projet ou l'app Milestones est activee.

    Un projet neuf nait SANS cette app et elle ne peut pas etre activee
    par API : il faut donc un projet de reference declare localement.
    """
    ref = local_config.reference_project_id()
    ms = mcp.call("fc_milestone_create", project_id=ref,
                  title="ZZ jalon E2E", due_date="2027-12-31", priority=1,
                  description="jetable")
    assert ms["title"] == "ZZ jalon E2E"
    assert ms["due_date"] == "2027-12-31"
    maj = mcp.call("fc_milestone_update", milestone_id=ms["id"],
                   project_id=ref, title="ZZ jalon E2E (modifie)")
    assert maj["title"] == "ZZ jalon E2E (modifie)"
