"""Tests des operations en lot (bulk).

Interet mesure : 1 appel MCP au lieu de N, et surtout un rapport partiel
exploitable quand le quota coupe le lot en cours de route.
"""
import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))



@pytest.fixture(scope="module")
def sandbox(api):
    groups = api.groups()
    p = api.project_create(
        "ZZ bulk %s" % datetime.datetime.now().strftime("%H%M%S"),
        group_id=groups[0]["group_id"], group_name=groups[0]["name"],
        description="jetable")
    yield p["project_id"]
    # Pas de `except: pass` ici : un nettoyage qui echoue doit se voir.
    api.project_archive(p["project_id"])


def test_create_bulk_cree_tout_le_lot(api, sandbox):
    liste = api.list_create(sandbox, "Lot")["id"]
    r = api.tasks_create_bulk(sandbox, [
        {"title": "Lot A", "list_id": liste, "due_date": "2027-04-10"},
        {"title": "Lot B", "list_id": liste, "priority": 2},
        {"title": "Lot C", "list_id": liste},
    ])
    assert r["requested"] == 3
    assert r["created"] == 3
    assert r["failed"] == 0
    dates = [x["task"]["due_date"] for x in r["results"]]
    assert "2027-04-10" in dates, "echeance perdue dans le lot"


def test_create_bulk_rapporte_les_erreurs_sans_tout_arreter(api, sandbox):
    """Une ligne invalide ne doit pas annuler les lignes valides."""
    r = api.tasks_create_bulk(sandbox, [
        {"title": "Valide 1"},
        {"title": "Date KO", "due_date": "10/04/2027"},   # format refuse
        {"description": "sans titre"},                      # title manquant
        {"title": "Valide 2"},
    ])
    assert r["created"] == 2
    assert r["failed"] == 2
    erreurs = [x for x in r["results"] if x["status"] == "error"]
    assert any("AAAA-MM-JJ" in x["error"] for x in erreurs)
    assert any("title" in x["error"] for x in erreurs)


def test_update_bulk_relit_chaque_tache(api, sandbox):
    liste = api.list_create(sandbox, "Lot maj")["id"]
    a = api.task_create(sandbox, "Maj A", list_id=liste)
    b = api.task_create(sandbox, "Maj B", list_id=liste)
    r = api.tasks_update_bulk([
        {"task_id": a["id"], "due_date": "2027-06-05", "title": "Maj A v2"},
        {"task_id": b["id"], "status": "completed"},
    ])
    assert r["updated"] == 2
    assert r["failed"] == 0
    par_id = {x["task"]["id"]: x["task"] for x in r["results"]}
    assert par_id[a["id"]]["due_date"] == "2027-06-05"
    assert par_id[a["id"]]["title"] == "Maj A v2"
    assert par_id[b["id"]]["status_title"] == "Completed"


def test_update_bulk_refuse_une_liste_vide(api):
    with pytest.raises(ValueError):
        api.tasks_update_bulk([])


def test_create_bulk_refuse_une_liste_vide(api, sandbox):
    with pytest.raises(ValueError):
        api.tasks_create_bulk(sandbox, [])
