# Échantillons issue #3 (Benjamin Drillat)

Fichiers fournis sur
[issue #3](https://github.com/kevin-guille/ChiroTool/issues/3)
(commentaire du 2026-08-03) pour cadrer le split multi-nuits / import `_Vu`
ChiroSurf.

## Contenu

| Fichier local | Rôle |
|---------------|------|
| `multi_nuits-observations.csv` | CSV Tadarida brut **2 nuits biologiques** (participation unique) |
| `Nuit_1-observations.csv` | Nuit 1 scindée (brut) |
| `Nuit_1-observations_Vu.csv` | Nuit 1 après validation ChiroSurf |
| `Nuit_2-observations.csv` | Nuit 2 scindée (brut) |
| `Nuit_2-observations_Vu.csv` | Nuit 2 après validation ChiroSurf |

Noms d’origine GitHub (convention retenue dans la SPEC) :

```
Nuit_1_<id>-participation-<id>-observations.csv
Nuit_1_<id>-participation-<id>-observations_Vu.csv
…
```

## Constats techniques (conception)

- Délimiteur `;`, 11 colonnes Vigie-Chiro standard.
- **Nuit biologique** = coupure à midi : 8000 + 7839 = total multi.
- `_Vu` = mêmes lignes, colonnes `observateur_taxon` /
  `observateur_probabilite` renseignées (ex. SUR / PROBABLE).
- ChiroSurf écrit le `_Vu` **à côté** du brut ; on rouvre le CSV sans `_Vu`
  pour continuer.

## Usage

Référence pour tests unitaires du futur module de split / import (Vague C).
Ne pas traiter comme données de production à redistribuer hors dev.

Conception associée : [`docs/SPEC_v06_parcours.md`](../../docs/SPEC_v06_parcours.md).
