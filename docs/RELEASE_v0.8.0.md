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

## Installation

Téléchargez `ChiroTool.exe` ci-dessous (portable, Windows). Remplacez
l'exe 0.7.x : les dossiers de nuits déjà traités sont conservés.

Tutoriel : [https://kevin-guille.github.io/ChiroTool/](https://kevin-guille.github.io/ChiroTool/)

## Avertissement

Outil indépendant, compatible avec le protocole Vigie-Chiro Point Fixe via son
API publique. Ce n'est pas un outil officiel du MNHN.

---

SHA-256 (`ChiroTool.exe`) : `7EC0BFDF69BB5398E3B09CCF3A6D3C831BE6533368AF1D9C43EF16532B50D50A`
