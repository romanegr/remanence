# CLAUDE.md — dépôt `remanence` (développement du logiciel)

> **Contexte Claude Code « développement ».** À relire au début de chaque session de
> code. Distinct du `CLAUDE.md` du dépôt `floppy-archive` (analyse/organisation des
> dumps). La spécification fonctionnelle est dans **`SOFTWARE-SPEC.md`** ; les schémas,
> vocabulaires et conventions dans **`CONVENTIONS.md`** (source de vérité). En cas de
> contradiction : `CONVENTIONS.md`, puis `SOFTWARE-SPEC.md`, puis ce fichier.

---

## 1. Mission

Développer et maintenir **`remanence`** : application Python à interface **PySide6**, cible **Linux uniquement**, offrant deux modes — **Dump** (acquisition de disquettes) et **Library** (consultation du catalogue, visualisation des listings et du flux).

## 2. Règles dures

1. **Tout en anglais** : code, noms de fichiers/répertoires, identifiants, variables, clés de données et **valeurs de vocabulaires contrôlés** (cf. `CONVENTIONS.md` §3). La prose des docs peut rester en français.
2. **Séparation cœur / interface** : toute la logique métier dans `remanence/core/` (testable sans GUI ni matériel) ; `gui/` et `cli/` n'orchestrent que `core/`. Aucune logique métier dans la GUI.
3. **Schémas = source de vérité** : lire/écrire les YAML conformément aux JSON Schema de `schemas/` ; valider à l'écriture. Ne pas diverger des schémas de `CONVENTIONS.md` §5 (inclure `schema_version`).
4. **Mode sans matériel obligatoire** : les pipelines *fixture* (commandes simulées) doivent permettre de dérouler toute la chaîne sans lecteur ni disque. Tout code matériel passe par là pour les tests.
5. **Commandes matérielles = squelettes à confirmer** : les invocations réelles (`gw`, OpenCBM, ADTPro…) sont générées comme squelettes explicitement marqués « à confirmer », jamais présentées comme testées (Claude Code ne les exécute pas).
6. **Pas de réseau pour le dump**, **aucun secret dans le dépôt** (clés Internet Archive hors dépôt, via `ia configure`).
7. **Écritures sûres** : atomiques, jamais d'écrasement silencieux ; n'écrire que dans `staging/` et le stock blobs configuré.
8. **Licence** : code sous **CeCILL-2.1** ; en-tête de licence dans les fichiers sources, `LICENSE` à la racine.

## 3. Conventions de code

- Casses : `snake_case` (fonctions, variables, clés YAML), `PascalCase` (classes), `SCREAMING_SNAKE` (constantes), `kebab-case` (slugs, dossiers de catalogue).
- Python ≥ 3.11. Dépendances figées (`pyproject.toml`/`requirements.txt`) : `PySide6`, `opencv-python`, `Pillow`, `numpy`, `ruamel.yaml`, `d64`, `greaseweazle` (via URL Git).
- Outils système (hors pip) vérifiés au préflight : OpenCBM (+xum1541), VICE (`c1541`/`petcat`), `mtools`, AppleCommander, ADTPro.

## 4. Quoi construire

Implémenter les exigences de `SOFTWARE-SPEC.md` : F1 sélection format/pipeline + préflight ; F2 acquisition ; F3 disque défectueux et multi-flux ; F4 photos (typage anglais front/back/label/sleeve/manual/other + retouche) ; F5 métadonnées ; F6 génération du staging + manifeste + `sha256` ; F7 dry-run/fixtures ; F8 `remanence --check` ; F9 reprise ; **F10 bibliothèque** ; **F11 visualisation flux**. Modules cibles : `core/{pipelines,runner,flux,fluxview,images,listing,catalog,manifest,staging}.py`, `gui/`, `cli/`, `schemas/`, `tests/`.

## 5. Tests

- **pytest** ; couvrir `core/` sans GUI ni matériel.
- Pipelines **fixture** pour la chaîne complète hors matériel.
- Valider chaque YAML produit contre son schéma dans les tests.

## 6. Méthode de travail

- **Procéder en deux temps** : d'abord proposer/valider l'arborescence + `pyproject.toml` + schémas + le format de `pipelines.yaml`, **puis** implémenter par incréments (un module/feature à la fois, avec tests).
- Ne pas tout générer d'un bloc sans validation.
- Tenir `schemas/` et les tests à jour à chaque évolution de structure.

## 7. Interdits

- Logique métier dans la GUI ; dépendance réseau pour le dump ; secrets ou blobs commités ; commandes matérielles présentées comme testées ; identifiants/chemins/énumérations non anglais ; divergence vis-à-vis des schémas de `CONVENTIONS.md`.

## 8. Checklist de fin de session

- [ ] Code et identifiants en anglais ; conventions de casse respectées.
- [ ] Logique dans `core/`, GUI/CLI en simples orchestrateurs.
- [ ] YAML conformes aux schémas (`schema_version` inclus) ; validation testée.
- [ ] Mode fixture fonctionnel (chaîne complète sans matériel).
- [ ] Commandes matérielles marquées « à confirmer ».
- [ ] Aucun secret ni blob ajouté ; en-têtes CeCILL-2.1 présents.
- [ ] Tests passants ; `remanence --check` opérationnel.
