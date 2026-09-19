# ChiroTool v0.8.1 : participation Titley, upload unitaire, Activité

> Version **0.8.1** (`version.py`). Tag GitHub `v0.8.1` à créer **après**
> le rebuild de l'exe. Tant que ce tag n'existe pas, l'exe téléchargeable
> reste la pre-release
> [v0.8.0](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.0).
>
> GitHub « Latest » reste [v0.7.2](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.7.2)
> tant que 0.8.x est en pre-release. L'app lit la liste des releases
> (pre-releases comprises).

La 0.8.0 était une pre-release incomplète (wizard upload, métadonnées
Titley, Activité). Cette 0.8.1 la remplace pour les tests terrain.

Répond aux issues
[#8](https://github.com/kevin-guille/ChiroTool/issues/8),
[#9](https://github.com/kevin-guille/ChiroTool/issues/9) et
[#10](https://github.com/kevin-guille/ChiroTool/issues/10).
Conserve le TE×10 Titley ([#4](https://github.com/kevin-guille/ChiroTool/issues/4))
et la méthode MNHN 10 % / 75 % ([#7](https://github.com/kevin-guille/ChiroTool/issues/7)).

## Ce qui arrive avec cette version

- **Participation Titley** : n° de série, type, micro. Horaires et T° lus
  dans le `log_*.csv` (`Recording start` / `stop`, pas les 38 °C de jour).
  T° corrigées à la main conservées. **Vérifier / Réparer** peut PATCH
  sans relancer Tadarida. Une reprise d'upload ne relance pas Tadarida
  si la nuit est déjà PLANIFIE / EN_COURS / TERMINE / FINI.
- **Upload unitaire** : l'assistant « Nouvelle participation » s'affiche
  tout de suite (plus de fenêtre noire sur un gros Data_k). Le batch ne
  change pas. Fermer le suivi d'upload le met en arrière-plan ; recliquer
  Upload le rouvre.
- **Activité** : tableurs en mémoire. Cocher MNHN / chiros ne relit plus
  le disque. Un `_Vu` à la racine de session ou dans `Data_k/` est lu.
  Cocher MNHN ne fait plus disparaître les autres carrés.
- **Export USB** : un paquet Data_k-only retrouve la session (plus le
  dossier `Data_k/` lui-même). Après nettoyage, la pastille TE reste verte.

## Installation

Rebuild `ChiroTool.exe` depuis ce commit, puis crée le tag `v0.8.1` avec
le même numéro que `version.py`. Remplace l'exe 0.8.0 chez les testeurs.

Tutoriel : [https://kevin-guille.github.io/ChiroTool/](https://kevin-guille.github.io/ChiroTool/)

## Avertissement

Outil indépendant, compatible avec le protocole Vigie-Chiro Point Fixe via
son API publique. Ce n'est pas un outil officiel du MNHN.
