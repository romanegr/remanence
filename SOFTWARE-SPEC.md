# SOFTWARE-SPEC — Logiciel `remanence` (outil de dump & bibliothèque, GUI)

> Version 0.3. Spécifie le logiciel **`remanence`** : acquisition (dump) et consultation
> (bibliothèque), interface graphique Qt. Vit dans le dépôt `remanence` (code, licence
> **CeCILL-2.1**), avec son propre `CLAUDE.md` de développement. Les schémas, vocabulaires
> et règles de nommage font référence à **`CONVENTIONS.md`** (source de vérité unique) ;
> ce document ne les redéfinit pas. Distinct de `ARCHITECTURE.md` (pipeline global).

---

## 1. Contexte et objectif

L'outil prend en charge l'**acquisition d'un disque** et la production de son livrable dans `staging/<run>/`, exploitable tel quel par la suite du pipeline. Il remplace/enrichit l'exécutable `dump` du pipeline par une interface graphique, tout en partageant le **même cœur logique** (registre de pipelines, manifeste, empreintes).

Ce que l'outil produit pour un disque :
- le(s) fichier(s) **flux**, et l'**image décodée** si le décodage réussit ;
- les **photos** retouchées et typées ;
- les **métadonnées** physiques et d'étiquette ;
- le **manifeste** (`manifest.yaml`) avec empreintes et contexte d'acquisition.

Ce que l'outil **ne fait pas** (hors périmètre) : groupement en unités de publication, nommage TOSEC, rédaction de descriptions, upload Internet Archive. Ces étapes relèvent de Claude Code et du script d'upload.

---

## 2. Pile technique

- **Langage** : Python (≥ 3.11), **intégralité des scripts en Python**.
- **GUI** : **PySide6** (Qt 6 officiel, licence LGPL — préféré à PyQt6 pour la souplesse de licence).
- **Traitement d'image** : **OpenCV** (`opencv-python`) pour la correction de perspective (trapèze) et les transformations ; **Pillow** pour le chargement/export et les ajustements simples ; **NumPy**.
- **Flux / lecteurs** : outils hôte **Greaseweazle** — **installables par pipx/pip** (`pipx install git+https://github.com/keirf/greaseweazle@latest`), donc intégrés au venv ; la commande `gw` est invoquée en sous-processus. Autres méthodes via le registre de pipelines.
- **Commodore (images & listing)** : module Python **`d64`** (PyPI) pour lire `.d64/.d71/.d80/.d81/.d82` et générer le listing nativement (détokenisation BASIC incluse). Repli CLI : **VICE** (`c1541`, `petcat`).
- **Commodore (acquisition xum1541)** : **OpenCBM** (`cbmctrl`, `d64copy`) pilote le lecteur 1541 réel via l'adaptateur xum1541 et produit le `.d64` (pipeline « image », distinct du flux Greaseweazle).
- **Métadonnées** : **ruamel.yaml** (round-trip, préserve commentaires) pour lire/écrire les YAML.
- **Empreintes** : `hashlib` (sha256).
- **Empaquetage** : **venv** dédié + `requirements.txt` (ou `pyproject.toml` + `pip-tools`). Option **PyInstaller** pour un exécutable autonome.

### Outils système externes (hors pip, à documenter comme prérequis)

Vérifiés au démarrage (préflight), selon les pipelines utilisés : **OpenCBM** + pilote xum1541 (acquisition Commodore), **VICE** (`c1541`/`petcat`, repli listing C64), **mtools** (`mdir`) pour IBM, **AppleCommander** pour Apple II, **ADTPro** pour le dump natif Apple II. (Greaseweazle, lui, est dans le venv.)

### Définition du venv (principe)

`requirements.txt` figé et versionné : `PySide6`, `opencv-python`, `Pillow`, `numpy`, `ruamel.yaml`, `d64`, et `greaseweazle` (via URL Git). Un script `setup_env.py`/`make venv` crée l'environnement, installe les dépendances, puis lance un **préflight** des outils système restants et affiche un rapport (présent / manquant / version).

---

## 3. Architecture logicielle

Séparation stricte **cœur / interface** pour permettre une utilisation GUI **et** CLI (réutilise l'exécutable `dump` du pipeline) :

```
remanence/
├── core/
│   ├── pipelines.py        # chargement + validation de pipelines.yaml
│   ├── runner.py           # exécution des steps, capture de log, substitution de variables
│   ├── flux.py             # gestion des captures flux, variantes, décodage, qualité
│   ├── fluxview.py         # parsing SCP + rendu (histogramme, carte de piste) pour la visualisation
│   ├── images.py           # retouche, correction trapèze, normalisation/export
│   ├── listing.py          # extraction de listing (d64 module, repli c1541/mdir/AppleCommander)
│   ├── catalog.py          # lecture du catalogue Git + stock blobs (mode bibliothèque)
│   ├── manifest.py         # construction/écriture du manifeste, hachage
│   └── staging.py          # création des runs, noms temporaires, écritures atomiques
├── gui/                    # PySide6 — mode Dump + mode Bibliothèque ; n'appelle que core/
├── cli/                    # entrée `dump` en ligne de commande
├── pipelines.yaml
└── requirements.txt
```

Règle : la **GUI ne contient aucune logique métier**, elle orchestre `core/`. Tout ce que fait la GUI doit être faisable en CLU pour les tests et le mode sans matériel.

---

## 4. Exigences fonctionnelles

### F1 — Sélection format et pipeline
- Lister les **formats** déclarés dans `pipelines.yaml`, puis les **pipelines** compatibles.
- Afficher la fiche du pipeline (matériel, logiciel, `produces`, `preservation_level`).
- **Préflight** : vérifier les outils `requires` ; bloquer/avertir si absent.
- Sélection du **périphérique** (port Greaseweazle…) et des paramètres exposés (révolutions, pistes).

### F2 — Acquisition (dump)
- Exécuter les `steps` du pipeline avec **journal en direct**, barre de progression, bouton **annuler**.
- Détecter le succès/échec de chaque step ; ne jamais écraser un fichier existant (écritures atomiques, noms temporaires).
- Enregistrer le `read_quality` observé et un **journal de lecture** (carte d'erreurs si l'outil le fournit).

### F3 — Disquette défectueuse et gestion du flux (exigence clé)
- **Flux non décodable** : si le décodage échoue (format exotique, protection, support abîmé), permettre de **sauvegarder le flux seul**, sans image, et marquer `decode_status: failed`, `needs_redecode: true`, `preservation_level: silver` (flux sans décodage vérifié) — ou `bronze` si même la capture flux est partielle.
- **Décodage différé** : un flux sauvegardé non décodé doit pouvoir être re-décodé plus tard (le flux est conservé tel quel ; aucune perte).
- **Flux instable / plusieurs versions** : permettre **plusieurs lectures** du même disque (bouton « relire »). Chaque lecture est conservée comme **variante distincte** : fichier propre, `sha256`, horodatage, statistiques de lecture. L'utilisateur peut :
  - garder **toutes** les variantes (recommandé pour un disque marginal, en vue d'un décodage par comparaison/vote ultérieur),
  - marquer une variante **« meilleure »** (`best: true`),
  - en supprimer.
- Le manifeste représente donc, pour un disque, **0..N flux** et **0..1 image** (voir §6).
- Indicateur visuel clair de l'état du disque : décodé / flux-seul / instable.

### F4 — Photos : import, typage, retouche
- **Import multiple** (glisser-déposer ou sélection). Formats d'entrée courants (JPEG, PNG, HEIC si dispo).
- **Typage par photo** (valeurs anglaises, cf. CONVENTIONS §3) : `front`, `back`, `label`, `sleeve`, `manual`, `other` ; rattachement à un disque (`disk-NN`) ; note libre ; ordre d'affichage.
- **Retouche non destructive** (l'original peut être conservé hors Git ; les opérations sont enregistrées et ré-appliquables) :
  - **Luminosité**, **contraste** (curseurs, aperçu temps réel).
  - **Rotation** (90° et fine), **recadrage**.
  - **Correction trapèze (keystone)** : voir §5.
- **Export normalisé** vers le staging selon la politique photos du pipeline : JPEG qualité ~80 %, bord long ≤ 2000 px, métadonnées EXIF nettoyées, nommage `disk-NN-<type>.jpg`.

### F5 — Métadonnées du disque
- Saisie : transcription de l'**étiquette** (`label_text`), **état physique** (média, faces, protégé en écriture, condition : moisissure, oxydation, lisibilité), **opérateur**, date.
- Champs pré-remplis depuis le pipeline (matériel, méthode, révolutions) — **non ressaisis**.

### F6 — Génération du livrable (staging)
- Créer `staging/<run>/`, y placer flux/variantes et image (noms temporaires), photos normalisées, listing (si produit par le pipeline), et écrire `manifest.yaml`.
- Calculer et inscrire le `sha256` de **chaque** fichier produit.
- Vérifier la cohérence avant clôture (au moins un flux ou une image ; au moins une photo recommandée ; champs obligatoires présents).

### F7 — Mode sans matériel (dry-run / fixtures)
- Pipelines « fixture » produisant des fichiers factices (commandes simulées) pour tester **toute la chaîne** sans lecteur ni disque. Indispensable au développement et à la recette.

### F8 — Validation et audit
- Équivalent `dump --check` : valider le schéma de `pipelines.yaml`, vérifier les outils de tous les pipelines, rapport lisible.

### F9 — Reprise de session
- Rouvrir un `run` existant pour **ajouter/retoucher des photos** ou compléter des métadonnées sans relancer le dump.
- Reprendre proprement un dump interrompu (pas de fichier à moitié écrit).

### F10 — Bibliothèque / consultation des disquettes archivées
Un **second mode** de l'application (lecture seule), partageant le cœur.
- **Parcourir** le catalogue : lit `catalog/` (métadonnées Git : `item.yaml`, `disks/*.yaml`, `contents.yaml`, photos, listings) et résout les blobs (flux/images) du stock local **par `sha256`**.
- **Filtrer / rechercher** par plateforme, titre, éditeur, format, niveau de préservation, statut.
- **Fiche disque/UP** : afficher photos, étiquette, inventaire de contenu, état d'acquisition.
- **Visualiser les listings** (texte, rendu PETSCII pour le Commodore quand pertinent). Régénérer un listing à la demande depuis l'image via `core/listing.py` (module `d64` / repli c1541, mdir, AppleCommander).
- **Lien d'intégrité** : vérifier que les `sha256` des blobs correspondent toujours aux métadonnées (détection de corruption silencieuse).
- Mode strictement **non destructif** : aucune écriture dans `catalog/` ni dans les blobs.

### F11 — Visualisation du flux
Visualisation parsant les fichiers **SCP** (format documenté) et le journal de lecture du pipeline.
- **Histogramme des intervalles de flux** : distribution des temps entre transitions (révèle l'encodage FM/MFM/GCR, les zones faibles).
- **Carte de piste / surface** : vue 2D piste × position angulaire, densité de transitions ou qualité de lecture, pour repérer pistes/secteurs problématiques.
- **Comparaison de variantes** : superposer/diff plusieurs lectures d'un disque instable (cf. F3) pour visualiser où elles divergent — aide au choix de la « meilleure » ou à un futur décodage par comparaison.
- **Approche par paliers** : v1 = histogramme + carte de densité/erreurs depuis le SCP et le log ; analyses fines (décodage de cellules, recouvrement de secteurs) ultérieures. Pour l'analyse experte, renvoyer vers des outils spécialisés (HxC Floppy Emulator, Aufit) plutôt que tout réimplémenter.

---

## 5. Correction trapèze (perspective) — détail

Objectif : redresser une photo de disque prise de biais en une vue rectifiée.

- L'utilisateur place **4 points** sur les coins de la disquette (ou du cadre de référence) ; points déplaçables avec zoom/aimantation.
- Calcul d'une **homographie** (OpenCV `getPerspectiveTransform`) vers un rectangle cible respectant le **ratio réel** du support (sélectionnable : 3.5″, 5.25″, 8″), puis `warpPerspective`.
- **Aperçu temps réel** ; possibilité d'annuler/rejouer.
- **Non destructif** : on enregistre les 4 points et le ratio cible ; l'image rectifiée est (re)générée à l'export. L'original reste disponible si conservé.
- Enchaînement type : trapèze → recadrage → luminosité/contraste → export normalisé.

---

## 6. Modèle de données produit (manifeste étendu)

Étend le manifeste pour couvrir multi-flux et disque défectueux. Le **schéma de référence unifié** (avec `schema_version`) est défini dans **`CONVENTIONS.md` §5** ; l'exemple ci-dessous l'illustre.

```yaml
run_id: 2026-06-11_run01
pipeline_id: gw-c64-1541
captured_by: "operateur"
date_captured: 2026-06-11T14:32:00+02:00
platform_hint: commodore-c64
acquisition:
  method: greaseweazle
  hardware: "Greaseweazle V4 + lecteur 5.25\""
  software: "gw 1.21"
  revolutions: 5
  preservation_level: silver        # gold|silver|bronze (voir F3)
decode_status: failed               # ok | failed | not_attempted
needs_redecode: true
flux_stable: false
physical:
  media: "5.25\" DD"
  sides: 1
  write_protected: false
  condition: "lecture difficile, support oxydé"
label_text_file: label.txt
listing_file: null                  # pas de listing si non décodé
files:
  - { temp_name: flux_read01.scp, role: flux, format: scp, variant: 1, best: false,
      sha256: "a1...", read_quality: "12 secteurs faibles", upload: true, tosec_name: null }
  - { temp_name: flux_read02.scp, role: flux, format: scp, variant: 2, best: true,
      sha256: "b2...", read_quality: "9 secteurs faibles",  upload: true, tosec_name: null }
  - { temp_name: flux_read03.scp, role: flux, format: scp, variant: 3, best: false,
      sha256: "c3...", read_quality: "15 secteurs faibles", upload: true, tosec_name: null }
  # aucune entrée 'image' : disque non décodable pour l'instant
photos:
  - { file: photos/front.jpg, type: front, edits: {keystone: true, ratio: "5.25"} }
  - { file: photos/back.jpg,  type: back,  edits: {brightness: 8, contrast: 5} }
  - { file: photos/sleeve.jpg, type: sleeve }
```

Cas nominal (disque sain) : `decode_status: ok`, `preservation_level: gold`, un flux + une image, `listing_file` renseigné.

---

## 7. Exigences non fonctionnelles

- **Plateformes** : Linux (cible principale) ; Windows souhaitable. Pas de dépendance réseau pour le dump.
- **Sécurité** : aucune clé Internet Archive dans cet outil (hors périmètre) ; ne jamais écrire hors de `staging/` et du stock blobs configuré.
- **Robustesse** : écritures atomiques, jamais d'écrasement silencieux, opérations longues annulables, journalisation persistante.
- **Performance** : fichiers flux volumineux et opérations image fluides (retouche en aperçu réactif, traitement lourd hors thread UI).
- **Ergonomie** : flux guidé (assistant en étapes), état du disque toujours visible, internationalisation FR (extensible).
- **Testabilité** : cœur testable sans GUI ni matériel (cf. F7).

---

## 8. Parcours utilisateur (écrans)

L'application a **deux modes** : **Dump** (acquisition) et **Bibliothèque** (consultation, F10/F11).

**Mode Dump** — assistant en étapes, navigation libre une fois un dump lancé :

1. **Format & pipeline** — sélection, préflight, périphérique, paramètres.
2. **Acquisition** — lancement, journal en direct, gestion des relectures (variantes flux), décodage et son résultat ; option « sauvegarder flux seul ».
3. **Photos** — import, typage, retouche (luminosité/contraste/rotation/recadrage/trapèze), aperçu.
4. **Métadonnées** — étiquette, état physique, opérateur.
5. **Récapitulatif & clôture** — vérifications, écriture du staging + manifeste, rapport.

**Mode Bibliothèque** — navigation/recherche dans le catalogue, fiche d'une UP, affichage des listings, visualisation du flux et comparaison des variantes, vérification d'intégrité. Lecture seule.

---

## 9. Cas limites et gestion d'erreurs

- Échec de décodage → proposer explicitement « conserver le flux seul » plutôt que d'échouer.
- Lecteur absent/déconnecté → message clair au préflight, pas de plantage.
- Disque illisible même en flux → autoriser une clôture en `bronze` documentant l'échec (utile pour tracer l'existence du support).
- Photos sans correction → export direct normalisé.
- Interruption (coupure, annulation) → run laissé dans un état cohérent, reprenable.

---

## 10. Hors périmètre

Groupement en unités de publication, inventaire de contenu, nommage TOSEC, génération des `item.yaml`/`contents.yaml`/`description.md`, upload Internet Archive, gestion des clés S3. (Pipeline + Claude Code + script d'upload.)

---

## 11. Critères d'acceptation

- Un dump nominal produit un `staging/<run>/` complet et cohérent (flux + image + photos typées + manifeste + empreintes), exploitable sans retouche manuelle par la suite du pipeline.
- Un disque non décodable produit un run **flux-seul** valide, marqué pour re-décodage.
- Un disque instable conserve **plusieurs variantes de flux** distinctes, hachées et qualifiées, dont une « meilleure » optionnelle.
- La correction trapèze redresse correctement une photo prise de biais, de façon non destructive.
- Le **mode sans matériel** permet de dérouler toute la chaîne via des pipelines fixture.
- `dump --check` valide la configuration et l'outillage.
- Le **mode Bibliothèque** parcourt le catalogue, affiche les listings et signale toute incohérence d'empreinte.
- La **visualisation flux** affiche au moins l'histogramme des intervalles et une carte de piste à partir d'un SCP réel.

---

## 12. Points à discuter / décisions ouvertes

**Tranché** : PySide6 (licence), **Linux seul** en v1, **bibliothèque intégrée** à l'application (cœur partagé). Voir aussi CONVENTIONS §1.

Restant :
1. **Conservation des originaux photo** : hors Git (stock blobs) par défaut (recommandé), à confirmer.
2. **Décodage par comparaison** des variantes flux (vote/merge) : intégré à l'outil, ou étape ultérieure ?
3. **HEIC en entrée** (photos iPhone) : dépendance supplémentaire (`pillow-heif`) — utile ?
4. **Détection auto des 4 coins** du disque (assistance avant ajustement manuel) : v1 ou ultérieur ?
5. **Multi-disque dans une même session** (enchaîner plusieurs disques d'un lot) : v1 ou ultérieur ?
6. **Profondeur de la visualisation flux** en v1 : histogramme + carte de densité, ou comparaison de variantes d'emblée ?
7. **Listing à la régénération** : stocker, ou recalculer à la volée à chaque consultation ?
