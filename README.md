<div align="center">

<img src="docs/captures/icon_256.png" width="104" alt="ChiroTool">

# ChiroTool

### Le traitement de vos nuits chiroptères, automatisé de A à Z

Outil libre pour le protocole **[Vigie-Chiro Point Fixe](https://www.vigienature.fr/fr/chauves-souris)** (MNHN)

[![Version](https://img.shields.io/github/v/release/kevin-guille/ChiroTool?include_prereleases&label=version&color=1f6feb)](https://github.com/kevin-guille/ChiroTool/releases)
[![Téléchargements](https://img.shields.io/github/downloads/kevin-guille/ChiroTool/total.svg?label=t%C3%A9l%C3%A9chargements&color=2ea043)](https://github.com/kevin-guille/ChiroTool/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/kevin-guille/ChiroTool/tests.yml?branch=main&label=tests&color=2ea043)](https://github.com/kevin-guille/ChiroTool/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-1f6feb.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab.svg)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-portable-0d419d.svg)](#installation)

**[⬇ Télécharger l’exe](https://github.com/kevin-guille/ChiroTool/releases)** ·
**[📖 Tutoriel PDF](docs/ChiroTool-Tutoriel.pdf)** ·
**[💬 Ouvrir une issue](https://github.com/kevin-guille/ChiroTool/issues)**

</div>

---

## Pourquoi ChiroTool ?

Sur une nuit Point Fixe, le parcours manuel est long et fragile :

> renommer → expansion TE×10 → créer la participation → uploader des centaines de WAV → attendre Tadarida → récupérer le xlsx → nettoyer dans un tableur → archiver.

**ChiroTool regroupe toute la chaîne dans une seule application locale et portable**, pensée pour le terrain et le bureau d’études :

| Avant | Avec ChiroTool |
|-------|----------------|
| 5–6 logiciels / étapes | **1 application** de bout en bout |
| Kaleidoscope pour le TE×10 | **TE×10 intégré** (Python, accélération Rust optionnelle) |
| Upload manuel, fragile | **Upload parallèle + reprise** sur coupure |
| Nettoyage « à la main » risqué | **Aperçu chiffré + garde-fous** avant toute suppression |
| Suivi campagne dispersé | **Registre multi-sites**, graphes, carte, validation |

Idéal pour les **bureaux d’études**, **associations** et **observateurs** qui livrent des campagnes Vigie-Chiro fiables, traçables et plus rapides.

> ⚠️ **Outil indépendant** — ChiroTool utilise l’API publique Vigie-Chiro mais **n’est pas un outil officiel du MNHN**. Vos données restent sur votre poste ; le token ne quitte pas votre machine hors appels API légitimes.

---

## Nouveautés v0.7

La **v0.7** reprend les retours [#4](https://github.com/kevin-guille/ChiroTool/issues/4)
(Titley, Valider), [#5](https://github.com/kevin-guille/ChiroTool/issues/5)
(démarrage) et [#6](https://github.com/kevin-guille/ChiroTool/issues/6) (WAC),
et **sépare** Synthèse et ChiroSurf :

| | Nouveauté | Bénéfice terrain |
|---|-----------|------------------|
| 📊 | **Synthèse** avec choix de **nuit** (xlsx, `_Vu` si présent) | Récap + activité **sans** ChiroSurf |
| 🌊 | **ChiroSurf nuits** optionnel (▶ brut / 📈 `_Vu`) | Méthode 10 %→75 % pour ceux qui l’utilisent |
| 🏷️ | **Titley** Anabat Swift / Ranger | Noms usine lus ; plus besoin de XnView |
| 🔍 | **Valider** : tri, filtres, bilan `X / Y` | Lecture plus rapide d’une nuit |
| 📂 | Plus de **scan auto** au démarrage | SSD EXFAT endormi ne fige plus l’UI |
| 📅 | **Dates** : WAV font foi si Summary cumulé | Carte SD non formatée : plus de mauvaise nuit |

**📊 Synthèse** et **🌊 ChiroSurf nuits** sont complémentaires : tout le monde
utilise la Synthèse ; ChiroSurf n’est utile que pour la méthode 10 %→75 %.

### v0.6 (rappel)

Vérifier / Réparer, export USB, pick + FOCUS carte, ChiroSurf multi-nuits
(CSV), synthèse `_Vu` / proba min, météo non bloquante — voir le
[changelog](CHANGELOG.md).

👉 Détail : [Changelog](CHANGELOG.md) · [Tutoriel](docs/TUTORIEL.md) · [SPEC](docs/SPEC_v06_parcours.md) · [Releases](https://github.com/kevin-guille/ChiroTool/releases)

---

## Aperçu

<p align="center">
  <img src="docs/captures/05-fenetre-principale.png" width="820" alt="Fenêtre principale ChiroTool">
</p>

<p align="center">
  <img src="docs/captures/06-vue-session.png" width="400" alt="Vue session">
  &nbsp;
  <img src="docs/captures/11-recap-nettoyage.png" width="400" alt="Récapitulatif de nettoyage">
</p>

<p align="center">
  <img src="docs/captures/13-registre.png" width="400" alt="Registre de campagne">
  &nbsp;
  <img src="docs/captures/exemple-graphe-activite.png" width="400" alt="Graphe d'activité">
</p>

---

## Fonctionnalités

### Chaîne de traitement

- **Renommage automatique** au format Vigie-Chiro (Wildlife, AudioMoth expandé, Titley Swift/Ranger, auto-réparation de noms proches)
- **Expansion temporelle TE×10** intégrée, validée *bit-à-bit* (remplace Kaleidoscope) : tout le son est conservé (tranches de 5 s)
- **Participation + upload** via l’API (workers parallèles, reprise, trigger compute ; dates WAV si le Summary couvre plusieurs jours)
- **Suivi Tadarida** et récupération des observations
- **Vérifier / Réparer** une nuit (diagnostic API + disque, alignement d’état, fetch / trigger avec confirmation)
- **Nettoyage par seuils** (chiros / orthos / micromammifères / oiseaux) avec aperçu et garde-fous

### Après l’analyse

- **Validation des contacts** (raccourcis, tri des colonnes, filtres observateur / chiros, ouverture WAV, envoi des identifications)
- **Vue session** : bilan `X / Y` ; **Valider** · **Nettoyer** · **Synthèse**
- **Synthèse** par espèce + niveaux d’activité (sélecteur de nuit, `_Vu` optionnel)
- **ChiroSurf nuits** (optionnel) : scission lazy `chirosurf/Nuit{n}_…csv` ; ▶ brut / 📈 `_Vu`
- **Graphes d’activité** (chiros seulement, taxons observateur, `_Vu`)
- **Registre de campagne** multi-sites (SQLite, export CSV / xlsx)
- **Export portable de sessions** (clé USB / partage : Data_k ± Data + métadonnées + `chirosurf/` si présent)
- **Carte OSM** : pick depuis les meta (5 km), FOCUS session, carrés STOC, create/reuse (y compris autre observateur)

### Robustesse

- Application **locale et portable** (exe one-file ou Python)
- **Accélération Rust optionnelle** pour le TE×10 (fallback Python transparent)
- Mode **compatible antivirus** pour les postes verrouillés
- Pas de **scan automatique** du dernier dossier au démarrage (SSD EXFAT / volume endormi) ; option pour mémoriser seulement le chemin
- Manifest de session + vérifications pour un traitement **idempotent**

---

## Enregistreurs compatibles

Tout enregistreur dont les fichiers sont **horodatés** dans le nom :

| Famille | Modèles / notes |
|---------|-----------------|
| **Wildlife Acoustics** | SM2 / SM3 / SM4(BAT) / Mini Bat (`SERIE_YYYYMMDD_HHMMSS.wav`). SM2 en **`.wac`** : conversion en WAV d’abord (ci-dessous). |
| **Autres horodatés** | Passive Recorder, Bat Recorder, etc. |
| **AudioMoth** | Fichiers *déjà expandés* via l’AudioMoth Configuration App (*File → Expand*). ChiroTool assure ensuite renommage + TE×10 (alternative à Kaleidoscope, devenu payant pour l’AudioMoth). |
| **Titley** | Anabat Swift / Ranger, nom usine `YYYY-MM-DD HH-MM-SS.wav` (espace ou underscore, n° d’enregistreur optionnel). |

Les formats à noms **non datés** (ex. Peersonic, Pettersson D500x) nécessitent un renommage préalable (XnView vers `YYYYMMDD_HHMMSS.wav`).

Les fichiers compressés Wildlife **`.wac`** (SM2, parfois SM3) et **`.w4v`** ne sont **pas** décompressés. Convertissez-les en WAV horodatés `PREFIX_YYYYMMDD_HHMMSS` **avant** Préparer : Kaleidoscope Lite (sans licence Pro) ou WAC2WAV + *Split Triggers* ; expansion de sortie **×1** (le TE×10, c’est ChiroTool) ; **Disable noise filtering** ; **un WAV par trigger** (un pavé d’une heure par WAC = triggers non extraits). Même logique que l’AudioMoth `T.WAV` à expander. Détail : [tutoriel §12](docs/TUTORIEL.md#12--questions-fréquentes--dépannage).

---

## Installation

### Option A — Exe portable (recommandé sur le terrain)

1. Téléchargez **`ChiroTool.exe`** depuis la
   [dernière release](https://github.com/kevin-guille/ChiroTool/releases).
2. Placez-le où vous voulez (clé USB, dossier campagne…).
3. Double-cliquez pour lancer.

**Mode portable** : créez un fichier vide `chirotool.cfg` à côté de l’exe  
→ config et préférences restent dans le même dossier.

**Mode installé** : sans ce marqueur, la config va dans `%APPDATA%\ChiroTool\`.

Au premier lancement : choisissez le **dossier de travail**, puis renseignez le
**token Vigie-Chiro** (Préférences → API, ou assistant d’onboarding).

---

### Option B — Depuis les sources (Python 3.11+)

#### PowerShell

```powershell
git clone https://github.com/kevin-guille/ChiroTool.git
cd ChiroTool
python -m pip install -r requirements.txt
python gui_app.py
```

#### Git Bash

```bash
git clone https://github.com/kevin-guille/ChiroTool.git
cd ChiroTool
python -m pip install -r requirements.txt
python gui_app.py
```

### Token API (une fois par poste)

Le token s’obtient après connexion au
[portail Vigie-Chiro](https://vigiechiro.herokuapp.com/)
(`localStorage` → clé `auth-session-token`). **Ne le partagez jamais**
(voir [SECURITY.md](SECURITY.md)).

**Via l’interface** (le plus simple) : *Préférences → API Vigie-Chiro*.

**Via la CLI** — saisie **masquée** (recommandé) :

```powershell
# PowerShell
python vigiechiro_api.py save-token
```

```bash
# Git Bash / terminal
python vigiechiro_api.py save-token
```

Autres options sûres :

```powershell
# Variable d'environnement (session courante)
$env:VIGIECHIRO_TOKEN = "VOTRE_TOKEN"
python vigiechiro_api.py save-token
```

```bash
# Pipe (évite l'historique argv)
echo VOTRE_TOKEN | python vigiechiro_api.py save-token
```

> ❌ Évitez `save-token VOTRE_TOKEN` en argument : le secret apparaît dans
> l’historique du shell et la liste des processus. Ce mode est **déprécié**.

Le token est stocké via le **Gestionnaire d’identifiants Windows** (ou DPAPI en secours).

### Accélération Rust (optionnelle)

Pour de gros volumes sur disque local rapide, compilez l’extension
`chirotool_fast` (gain typique ~×2 à ×10 selon le support).  
Sans elle, le TE×10 reste en **Python pur** — aucune action requise.

Voir [`rust_ext/README.md`](rust_ext/README.md).

---

## Utilisation en ligne de commande

Le moteur est **indépendant de l’interface** : tout peut tourner en CLI / scripts.

```bash
python scan.py [<racine>]                           # état des sessions
python vigiechiro_api.py save-token                 # token (saisie masquée)
python rename.py <session> --auto                   # renommage
python te10.py <session-ou-Data>                    # expansion temporelle
python cleanup.py <session> --threshold-chiros 0.5  # nettoyage par seuils
python pipeline.py <session> --advance --use-api    # pipeline complet (cloud)
python registry.py scan <racine>                    # (re)peuple le registre
python vigiechiro_api.py resolve-carre <lat> <lon>  # carré STOC (lecture)
```

---

## Tutoriel & documentation

| Document | Public |
|----------|--------|
| 📘 [**Tutoriel PDF**](docs/ChiroTool-Tutoriel.pdf) | Utilisateurs (version publiée) |
| 📘 [**Tutoriel Markdown**](docs/TUTORIEL.md) | Utilisateurs (source du PDF) |
| 🧭 [**SPEC parcours post-0.5**](docs/SPEC_v06_parcours.md) | Conception / dev (issue #3) |
| 📝 [**Changelog**](CHANGELOG.md) | Versions & *Prévu* |
| 🤝 [**Contribuer**](CONTRIBUTING.md) | Contributeurs |

Captures sources : [`docs/captures/`](docs/captures/).

---

## Architecture

Moteur Python testable sans UI + interface CustomTkinter.

| Couche | Modules clés |
|--------|----------------|
| **Logique pure** | `chiro_core`, `naming`, `taxons`, `manifest`, `verify`, `vigiechiro_enums` |
| **Accès données** | `vigiechiro_api`, `credentials`, `registry`, `suivi`, `suivi_write` |
| **Opérations** | `scan`, `rename`, `te10`, `cleanup`, `pipeline` |
| **GUI** | `gui_app`, `gui_validation`, `gui_map`, `gui_registry`, wizards… |
| **Natif (opt.)** | `rust_ext` → `chirotool_fast` |

Tests : `pytest tests/` (également en [CI GitHub Actions](https://github.com/kevin-guille/ChiroTool/actions)).

---

## Pour les naturalistes & bureaux d’études

Vous avez une saison Point Fixe devant vous ? **ChiroTool est fait pour ça.**

1. **[Téléchargez la v0.6](https://github.com/kevin-guille/ChiroTool/releases)** (exe ou sources)
2. Traitez une nuit test de bout en bout
3. Envoyez un retour — bug, idée, besoin de formation —
   via une [**issue GitHub**](https://github.com/kevin-guille/ChiroTool/issues)
   ou en contactant l’auteur

Les retours terrain (BE, assos, observateurs) orientent directement la roadmap.
Le code est **libre (MIT)** : audit, adaptation interne, contribution bienvenus —
voir [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Sécurité

- Token chiffré localement (Credential Manager / DPAPI)
- Pas d’envoi du token ailleurs que vers l’API Vigie-Chiro (HTTPS)
- Signalement de vulnérabilité **en privé** — voir [`SECURITY.md`](SECURITY.md)

---

## Licence

Distribué sous licence **[MIT](LICENSE)** — usage, modification et redistribution libres.

---

## Crédits

- **Auteur** : [Kevin Guille](https://fr.linkedin.com/in/kevin-guille-764b6a150) — chargé d’études naturalistes
- **Avec le soutien de** : [Acer Campestre](https://www.acer-campestre.fr/)
  ([LinkedIn](https://fr.linkedin.com/company/acer-campestre))
- **Protocole & API** : [Vigie-Chiro / MNHN](https://www.vigienature.fr/fr/chauves-souris)

---

<div align="center">

🦇 **Bon traitement, et bonnes chauves-souris !**

[⬆ Télécharger](https://github.com/kevin-guille/ChiroTool/releases)
·
[📖 Tutoriel](docs/ChiroTool-Tutoriel.pdf)
·
[💬 Issues](https://github.com/kevin-guille/ChiroTool/issues)

</div>
