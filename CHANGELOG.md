# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Les versions publiées suivent le SemVer du fichier `version.py` / tags GitHub.

## [Non publié]

### Ajouté

- **Vérifier / Réparer** (une nuit) : diagnostic local ↔ serveur (Data_k, fichiers
  de participation, `traitement.etat`, xlsx), alignement des flags, téléchargement
  du tableur et relance Tadarida **avec confirmations**. Bouton en vue session
  (mis en avant si pastille ⏳).
- **Export portable de sessions** : wizard Registre → Exporter → Sessions (USB).
  Choix contrats / nuits, options Data / Data_k, métadonnées toujours incluses,
  estimation de volume, paquet `ChiroTool_export_…` avec README + manifeste.
- Modules `repair.py` et `export_sessions.py` (API pure, testables, sans GUI).

### Corrigé

- **Point actif (carte → wizard meta)** : créer *ou* réutiliser un point
  (y compris d’un autre observateur) le mémorise (`active_point.json` + sites
  externes). L’assistant de métadonnées préremplit carré/point et propose le
  choix en tête des « Points récents » (badge ★ / « autre obs. »). Corrige le
  parcours bloquant signalé quand le renommage restait vide après reuse carte.
- Branche upload « tous les WAV déjà sur le serveur » : plus de pose silencieuse
  du flag `uploaded` ; le résultat de `trigger_compute` est toujours journalisé
  via `record_action` ; en cas d’échec, le flag n’est pas posé (reprise /
  réparation possibles).

### Documentation

- README : fonctionnalités repair + export portable.
- Tutoriel : pastille ⏳, procédure Vérifier / Réparer, export USB / partage.

## [0.5.0] — 2026-07-19

Voir la [release GitHub](https://github.com/kevin-guille/ChiroTool/releases) et
le message de tag `v0.5.0` (token sécurisé, nettoyage renforcé, envoi des
identifications, synthèse / activité, etc.).
