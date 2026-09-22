# ChiroTool v0.8.0 : relecture d'un _Vu ChiroSurf (Synthèse et Activité)

> **Remplacée par [v0.8.1](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.1)**
> (Latest, 2026-09-19). Pre-release GitHub du 2026-09-09 :
> [v0.8.0](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.0).
> SHA-256 de l'asset `ChiroTool.exe` :
> `225FD7B1D96740724459A76DB46601FDBC26F667F9D988897023AA3E71964ED7`.

Répond à l'issue
[#7](https://github.com/kevin-guille/ChiroTool/issues/7) : après un `_Vu`
produit dans ChiroSurf, la Synthèse **et** l'onglet Activité peuvent le
relire. Ce n'est pas la procédure de validation Vigie-Chiro, qui se fait
dans ChiroSurf. Issue
[#4](https://github.com/kevin-guille/ChiroTool/issues/4) : un WAV Titley
de plus de 5 s est découpé en entier.

## Ce qui arrive avec cette version

- **📊 Synthèse** : case **Interprétation _Vu (ChiroSurf)**, distincte de
  « Identifications validées seulement » (contacts écoutés). Relecture
  d'un fichier produit dans ChiroSurf (bandes de confiance Tadarida, pas
  le temps). Colonne **Seuil _Vu** dans le tableau.
  Export CSV avec `Atteint_75`, `F75`, le pool Tadarida et les proba
  illisibles. Un `_Vu` cassé affiche le nom du fichier et replie sur
  le tableur.
- **Activité** : un `_Vu` remplace le tableur **pour cette nuit seulement**
  (une nuit 2 n'est plus masquée). Même case de relecture que la Synthèse.
  Ce n'est pas l'évaluation d'activité de ChiroSurf.
- Avertissement si la relecture tourne sur un xlsx sans `_Vu` : elle vise
  un fichier produit dans ChiroSurf, pas la validation contact par contact.

Les sessions déjà préparées (v0.7.x) restent utilisables. La case est
décochée par défaut.

## Correctifs inclus dans cet exe (2026-09-08)

Version toujours **0.8.0**. Même tag GitHub.

- **Upload** : un WAV déjà enregistré (code 409) n'est plus un échec.
  Il est sauté, Tadarida peut partir. Cas typique : l'envoi a créé les
  fiches, puis s'est interrompu avant l'analyse.
- **Vérifier / Réparer** : si le portail n'arrive pas à lister les
  fichiers, sonde les noms Data_k. Tous déjà enregistrés : propose de
  lancer Tadarida. Si l'analyse sort 0 contact, le son n'est probablement
  pas sur le serveur (nouvelle participation, renvoyer `Data_k/`).
- **Afficher le bureau** (Win+D) : recliquer ChiroTool ramène la fenêtre
  de progression. Plus besoin du Gestionnaire des tâches.

## Correctifs inclus dans cet exe (2026-09-09)

Version toujours **0.8.0**. Même tag GitHub.

- **TE×10 Titley / Wildlife** (issue
  [#4](https://github.com/kevin-guille/ChiroTool/issues/4)) : un WAV de
  plus de 5 s (Anabat Swift / Ranger jusqu'à 15 s) est découpé en
  entier. La 0.7.2 ne gardait que les 5 premières secondes. Relancer
  **▶ Préparer** : les tranches manquantes s'ajoutent, Upload reste
  grisé tant que `Data_k` est incomplet.
- Historique : `N sources → M segments · W écrits` avec W < M signale
  le trou.
- **Activité** : case **Interprétation _Vu (ChiroSurf)** (issue #7).

## Installation

Téléchargez `ChiroTool.exe` ci-dessous (portable, Windows). Remplacez
l'exe 0.7.x : les dossiers de nuits déjà traités sont conservés.

Tutoriel : [https://kevin-guille.github.io/ChiroTool/](https://kevin-guille.github.io/ChiroTool/)

## Avertissement

Outil indépendant, compatible avec le protocole Vigie-Chiro Point Fixe via son
API publique. Ce n'est pas un outil officiel du MNHN.

---

SHA-256 (`ChiroTool.exe`) : `225FD7B1D96740724459A76DB46601FDBC26F667F9D988897023AA3E71964ED7`
