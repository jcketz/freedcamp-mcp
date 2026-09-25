"""Tests E2E du client et de l'API Freedcamp — AUCUN MOCK.

Tout s'execute contre l'API reelle dans un projet BAC A SABLE cree puis
detruit par la fixture de session.

Les tests qui ont besoin d'un projet REEL (app Milestones activee) le
lisent depuis tests/local_config.py et se sautent proprement s'il n'est
pas declare : aucun identifiant de compte n'est code en dur ici.
"""
import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from api import FreedcampAPI  # noqa: E402
import local_config  # noqa: E402
from client import FreedcampClient, FreedcampError  # noqa: E402

REFERENCE = local_config.reference_project_id()


@pytest.fixture(scope="session")
def api():
    return FreedcampAPI(FreedcampClient())


@pytest.fixture(scope="session")
def sandbox(api, groupe_test):
    """Projet jetable, cree dans le groupe bac a sable declare.

    Jamais `groups()[0]` : ce serait ecrire dans un groupe metier reel.
    """
    p = api.project_create("ZZ MCP test %s" % datetime.datetime.now().strftime("%H%M%S"),
                           group_id=groupe_test["group_id"],
                           description="jetable")
    pid = p["project_id"]
    yield pid
    # Pas de `except: pass` : un archivage qui echoue doit etre visible,
    # sinon le projet jetable reste dans l'espace de travail reel.
    api.project_archive(pid)


@pytest.fixture(scope="session")
def liste(api, sandbox):
    return api.list_create(sandbox, "Liste de test")["id"]


# --------------------------------------------------------------- transport
def test_whoami_authentifie(api):
    r = api.whoami()
    assert r["authenticated"] is True


def test_erreur_http_levee_proprement(api):
    with pytest.raises(FreedcampError) as e:
        api.client.get("tasks/999999999999")
    assert e.value.status in (400, 403, 404)


def test_secret_absent_des_messages_d_erreur(api):
    with pytest.raises(FreedcampError) as e:
        api.client.get("tasks/999999999999")
    assert api.client.api_secret not in str(e.value)


# ---------------------------------------------------------------- projets
def test_projects_liste_non_vide(api):
    ps = api.projects()
    assert ps, "aucun projet accessible avec ces identifiants"
    assert all("project_id" in p and "name" in p for p in ps)


def test_project_get_par_id(api, sandbox):
    p = api.project_get(sandbox)
    assert str(p["project_id"]) == str(sandbox)


def test_project_create_exige_un_groupe(api):
    with pytest.raises(FreedcampError):
        api.project_create("ZZ sans groupe", group_id=None)


# ----------------------------------------------------------------- listes
def test_list_create_et_lecture(api, sandbox):
    lid = api.list_create(sandbox, "Liste A")["id"]
    titres = [x["title"] for x in api.lists(sandbox)]
    assert "Liste A" in titres
    assert lid


def test_list_archive_la_retire_du_listing(api, sandbox):
    lid = api.list_create(sandbox, "Liste a archiver")["id"]
    api.list_archive(lid)
    ids = [str(x["id"]) for x in api.lists(sandbox)]
    assert str(lid) not in ids


# ------------------------------------------------------------------ taches
def test_task_create_renvoie_etat_relu(api, sandbox, liste):
    t = api.task_create(sandbox, "Tache T1", list_id=liste)
    assert t["title"] == "Tache T1"
    assert str(t["task_group_id"]) == str(liste)


def test_task_update_echeance_chaine_est_persistee(api, sandbox, liste):
    """Le piege n1 : un entier renvoie 200 et EFFACE la date."""
    t = api.task_create(sandbox, "Tache echeance", list_id=liste)
    r = api.task_update(t["id"], due_date="2027-03-15")
    assert r["due_date"] == "2027-03-15", "echeance non persistee"


def test_task_update_refuse_une_date_mal_formee(api, sandbox, liste):
    t = api.task_create(sandbox, "Tache date KO", list_id=liste)
    with pytest.raises(ValueError):
        api.task_update(t["id"], due_date="15/03/2027")


def test_statuts_mapping_reel(api, sandbox, liste):
    """Piege n2 : 1 = Completed, 2 = In Progress."""
    t = api.task_create(sandbox, "Tache statut", list_id=liste)
    assert api.task_status_set(t["id"], "completed")["status_title"] == "Completed"
    assert api.task_status_set(t["id"], "in_progress")["status_title"] == "In Progress"
    assert api.task_status_set(t["id"], "todo")["status_title"] == "No Progress"


def test_statut_invalide_rejete(api, sandbox, liste):
    t = api.task_create(sandbox, "Tache statut KO", list_id=liste)
    with pytest.raises(ValueError):
        api.task_status_set(t["id"], "done")


def test_task_assign_et_relecture(api, sandbox, liste):
    us = api.users(sandbox)
    uid = us[0]["user_id"]
    t = api.task_create(sandbox, "Tache assignee", list_id=liste)
    r = api.task_assign(t["id"], uid)
    assert str(r["assigned_to_id"]) == str(uid)


def test_sous_tache_rattachee_au_parent(api, sandbox, liste):
    p = api.task_create(sandbox, "Parent", list_id=liste)
    c = api.task_create(sandbox, "Enfant", list_id=liste, parent_id=p["id"])
    assert str(c["parent_id"]) == str(p["id"])


def test_task_delete(api, sandbox, liste):
    t = api.task_create(sandbox, "A supprimer", list_id=liste)
    api.task_delete(t["id"])
    ids = [str(x["id"]) for x in api.tasks(sandbox)]
    assert str(t["id"]) not in ids


def test_tasks_filtre_par_statut_cote_client(api, sandbox, liste):
    t = api.task_create(sandbox, "Filtrable", list_id=liste)
    api.task_status_set(t["id"], "completed")
    ouvertes = api.tasks(sandbox, status="open")
    assert all(x["status_title"] != "Completed" for x in ouvertes)


def test_tasks_recherche_texte(api, sandbox, liste):
    api.task_create(sandbox, "Chercher ce motif unique XYZZY", list_id=liste)
    r = api.tasks(sandbox, query="XYZZY")
    assert len(r) >= 1
    assert all("xyzzy" in x["title"].lower() for x in r)


def test_task_get_inclut_les_commentaires(api, sandbox, liste):
    t = api.task_create(sandbox, "Avec commentaire", list_id=liste)
    api.comment_add(t["id"], "Un commentaire de test")
    d = api.task_get(t["id"])
    assert d["comments_count"] >= 1
    assert any("commentaire" in c["text"].lower() for c in d["comments"])


# ------------------------------------------------------------------ jalons
def test_milestones_sur_projet_sans_app_message_clair(api, sandbox):
    """L'app Milestones n'est pas activable par API : message actionnable."""
    with pytest.raises(FreedcampError) as e:
        api.milestones(sandbox)
    assert "activer" in str(e.value).lower() or "app" in str(e.value).lower()


@pytest.mark.skipif(not REFERENCE,
                    reason="aucun projet de reference declare "
                           "(voir tests/local_config.py)")
def test_milestones_lecture_sur_projet_de_reference(api):
    """Projet reel avec l'app Milestones activee : LECTURE SEULE."""
    ms = api.milestones(REFERENCE)
    assert ms, "le projet de reference ne contient aucun jalon"
    assert all("title" in m and "due_date" in m for m in ms)


# ------------------------------------------------------------- utilisateurs
def test_users_du_projet(api, sandbox):
    us = api.users(sandbox)
    assert len(us) >= 1
    assert all("user_id" in u and "name" in u for u in us)
