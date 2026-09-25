"""Transport HTTP + authentification HMAC-SHA1 pour l'API Freedcamp.

Cette couche ne connait RIEN du metier ni de MCP : elle signe, envoie,
et remonte les erreurs proprement. Le secret n'apparait jamais dans un
message d'erreur.
"""
import hashlib
import hmac
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://freedcamp.com/api/v1"
DEFAULT_TIMEOUT = 30


class FreedcampError(RuntimeError):
    """Erreur d'API. Porte le code HTTP et le message serveur."""

    def __init__(self, status, message, payload=None):
        self.status = status
        self.payload = payload
        super().__init__("HTTP %s : %s" % (status, message))


def _secrets_path():
    """Emplacement du fichier d'identifiants.

    Ordre de recherche :
      1. $FREEDCAMP_CREDENTIALS (chemin explicite)
      2. ~/.freedcamp-mcp.json  (defaut portable)
      3. $LOCALAPPDATA/hermes/secrets/freedcamp.json (integration Hermes)
    """
    explicite = os.environ.get("FREEDCAMP_CREDENTIALS")
    if explicite:
        return pathlib.Path(explicite)

    maison = pathlib.Path.home() / ".freedcamp-mcp.json"
    if maison.exists():
        return maison

    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        hermes = pathlib.Path(localappdata) / "hermes" / "secrets" / "freedcamp.json"
        if hermes.exists():
            return hermes
    return maison


class FreedcampClient:
    """Client HTTP signe. Reutilisable, sans etat entre les appels."""

    def __init__(self, api_key=None, api_secret=None, base_url=BASE_URL,
                 timeout=DEFAULT_TIMEOUT):
        if api_key is None or api_secret is None:
            path = _secrets_path()
            if not path.exists():
                raise FreedcampError(
                    0, "Identifiants absents : %s. Les generer sur "
                       "https://freedcamp.com/manage/account (onglet API)." % path)
            conf = json.loads(path.read_text(encoding="utf-8"))
            api_key = api_key or conf.get("api_key")
            api_secret = api_secret or conf.get("api_secret", "")
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # -- signature ---------------------------------------------------------
    def _auth(self):
        params = {"api_key": self.api_key}
        if self.api_secret:
            ts = str(int(time.time()))
            params["timestamp"] = ts
            params["hash"] = hmac.new(
                self.api_secret.encode(), (self.api_key + ts).encode(),
                hashlib.sha1).hexdigest()
        return params

    def _scrub(self, text):
        """Retire toute trace du secret et de la cle d'un message."""
        for v in (self.api_secret, self.api_key):
            if v and len(v) > 6:
                text = text.replace(v, "***")
        return text

    # -- requete -----------------------------------------------------------
    def request(self, path, params=None, data=None, method=None, _retries=4):
        """Envoie la requete signee.

        Rejoue sur 429 (quota) et 5xx avec un recul exponentiel genereux.
        Le quota Freedcamp est strict et sa fenetre se compte en minutes :
        un recul de quelques secondes ne suffit pas, d'ou 5s/15s/45s/135s.
        """
        query = self._auth()
        query.update({k: v for k, v in (params or {}).items() if v is not None})
        url = "%s/%s?%s" % (self.base_url, path.lstrip("/"),
                            urllib.parse.urlencode(query))
        body = None
        headers = {"User-Agent": "gunouze-freedcamp-mcp/1.0"}
        if data is not None:
            body = urllib.parse.urlencode({"data": json.dumps(data)}).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=body, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and _retries > 0:
                time.sleep(5 * (3 ** (4 - _retries)))
                return self.request(path, params, data, method, _retries - 1)
            raw = exc.read().decode("utf-8", "replace")
            message, payload = raw[:300], None
            try:
                payload = json.loads(raw)
                message = str(payload.get("msg", message))
                errors = (payload.get("data") or {}).get("errors")
                if errors:
                    message += " | " + json.dumps(errors, ensure_ascii=False)[:200]
            except ValueError:
                pass
            raise FreedcampError(exc.code, self._scrub(message), payload)
        except urllib.error.URLError as exc:
            if _retries > 0:
                time.sleep(5 * (3 ** (4 - _retries)))
                return self.request(path, params, data, method, _retries - 1)
            raise FreedcampError(0, self._scrub("reseau indisponible : %s"
                                                % exc.reason))

    def get(self, path, params=None):
        return self.request(path, params=params)

    def post(self, path, data, params=None):
        return self.request(path, params=params, data=data)

    def delete(self, path, params=None):
        return self.request(path, params=params, method="DELETE")

    @staticmethod
    def payload(response, key):
        """Extrait data.<key> d'une reponse, toujours sous forme de liste."""
        value = (response.get("data") or {}).get(key)
        if value is None:
            return []
        return value if isinstance(value, list) else [value]
