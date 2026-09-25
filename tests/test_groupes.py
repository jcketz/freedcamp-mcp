"""Creer un projet ne doit JAMAIS creer de groupe.

Ce test existe parce que le bug est arrive en production : `project_create`
transmettait `group_name` en plus de `group_id`, et l'API creait alors un
NOUVEAU groupe portant ce nom au lieu de ranger le projet dans le groupe
demande. Vingt-neuf groupes « Maison » et « Village Gaulois » en double se
sont accumules dans l'espace de travail reel de l'utilisateur.

Aggravant : un groupe ne peut etre ni supprime ni archive par l'API (501
sur les deux). Le degat est donc irreversible sans intervention manuelle
dans l'interface web — raison pour laquelle ce test garde la porte.
"""
import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from client import FreedcampError  # noqa: E402


def _nb_groupes(api):
    return len(api.groups())


def test_creer_un_projet_ne_cree_aucun_groupe(api, groupe_test):
    """Le compte de groupes doit etre IDENTIQUE avant et apres."""
    avant = _nb_groupes(api)

    nom = "ZZ nogroup %s" % datetime.datetime.now().strftime("%H%M%S%f")
    proj = api.project_create(nom, group_id=groupe_test["group_id"])

    apres = _nb_groupes(api)
    assert apres == avant, (
        "REGRESSION : %d groupe(s) cree(s) en creant un projet. "
        "C'est le bug qui a pollue l'espace de l'utilisateur, et les "
        "groupes ne peuvent pas etre supprimes (501)." % (apres - avant)
    )

    api.project_archive(proj["project_id"])


def test_le_projet_atterrit_dans_le_groupe_demande(api, groupe_test):
    """Verifie le rangement effectif, pas seulement l'absence de doublon."""
    nom = "ZZ rangement %s" % datetime.datetime.now().strftime("%H%M%S%f")
    proj = api.project_create(nom, group_id=groupe_test["group_id"])

    assert str(proj["group_id"]) == str(groupe_test["group_id"])
    assert proj["group_name"] == groupe_test["name"]

    api.project_archive(proj["project_id"])


def test_group_id_manquant_refuse(api):
    """Sans group_id, echec explicite plutot qu'un projet egare."""
    with pytest.raises(FreedcampError):
        api.project_create("ZZ sans groupe", group_id=None)


def test_groupe_non_supprimable(api, groupe_test):
    """Documente pourquoi le bug etait grave : aucune reparation par API.

    Le code exact varie (501 « not available publicly », 400 « no access »)
    selon le groupe et l'etat du compte. Ce qui compte et qui ne varie
    pas : **aucune des deux voies n'aboutit**. Un groupe cree par erreur
    doit etre supprime a la main dans l'interface web.
    """
    gid = groupe_test["group_id"]

    with pytest.raises(FreedcampError) as suppr:
        api.client.request("/groups/%s" % gid, method="DELETE")
    assert suppr.value.status in (400, 501), (
        "la suppression de groupe semble desormais possible (%s) : "
        "mettre a jour le README" % suppr.value.status)

    with pytest.raises(FreedcampError) as arch:
        api.client.post("groups/%s" % gid, {"f_active": 0})
    assert arch.value.status in (400, 501), (
        "l'archivage de groupe semble desormais possible (%s) : "
        "mettre a jour le README" % arch.value.status)
