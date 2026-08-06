# ChiroTool v0.6.0 : multi-nuits ChiroSurf, carte & reprise fiable

ChiroTool automatise toute la chaîne de traitement des enregistrements
Vigie-Chiro Point Fixe, du dossier brut jusqu'aux résultats validés, dans une
seule application libre et gratuite.

## ✨ La nouveauté de cette version

La **v0.6** répond à l’[issue #3](https://github.com/kevin-guille/ChiroTool/issues/3)
(Benjamin Drillat / usage LPO–MNHN) : scinder une participation multi-nuits pour
la **méthode de validation ChiroSurf 10 % → 75 %**, nuit par nuit, tout en
conservant la validation contact-par-contact déjà présente.

Elle fiabilise aussi le parcours **point ↔ carte ↔ serveur** : choisir un point
sur la carte pour les métadonnées, recentrer une nuit sans recharger toute la
France, et **réaligner l’état local** après un upload partiel ou une analyse
relancée sur le portail web.

## 🧰 Ce qui arrive avec cette version

- **🌊 ChiroSurf nuits** — dossier `chirosurf/Nuit{n}_…-observations.csv`
  (nuit biologique, coupure midi) ; import des `_Vu` ; synthèse par nuit
- **🔧 Vérifier / Réparer** — diagnostic Data_k ↔ serveur, couverture WAV,
  fetch xlsx, alignement des flags, relance Tadarida **avec confirmations**
- **🗺️ Pick carte** depuis l’assistant métadonnées (commune, rayon 5 km,
  create / reuse → champs remplis)
- **📍 FOCUS carte** — pin rose, GPS dans le manifest, recentrage sans full-API ;
  « 🔄 Recharger sites » = vue tous les sites
- **💾 Export USB** de sessions (Data_k ± Data + métadonnées)
- **📊 Synthèse** — source xlsx ou `_Vu`, filtre **proba Tadarida minimale**
- **🌤 Météo non bloquante** — T° préremplies depuis le Summary ; vent /
  couverture optionnels (complétables plus tard sur le portail)

## 🔧 Corrections

- Point actif **create et reuse** (y compris autre observateur) mémorisé pour
  le wizard meta
- Upload « tous WAV déjà sur serveur » : plus de flag `uploaded` silencieux ;
  journalisation de `trigger_compute`
- Listing fichiers serveur : pagination + `max_results=99`, fallback `/donnees`,
  message clair si token **401**
- Couverture = WAV **encore dans Data_k** (fichiers purgés localement après
  nettoyage = « sur serveur seul », pas un échec d’upload)

## 📦 Installation

Téléchargez `ChiroTool.exe` ci-dessous. Application portable, aucune installation
(Windows).  
Tutoriel : [https://kevin-guille.github.io/ChiroTool/](https://kevin-guille.github.io/ChiroTool/)  
Changelog : [CHANGELOG.md](https://github.com/kevin-guille/ChiroTool/blob/main/CHANGELOG.md)

## ⚠️ Avertissement

Outil indépendant, compatible avec le protocole Vigie-Chiro Point Fixe via son
API publique. Ce n’est pas un outil officiel du MNHN.

---

SHA-256 (`ChiroTool.exe`) : `3DFFF47B244FAF9616FC62D1C2CFD8E62D45A57BD26FE3FD095019593ED66647`
