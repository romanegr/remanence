# CONVENTIONS.md — Référentiel unique du projet

> **Source de vérité unique** pour les règles, vocabulaires et schémas. Les autres
> documents (`ARCHITECTURE.md`, `CLAUDE.md`, `SOFTWARE-SPEC.md`) y renvoient et **ne
> redéfinissent pas** ces éléments. En cas de divergence, **ce fichier fait foi**.
> Prose en français ; **tous les identifiants, chemins, noms et vocabulaires en anglais**.

---

## 1. Décisions verrouillées

- **Bibliothèque intégrée** à l'application (un seul logiciel, deux modes : Dump et Library).
- **Cible Linux uniquement** (v1).
- **Granularité d'item** : par défaut 1 disque = 1 item ; regroupement multi-disques seulement si tout cohérent.
- **Nommage des fichiers d'images** : TOSEC (voir §6).
- **Pivot d'intégrité** : `sha256` de chaque fichier ; correspondance par hash, jamais par nom.
- **Garde-fous d'upload** : `status: ready` requis, blocage `commercial` sans dérogation explicite, unicité d'identifiant vérifiée.

### Noms et dépôts (décidés)

- **Application** : **`remanence`** (la rémanence magnétique : l'aimantation résiduelle, ce qui survit sur le support — métaphore de la préservation).
- **Deux dépôts** : `remanence` (le logiciel) et `floppy-archive` (les données/catalogue). Chacun a **son propre `CLAUDE.md`** (deux contextes Claude Code distincts, voir §4).
- **Licences** : code en **CeCILL-2.1**, données/métadonnées en **Licence Ouverte 2.0 (Etalab)** (voir §10).

---

## 2. Convention de langue et de nommage

- **Anglais obligatoire** pour : code, noms de répertoires, noms de fichiers, identifiants, variables, **clés** de métadonnées et **valeurs de vocabulaires contrôlés** (§3).
- La **prose documentaire** peut rester en français ; les données d'exemple libres (ex. `condition: "support oxydé"`) aussi. Mais jamais une clé ou une valeur d'énumération.
- **Casses** : `snake_case` pour les clés YAML/Python ; `kebab-case` pour les slugs et dossiers de catalogue ; `PascalCase` pour les classes ; `SCREAMING_SNAKE` pour les constantes.
- **Documents du dépôt en anglais** : `README.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `CLAUDE.md`, `SOFTWARE-SPEC.md`.

Correspondance avec les brouillons actuels (à renommer lors du scaffolding) :

| Brouillon (FR) | Fichier cible |
|---|---|
| conception-pipeline-archivage.md | `ARCHITECTURE.md` |
| MANUEL-CLAUDE-CODE.md | `CLAUDE.md` |
| cahier-des-charges-logiciel-dump.md | `SOFTWARE-SPEC.md` |

---

## 3. Vocabulaires contrôlés (anglais)

| Champ | Valeurs |
|---|---|
| `platform` | `commodore-c64`, `apple-ii`, `ibm-pc`, `amiga`, `atari-st`, … (kebab-case) |
| `preservation_level` | `gold` (flux+image vérifiée) · `silver` (flux sans décodage vérifié) · `bronze` (image seule ou capture partielle) |
| `decode_status` | `ok` · `failed` · `not_attempted` |
| `kind` | `single_title` · `compilation` |
| `status` | `draft` · `ready` · `published` |
| `copyright_status` | `public_domain` · `freeware` · `shareware` · `licenseware` · `cardware` · `commercial` · `unknown` |
| `photo.type` | `front` · `back` · `label` · `sleeve` · `manual` · `other` |
| `acquisition.method` | `greaseweazle` · `opencbm` · `adtpro` · `applesauce` · … |
| `file.role` | `flux` · `image` · `listing` · `photo` · `readlog` · `checksums` |

> Remplace les libellés français antérieurs (recto→`front`, verso→`back`, étiquette→`label`, pochette→`sleeve`, notice→`manual`, autre→`other`).

---

## 4. Structure des dépôts (deux dépôts, deux contextes Claude Code)

Chaque dépôt a **son propre `CLAUDE.md`** : le contexte Claude Code du dépôt logiciel (développement) est distinct de celui du dépôt de données (analyse/organisation des dumps).

**`remanence/`** — le logiciel (code réutilisable, versionné indépendamment) :

```
remanence/
├── README.md
├── LICENSE                   # CeCILL-2.1
├── CLAUDE.md                 # contexte Claude Code « développement » (cf. §… du SOFTWARE-SPEC)
├── CONVENTIONS.md            # copie/lien du référentiel partagé
├── pyproject.toml            # ou requirements.txt figé
├── remanence/
│   ├── core/                 # logique métier (sans GUI)
│   ├── gui/                  # PySide6 : modes Dump + Library
│   └── cli/                  # entrée `remanence` (équiv. `dump`)
├── schemas/                  # JSON Schema (validation) — voir §5
└── tests/                    # pytest + fixtures
```

**`floppy-archive/`** — les données et la gouvernance (croît dans le temps) :

```
floppy-archive/
├── README.md
├── LICENSE                   # Licence Ouverte 2.0 (données/métadonnées)
├── CONVENTIONS.md            # ce fichier (référence partagée)
├── ARCHITECTURE.md
├── CLAUDE.md                 # contexte Claude Code « analyse/organisation » (manuel opératoire)
├── pipelines.yaml            # registre des pipelines (matériel local)
├── .gitignore
├── staging/                  # zone d'attente (métadonnées versionnées, blobs ignorés)
└── catalog/<platform>/<item-slug>/   # items finalisés
```

Le **stock blobs** (`~/floppy-blobs/`, flux/images) est **hors des deux dépôts** (§7). `remanence` lit `pipelines.yaml` et écrit dans `staging/` ; Claude Code (contexte floppy-archive) organise `catalog/` ; le script d'upload publie. `CONVENTIONS.md` est partagé entre les deux dépôts (lien de symbole, sous-module, ou copie synchronisée).

---

## 5. Schémas (source unique)

Chaque artefact porte un `schema_version` (entier) pour permettre les migrations.

### `manifest.yaml` (unifié — multi-flux + disque défectueux)

```yaml
schema_version: 1
run_id: 2026-06-11_run01
pipeline_id: gw-c64-1541
captured_by: "operator-id"
date_captured: 2026-06-11T14:32:00+02:00
platform_hint: commodore-c64
acquisition:
  method: greaseweazle
  hardware: "Greaseweazle V4 + 5.25 drive"
  software: "gw 1.23"
  revolutions: 5
  preservation_level: silver
decode_status: failed
needs_redecode: true
flux_stable: false
physical:
  media: "5.25 DD"
  sides: 1
  write_protected: false
  condition: "oxidized, hard to read"
label_text_file: label.txt
listing_file: null
files:
  - { temp_name: flux_read01.scp, role: flux,  format: scp, variant: 1, best: false,
      sha256: "a1…", read_quality: "12 weak sectors", upload: true, tosec_name: null }
  - { temp_name: flux_read02.scp, role: flux,  format: scp, variant: 2, best: true,
      sha256: "b2…", read_quality: "9 weak sectors",  upload: true, tosec_name: null }
photos:
  - { file: photos/front.jpg, type: front, edits: { keystone: true, ratio: "5.25" } }
  - { file: photos/back.jpg,  type: back,  edits: { brightness: 8, contrast: 5 } }
```

Cas nominal : `decode_status: ok`, `preservation_level: gold`, un flux + une image, `listing_file` renseigné.

### `item.yaml`

```yaml
schema_version: 1
ia_identifier: bards-tale-the-1985-electronic-arts-c64
status: draft                      # draft | ready | published
title: "Bard's Tale, The"
kind: single_title                 # single_title | compilation
date: 1985
publisher: "Electronic Arts"
platform: commodore-c64
country: US                        # ISO 3166-1 alpha-2
language: en                       # ISO 639-1
copyright_status: commercial
publish_despite_copyright: false   # décision humaine exclusive
subjects: ["Commodore 64", "floppy disk preservation"]
cross_refs: { tosec: "", mobygames: "" }
collection: opensource
rights: "see description.md"
disks: [disk-01, disk-02]
notes: ""
```

### `contents.yaml`

```yaml
schema_version: 1
titles:
  - { title: "Bard's Tale, The", date: 1985, publisher: "Electronic Arts", on_disks: [disk-01, disk-02] }
```

Déduplication : un titre sur plusieurs disques = une entrée (`on_disks`). Versions différentes = entrées distinctes (champ `version`).

### `disk-NN.yaml`

```yaml
schema_version: 1
disk_id: disk-01
media_type: "Disk 1 of 2"
media_label: ""
physical: { media: "5.25 DD", sides: 1, write_protected: false, condition: "good" }
label_text: "BARDS TALE DISK 1"
acquisition:
  method: greaseweazle
  hardware: "Greaseweazle V4 + 5.25 drive"
  software: "gw 1.23"
  revolutions: 5
  preservation_level: gold
  read_quality: "clean"
  readlog: disk-01.readlog.txt
files:
  - { role: flux,  format: scp, sha256: "e3b0…", tosec_name: "Bard's Tale, The (1985)(Electronic Arts)(US)(Disk 1 of 2)[!].scp", upload: true }
  - { role: image, format: d64, sha256: "9f86…", tosec_name: "Bard's Tale, The (1985)(Electronic Arts)(US)(Disk 1 of 2)[!].d64", upload: true }
listing: listings/disk-01.txt
photos: [photos/disk-01-front.jpg, photos/disk-01-back.jpg]
```

### `pipelines.yaml`

Voir `ARCHITECTURE.md` §6.2 ; ajouter `schema_version` en tête. Validé par `schemas/pipelines.schema.json` et `remanence --check`.

> **JSON Schema.** Un fichier par artefact dans `remanence/schemas/` ; utilisés pour valider à l'écriture (logiciel) et pour la conformité (Claude Code).

---

## 6. Nommage TOSEC

Règles inchangées (voir `ARCHITECTURE.md` §5 et `CLAUDE.md` §8). Rappel des points durs : un nom par image de disque ; `Titre (date)(éditeur)` minimum ; article en fin (`Bard's Tale, The`) ; titre inconnu `ZZZ-UNK-` ; ASCII bas, tiret, pas de caractères interdits ; pays ISO alpha-2 majuscules, langue ISO minuscules ; `[!]` seulement sur lecture propre ; compilations nommées par la compilation, contenu détaillé dans `contents.yaml`.

---

## 7. Cycle de vie des blobs (flux/images)

- Stock unique `~/floppy-blobs/`, **hors dépôts**, **indexé par `sha256`** (un fichier d'index `blob-index.json` : `sha256 → chemin`).
- À la clôture d'un dump, `remanence` enregistre les blobs du `staging/` dans le stock et met à jour l'index. **La localisation physique n'a aucune importance** : tout se retrouve par hash.
- Claude Code ne touche jamais aux blobs ; il n'écrit que les `tosec_name` cibles.
- Le script d'upload résout chaque fichier par `sha256`, le renomme en `tosec_name`, publie.
- **Sauvegarde 3-2-1** du stock (≥3 copies, 2 supports, 1 hors site). Internet Archive = une copie, pas la sauvegarde.

---

## 8. `.gitignore` (spécification)

À placer dans `floppy-archive/` et adapter pour `remanence/` :

```
# Blobs (jamais dans Git)
floppy-blobs/
blob-index.json
*.scp
*.a2r
*.raw
*.img
*.d64
*.g64
*.adf
*.hfe
*.dsk
*.woz
*.nib

# Staging : ignorer les blobs, garder les métadonnées
staging/**/*.scp
staging/**/*.img
# (photos, listing.txt, label.txt, manifest.yaml restent versionnés)

# Python / outils
.venv/
__pycache__/
*.pyc
build/
dist/
*.egg-info/

# Secrets / config locale
.env
*.local.yaml
```

> Les **photos** sont versionnées : ne pas les ignorer. Vérifier qu'aucune règle large ne les capture.

---

## 9. Secrets

- Clés Internet Archive (IA-S3) configurées via `ia configure` dans la config utilisateur (hors dépôt) ; lues par le script d'upload depuis l'environnement / la config `ia`. **Jamais** dans le dépôt.
- Aucun secret n'est requis côté `remanence` (le dump n'a pas besoin du réseau).

---

## 10. Licences (décidées, droit français)

> Information générale, pas un avis juridique. En cas de doute, consulter un juriste.

- **Code (`remanence`)** : **CeCILL-2.1**. Licence libre de **droit français**, approuvée OSI/FSF, **compatible GPL-2.0+/AGPL-3.0+/EUPL**, copyleft fort. Fichier `LICENSE` à la racine du dépôt logiciel + en-tête dans les sources.
- **Données et métadonnées originales (`floppy-archive`)** : **Licence Ouverte 2.0 (Etalab)**, de **droit français**, compatible **CC-BY** et **ODC-BY** (réutilisation libre avec mention de la source). Couvre **vos contributions originales** : métadonnées du catalogue, descriptions, transcriptions d'étiquettes, photos prises par vous, listings générés, et la base de données (catalogue) elle-même.
- **Œuvres tierces archivées** (flux/images de logiciels sous droits) : **non relicenciées**. Elles restent sous leur droit d'auteur d'origine et sont régies **item par item** via `rights` et `copyright_status` ; publication uniquement quand c'est licite (cf. garde-fou `commercial`). La Licence Ouverte **ne s'applique pas** à ces contenus.
- Pratique : un fichier `LICENSE` par dépôt, et un `rights` explicite par item indiquant la licence des métadonnées et le statut de l'œuvre.

---

## 11. Tests et qualité

- **pytest** ; le `core/` est testable sans GUI ni matériel.
- **Pipelines fixture** (commandes simulées produisant des fichiers factices) pour dérouler toute la chaîne hors matériel.
- **Validation de schéma** systématique à l'écriture des YAML ; `remanence --check` audite `pipelines.yaml` et l'outillage.
- CI possible (lint + tests) ultérieurement.

---

## 12. Décisions encore ouvertes

1. Conservation des originaux photo : recommandation = dans le stock blobs (hors Git) **par défaut**, à confirmer.
2. Profondeur de la visualisation flux en v1 (cf. `SOFTWARE-SPEC.md` §F11).
