# ChiroTool v0.8.1 : participation Titley, upload unitaire, Activité

> **Pre-release GitHub** (2026-09-19) :
> [v0.8.1](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.1).
> SHA-256 de l'asset `ChiroTool.exe` :
> `14C620BC40BC1E2DB9059653B6830E5B107A1726DCF0107DB3D16BD4123B19AE`.
> GitHub « Latest » reste [v0.7.2](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.7.2)
> tant que 0.8.x est en pre-release. L'app lit la liste des releases
> (pre-releases comprises).

Remplace la pre-release [v0.8.0](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.0)
pour les tests terrain (wizard upload, métadonnées Titley, Activité).

Répond aux issues
[#8](https://github.com/kevin-guille/ChiroTool/issues/8),
[#9](https://github.com/kevin-guille/ChiroTool/issues/9) et
[#10](https://github.com/kevin-guille/ChiroTool/issues/10).
Conserve le TE×10 Titley ([#4](https://github.com/kevin-guille/ChiroTool/issues/4))
et la méthode MNHN 10 % / 75 % ([#7](https://github.com/kevin-guille/ChiroTool/issues/7)).

L'issue [#11](https://github.com/kevin-guille/ChiroTool/issues/11) (suivi
d'upload) est **partielle** : réouvrir la fenêtre est dans cette version ;
fermeture de l'exe et historique en direct restent ouverts.

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

Téléchargez `ChiroTool.exe` ci-dessous (portable, Windows). Remplacez
l'exe 0.8.0 : les dossiers de nuits déjà traités sont conservés.

Tutoriel : [https://kevin-guille.github.io/ChiroTool/](https://kevin-guille.github.io/ChiroTool/)

## Avertissement

Outil indépendant, compatible avec le protocole Vigie-Chiro Point Fixe via
son API publique. Ce n'est pas un outil officiel du MNHN.

---

SHA-256 (`ChiroTool.exe`) : `14C620BC40BC1E2DB9059653B6830E5B107A1726DCF0107DB3D16BD4123B19AE`
