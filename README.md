<div align="center">

<img src="docs/captures/icon_256.png" width="96" alt="ChiroTool">

# ChiroTool

**Le traitement de vos nuits chiroptères, automatisé de A à Z.**

Outil libre pour le protocole **Vigie-Chiro Point Fixe** (MNHN).

[![License: MIT](https://img.shields.io/badge/License-MIT-1f6feb.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab.svg)](https://www.python.org/)
[![Plateforme](https://img.shields.io/badge/Windows-portable-0d419d.svg)](#installation)

</div>

---

**ChiroTool** automatise de A à Z le traitement des nuits d'enregistrement ultrason
de chauves-souris dans le cadre du protocole **Vigie-Chiro Point Fixe** du Muséum
national d'Histoire naturelle (MNHN).

Là où le workflow manuel enchaîne plusieurs logiciels et de longues manipulations
répétitives (renommage des fichiers, expansion temporelle, création de participation,
upload, attente de l'analyse Tadarida, nettoyage dans un tableur), ChiroTool réunit
toute la chaîne dans une **seule application locale et portable**.

> ⚠️ **Outil indépendant** : ChiroTool utilise l'API publique Vigie-Chiro mais n'est
> pas un outil officiel du MNHN. Il s'adresse aux bureaux d'études et associations
> naturalistes qui participent au programme.

## ✨ Fonctionnalités

- 🏷️ **Renommage automatique** au format Vigie-Chiro
- ⏱️ **Expansion temporelle (TE×10)** intégrée, validée *bit-à-bit* (remplace Kaleidoscope)
- ☁️ **Création de participation + upload** via l'API Vigie-Chiro (parallèle, reprise sur coupure)
- 🤖 **Suivi de l'analyse Tadarida** et récupération automatique des résultats
- 🧹 **Nettoyage par seuils de confiance** (par groupe : chiros, orthos, micromam, oiseaux)
- 📋 **Registre de suivi de campagne** multi-sites (SQLite, export CSV/xlsx)
- 📊 **Graphes d'activité**, **carte des points** (OSM), ouverture des sons dans **ChiroSurf**
- ⚡ **Accélération Rust optionnelle** pour le TE×10 (fallback Python transparent)

![Interface ChiroTool](docs/captures/05-fenetre-principale.png)

## 📖 Tutoriel

Un **tutoriel illustré complet** (PDF, 15 pages) est disponible :
👉 [`docs/ChiroTool-Tutoriel.pdf`](docs/ChiroTool-Tutoriel.pdf)

## Installation

Python **3.11+** recommandé.

```bash
python -m pip install -r requirements.txt
python gui_app.py
```

Au premier lancement : **Parcourir…** pour choisir le dossier de travail, puis
collez votre token Vigie-Chiro dans **⚙ Préférences → API Vigie-Chiro**.

### Accélération Rust (optionnelle)

Pour les gros volumes, compilez l'extension `chirotool_fast` (gain ~×2 sur NVMe).
Sans elle, `te10.py` utilise sa version Python pure (aucune action requise).
Voir [`rust_ext/README.md`](rust_ext/README.md).

## Utilisation en ligne de commande

ChiroTool fonctionne aussi entièrement en CLI (le moteur est indépendant de l'UI) :

```bash
python scan.py [<racine>]                          # scan + état des sessions
python vigiechiro_api.py save-token <TOKEN>        # token (1 fois par poste)
python rename.py <session> --auto                  # renommage
python te10.py <session-ou-Data>                   # expansion temporelle
python cleanup.py <session> --threshold-chiros 0.5 # nettoyage par seuils
python pipeline.py <session> --advance --use-api   # pipeline complet (cloud)
python registry.py scan <racine>                   # (re)peuple le registre
```

## Architecture

Moteur Python sans dépendance à l'UI (testable seul) + couche GUI CustomTkinter.

| Couche | Modules |
|---|---|
| **Logique pure** | `chiro_core`, `naming`, `taxons`, `manifest`, `campaign_log`, `verify`, `vigiechiro_enums` |
| **Accès données** | `suivi`, `suivi_write`, `registry`, `vigiechiro_api`, `credentials` |
| **Opérations CLI** | `scan`, `rename`, `te10`, `cleanup`, `pipeline` |
| **GUI** | `gui_app`, `gui_map`, `gui_validation`, `gui_registry`, `gui_*_wizard`, … |

## Contribuer

Les retours, idées et contributions sont les bienvenus — voir
[`CONTRIBUTING.md`](CONTRIBUTING.md). Pour signaler un bug ou proposer une
fonctionnalité, ouvrez une [issue](https://github.com/kevin-guille/ChiroTool/issues).

## Licence

Distribué sous licence **MIT** — voir [`LICENSE`](LICENSE).
Usage, modification et redistribution libres.

## Crédits

- **Auteur** : Kevin Guille — Chargé d'études naturalistes
  ([LinkedIn](https://fr.linkedin.com/in/kevin-guille-764b6a150))
- **Avec le soutien de** : [Acer Campestre](https://www.acer-campestre.fr/)
  ([LinkedIn](https://fr.linkedin.com/company/acer-campestre))
- **Protocole & API** : [Vigie-Chiro / MNHN](https://www.vigienature.fr/fr/chauves-souris)

<div align="center">

🦇 *Bon traitement, et bonnes chauves-souris !*

</div>
