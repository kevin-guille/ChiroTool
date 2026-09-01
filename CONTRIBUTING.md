# Contribuer à ChiroTool

Merci de l'intérêt que vous portez au projet ! ChiroTool est développé sur du
temps personnel et maintenu à temps partiel — les retours de terrain sont
précieux et toute aide est bienvenue.

## Signaler un bug ou proposer une idée

Ouvrez une [issue](https://github.com/kevin-guille/ChiroTool/issues) en
décrivant :

- ce que vous faisiez et ce qui s'est passé (vs. attendu) ;
- votre version de ChiroTool (visible dans la page **À propos**) et de Windows ;
- si possible, le fichier de log : `%APPDATA%\ChiroTool\chirotool.log`.

## ⚠️ Confidentialité — à lire avant de poster

- **Ne partagez jamais votre token Vigie-Chiro** (ni dans une issue, ni dans un
  log, ni dans une capture). C'est l'équivalent d'un mot de passe de votre compte.
- **Anonymisez les données clients** : masquez les noms de contrats, numéros de
  sites précis et coordonnées GPS de points d'écoute avant de joindre une capture
  ou un fichier d'exemple.

## Conception livrée (v0.6 + v0.7)

Parcours PointSelection / carte / ChiroSurf : **v0.6**. Synthèse autonome
(sélecteur de nuit, sans ChiroSurf), Titley, Valider, démarrage sans scan auto,
WAC documenté : **v0.7** ([release](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.7.0)).
Liaison ChiroSurf (CSV à côté des WAV, `_Vu` `Nuit_1_…`) : **v0.7.1**.
Nuit biologique D12 (midi, jamais minuit) + barre d'actions glissable :
**v0.7.2**.

| Document | Rôle |
|----------|------|
| [`docs/SPEC_v06_parcours.md`](docs/SPEC_v06_parcours.md) | **Source de vérité** parcours (vagues A–C livrées ; D plus tard) |
| [`CHANGELOG.md`](CHANGELOG.md) | Versions publiées + *Suite possible* |
| [`docs/RELEASE_v0.6.0.md`](docs/RELEASE_v0.6.0.md) | Note de release GitHub v0.6 |
| [`docs/RELEASE_v0.7.0.md`](docs/RELEASE_v0.7.0.md) | Note de release GitHub v0.7 |
| [`docs/RELEASE_v0.7.1.md`](docs/RELEASE_v0.7.1.md) | Note de pre-release GitHub v0.7.1 (issue #7, remplacée par 0.7.2) |
| [`docs/RELEASE_v0.7.2.md`](docs/RELEASE_v0.7.2.md) | Note de release GitHub v0.7.2 (courante) |
| [`docs/TUTORIEL.md`](docs/TUTORIEL.md) | Guide utilisateur (pick, Synthèse, ChiroSurf optionnel, repair) |
| [`docs/ChiroTool-Tutoriel.pdf`](docs/ChiroTool-Tutoriel.pdf) | PDF généré via `python docs/build_pdf.py` |
| [`samples/issue3_benjamin/`](samples/issue3_benjamin/) | Fixtures CSV multi-nuits + `_Vu` (issue #3) |

En cas de doute d’implémentation, la **SPEC prime**. Tout écart = amendement
explicite du §8 de la SPEC avant merge. Le détail tutoriel des features livrées
se met à jour **après** chaque vague, pas avant. Régénérer le PDF après
modification de `TUTORIEL.md`.

## Proposer du code

1. *Forkez* le dépôt et créez une branche (`git checkout -b fix/mon-correctif`).
2. Gardez les changements ciblés et commentés (le code est en français).
3. Vérifiez que les tests passent : `python -m pytest`.
4. Ouvrez une *pull request* en expliquant le pourquoi du changement.
5. Si le changement touche carte / meta / ChiroSurf : alignez-vous sur la SPEC
   ci-dessus (ou proposez un amendement dans son §8).

### Style

- Python 3.11+, lignes ~88-100 colonnes, docstrings en français.
- La **logique pure** (parsing, nommage, règles) ne doit pas dépendre de l'UI,
  pour rester testable seule.
- Pas de données réelles (WAV, xlsx, registre, token) dans les commits — voir
  le `.gitignore`.

## Environnement de développement

```bash
python -m pip install -r requirements.txt
python -m pytest          # tests
python gui_app.py         # lancer la GUI
```

L'extension Rust est **optionnelle** (voir `rust_ext/README.md`) ; sans elle,
tout fonctionne en Python pur.

---

Encore merci 🦇 — chaque retour aide à fiabiliser l'outil pour toute la
communauté chiro.
