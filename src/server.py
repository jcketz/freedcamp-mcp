#!/usr/bin/env python3
"""Serveur MCP Freedcamp — transport stdio, JSON-RPC 2.0.

Trois methodes suffisent a l'hote : initialize, tools/list, tools/call.
Aucune dependance externe.

Les erreurs metier remontent en isError:true avec un message ACTIONNABLE
(ce qu'il faut faire), jamais une trace brute.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import FreedcampAPI  # noqa: E402
from client import FreedcampError  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "freedcamp", "version": "1.0.0"}

_api = None


def api():
    global _api
    if _api is None:
        _api = FreedcampAPI()
    return _api


def _str(v):
    return None if v is None else str(v)


# --------------------------------------------------------------- outils
# (nom, description, schema, fonction)
def _p(**props):
    return props


TOOLS = []


def tool(_name, _description, _required=(), **properties):
    """Enregistre un outil MCP.

    Les parametres internes sont prefixes d'un underscore : une propriete de
    schema peut legitimement s'appeler 'description' ou 'name', et sans ce
    prefixe Python leve 'got multiple values for argument'.
    """
    def register(fn):
        TOOLS.append({
            "name": _name,
            "description": _description,
            "inputSchema": {"type": "object", "properties": properties,
                            "required": list(_required)},
            "handler": fn,
        })
        return fn
    return register


# ---- lecture ---------------------------------------------------------
@tool("fc_whoami", "Verifie que les identifiants Freedcamp fonctionnent.")
def _whoami():
    return api().whoami()


@tool("fc_projects", "Liste les projets accessibles (id, nom, groupe, apps actives).",
      include_archived={"type": "boolean",
                        "description": "inclure les projets archives"})
def _projects(include_archived=False):
    return api().projects(include_archived=include_archived)


@tool("fc_groups", "Liste les groupes de projets. Necessaire pour creer un projet.")
def _groups():
    return api().groups()


@tool("fc_lists", "Listes de taches d'un projet (colonnes/categories).",
      _required=("project_id",),
      project_id={"type": "string", "description": "id du projet"})
def _lists(project_id):
    return api().lists(project_id)


@tool("fc_tasks",
      "Taches d'un projet, triees par ordre de priorite (le HAUT de liste "
      "est le plus prioritaire). Les filtres sont appliques cote client car "
      "l'API Freedcamp ignore les siens.",
      _required=("project_id",),
      project_id={"type": "string"},
      status={"type": "string",
              "enum": ["todo", "in_progress", "completed", "open", "all"],
              "description": "open = tout sauf terminees (defaut : all)"},
      assigned_to={"type": "string", "description": "filtrer par user_id"},
      list_id={"type": "string", "description": "filtrer par liste"},
      milestone_id={"type": "string", "description": "filtrer par jalon"},
      query={"type": "string", "description": "recherche texte titre/description"},
      limit={"type": "integer", "description": "nombre maximum de resultats"})
def _tasks(project_id, status=None, assigned_to=None, list_id=None,
           milestone_id=None, query=None, limit=None):
    return api().tasks(project_id, status=status, assigned_to=assigned_to,
                       list_id=list_id, milestone_id=milestone_id,
                       query=query, limit=limit)


@tool("fc_task_get", "Detail d'une tache, commentaires inclus.",
      _required=("task_id",), task_id={"type": "string"})
def _task_get(task_id):
    return api().task_get(task_id)


@tool("fc_milestones",
      "Jalons d'un projet. Si l'app Milestones n'est pas activee, renvoie "
      "un message expliquant comment l'activer (impossible par API).",
      _required=("project_id",), project_id={"type": "string"})
def _milestones(project_id):
    return api().milestones(project_id)


@tool("fc_users", "Membres d'un projet (ou tous si project_id omis).",
      project_id={"type": "string"})
def _users(project_id=None):
    return api().users(project_id)


# ---- ecriture --------------------------------------------------------
@tool("fc_task_create", "Cree une tache. Le project_id est OBLIGATOIRE et "
      "explicite : aucun projet par defaut.",
      _required=("project_id", "title"),
      project_id={"type": "string"}, title={"type": "string"},
      list_id={"type": "string", "description": "liste de destination"},
      description={"type": "string"},
      due_date={"type": "string", "description": "echeance 'AAAA-MM-JJ'"},
      priority={"type": "integer", "description": "0 a 3"},
      assigned_to={"type": "string", "description": "user_id"},
      parent_id={"type": "string", "description": "id de la tache parente"},
      milestone_id={"type": "string"})
def _task_create(project_id, title, list_id=None, description=None,
                 due_date=None, priority=None, assigned_to=None,
                 parent_id=None, milestone_id=None):
    return api().task_create(project_id, title, list_id=list_id,
                             description=description, due_date=due_date,
                             priority=priority, assigned_to=assigned_to,
                             parent_id=parent_id, milestone_id=milestone_id)


@tool("fc_task_update", "Modifie une tache et renvoie son etat RELU "
      "(l'API renvoie 200 sur des ecritures sans effet).",
      _required=("task_id",), task_id={"type": "string"},
      title={"type": "string"}, description={"type": "string"},
      due_date={"type": "string",
                "description": "'AAAA-MM-JJ' obligatoirement en chaine"},
      priority={"type": "integer"}, list_id={"type": "string"},
      milestone_id={"type": "string"})
def _task_update(task_id, **kw):
    return api().task_update(task_id, **{k: v for k, v in kw.items()
                                         if v is not None})


@tool("fc_task_status_set",
      "Change le statut. ATTENTION au mapping Freedcamp : completed=1, "
      "in_progress=2 (contre-intuitif). Utiliser les libelles, pas les codes.",
      _required=("task_id", "status"), task_id={"type": "string"},
      status={"type": "string", "enum": ["todo", "in_progress", "completed"]})
def _task_status_set(task_id, status):
    return api().task_status_set(task_id, status)


@tool("fc_task_assign", "Assigne une tache a un utilisateur.",
      _required=("task_id", "user_id"),
      task_id={"type": "string"}, user_id={"type": "string"})
def _task_assign(task_id, user_id):
    return api().task_assign(task_id, user_id)


@tool("fc_task_delete", "Supprime definitivement une tache.",
      _required=("task_id",), task_id={"type": "string"})
def _task_delete(task_id):
    return api().task_delete(task_id)


@tool("fc_tasks_create_bulk",
      "Cree PLUSIEURS taches en un seul appel. Economise le quota Freedcamp "
      "(strict, fenetre en minutes). Ne s'arrete pas a la premiere erreur : "
      "renvoie un rapport ligne par ligne (created/error) pour savoir ou "
      "reprendre si le quota coupe le lot.",
      _required=("project_id", "tasks"),
      project_id={"type": "string"},
      tasks={"type": "array",
             "description": "liste d'objets {title, list_id?, description?, "
                            "due_date?, priority?, assigned_to?, parent_id?, "
                            "milestone_id?}",
             "items": {"type": "object"}})
def _tasks_create_bulk(project_id, tasks):
    return api().tasks_create_bulk(project_id, tasks)


@tool("fc_tasks_update_bulk",
      "Modifie PLUSIEURS taches en un seul appel. Chaque element porte son "
      "task_id. Rapport ligne par ligne avec l'etat RELU de chaque tache.",
      _required=("updates",),
      updates={"type": "array",
               "description": "liste d'objets {task_id, title?, description?, "
                              "due_date?, priority?, list_id?, milestone_id?, "
                              "status?, assigned_to?}",
               "items": {"type": "object"}})
def _tasks_update_bulk(updates):
    return api().tasks_update_bulk(updates)


@tool("fc_list_create", "Cree une liste de taches dans un projet.",
      _required=("project_id", "title"),
      project_id={"type": "string"}, title={"type": "string"})
def _list_create(project_id, title):
    return api().list_create(project_id, title)


@tool("fc_list_archive", "Archive une liste (elle disparait du listing).",
      _required=("list_id",), list_id={"type": "string"})
def _list_archive(list_id):
    return api().list_archive(list_id)


@tool("fc_milestone_create", "Cree un jalon. priority est requis par l'API.",
      _required=("project_id", "title"),
      project_id={"type": "string"}, title={"type": "string"},
      due_date={"type": "string", "description": "'AAAA-MM-JJ'"},
      priority={"type": "integer", "description": "defaut 1"},
      description={"type": "string"})
def _milestone_create(project_id, title, due_date=None, priority=1,
                      description=""):
    return api().milestone_create(project_id, title, due_date=due_date,
                                  priority=priority, description=description)


@tool("fc_milestone_update", "Modifie un jalon.",
      _required=("milestone_id", "project_id"),
      milestone_id={"type": "string"}, project_id={"type": "string"},
      title={"type": "string"}, due_date={"type": "string"},
      priority={"type": "integer"}, description={"type": "string"})
def _milestone_update(milestone_id, project_id, **kw):
    return api().milestone_update(milestone_id, project_id,
                                  **{k: v for k, v in kw.items() if v is not None})


@tool("fc_comment_add", "Ajoute un commentaire a une tache.",
      _required=("task_id", "text"),
      task_id={"type": "string"}, text={"type": "string"})
def _comment_add(task_id, text):
    return api().comment_add(task_id, text)


@tool("fc_project_create",
      "Cree un projet dans un groupe EXISTANT (voir fc_groups). "
      "N'envoie jamais group_name : l'API creerait un groupe en double.",
      _required=("name", "group_id"),
      name={"type": "string"}, group_id={"type": "string"},
      description={"type": "string"})
def _project_create(name, group_id, description=""):
    return api().project_create(name, group_id, description=description)


@tool("fc_project_archive", "Archive un projet.",
      _required=("project_id",), project_id={"type": "string"})
def _project_archive(project_id):
    return api().project_archive(project_id)


BY_NAME = {t["name"]: t for t in TOOLS}


# ----------------------------------------------------------- protocole
def _public(t):
    return {k: t[k] for k in ("name", "description", "inputSchema")}


def handle(msg):
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO}}

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid,
                "result": {"tools": [_public(t) for t in TOOLS]}}

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        spec = BY_NAME.get(name)
        if spec is None:
            return {"jsonrpc": "2.0", "id": mid, "error": {
                "code": -32601,
                "message": "outil inconnu : %s. Outils disponibles : %s"
                           % (name, ", ".join(sorted(BY_NAME)))}}
        manquants = [r for r in spec["inputSchema"]["required"] if r not in args]
        if manquants:
            return _error(mid, "argument(s) obligatoire(s) manquant(s) : %s"
                               % ", ".join(manquants))
        try:
            result = spec["handler"](**args)
            return _ok(mid, result)
        except FreedcampError as exc:
            return _error(mid, str(exc))
        except (ValueError, TypeError) as exc:
            return _error(mid, str(exc))
        except Exception:
            return _error(mid, "erreur interne : %s"
                               % traceback.format_exc(limit=2).splitlines()[-1])

    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": "methode inconnue : %s" % method}}


def _ok(mid, payload):
    return {"jsonrpc": "2.0", "id": mid, "result": {
        "content": [{"type": "text",
                     "text": json.dumps(payload, ensure_ascii=False, indent=1)}],
        "isError": False}}


def _error(mid, message):
    return {"jsonrpc": "2.0", "id": mid, "result": {
        "content": [{"type": "text",
                     "text": json.dumps({"error": message}, ensure_ascii=False)}],
        "isError": True}}


def main():
    # L'hote MCP lit stdout en UTF-8 ; sous Windows le flux par defaut est
    # en cp1252 et corrompt les accents ("Interieur" -> "Int?rieur").
    # On force l'encodage des deux cotes avant toute lecture/ecriture.
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        response = handle(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
