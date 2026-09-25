"""Operations metier Freedcamp.

Toutes les subtilites de l'API sont encapsulees ICI, pour qu'aucun appelant
n'ait a les connaitre :

  * due_date doit etre une CHAINE 'AAAA-MM-JJ' ; un entier renvoie 200 OK et
    EFFACE la date sans erreur.
  * status : 0 = No Progress, 1 = Completed, 2 = In Progress (contre-intuitif).
  * rattachement a un jalon : champ 'ms_id' (milestone_id est ignore).
  * les listes vivent sous /lists/2 (app_id dans le CHEMIN).
  * les filtres serveur (status, assigned_to_id, q, order) sont IGNORES par
    l'API : on filtre cote client.
  * les tags sont acceptes mais jamais persistes : non exposes.

Chaque ecriture RELIT la ressource et renvoie son etat reel.
"""
import datetime
import re

from client import FreedcampClient, FreedcampError

APP_TASKS = 2

# mapping VERIFIE par appels reels, contraire a la doc officielle
STATUS_TO_CODE = {"todo": 0, "completed": 1, "in_progress": 2}
CODE_TO_LABEL = {0: "No Progress", 1: "Completed", 2: "In Progress"}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date(value):
    """Impose la chaine AAAA-MM-JJ : c'est le seul format qui persiste."""
    if value is None or value == "":
        return value
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValueError(
            "due_date doit etre une chaine 'AAAA-MM-JJ' (recu : %r). "
            "Un entier est accepte par l'API mais EFFACE la date." % (value,))
    datetime.date.fromisoformat(value)
    return value


def _ts_to_date(ts):
    try:
        value = int(ts)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return datetime.date.fromtimestamp(value).isoformat()


class FreedcampAPI:
    def __init__(self, client=None):
        self.client = client or FreedcampClient()

    # ------------------------------------------------------------ mapping
    @staticmethod
    def _task(raw):
        code = int(raw.get("status") or 0)
        return {
            "id": str(raw.get("id")),
            "title": raw.get("title") or "",
            "description": raw.get("description") or "",
            "status": code,
            "status_title": raw.get("status_title") or CODE_TO_LABEL.get(code, "?"),
            "project_id": str(raw.get("project_id") or ""),
            "task_group_id": str(raw.get("task_group_id") or ""),
            "list_name": raw.get("task_group_name") or "",
            "assigned_to_id": str(raw.get("assigned_to_id") or "") or None,
            "assigned_to": raw.get("assigned_to_fullname") or None,
            "due_date": _ts_to_date(raw.get("due_ts")),
            "start_date": _ts_to_date(raw.get("start_ts")),
            "milestone_id": str(raw.get("ms_id") or "") or None,
            "parent_id": str(raw.get("h_parent_id") or "") or None,
            "priority": raw.get("priority"),
            "comments_count": int(raw.get("comments_count") or 0),
            "order": float(raw.get("order") or 0),
            "url": raw.get("url"),
        }

    @staticmethod
    def _comment(raw):
        text = re.sub(r"<[^>]+>", "", raw.get("description") or "").strip()
        return {"id": str(raw.get("id")), "text": text,
                "author_id": str(raw.get("user_id") or ""),
                "created": _ts_to_date(raw.get("created_ts"))}

    # ---------------------------------------------------------- session
    def whoami(self):
        self.client.get("sessions/current")
        return {"authenticated": True}

    # ---------------------------------------------------------- projets
    def projects(self, include_archived=False):
        raw = self.client.payload(self.client.get("projects"), "projects")
        out = []
        for p in raw:
            if not include_archived and str(p.get("archived_ts") or "0") not in ("0", "", "None"):
                continue
            out.append({
                "project_id": str(p.get("project_id")),
                "name": p.get("project_name"),
                "group": p.get("group_name"),
                "description": p.get("project_description") or "",
                "apps": p.get("applications") or [],
            })
        return out

    def project_get(self, project_id):
        for p in self.projects(include_archived=True):
            if str(p["project_id"]) == str(project_id):
                return p
        raise FreedcampError(404, "projet %s introuvable" % project_id)

    def project_create(self, name, group_id, group_name, description=""):
        if not group_id or not group_name:
            raise FreedcampError(
                400, "group_id ET group_name sont requis par l'API pour creer "
                     "un projet (voir fc_groups).")
        resp = self.client.post("projects", {
            "project_name": name, "group_id": int(group_id),
            "group_name": group_name, "description": description})
        created = self.client.payload(resp, "projects")
        pid = str(created[0]["project_id"]) if created else None
        return self.project_get(pid)

    def project_archive(self, project_id):
        self.client.post("projects/%s" % project_id, {"f_archived": 1})
        return {"project_id": str(project_id), "archived": True}

    def groups(self):
        raw = self.client.payload(self.client.get("groups"), "groups")
        return [{"group_id": str(g.get("group_id")), "name": g.get("name")}
                for g in raw]

    # ------------------------------------------------------------ listes
    def lists(self, project_id):
        resp = self.client.get("lists/%d" % APP_TASKS,
                               {"project_id": str(project_id)})
        return [{"id": str(x.get("id")), "title": x.get("title"),
                 "project_id": str(project_id)}
                for x in self.client.payload(resp, "lists")]

    def list_create(self, project_id, title):
        resp = self.client.post("lists/%d" % APP_TASKS,
                                {"project_id": int(project_id), "title": title})
        created = self.client.payload(resp, "lists")
        lid = str(created[0]["id"]) if created else None
        for item in self.lists(project_id):
            if item["id"] == lid:
                return item
        return {"id": lid, "title": title, "project_id": str(project_id)}

    def list_archive(self, list_id):
        self.client.post("lists/%d/%s" % (APP_TASKS, list_id), {"f_archived": 1})
        return {"id": str(list_id), "archived": True}

    # ------------------------------------------------------------ taches
    def _fetch_tasks(self, project_id):
        out, offset = [], 0
        while True:
            resp = self.client.get("tasks", {"project_id": str(project_id),
                                             "limit": 200, "offset": offset})
            batch = self.client.payload(resp, "tasks")
            out.extend(batch)
            if len(batch) < 200:
                return out
            offset += len(batch)

    def tasks(self, project_id, status=None, assigned_to=None, list_id=None,
              query=None, milestone_id=None, limit=None):
        """Filtrage COTE CLIENT : l'API ignore ses propres parametres de filtre."""
        items = [self._task(t) for t in self._fetch_tasks(project_id)]
        if status == "open":
            items = [t for t in items if t["status"] != 1]
        elif status in STATUS_TO_CODE:
            items = [t for t in items if t["status"] == STATUS_TO_CODE[status]]
        elif status not in (None, "all"):
            raise ValueError("status invalide : %r (todo|in_progress|completed|"
                             "open|all)" % status)
        if assigned_to:
            items = [t for t in items if str(t["assigned_to_id"]) == str(assigned_to)]
        if list_id:
            items = [t for t in items if t["task_group_id"] == str(list_id)]
        if milestone_id:
            items = [t for t in items if t["milestone_id"] == str(milestone_id)]
        if query:
            q = query.lower()
            items = [t for t in items
                     if q in t["title"].lower() or q in t["description"].lower()]
        items.sort(key=lambda t: t["order"])
        return items[:limit] if limit else items

    def task_get(self, task_id):
        resp = self.client.get("tasks/%s" % task_id)
        raw = self.client.payload(resp, "tasks")
        if not raw:
            raise FreedcampError(404, "tache %s introuvable" % task_id)
        task = self._task(raw[0])
        task["comments"] = [self._comment(c) for c in (raw[0].get("comments") or [])]
        return task

    def task_create(self, project_id, title, list_id=None, description=None,
                    due_date=None, priority=None, assigned_to=None,
                    parent_id=None, milestone_id=None):
        payload = {"project_id": int(project_id), "title": title}
        if list_id:
            payload["task_group_id"] = int(list_id)
        if description:
            payload["description"] = description
        if due_date:
            payload["due_date"] = _check_date(due_date)
        if priority is not None:
            payload["priority"] = int(priority)
        if assigned_to:
            payload["assigned_to_id"] = int(assigned_to)
        if parent_id:
            payload["h_parent_id"] = int(parent_id)
        if milestone_id:
            payload["ms_id"] = int(milestone_id)
        created = self.client.payload(self.client.post("tasks", payload), "tasks")
        if not created:
            raise FreedcampError(500, "creation sans retour de tache")
        return self.task_get(created[0]["id"])

    def task_update(self, task_id, title=None, description=None, due_date=None,
                    priority=None, list_id=None, milestone_id=None):
        payload = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if due_date is not None:
            payload["due_date"] = _check_date(due_date)
        if priority is not None:
            payload["priority"] = int(priority)
        if list_id is not None:
            payload["task_group_id"] = int(list_id)
        if milestone_id is not None:
            payload["ms_id"] = int(milestone_id)
        if not payload:
            raise ValueError("aucun champ a modifier")
        self.client.post("tasks/%s" % task_id, payload)
        return self.task_get(task_id)        # relecture obligatoire

    def task_status_set(self, task_id, status):
        if status not in STATUS_TO_CODE:
            raise ValueError("status invalide : %r (todo|in_progress|completed)"
                             % status)
        self.client.post("tasks/%s" % task_id, {"status": STATUS_TO_CODE[status]})
        return self.task_get(task_id)

    def task_assign(self, task_id, user_id):
        self.client.post("tasks/%s" % task_id, {"assigned_to_id": int(user_id)})
        return self.task_get(task_id)

    def task_delete(self, task_id):
        self.client.delete("tasks/%s" % task_id)
        return {"id": str(task_id), "deleted": True}

    # ------------------------------------------------- operations en lot
    def tasks_create_bulk(self, project_id, tasks):
        """Cree plusieurs taches. Renvoie un rapport par element.

        Le quota Freedcamp se compte en minutes : un lot interrompu laisse
        un etat partiel. On ne leve donc PAS a la premiere erreur, on
        poursuit et on rend compte de chaque ligne (created / error),
        pour que l'appelant sache exactement ou reprendre.
        """
        if not isinstance(tasks, list) or not tasks:
            raise ValueError("tasks doit etre une liste non vide")
        rapport = []
        for index, spec in enumerate(tasks):
            titre = (spec or {}).get("title")
            if not titre:
                rapport.append({"index": index, "status": "error",
                                "error": "title obligatoire"})
                continue
            try:
                cree = self.task_create(
                    project_id, titre,
                    list_id=spec.get("list_id"),
                    description=spec.get("description"),
                    due_date=spec.get("due_date"),
                    priority=spec.get("priority"),
                    assigned_to=spec.get("assigned_to"),
                    parent_id=spec.get("parent_id"),
                    milestone_id=spec.get("milestone_id"))
                rapport.append({"index": index, "status": "created",
                                "task": cree})
            except (FreedcampError, ValueError) as exc:
                rapport.append({"index": index, "status": "error",
                                "title": titre, "error": str(exc)})
        return {"requested": len(tasks),
                "created": sum(1 for r in rapport if r["status"] == "created"),
                "failed": sum(1 for r in rapport if r["status"] == "error"),
                "results": rapport}

    def tasks_update_bulk(self, updates):
        """Modifie plusieurs taches. Chaque element porte son task_id.

        Meme principe : aucun arret premature, un rapport par ligne, et
        l'etat RELU de chaque tache modifiee.
        """
        if not isinstance(updates, list) or not updates:
            raise ValueError("updates doit etre une liste non vide")
        rapport = []
        for index, spec in enumerate(updates):
            task_id = (spec or {}).get("task_id")
            if not task_id:
                rapport.append({"index": index, "status": "error",
                                "error": "task_id obligatoire"})
                continue
            champs = {k: v for k, v in (spec or {}).items()
                      if k != "task_id" and v is not None}
            try:
                if "status" in champs:
                    statut = champs.pop("status")
                    self.task_status_set(task_id, statut)
                if "assigned_to" in champs:
                    self.task_assign(task_id, champs.pop("assigned_to"))
                relu = self.task_update(task_id, **champs) if champs \
                    else self.task_get(task_id)
                rapport.append({"index": index, "status": "updated",
                                "task": relu})
            except (FreedcampError, ValueError) as exc:
                rapport.append({"index": index, "status": "error",
                                "task_id": str(task_id), "error": str(exc)})
        return {"requested": len(updates),
                "updated": sum(1 for r in rapport if r["status"] == "updated"),
                "failed": sum(1 for r in rapport if r["status"] == "error"),
                "results": rapport}

    # ------------------------------------------------------------ jalons
    def milestones(self, project_id):
        try:
            resp = self.client.get("milestones", {"project_id": str(project_id)})
        except FreedcampError as exc:
            if exc.status == 400 and "access" in str(exc).lower():
                raise FreedcampError(
                    400, "l'app Milestones n'est pas activee sur le projet %s. "
                         "L'activer depuis l'interface Freedcamp (Project "
                         "Settings > Apps) : l'API ne permet pas de l'activer."
                         % project_id)
            raise
        return [{"id": str(m.get("id")), "title": m.get("title"),
                 "due_date": _ts_to_date(m.get("due_ts")),
                 "description": m.get("description") or "",
                 "status": m.get("status"), "priority": m.get("priority"),
                 "project_id": str(m.get("project_id") or project_id)}
                for m in self.client.payload(resp, "milestones")]

    def milestone_create(self, project_id, title, due_date=None, priority=1,
                         description=""):
        payload = {"project_id": int(project_id), "title": title,
                   "priority": int(priority), "description": description}
        if due_date:
            payload["due_date"] = _check_date(due_date)
        created = self.client.payload(
            self.client.post("milestones", payload), "milestones")
        mid = str(created[0]["id"]) if created else None
        for m in self.milestones(project_id):
            if m["id"] == mid:
                return m
        raise FreedcampError(500, "jalon cree mais introuvable en relecture")

    def milestone_update(self, milestone_id, project_id, title=None,
                         due_date=None, priority=None, description=None):
        payload = {}
        if title is not None:
            payload["title"] = title
        if due_date is not None:
            payload["due_date"] = _check_date(due_date)
        if priority is not None:
            payload["priority"] = int(priority)
        if description is not None:
            payload["description"] = description
        if not payload:
            raise ValueError("aucun champ a modifier")
        self.client.post("milestones/%s" % milestone_id, payload)
        for m in self.milestones(project_id):
            if m["id"] == str(milestone_id):
                return m
        raise FreedcampError(404, "jalon %s introuvable" % milestone_id)

    # ------------------------------------------------------ commentaires
    def comment_add(self, task_id, text):
        self.client.post("comments", {"item_id": int(task_id),
                                      "app_id": APP_TASKS, "description": text})
        return self.task_get(task_id)

    # ------------------------------------------------------ utilisateurs
    def users(self, project_id=None):
        params = {"project_id": str(project_id)} if project_id else None
        raw = self.client.payload(self.client.get("users", params), "users")
        out = []
        for u in raw:
            uid = u.get("user_id") or u.get("id")
            name = (" ".join(filter(None, [u.get("first_name"),
                                           u.get("last_name")])) or "").strip()
            out.append({"user_id": str(uid), "name": name or u.get("email", ""),
                        "email": u.get("email", "")})
        return out
