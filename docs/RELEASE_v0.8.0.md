# ChiroTool v0.8.0 : méthode MNHN 10 % / 75 % dans la Synthèse

Release courante. Répond à l'issue
[#7](https://github.com/kevin-guille/ChiroTool/issues/7) : après un `_Vu`
ChiroSurf, la Synthèse peut reconstituer l'interprétation 10 % / 75 %.

## Ce qui arrive avec cette version

- **📊 Synthèse** : case **Méthode MNHN 10 % / 75 %**, distincte de
  « Identifications validées seulement » (contacts écoutés). Bandes de
  confiance Tadarida (pas le temps). Colonne **75 %** dans le tableau.
  Export CSV avec `Atteint_75`, `F75`, le pool Tadarida et les proba
  illisibles. Un `_Vu` cassé affiche le nom du fichier et replie sur
  le tableur.
- **Activité** : un `_Vu` remplace le tableur **pour cette nuit seulement**
  (une nuit 2 n'est plus masquée). Les graphes n'appliquent pas encore
  la méthode MNHN.
- Avertissement si MNHN tourne sur un xlsx sans `_Vu` (ce n'est pas le
  même protocole qu'une validation contact par contact).

Les sessions déjà préparées (v0.7.x) restent utilisables. La case MNHN
est décochée par défaut.

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

## Installation

Téléchargez `ChiroTool.exe` ci-dessous (portable, Windows). Remplacez
l'exe 0.7.x : les dossiers de nuits déjà traités sont conservés.

Tutoriel : [https://kevin-guille.github.io/ChiroTool/](https://kevin-guille.github.io/ChiroTool/)

## Avertissement

Outil indépendant, compatible avec le protocole Vigie-Chiro Point Fixe via son
API publique. Ce n'est pas un outil officiel du MNHN.

---

SHA-256 (`ChiroTool.exe`) : `349241B5D771205C26F4B631EB4220BA7E95C97D8D47D1E93747984FB5F6DC27`
