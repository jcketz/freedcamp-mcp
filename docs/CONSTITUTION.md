# CONSTITUTION — freedcamp-mcp

## Mission

Serveur MCP donnant à Gunouze un accès complet et sûr à Freedcamp : projets,
listes, tâches, jalons, assignations, commentaires, archivage.

## Stack

- **Python 3.11**, stdlib uniquement pour le client HTTP (`urllib`, `hmac`, `hashlib`).
  Pas de `requests` : le serveur doit démarrer sans installation.
- **MCP via stdio**, protocole JSON-RPC 2.0 écrit à la main (pas de SDK) pour
  rester sans dépendance et maîtriser le comportement.
- **pytest** pour les tests.

## Règles non négociables

1. **Aucune écriture non demandée.** Tout outil qui modifie ou supprime porte
   un nom explicite et n'est jamais appelé en fallback d'une lecture.
2. **`project_id` obligatoire et explicite** sur toute écriture. Jamais de
   projet « par défaut » implicite : le risque est d'écrire dans le mauvais
   projet en croyant écrire ailleurs.
3. **Relecture après écriture.** L'API renvoie `200 OK` sur des écritures qui
   n'ont rien fait (voir pièges). Toute fonction d'écriture relit et renvoie
   l'état réel.
4. **Statuts : jamais de code numérique nu en sortie.** Toujours accompagner du
   `status_title` lu de l'API.
5. **Les tests tapent l'API réelle.** Zéro mock. Ils s'exécutent dans un projet
   bac à sable créé et détruit par la suite de tests.
6. **Aucun identifiant de compte dans le code.** Les tests qui ont besoin
   d'un projet réel le lisent depuis `tests/local_config.py`, non versionné,
   et se sautent proprement s'il n'est pas déclaré.

## Frontières de modules

```
src/
  client.py     # transport HTTP + auth HMAC. Ne connaît pas MCP.
  api.py        # opérations métier Freedcamp. Ne connaît pas MCP.
  server.py     # couche MCP (JSON-RPC, registre d'outils). Ne parle pas HTTP.
```

Le sens des dépendances est strict : `server → api → client`. Jamais l'inverse.

## Tests

- Chaque outil MCP a au moins un test E2E qui l'exécute contre l'API réelle.
- Un test qui échoue bloque le commit. Pas de `skip` pour « on verra plus tard ».
- La suite nettoie ses artefacts (projet bac à sable supprimé en teardown).

## Secrets

Lus depuis `$FREEDCAMP_CREDENTIALS`, `~/.freedcamp-mcp.json`, ou l'emplacement
Hermes. Jamais en dur, jamais dans les logs, jamais dans un message d'erreur :
le client expurge la clé et le secret de toute exception.
