"""Archivage de projet : le contrat est l'etat RELU, pas le code HTTP.

Ce test existe parce que le bug est arrive en production : la premiere
implementation postait `f_archived: 1`, recevait `200 OK`, et renvoyait
`archived: True`. Dix-sept projets bac a sable sont restes visibles dans
l'espace de travail de l'utilisateur alors que le code affirmait les avoir
archives.

La lecon generale : sur cette API, `200 OK` ne prouve rien. Tout ecrit doit
etre relu.
"""
import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from client import FreedcampError  # noqa: E402


def _etat(api, pid):
    """Etat brut du projet tel que l'API le renvoie."""
    return api._project_state(pid)


def test_archive_rend_le_projet_inactif(api, groupe_test):
    """Apres archivage, f_active doit etre faux ET archived_ts renseigne."""
    nom = "ZZ archive %s" % datetime.datetime.now().strftime("%H%M%S%f")
    proj = api.project_create(nom, group_id=groupe_test["group_id"],
                              group_name=groupe_test["name"])
    pid = proj["project_id"]

    avant = _etat(api, pid)
    assert avant is not None, "le projet cree doit etre listable"
    assert avant.get("f_active"), "un projet neuf doit etre actif"

    res = api.project_archive(pid)
    assert res["archived"] is True

    apres = _etat(api, pid)
    assert apres is not None, "un projet archive reste listable"
    assert not apres.get("f_active"), (
        "REGRESSION : le projet est encore actif apres archivage — "
        "c'est exactement le bug qui a pollue l'espace de l'utilisateur"
    )
    assert apres.get("archived_ts"), "archived_ts doit etre horodate"


def test_f_archived_ne_marche_pas(api, groupe_test):
    """Documente le faux ami : `f_archived` repond 200 et n'archive rien.

    Si Freedcamp corrige un jour son API, ce test echouera et nous
    apprendra que le champ est devenu fonctionnel.
    """
    nom = "ZZ faux ami %s" % datetime.datetime.now().strftime("%H%M%S%f")
    proj = api.project_create(nom, group_id=groupe_test["group_id"],
                              group_name=groupe_test["name"])
    pid = proj["project_id"]

    api.client.post("projects/%s" % pid, {"f_archived": 1})

    etat = _etat(api, pid)
    assert etat.get("f_active"), (
        "f_archived semble desormais fonctionner : mettre a jour "
        "project_archive() et la table des pieges du README"
    )

    api.project_archive(pid)  # nettoyage par la voie qui marche


def test_suppression_de_projet_indisponible(api, groupe_test):
    """DELETE /projects/<id> renvoie 501 : l'archivage est la seule sortie.

    Consequence documentee pour l'utilisateur : un projet cree par erreur
    ne peut pas etre efface, seulement masque.
    """
    nom = "ZZ delete %s" % datetime.datetime.now().strftime("%H%M%S%f")
    proj = api.project_create(nom, group_id=groupe_test["group_id"],
                              group_name=groupe_test["name"])
    pid = proj["project_id"]

    with pytest.raises(FreedcampError) as exc:
        api.client.request("/projects/%s" % pid, method="DELETE")
    assert exc.value.status == 501

    api.project_archive(pid)
