# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Les versions publiées suivent le SemVer du fichier `version.py` / tags GitHub.

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
