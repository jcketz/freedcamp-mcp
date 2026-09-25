# freedcamp-mcp

A **local, dependency-free MCP server** for [Freedcamp](https://freedcamp.com):
projects, lists, tasks, milestones, assignments, comments, archiving, and bulk
operations.

Python 3.11, **standard library only** — no `pip install`, no `node_modules`,
no Docker. MCP over stdio (JSON-RPC 2.0), written from scratch.

---

## Why a local server when Freedcamp ships an official hosted one?

Freedcamp [announced a hosted MCP server](https://blog.freedcamp.com/2026/05/07/freedcamp-mcp-drive-your-entire-workspace-from-any-ai-assistant/)
with 100+ tools. It works. This project exists anyway, for reasons that are
**measured rather than assumed**.

### Tool-catalogue weight — the number that matters most

An MCP client pays for the tool catalogue **on every conversation turn**,
whether or not a tool is ever called. Measured on the same account:

| | this server | official hosted |
|---|---|---|
| Tools exposed | 22 | 102 |
| Catalogue size | 7.4 KB (**~1 840 tokens**) | 42.2 KB (**~10 545 tokens**) |

That is roughly **8 700 tokens of context reclaimed on every turn** for the
actual conversation. If your assistant never touches the CRM, time-tracking or
wiki modules, you are carrying 40 tool definitions you will never call — and a
larger catalogue also degrades tool-selection accuracy.

### Latency

Best / mean over 3 runs, same account, same data:

| Operation | this server | official hosted |
|---|---|---|
| List projects | **0.36 s / 0.43 s** | 0.94 s / 1.04 s |
| List tasks (75 items) | **0.37 s / 0.44 s** | 1.18 s / 1.26 s |

No round-trip to a third party, no multi-tenant queue.

### The reasons that are not numbers

- **You can change it.** Domain policy — client-side filtering because the API
  ignores its own filters, mandatory re-read after every write, rejecting
  malformed dates — is *yours*, not a vendor's. Bulk operations were added here
  in under an hour. With a hosted service you file an issue and wait.
- **Hosted endpoints move.** The URL published in Freedcamp's own announcement
  (`mcp-oauth.freedcamp.top`) **no longer resolves** four months later; the
  working host today is `mcp.freedcamp.top`. A scheduled job depending on it
  would have failed silently.
- **Credentials stay on your machine.** A hosted server carries your API key and
  secret in headers to a third party on every request. Here they are read from a
  local file and never leave the process.

### When the official server is the better choice

Be honest about this: it is zero-maintenance, and it covers far more surface.
See *What this does not cover* below before choosing.

---

## What this does NOT cover

This server deliberately covers the **task-management core** and covers it
carefully. Freedcamp has many more apps. Not implemented here:

| Freedcamp app | Status here | Why |
|---|---|---|
| **CRM** (contacts, calls) | ✗ | Out of scope; the hosted server has 10 tools for it |
| **Time tracking** | ✗ | Out of scope; hosted has 9 tools |
| **Wikis** | ✗ | Out of scope; hosted has 6 tools |
| **Issue tracker** | ✗ | Distinct app (app_id 9), same API shape — easy to add |
| **Calendar events** | ✗ | Distinct app (app_id 10) |
| **Discussions** | ✗ | Distinct app (app_id 5) |
| **File upload** | ✗ | Requires multipart; only file *metadata* is reachable today |
| **Custom fields** | ✗ | Readable via `f_adv_data`, never written |
| **Tags** | ✗ **by design** | The API accepts them and persists nothing — see pitfalls |
| **Enabling an app on a project** | ✗ **impossible** | No API endpoint; use the web UI |
| **Notifications, invitations, backups** | ✗ | Out of scope |
| **Recurring tasks** (`r_rule`) | ✗ | Field exists, untested here |

Also absent: OAuth (this uses API key + secret), multi-account support, and any
form of caching.

### Falling back to the official server for the rest

The two are **complementary, and can run side by side** — nothing conflicts,
they are separate MCP servers with separate tool prefixes:

```json
{
  "mcpServers": {
    "freedcamp": {
      "command": "python",
      "args": ["/path/to/freedcamp-mcp/src/server.py"]
    },
    "freedcamp-full": {
      "url": "https://mcp.freedcamp.top/mcp",
      "headers": {
        "X-Freedcamp-Api-Key": "...",
        "X-Freedcamp-Api-Secret": "..."
      }
    }
  }
}
```

A pragmatic split:

- **Daily task work** → this server. Light catalogue, fast, predictable,
  pitfalls neutralised.
- **Occasional CRM / time / wiki / files** → enable the hosted one when you
  actually need it, disable it afterwards. You pay its ~10 500-token catalogue
  only while it is on.
- **Adding a missing feature** → the hosted server is a good *reference* for
  payload shapes. Implementing it here keeps the catalogue small and the
  behaviour yours. `src/api.py` is the only file to touch for a new endpoint;
  `src/server.py` for its tool definition.

Note the two servers use different naming (`fc_tasks` here, `tasks_list`
there), so running both never creates ambiguity for the model.

---

## Install

```bash
git clone https://github.com/<you>/freedcamp-mcp.git
cd freedcamp-mcp
```

Nothing to install for the server itself. `pytest` only if you run the tests.

Credentials are read from `FREEDCAMP_CREDENTIALS` (a path), or
`~/.freedcamp-mcp.json`:

```json
{"api_key": "...", "api_secret": "..."}
```

Generate them at https://freedcamp.com/manage/account → Integrations / API.
Prefer a **secret-secured key**: requests are signed with HMAC-SHA1, so the
secret itself never travels.

Register with any MCP client:

```json
{
  "mcpServers": {
    "freedcamp": {
      "command": "python",
      "args": ["/path/to/freedcamp-mcp/src/server.py"]
    }
  }
}
```

## Tools

**Read** — `fc_whoami`, `fc_projects`, `fc_groups`, `fc_lists`, `fc_tasks`,
`fc_task_get`, `fc_milestones`, `fc_users`

**Write** — `fc_task_create`, `fc_task_update`, `fc_task_status_set`,
`fc_task_assign`, `fc_task_delete`, `fc_list_create`, `fc_list_archive`,
`fc_milestone_create`, `fc_milestone_update`, `fc_comment_add`,
`fc_project_create`, `fc_project_archive`

**Bulk** — `fc_tasks_create_bulk`, `fc_tasks_update_bulk`

Every write **re-reads** the resource and returns its actual state. Bulk
operations never abort on the first failure: they return a per-row report
(`created` / `updated` / `error`), so a rate-limit cut-off mid-batch leaves you
knowing exactly where to resume.

## Freedcamp API pitfalls

Found by **end-to-end exploration against the live API**, not by reading docs.
The official documentation and every third-party wrapper get several of these
wrong. This table is arguably the most useful part of the repository.

| Pitfall | Reality |
|---|---|
| **Task status** | `0` = No Progress, **`1` = Completed**, **`2` = In Progress**. Counter-intuitive, and the opposite of what popular wrappers document. Writing `3` silently falls back to `2`. |
| **`due_date`** | Must be a **string** `YYYY-MM-DD`. An integer returns `200 OK` and **wipes the date** (`due_ts` becomes `-3600`). Entirely silent. |
| **Task → milestone** | The field is `ms_id`. `milestone_id` and `task_milestone_id` return `200 OK` and do nothing. |
| **Lists endpoint** | `GET /lists/2` — the app id goes in the **path**. `GET /lists?app_id=2` returns `400 This app is not supported`. |
| **Server-side filters** | `status`, `assigned_to_id`, `q`, `order` are **ignored**. Only `limit`/`offset` work. Filter client-side. |
| **Tags** | `tags`, `tag_names`, `new_tags`, `item_tags` all return `200 OK` and **persist nothing**. Not exposed here on purpose: a tool that silently no-ops is worse than a missing one. |
| **Enabling an app** | Not possible via API. Milestones must be enabled in the web UI (*Project Settings → Apps*). A fresh project ships without it. |
| **Creating a project** | Requires **both** `group_id` and `group_name`. |
| **Creating a milestone** | `priority` is mandatory. |
| **Reading comments** | Via `GET /tasks/{id}` → `comments` field. `GET /comments?item_id=` returns 404. |
| **Archiving a project** | The field is **`f_active: 0`**, not `f_archived`. `f_archived`, `archived` and `status` all return `200 OK` and **do nothing**. A project you believe archived stays visible in the user's workspace. |
| **Deleting a project** | `DELETE /projects/<id>` returns **501 — not available publicly**. Archiving is the only exit; a project created by mistake can never be erased. |
| **Rate limit** | Strict, recovery window measured in **minutes**. The client retries 429/5xx with 5s/15s/45s/135s backoff. Never run two Freedcamp workloads in parallel. |
| **UTF-8 on Windows** | A subprocess' stdout defaults to cp1252 and silently mangles accented labels. `sys.stdout.reconfigure(encoding="utf-8")` is required. |

## Tests

```bash
python -m pytest tests/ -q
```

**Zero mocks.** Everything runs against the live API inside throwaway sandbox
projects, archived on teardown, plus a session-wide safety net that archives any
`ZZ *` project left active — loudly reporting failures rather than swallowing
them. Mocks would have hidden every pitfall above — each one is a gap between
documented and actual behaviour.

> A teardown that swallows its own failure (`except Exception: pass`) is worse
> than no teardown: seventeen sandbox projects once polluted a real workspace
> because the archive call was broken *and* silenced. Cleanup code must verify
> and must shout.

`FC_TEST_THROTTLE` (default 1.5 s) spaces calls to stay under the rate limit.
A full run takes ~20 minutes; that is the API's constraint, not the code's.

`cleanup_sandbox.py` archives leftover `ZZ *` sandbox projects.

## Architecture

```
src/client.py   HTTP transport, HMAC signing, retry.   Knows no Freedcamp semantics.
src/api.py      Freedcamp operations, pitfalls encapsulated.   Knows nothing of MCP.
src/server.py   MCP layer (JSON-RPC over stdio).   Speaks no HTTP.
```

Strictly one-directional: `server → api → client`.

## Licence

MIT.
