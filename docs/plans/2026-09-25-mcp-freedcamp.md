# Spec — serveur MCP Freedcamp

Date : 2026-09-25 · Statut : validée par exploration E2E de l'API réelle

## 1. Ce que l'exploration a établi

Toutes les lignes ci-dessous ont été **vérifiées par appel réel** sur un projet
bac à sable (id 3776833), pas lues dans une documentation.

### Authentification
HMAC-SHA1 : `hash = HMAC-SHA1(secret, api_key + timestamp)`, envoyé en query
avec `api_key` et `timestamp`. Le secret ne circule jamais.
Validation : `GET /sessions/current`.

### Capacités confirmées ✅

| Opération | Endpoint | Note |
|---|---|---|
| Lister projets | `GET /projects` | renvoie aussi `applications`, `group_name` |
| Créer projet | `POST /projects` | **`group_id` ET `group_name` requis** |
| Modifier projet | `POST /projects/{id}` | |
| Archiver projet | `POST /projects/{id}` `{f_archived:1}` | |
| Lister groupes | `GET /groups` | clé = `group_id` (pas `id`) |
| Lister listes | `GET /lists/2?project_id=` | **app_id dans le CHEMIN** |
| Créer liste | `POST /lists/2` | |
| Modifier / archiver liste | `POST /lists/2/{id}` `{f_archived:1}` | disparaît du listing |
| Supprimer liste | `DELETE /lists/2/{id}` | |
| Lister tâches | `GET /tasks?project_id=` | `limit`/`offset` |
| Créer tâche | `POST /tasks` | `task_group_id` = la liste |
| Lire / modifier / supprimer tâche | `GET|POST|DELETE /tasks/{id}` | |
| Sous-tâche | `POST /tasks` `{h_parent_id}` | |
| Assigner | `POST /tasks/{id}` `{assigned_to_id}` | |
| Lister membres | `GET /users?project_id=` | |
| Jalons | `GET|POST /milestones` | **`priority` requis en création** |
| Rattacher tâche→jalon | `POST /tasks/{id}` `{ms_id}` | |
| Commenter | `POST /comments` `{item_id, app_id, description}` | |
| Lire commentaires | via `GET /tasks/{id}` → champ `comments` | `GET /comments?item_id` = 404 |

### Limites constatées ⚠️

- **Tags : non exploitables.** `tags`, `tag_names`, `new_tags`, `item_tags`
  renvoient tous `200 OK` et **rien n'est posé** (`/tags` reste vide, aucun
  champ tag en lecture). → **Hors périmètre du MCP.** Substitut : les listes
  et les jalons jouent le rôle de classement.
- **Activation d'app impossible par API.** `applications`, `apps`,
  `add_application` renvoient `200` sans effet. L'app Milestones doit être
  activée depuis l'UI. → le MCP **détecte** l'absence et
  renvoie un message actionnable au lieu d'un 400 brut.
- **Filtres serveur non fiables.** `status`, `assigned_to_id`, `q`, `order`
  renvoient tous le même jeu : ils sont **ignorés**. → filtrage **côté client**
  dans `api.py`, seuls `limit`/`offset` sont respectés.
- Pas de `meta.has_more` : pagination par `len(batch) < limit`.

### Pièges qui ont déjà causé des dégâts 🔴

1. **`due_date` doit être une CHAÎNE `AAAA-MM-JJ`.** En entier → `200 OK` et la
   date est **effacée** (`due_ts` = -3600). Silencieux.
2. **Statuts : `0` = No Progress, `1` = **Completed**, `2` = In Progress.**
   Contre-intuitif et contraire aux wrappers tiers. Écrire `3` retombe sur `2`.
   A causé la replanification de 6 tâches déjà terminées.
3. **Rattachement jalon = `ms_id`.** `milestone_id` et `task_milestone_id`
   renvoient `200` sans rien faire.
4. **`GET /lists/2`**, pas `GET /lists?app_id=2` (→ 400).

## 2. Outils MCP exposés

Nommage `domaine_action`, verbe explicite pour les écritures.

**Lecture** — `fc_whoami`, `fc_projects`, `fc_project_get`, `fc_lists`,
`fc_tasks` (filtres client : statut, assigné, liste, recherche, échéance),
`fc_task_get` (avec commentaires), `fc_milestones`, `fc_users`.

**Écriture** — `fc_task_create`, `fc_task_update` (titre, description, échéance,
priorité, liste, jalon), `fc_task_status_set`, `fc_task_assign`,
`fc_task_delete`, `fc_list_create`, `fc_list_archive`, `fc_milestone_create`,
`fc_milestone_update`, `fc_comment_add`, `fc_project_create`,
`fc_project_archive`.

Chaque écriture **relit** et renvoie l'état effectif.

## 3. Décisions challengées

**Python vs TypeScript.** Un wrapper TS existe (freedcampMCP) mais documente le
mauvais `app_id` et ignore les pièges ci-dessus. Python : aucune dépendance,
`node_modules` évité, cohérent avec le reste des scripts Hermes. → Python.

**SDK MCP vs JSON-RPC à la main.** Le protocole nécessaire tient en trois
méthodes (`initialize`, `tools/list`, `tools/call`). Un SDK ajouterait une
dépendance et une couche opaque. → à la main, ~120 lignes.

**Mocks vs API réelle.** Les trois pièges majeurs sont précisément ce qu'un mock
aurait masqué : ils viennent tous d'un écart entre la doc et le comportement.
→ E2E réel sur bac à sable jetable.

**Exposer les tags ?** Non : un outil qui retourne `200` sans effet est pire
qu'un outil absent. Documenté comme limite.

## 4. Test Impact

Nouveau projet, aucun code existant modifié. Le bac à sable est créé puis
détruit par la suite de tests.

## 5. Rollback

Retirer l'entrée `freedcamp` de la configuration MCP du client suffit :
le serveur n'a aucun état persistant.
