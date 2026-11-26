# Troubleshooting

[Docs home](README.md) › Troubleshooting

Problems seen when running or training the Named Entity Linker, with the cause and the fix.

## Running the service

| Symptom | Likely cause | Fix |
| :--- | :--- | :--- |
| `ModuleNotFoundError: No module named 'talkingdb'` | The `base-tdb-*` packages are not installed in the environment that runs [uvicorn](https://www.uvicorn.org/) | `poetry install --with dev`, then start with `make local` (which uses `poetry run`). For side by side edits, `make sync MODE=local` |
| `make local` fails on `--reload-dir ../base-tdb-models` | The base repositories are not cloned next to this one | Clone them as siblings, or run `make clone` in [infra-tdb-platform](https://github.com/TalkingDB/infra-tdb-platform) |
| `make: command not found` on Windows | The Makefile is Bash | Use [WSL](https://learn.microsoft.com/en-us/windows/wsl/about) Ubuntu or a dev container |
| `http://localhost:8092/` returns 404 but `/docs` works | `playground/dist` does not exist, so the UI is not mounted | `cd playground && npm install && npm run build` |
| The UI does not show a change you made in `playground/src` | `playground/dist` is committed and not rebuilt in CI | Run `npm run build` and commit `playground/dist` |
| Port 8092 already in use | Another NEL instance, or a container, is running | Stop it, or change `--port` in the `local` target |

## Data and databases

| Symptom | Likely cause | Fix |
| :--- | :--- | :--- |
| Data went to `data/*.db` instead of the paths you set | `ENTITY_DB`, `DICTIONARY_DB` and `REGEX_DB` were set after `talkingdb_nel` was imported; the connections open at import time | Set the variables in the environment before the process starts, or before the first import |
| `sqlite3.OperationalError: database is locked` | A long write (for example a bulk upload) holds the lock | Retry after it finishes; raise `TDB_SQLITE_BUSY_TIMEOUT_MS` (see [base-tdb-clients](https://github.com/TalkingDB/base-tdb-clients#configuration)) |
| A temporary database folder cannot be deleted on Windows | The connections stay open for the life of the process | Delete on a best effort basis at exit |
| `404 Namespace 'x' not found` | Every route below `/api/namespaces/{namespace}` checks the namespace exists | Create it first with `POST /api/namespaces` |

## Matching results

| Symptom | Likely cause | Fix |
| :--- | :--- | :--- |
| One phrase returns two or more entities | The same [surface text](https://github.com/TalkingDB/ConceptDigger/blob/main/docs/concepts.md#surface-texts-every-name-for-a-thing) is trained on more than one entity | Remove the duplicate from one entity. Treat duplicates as a vocabulary error and check for them before every bulk upload |
| A misspelt word is not matched | `word_correction` is `false`, or the word is more than one edit away | Send `"word_correction": true`. Correction allows one edit; add a surface text for common misspellings that are further away |
| A plural or other form is not matched | The lemmatizer did not reduce it to the trained form | Add the form as a surface text |
| A regex match disappears | It overlapped a date match; date rule hits win over other regex hits on the same characters | Narrow the date rule or the other pattern so they do not overlap |
| Words come back in `no_tag_entities` | Nothing in the namespace matches them | Train the missing vocabulary, then add a test case so it stays fixed |
| Accuracy changed after training | New surface texts can change existing matches | Compare test runs by commit, and roll back with `POST .../commits/{commit_id}/rollback` if needed |

## Further reading

- [SQLite: database is locked](https://www.sqlite.org/rescode.html#busy)
- [Vite: building for production](https://vite.dev/guide/build)

---

**Related:** [Usage and examples](usage-and-examples.md) · [Architecture Decision Records](adrs/README.md) · [Architecture (C4 model)](architecture/README.md) · [README](../README.md)
