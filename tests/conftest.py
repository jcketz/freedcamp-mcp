"""Configuration pytest commune.

L'API Freedcamp applique un quota strict : une suite complete lancee
d'une traite le declenche (HTTP 429) et fait echouer des tests corrects.
On espace donc les appels et on partage UN SEUL projet bac a sable pour
toute la session, au lieu d'un par module.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Pause entre chaque test : lisse la cadence sous le seuil de l'API.
THROTTLE_SECONDS = float(os.environ.get("FC_TEST_THROTTLE", "1.5"))


@pytest.fixture(autouse=True)
def _throttle():
    yield
    time.sleep(THROTTLE_SECONDS)
