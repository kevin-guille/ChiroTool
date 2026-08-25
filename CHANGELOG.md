# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Les versions publiées suivent le SemVer du fichier `version.py` / tags GitHub.

## [Unreleased]

### Ajouté

- **Valider** : tri au clic sur les en-têtes (asc / desc / ordre d'origine) ;
  filtre « Taxon observateur renseigné uniquement » (issue #4).
- **Vue session** : bilan `X / Y` contacts avec taxon observateur (xlsx en
  arrière-plan, cache) et nombre d'identifications déjà envoyées si sidecar.

### Corrigé

- **Valider** : le 2e clic sur un en-tête conserve le tri (callback heading
  reposé après mise à jour du libellé ▲ / ▼).

### Documentation

- Tutoriel : tri / filtre Valider, bilan `X / Y` en Vue session, comportement
  réel de « identifications validées seulement » sur un `_Vu` ChiroSurf,
  découpage TE×10 en tranches de 5 s (tout le son conservé), FAQ **EXFAT**.

### Tests

- TE×10 : un WAV de 15 s raw produit **3** segments (pas de troncature).
- Cohérence synthèse / compteur observateur sur le `_Vu` Nuit_1 issue #3.

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

### Suite possible (post-0.6)

- Robustesse / UX **mode batch** (données complémentaires participation,
  template avant lot, journal d'upload).
- Export multi-nuits compilé (espèces × nuits).
- Modes export formalisés Léger / Travail / Complet.
- Captures d'écran tutoriel (pick carte, ChiroSurf nuits, diagnostic).

## [0.5.0] — 2026-07-19

Voir la [release GitHub](https://github.com/kevin-guille/ChiroTool/releases) et
le message de tag `v0.5.0` (token sécurisé, nettoyage renforcé, envoi des
identifications, synthèse / activité, etc.).
