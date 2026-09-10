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

## Conception livrée (v0.8 courante)

**Ne pas** traiter le 1er message des issues
[#4](https://github.com/kevin-guille/ChiroTool/issues/4) (SPEC
[`§0.1`](docs/SPEC_v06_parcours.md)) et
[#7](https://github.com/kevin-guille/ChiroTool/issues/7) (SPEC
[`§0.2`](docs/SPEC_v06_parcours.md)) comme une todo.
En particulier : **pas plusieurs exe** (mode Batch, D14) ; **Valider puis
Nettoyer** déjà en 0.7 ; **MNHN 10 % / 75 %** dans la **Synthèse et Activité**
(v0.8, P8) ; ChiroSurf / `_Vu` déjà en 0.7.1.

- **v0.6** : PointSelection, carte pick/FOCUS, Vérifier / Réparer, export USB.
- **v0.7** : Synthèse autonome, Titley (noms), Valider tri/filtres, Batch,
  plus de scan auto (#5), WAC documenté (#6). **v0.7.1 / 0.7.2** : ChiroSurf
  CSV + `_Vu`, nuit bio midi (D12), barre d'actions glissable.
- **v0.8.0** : MNHN 10 % / 75 % dans la Synthèse et Activité (P8, issue #7).
  Exe du 2026-09-08 : upload 409, Afficher le bureau. Correctif Titley TE×10
  (2026-09-09) : WAV > 5 s découpé en entier. **Publiée** GitHub le 2026-09-09
  en pre-release ([v0.8.0](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.0)).
- **v0.8.1-dev** (2026-09-10) : scan d'un export Data_k-only (session = parent,
  pas `Data_k/`) ; TE×10 conservé après nettoyage (pastille verte). Pas de
  tag GitHub.

| Document | Rôle |
|----------|------|
| [`docs/SPEC_v06_parcours.md`](docs/SPEC_v06_parcours.md) | **Source de vérité** (v0.8 livrée ; §0.1 issue #4 ; §0.2 issue #7 ; D14 Batch) |
| [`CHANGELOG.md`](CHANGELOG.md) | Versions publiées + *Suite possible* |
| [`docs/RELEASE_v0.6.0.md`](docs/RELEASE_v0.6.0.md) | Note de release GitHub v0.6 |
| [`docs/RELEASE_v0.7.0.md`](docs/RELEASE_v0.7.0.md) | Note de release GitHub v0.7 |
| [`docs/RELEASE_v0.7.1.md`](docs/RELEASE_v0.7.1.md) | Note de pre-release GitHub v0.7.1 (issue #7, remplacée) |
| [`docs/RELEASE_v0.7.2.md`](docs/RELEASE_v0.7.2.md) | Note de release GitHub v0.7.2 (Latest GitHub tant que 0.8.0 est pre-release) |
| [`docs/RELEASE_v0.8.0.md`](docs/RELEASE_v0.8.0.md) | Note de pre-release GitHub v0.8.0 (courante à tester, 2026-09-09) |
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
