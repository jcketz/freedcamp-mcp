"""Configuration des tests, isolee du code publiable.

AUCUNE valeur propre a un compte ne doit apparaitre dans les tests :
ils tournent chez n'importe qui. Les tests qui ont besoin d'un projet
REEL (app Milestones activee, libelles accentues) le lisent ici, et se
sautent proprement si l'utilisateur n'en a pas declare.

Pour activer ces tests, creer un fichier `tests/local_config.json` (non
versionne) :

    {
      "reference_project_id": "1234567",
      "reference_milestone_id": "89012"
    }

ou definir la variable d'environnement FC_REFERENCE_PROJECT_ID.
"""
import json
import os
import pathlib

_ICI = pathlib.Path(__file__).parent
_FICHIER = _ICI / "local_config.json"


def _charger():
    if _FICHIER.exists():
        try:
            return json.loads(_FICHIER.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


_CONF = _charger()


def reference_project_id():
    """Projet reel servant de reference en LECTURE SEULE.

    Doit avoir l'app Milestones activee et contenir des libelles
    accentues pour que les tests correspondants aient du sens.
    """
    return (os.environ.get("FC_REFERENCE_PROJECT_ID")
            or _CONF.get("reference_project_id"))


def reference_milestone_id():
    return (os.environ.get("FC_REFERENCE_MILESTONE_ID")
            or _CONF.get("reference_milestone_id"))


def test_group_id():
    """Groupe ou les tests ont le droit de creer des projets jetables.

    A declarer explicitement : sans lui, les tests ecrivent dans un groupe
    choisi par defaut, qui peut etre un groupe metier reel.
    """
    return (os.environ.get("FC_TEST_GROUP_ID")
            or _CONF.get("test_group_id"))


def credentials_path():
    """Chemin du fichier d'identifiants, pour le test d'etancheite."""
    from client import _secrets_path
    return _secrets_path()
