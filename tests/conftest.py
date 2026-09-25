"""Configuration pytest commune.

L'API Freedcamp applique un quota strict : une suite complete lancee
d'une traite le declenche (HTTP 429) et fait echouer des tests corrects.
On espace donc les appels.

Regle de proprete, apprise a nos depens : chaque projet cree par les tests
DOIT etre archive, et l'archivage DOIT etre verifie. Dix-sept projets
jetables ont pollue l'espace de travail reel de l'utilisateur parce qu'un
teardown avalait l'echec avec `except Exception: pass`. Un nettoyage
silencieux qui echoue est pire que pas de nettoyage du tout.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from api import FreedcampAPI  # noqa: E402
from client import FreedcampClient  # noqa: E402

# Pause entre chaque test : lisse la cadence sous le seuil de l'API.
THROTTLE_SECONDS = float(os.environ.get("FC_TEST_THROTTLE", "1.5"))


@pytest.fixture(autouse=True)
def _throttle():
    yield
    time.sleep(THROTTLE_SECONDS)


@pytest.fixture(scope="session")
def api():
    """Client API partage par toute la session."""
    return FreedcampAPI(FreedcampClient())


@pytest.fixture(scope="session")
def groupe_test(api):
    """Groupe ou creer les projets jetables.

    Choisi explicitement, jamais au hasard : `groups()[0]` peut viser un
    groupe metier reel (celui qui contient les vrais projets) ou un groupe
    supprime entre deux sessions. On lit donc `tests/local_config.json`
    (cle `test_group_id`) et, a defaut, on prend le dernier groupe de la
    liste — le plus recent, donc le moins susceptible d'etre structurant.

    ATTENTION : ne jamais passer `group_name` a `project_create`, l'API
    creerait un groupe en double (irreparable, voir test_groupes.py).
    """
    import local_config

    groupes = api.groups()
    assert groupes, "aucun groupe accessible avec ces identifiants"

    voulu = local_config.test_group_id()
    if voulu:
        for g in groupes:
            if str(g["group_id"]) == str(voulu):
                return g
        pytest.skip("groupe de test %s introuvable (supprime ?)" % voulu)

    return groupes[-1]


@pytest.fixture(scope="session", autouse=True)
def _filet_de_securite(api):
    """Archive en fin de session TOUT projet `ZZ ` reste actif.

    Filet de derniere ligne : meme si un test plante avant son propre
    teardown, l'espace de travail de l'utilisateur reste propre. Les
    echecs sont signales bruyamment, jamais avales.
    """
    yield

    try:
        data = api.client.get("projects")
        projets = (data.get("data") or {}).get("projects") or []
    except Exception as exc:  # noqa: BLE001 - diagnostic, pas de silence
        print("\n[nettoyage] impossible de lister les projets : %s" % exc)
        return

    restants = [p for p in projets
                if str(p.get("project_name", "")).startswith("ZZ")
                and p.get("f_active")]
    if not restants:
        return

    print("\n[nettoyage] %d projet(s) jetable(s) a archiver" % len(restants))
    echecs = []
    for p in restants:
        pid = p["project_id"]
        try:
            api.project_archive(pid)
            time.sleep(1.0)
        except Exception as exc:  # noqa: BLE001
            echecs.append((pid, p.get("project_name"), str(exc)[:120]))

    for pid, nom, err in echecs:
        print("[nettoyage] ECHEC %s (%s) : %s" % (pid, nom, err))
    if echecs:
        print("[nettoyage] %d projet(s) restent visibles dans Freedcamp — "
              "les archiver a la main." % len(echecs))
