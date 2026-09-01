# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Les versions publiées suivent le SemVer du fichier `version.py` / tags GitHub.

## [Unreleased]

## [0.7.2] — 2026-09-01

Release courante. Correctifs terrain après 0.7.0 / pre-release 0.7.1
([#7](https://github.com/kevin-guille/ChiroTool/issues/7)).

### Corrigé

- **Vue session** : barre d'actions sur **une ligne**, glissement horizontal
  si le panneau est trop étroit (plus rien de coupé après 📍 Carte). Dans
  **ChiroSurf nuits**, les boutons ▶ / 📈 / Synthèse passent sous le libellé,
  alignés à gauche.
- **Synthèse / nuit biologique (D12)** : une pose qui passe **minuit**
  (soir + matin) est **une** nuit. Plus de sélecteur « Nuit 1 / Nuit 2 »
  fantôme (l'ancien fallback date calendaire sans heure scindait à minuit).
  Les vraies participations multi-nuits (2 soirs) restent scindées à midi.

### Tests

- Pose 21 h → 6 h = 1 slice ; suffixe / espace dans le nom ; Titley overnight ;
  ligne sans horodatage n'invente pas une Nuit 2.

### Documentation

- SPEC D12 (règle de nuit, anti-patterns) ; tutoriel §8/§9/FAQ ; README ;
  landing ; note [`docs/RELEASE_v0.7.2.md`](docs/RELEASE_v0.7.2.md).

## [0.7.1] — 2026-08-31

Issue [#7](https://github.com/kevin-guille/ChiroTool/issues/7)
(Benjamin — liaison ChiroSurf).

### Corrigé

- **▶ ChiroSurf** (fenêtre nuits) : le CSV est copié à côté des WAV
  (`Data_k/` sinon `Data/`) avant lancement. ChiroSurf 4.x glob
  `*.{wav,mp3}` dans le dossier du tableur ; un CSV isolé dans
  `chirosurf/` faisait planter le script de démarrage (Tcl
  *no files matched glob pattern*). S'il n'y a aucun WAV, l'ouverture
  est refusée avec un message clair (nuit déjà nettoyée).
- **`_Vu` hors ChiroTool** : reconnaissance de `Nuit1_`, `Nuit_1_` et
  `Nuit_1-` ; un `_Vu` collé dans `chirosurf/` ou écrit par ChiroSurf
  dans `Data_k/` (à côté du CSV ouvert) est listé, rapatrié vers
  `chirosurf/`, et lu par Synthèse / Activité.

### Tests

- Naming Benjamin (`Nuit_1-observations_Vu.csv`) + préfixe avant
  `participation`.
- Staging CSV → `Data_k/` ; refus sans WAV ; harvest `_Vu`.

### Documentation

- Tutoriel §8 B + FAQ issue #7 ; landing / README / SPEC / CONTRIBUTING.
- Note de pre-release [`docs/RELEASE_v0.7.1.md`](docs/RELEASE_v0.7.1.md)
  (SHA-256 de l'exe).

## [0.7.0] — 2026-08-30

Retours issues [#4](https://github.com/kevin-guille/ChiroTool/issues/4),
[#5](https://github.com/kevin-guille/ChiroTool/issues/5),
[#6](https://github.com/kevin-guille/ChiroTool/issues/6).

### Ajouté

- **Valider** : tri au clic sur les en-têtes (asc / desc / ordre d'origine) ;
  filtre « Taxon observateur renseigné uniquement » ; filtre **Chiros
  seulement** (issue #4).
- **Vue session** : bilan `X / Y` contacts avec taxon observateur (xlsx en
  arrière-plan, cache) et nombre d'identifications déjà envoyées si sidecar.
- **Synthèse** : sélecteur de **nuit biologique** (indépendant de ChiroSurf) ;
  `_Vu` lu s'il existe ; cumul multi-nuits sans classes d'activité
  (contacts/nuit).
- **ChiroSurf nuits** : ouverture du CSV brut (▶ ChiroSurf) et du `_Vu`
  (📈 graphes) depuis la liste des nuits et depuis Valider (issue #4.8) —
  **optionnel**, distinct de la Synthèse.
- **Activité** : filtres **Chiros seulement** et **Taxons observateur** ;
  lecture des CSV `_Vu` (issue #4.9–10).
- **Titley Swift / Ranger** (issue #4) : noms usine `YYYY-MM-DD HH-MM-SS`
  (espace ou underscore, ± n° d'enregistreur) lus au renommage ; TE×10
  incrémente l'heure des tranches ; **Préparer s'arrête** si aucun nom
  n'est lisible.

### Corrigé

- **Valider** : le 2e clic sur un en-tête conserve le tri (callback heading
  reposé après mise à jour du libellé ▲ / ▼).
- **Vue session** : bouton **Nettoyer** à droite de **Valider** (issue #4.5) ;
  **📊 Synthèse** avant **🌊 ChiroSurf nuits** (complémentaires, pas un
  remplacement).
- **Upload / participation** : libellés Vent et Couverture nuageuse lisibles
  (titre + aide empilés, plus superposés).
- **Démarrage** (issue #5) : plus de scan auto du dernier dossier (EXFAT /
  SSD endormi figeait l'UI et grisait Parcourir). Préférences → Général :
  « Garder en mémoire le dernier dossier » (coché par défaut) ; décoché,
  le chemin n'est plus restauré. Parcourir reste cliquable pendant un scan.
- **Dates Summary vs une nuit** (Jeanne) : si le Summary ne correspond pas
  aux WAV (carte SD non formatée, pose cumulée), **avertissement** à la
  préparation et avant l'upload ; dates (et T° si recoupement) prises sur
  les fichiers ; une participation déjà créée au mauvais jour n'est plus
  réutilisée.

### Documentation

- Tutoriel + PDF : distinction Synthèse / ChiroSurf ; coupure **midi** (nuit
  biologique) ; Titley ; dates Summary ≠ WAV ; démarrage sans scan auto ;
  SM2 / `.wac` / `.w4v` (issue [#6](https://github.com/kevin-guille/ChiroTool/issues/6)).
- README + landing GitHub Pages : v0.7.

### Tests

- TE×10 : un WAV de 15 s raw produit **3** segments (pas de troncature).
- Cohérence synthèse / compteur observateur sur le `_Vu` Nuit_1 issue #3.
- Titley : parse noms, rename, TE×10 15 s sans collision, stop si illisible.
- Dates Jeanne : Summary multi-jours → WAV ; participation périmée non réutilisée.
- Nuit biologique : coupure midi ; sélecteur Synthèse (Nuit 1 / toutes).

## [0.6.0] — 2026-08-07

Issue [#3](https://github.com/kevin-guille/ChiroTool/issues/3) (retours terrain)
+ SPEC [`docs/SPEC_v06_parcours.md`](docs/SPEC_v06_parcours.md).

### Ajouté

- **Vérifier / Réparer** (une nuit) : diagnostic local ↔ serveur, alignement
  flags, fetch xlsx / relance Tadarida **avec confirmations**.
- **Export portable de sessions** (Registre → Sessions USB) : Data_k ± Data +
  métadonnées, estimation de volume, paquet horodaté.
- **PointSelection** + GPS dans le **manifest** (lat/lon, site_id, commune).
- **Mode pick carte** depuis l’assistant métadonnées (« 🗺️ Choisir sur la carte… ») :
  commune, points dans **5 km**, create/reuse → champs remplis.
- **FOCUS 📍 Carte** : recentrage sans full-API (manifest → active_point → cache),
  marqueurs du projet/dossier + highlight de la nuit.
- **ChiroSurf multi-nuits** (lazy) : bouton **🌊 ChiroSurf nuits** → dossier
  `chirosurf/Nuit{n}_…-observations.csv` (nuit biologique, coupure midi) ;
  ouverture dossier ; synthèse par nuit / `_Vu`.
- **Synthèse** : filtre **proba Tadarida minimale** ; source xlsx ou `_Vu`.
- Modules `point_selection.py`, `chirosurf_nights.py` (tests unitaires).

### Corrigé

- **Point actif** create **et** reuse (y compris autre observateur) mémorisé
  pour le wizard meta (parcours carte → préparer).
- Upload « tous WAV déjà sur serveur » : plus de flag `uploaded` silencieux ;
  journalisation `trigger_compute`.
- **📍 FOCUS carte** : ne plus être écrasé par le chargement API (vue France) ;
  pin rose unique `★ Zx` / `★ Zx · N nuits` ; **🔄 Recharger sites** sort du
  FOCUS et montre tous les sites ; fiche point avec bouton bas toujours visible.
- **Vérifier / Réparer** (retours beta) :
  - pagination `/fichiers` + **`max_results=99`** (plafond Eve) ;
  - fallback titres via `/participations/<id>/donnees` ;
  - token **401** : message clair, pas de re-upload massif fantôme ;
  - couverture = WAV **encore dans Data_k** ; purges nettoyage = info
    « sur serveur seul » (ex. 185 fichiers).
- **Météo participation non bloquante** (retours terrain) : vent / couverture
  et T° vides n'empêchent plus l'upload ; Summary continue de préremplir les
  T° ; pas de valeur inventée ; complétion possible plus tard sur le portail.

### Documentation

- Tutoriel v0.6 (meta/carte FOCUS, ChiroSurf nuits, repair/token, météo
  optionnelle, FAQ) + PDF régénéré.
- SPEC, samples issue #3, CONTRIBUTING, README, landing GitHub Pages.

### Suite possible (post-0.7)

- Robustesse / UX **mode batch** (données complémentaires participation,
  template avant lot, journal d'upload).
- Export multi-nuits compilé (espèces × nuits).
- Fusion `_Vu` → xlsx (choix produit : la méthode 10 %→75 % n'alimente pas
  l'envoi Vigie-Chiro aujourd'hui).
- Lancer plusieurs instances de ChiroTool en parallèle (issue #4.2).
- Modes export formalisés Léger / Travail / Complet.

## [0.5.0] — 2026-07-19

Voir la [release GitHub](https://github.com/kevin-guille/ChiroTool/releases) et
le message de tag `v0.5.0` (token sécurisé, nettoyage renforcé, envoi des
identifications, synthèse / activité, etc.).
