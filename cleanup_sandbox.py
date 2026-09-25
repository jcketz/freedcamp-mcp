"""Nettoyage des projets bac a sable laisses par les suites de tests.

Archive tout projet dont le nom commence par 'ZZ ' (convention des tests).
Respecte le quota : une pause entre chaque appel, et on abandonne
proprement si l'API renvoie 429 plutot que de s'acharner.
"""
import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from api import FreedcampAPI          # noqa: E402
from client import FreedcampError     # noqa: E402

PREFIXE = "ZZ "


def main():
    api = FreedcampAPI()
    try:
        projets = api.projects()
    except FreedcampError as exc:
        print("quota indisponible (%s). Reessayer dans quelques minutes." % exc)
        return 1

    cibles = [p for p in projets if (p["name"] or "").startswith(PREFIXE)]
    if not cibles:
        print("aucun projet bac a sable a nettoyer.")
        return 0

    print("%d projet(s) a archiver :" % len(cibles))
    ok = 0
    for p in cibles:
        try:
            api.project_archive(p["project_id"])
            print("  archive  %-10s %s" % (p["project_id"], p["name"]))
            ok += 1
        except FreedcampError as exc:
            print("  echec    %-10s %s (%s)" % (p["project_id"], p["name"],
                                                str(exc)[:60]))
        time.sleep(3)
    print("%d/%d archives" % (ok, len(cibles)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
