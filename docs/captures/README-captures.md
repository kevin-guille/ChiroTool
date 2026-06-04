# Guide des captures d'écran du tutoriel

Ce dossier contient les images du tutoriel `TUTORIEL.md`. Deux d'entre elles
sont déjà générées et prêtes :

| Fichier | État | Contenu |
|---|---|---|
| `icon_256.png` | ✅ fourni | Logo ChiroTool (utilisé en en-tête) |
| `exemple-graphe-activite.png` | ✅ fourni | Exemple de graphe d'activité (section 9) |

## Les 13 captures à prendre toi-même

Le tutoriel référence 13 captures (balises `📸 [Capture XX — …]`). Tu dois les
prendre depuis l'application, puis les enregistrer dans ce dossier sous les noms
indiqués ci-dessous. Le tutoriel les affichera automatiquement à condition de
remplacer chaque balise `📸 [Capture XX — …]` par la syntaxe markdown d'image
(voir « Comment insérer » plus bas).

> 💡 **Bonne nouvelle** : tu as déjà partagé la plupart de ces écrans pendant le
> développement. Réutilise-les ! La colonne « Tu l'as déjà ? » t'indique
> lesquelles.

| N° | Nom de fichier à enregistrer | Écran à capturer | Tu l'as déjà ? |
|---|---|---|---|
| 01 | `01-exe-explorateur.png` | `ChiroTool.exe` dans l'explorateur Windows (montre l'icône bleue) | ✅ oui (capture envoyée) |
| 02 | `02-onboarding-token.png` | Assistant d'accueil, étape 1 (Token). *Au 1er lancement, ou via Préférences si onboarding déjà fait.* | ❌ à prendre |
| 03 | `03-onboarding-workspace.png` | Assistant d'accueil, étape 2 (Dossier de travail) | ❌ à prendre |
| 04 | `04-prefs-materiels.png` | Préférences → onglet « Mes matériels » | ✅ oui (capture envoyée) |
| 05 | `05-fenetre-principale.png` | Fenêtre principale complète (sidebar + onglet Carte ou Vue session) | ✅ oui (plusieurs envoyées) |
| 06 | `06-vue-session.png` | Vue session avec les 3 boutons Préparer / Upload / Nettoyer | ✅ oui (capture envoyée) |
| 07 | `07-wizard-metadonnees.png` | Assistant « Métadonnées de la session » | ✅ oui (capture envoyée) |
| 08 | `08-progression.png` | Fenêtre de progression (barre + ETA) pendant un upload ou TE×10 | ❌ à prendre |
| 09 | `09-wizard-participation.png` | Assistant « Nouvelle participation Vigie-Chiro » (météo + matériel) | ❌ à prendre |
| 10 | `10-prefs-nettoyage.png` | Préférences → onglet « Nettoyage » | ✅ oui (capture envoyée) |
| 11 | `11-recap-nettoyage.png` | Récapitulatif du nettoyage (graphe avant/après) | ❌ à prendre |
| 12 | `12-mode-batch.png` | Mode Batch activé : cases à cocher + barre d'actions | ❌ à prendre |
| 13 | `13-registre.png` | Onglet Registre, vue groupée par contrat | ✅ oui (capture envoyée) |

## Comment prendre une capture propre

1. Ouvre l'écran voulu dans ChiroTool.
2. Sous Windows : **`Touche Windows + Maj + S`** → sélectionne la zone de la
   fenêtre.
3. Colle dans **Paint** (`Ctrl+V`) puis **Enregistre sous** → format **PNG** →
   dans ce dossier `docs/captures/` avec le nom exact du tableau ci-dessus.

> Pour une capture de la fenêtre entière uniquement (sans le reste du bureau) :
> clique d'abord sur la fenêtre ChiroTool, puis **`Alt + Impr. écran`**, et colle
> dans Paint.

## Comment insérer une capture dans le tutoriel

Dans `TUTORIEL.md`, remplace chaque ligne de balise :

```markdown
> 📸 **[Capture 06 — Vue session avec les 3 boutons d'action…]**
```

par la syntaxe d'image markdown :

```markdown
![Vue session avec les 3 boutons d'action](captures/06-vue-session.png)
```

C'est tout : l'image s'affichera dans le tutoriel (sur GitHub, dans un éditeur
markdown, ou après conversion en PDF).

## Astuce : générer un PDF du tutoriel

Pour partager le tutoriel en PDF (pratique pour les réseaux chiros) :

- **Le plus simple** : ouvre `TUTORIEL.md` dans un éditeur markdown (Typora,
  Obsidian, VS Code + extension « Markdown PDF ») → Exporter en PDF.
- **En ligne** : colle le contenu dans [Dillinger](https://dillinger.io/) ou
  [StackEdit](https://stackedit.io/) → export PDF.
- **Via pandoc** (si installé) :
  ```
  pandoc TUTORIEL.md -o ChiroTool-Tutoriel.pdf --pdf-engine=wkhtmltopdf
  ```
