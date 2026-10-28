# Tags: how coding skills are matched to a task

Coding skills in `registry.toml` carry `tags`. A skill is given to a unit only when **every** tag of the skill is among the unit's tags. A skill with `tags = []` (for example `tdd`) applies to every coding unit. Tags are lowercase; `registry.toml` is rejected when an entry uses a tag that is not listed here.

A unit's tags are the union of three sources:

1. **Stack tags**, detected from the workspace by `detect_stack.py` (no model involved).
2. **Layer tags**, added by sharron from the request and the coding intake answer.
3. **Activity tags**, added by sharron from the unit's goal.

## Stack tags (detected)

| Tag | Meaning |
|---|---|
| `python` | Python code |
| `javascript` | JavaScript or Node code |
| `typescript` | TypeScript code |
| `rust` | Rust code |
| `go` | Go code |
| `terraform` | Terraform configuration |
| `helm` | Helm chart |
| `kubernetes` | Kubernetes manifests |
| `bash` | Shell scripts |
| `docker` | Docker images |
| `frontend` | A browser UI framework (React, Vue, Next.js or Nuxt) |
| `threejs` | three.js 3D graphics |
| `cloudflare` | Cloudflare Workers or Pages |

### Detection rules

`detect_stack.py` looks at the files in the workspace and in the folders up to 3 levels below it. It skips hidden folders and `node_modules`, `venv`, `dist`, `build`, `target`, `vendor` and `__pycache__`, and reads at most the first 64 KB of a file.

| Found | Tags |
|---|---|
| `pyproject.toml`, `setup.py`, `requirements.txt` | `python` |
| `package.json` | `javascript`; a `react`, `react-dom`, `vue`, `next` or `nuxt` dependency adds `frontend`; `three` adds `threejs` (dependencies and devDependencies) |
| `tsconfig.json` | `typescript` |
| `Cargo.toml` | `rust` |
| `go.mod` | `go` |
| `*.tf` | `terraform` |
| `Chart.yaml` | `helm`, `kubernetes` |
| `*.yaml` or `*.yml` with lines starting `apiVersion:` and `kind:` | `kubernetes` |
| `*.sh`, `*.bash`, or a first line matching `^#!.*\b(ba)?sh\b` | `bash` |
| `Dockerfile` | `docker` |
| `wrangler.toml`, `wrangler.json`, `wrangler.jsonc` | `cloudflare` |

Run it with `sh <skill>/scripts/run.sh detect_stack.py tags --workspace <folder>`. It prints `{"tags": [...]}`.

## Layer tags (added from the request)

| Tag | Meaning |
|---|---|
| `backend` | Server-side code, services, data handling |
| `frontend` | Browser UI (also detected from React, Vue, Next.js and Nuxt) |
| `infra` | Infrastructure, deployment, cloud configuration |
| `cli` | A command-line program |
| `ui-design` | Visual design of an interface |

The workspace cannot show what the user wants to build, so sharron reads the request and the answer to the coding intake question and adds the layers that apply. A request for a landing page adds `frontend` and `ui-design`; a request for an API adds `backend`; a Helm or Terraform change adds `infra`. Sharron never adds `frontend` or `ui-design` to a backend task. Detection can still add `frontend` or `threejs` when a matching dependency sits anywhere in the tree, such as a `web/package.json` in a monorepo, so only skills that need `ui-design` are sure to stay away from backend work. When the request does not say, add no layer tag rather than guess.

## Activity tags (added from each unit's goal)

| Tag | Meaning |
|---|---|
| `testing` | Writing or running tests |
| `async` | Asynchronous code |
| `concurrency` | Goroutines, threads and shared state |
| `database` | Database access and schema |
| `grpc` | gRPC services |
| `cli` | Building a command-line interface |
| `observability` | Logging, metrics and tracing |
| `performance` | Profiling and speed |
| `new-project` | Starting a project from scratch |
| `refactoring` | Restructuring existing code |
| `import` | Importing existing resources (for example into Terraform) |
| `lint` | Linters and static checks |

sharron gives each coding unit the activity tags that its own goal needs, not the whole task's: `python-testing-patterns` (`python`, `testing`) then reaches only the unit that writes tests. `cli` is both a layer and an activity tag; either source makes it part of the unit's tags.

## Selecting skills

```
sh <skill>/scripts/run.sh detect_stack.py select --role <role> --playbook <playbook> --domain <domain> --tier <T1|T2|T3> \
    [--tags <layer and activity tags, comma-separated>] [--workspace <folder>]
```

It unions the detected tags with `--tags` (an unknown tag exits 1) and prints:

```json
{"tags": ["python", "testing"],
 "skills": [{"name": "...", "repo": "...", "plugin": "...", "matched": ["python", "testing"], "min_tier": "T2"}],
 "dropped": ["..."]}
```

An entry is selected when all of these hold:

- its `status` is `active`;
- the unit's role is in its `roles`, or `roles` is `["*"]`; the same for `playbooks` and `domains`;
- its `min_tier` is not above the unit's tier;
- every tag of the entry is among the unit's tags.

When more entries match than `max_skills_per_brief` (default 4), the most specific win: more tags first, then the lower `min_tier`, then registry order. The rest are listed under `dropped`; sharron may still add one of them back or drop a selected skill, with a one-line reason.

## In the brief

Each selected skill goes into the brief with the tags that matched it, so the choice can be checked:

```
python-testing-patterns — matched: python, testing
```
