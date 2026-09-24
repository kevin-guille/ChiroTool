# ChiroTool v0.8.2 : carte, suivi d'upload, diagnostic

> **Pré-release GitHub** (2026-09-24) :
> [v0.8.2](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.2).
> SHA-256 de l'asset `ChiroTool.exe` :
> `12395A07E4D0904BAE03458A082865B7368B3A2A7599B18D279479B48D8A63B8`.
> La Latest reste
> [v0.8.1](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.1)
> tant que cette pré-release n'est pas promue.

À tester sur les retours de Benjamin :
[#11](https://github.com/kevin-guille/ChiroTool/issues/11),
[#12](https://github.com/kevin-guille/ChiroTool/issues/12),
[#13](https://github.com/kevin-guille/ChiroTool/issues/13),
[#14](https://github.com/kevin-guille/ChiroTool/issues/14).

La validation Vigie-Chiro se fait dans le logiciel externe.
Pour ce type d'analyse, se reporter à ChiroSurf.
La relecture d'un `_Vu` dans ChiroTool ne change pas de calcul.

Les sessions déjà préparées restent utilisables. Remplacez seulement l'exe.

## Ce qui change

- **🗺️ Carte** (issue #13) : « Choisir sur la carte » dans les métadonnées
  ouvre bien l'onglet Carte. Le message « Onglet Carte indisponible »
  venait du bouton, pas de l'onglet.
- **☁️ Suivi d'upload** (issue #11) : fermer la fenêtre de suivi rend les
  clics. Recliquer Upload rouvre aussi un batch en cours.
- **🔧 Vérifier / Réparer** (issue #14) : si le portail dit la nuit
  déjà analysée, les WAV ne sont plus comparés un par un. Le tableur
  manquant est téléchargé. « à reprendre » veut dire : participation
  connue, tableur absent du dossier. Tadarida n'est pas relancée.
- **☁️ Fermeture** (issue #11) : fermer ChiroTool pendant un traitement
  demande confirmation. L'historique se met à jour tout seul pendant
  l'envoi.
- **📈 Activité** (issue #12) : une nuit dont les espèces ne sont pas
  dans la sélection globale affiche ces espèces. La case s'appelle
  « Interprétation _Vu ». Le calcul de relecture ne change pas.
- **▶ Batch Préparer** : une nuit ignorée (métadonnées incomplètes) n'est
  plus comptée comme un succès. Un log Titley donne l'horaire sans
  lister tous les WAV. Une nuit déjà préparée n'est pas refaite.

## Installation

1. Téléchargez `ChiroTool.exe` de cette pré-release.
2. Remplacez l'ancien exe. Les dossiers de nuits ne bougent pas.
3. Au premier lancement, SmartScreen peut demander « Informations
   complémentaires », puis « Exécuter quand même ».
