# remanence

`remanence` — outil d'**acquisition de disquettes** (mode Dump) et de **consultation
du catalogue** (mode Library), avec interface graphique PySide6. Cible **Linux**.

> *Rémanence* : l'aimantation résiduelle, ce qui survit sur le support — métaphore de
> la préservation.

Le logiciel produit, pour chaque disque, un livrable dans `staging/<run>/` : flux,
image décodée (si possible), photos typées et retouchées, métadonnées et un
`manifest.yaml` avec empreintes `sha256`. Les données vivent dans un dépôt distinct
(`floppy-archive`).

## Architecture

Séparation stricte **cœur / interface** (cf. `CONVENTIONS.md`, source de vérité, et
`SOFTWARE-SPEC.md`) :

- `remanence/core/` — logique métier, testable sans GUI ni matériel.
- `remanence/gui/` — PySide6 (modes Dump + Library), orchestre `core/`.
- `remanence/cli/` — entrée `remanence` (dump, `--check`, `--dry-run`).
- `schemas/` — JSON Schema (validés à l'écriture des YAML).
- `tests/` — pytest + pipelines *fixture* (chaîne complète sans matériel).

## Développement

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
remanence --check        # validation pipelines.yaml + préflight des outils
```

## Licence

Code sous **CeCILL-2.1** (voir `LICENSE`). Les œuvres tierces archivées ne sont pas
relicenciées ; elles sont régies item par item (cf. `CONVENTIONS.md` §10).
