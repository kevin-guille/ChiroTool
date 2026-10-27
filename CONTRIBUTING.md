# Contribuer à ChiroTool

Merci de l'intérêt que vous portez au projet ! ChiroTool est développé sur du
temps personnel et maintenu à temps partiel — les retours de terrain sont
précieux et toute aide est bienvenue.

## Formulation

ChiroTool prépare, envoie, suit, archive et produit une synthèse de campagne.
Pour la validation Vigie-Chiro ou la relecture fine d'un _Vu, utiliser une seule phrase : « Pour ce type d'analyse, se reporter à ChiroSurf. » Ailleurs : logiciel externe, fichier _Vu, CSV par nuit, Interprétation _Vu.
Libellés : case « Interprétation _Vu », barre « CSV nuits », bouton CSV « Ouvrir le CSV », écoute « Ouvrir le son ».
Ne pas présenter la méthode du MNHN comme une fonction, ni ajouter de formule d'interdiction ou de publicité. Ne pas réintroduire Acer.
Conserver chirosurf/ et les noms de code, la logique Python, les assertions et les scénarios de test. Écrire en français, sans tiret cadratin, demi-cadratin ni double tiret.

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
[`§0.1`](docs/SPEC_v06_parcours.md)),
[#7](https://github.com/kevin-guille/ChiroTool/issues/7) (SPEC
[`§0.2`](docs/SPEC_v06_parcours.md)),
[#8](https://github.com/kevin-guille/ChiroTool/issues/8) (SPEC
[`§0.3`](docs/SPEC_v06_parcours.md)),
[#9](https://github.com/kevin-guille/ChiroTool/issues/9),
[#10](https://github.com/kevin-guille/ChiroTool/issues/10) (SPEC
[`§0.4`](docs/SPEC_v06_parcours.md)) et
[#11](https://github.com/kevin-guille/ChiroTool/issues/11) (SPEC
[`§0.5`](docs/SPEC_v06_parcours.md), code dans la pré-release 0.8.2)
comme une todo.
Le batch Préparer est **interne** :
SPEC [`§0.6`](docs/SPEC_v06_parcours.md), pas d'issue GitHub, dans l'exe 0.8.2.
En particulier : **pas plusieurs exe** (mode Batch, D14) ; **Valider puis
Nettoyer** déjà en 0.7 ; relecture d'un `_Vu` produit dans le logiciel externe dans
la **Synthèse et Activité** (v0.8, P8, pas la procédure de validation
Vigie-Chiro) ; CSV pour ouvrir une nuit dans le logiciel externe déjà en 0.7.1.

- **v0.6** : PointSelection, carte pick/FOCUS, Vérifier / Réparer, export USB.
- **v0.7** : Synthèse autonome, Titley (noms), Valider tri/filtres, Batch,
  plus de scan auto (#5), WAC documenté (#6). **v0.7.1 / 0.7.2** :
  CSV par nuit + `_Vu`, nuit bio midi (D12), barre d'actions glissable.
- **v0.8.0** : relecture d'un `_Vu` dans la Synthèse et Activité (P8, issue #7).
  Exe du 2026-09-08 : upload 409, Afficher le bureau. Correctif Titley TE×10
  (2026-09-09) : WAV > 5 s découpé en entier. **Publiée** GitHub le 2026-09-09
  en pre-release ([v0.8.0](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.0)).
- **v0.8.1** (2026-09-19) : issues #8 (série / log Titley / T°), #9 (wizard
  upload), #10 (Activité cache, `_Vu` racine / Data_k, filtres de relecture). Scan
  d'un export Data_k-only ; TE×10 conservé après nettoyage. Reprise d'upload
  sans relancer Tadarida si la nuit est déjà analysée. **Publiée** GitHub
  le 2026-09-19 en Latest
  ([v0.8.1](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.1)).
- **v0.8.2** (2026-09-24, pré-release publiée) : #13 choix sur la carte, #11
  suivi d'upload (clics, confirmation à la fermeture, historique pendant
  l'envoi), #14 nuit déjà analysée sans comparer les WAV, #12 espèces de
  la nuit affichée, libellés, batch Préparer (§0.6). Le calcul de relecture
  d'un `_Vu` ne change pas. Dossiers, manifests et registre existants
  restent en place (schéma du registre inchangé). Elle n'a pas été
  promue. La Latest est la
  [v0.8.5](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.5)
  ([v0.8.2](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.2)).
- **v0.8.3** (2026-10-18) : build local, **non publié**. Le tag
  v0.8.3 n'est pas créé. Le contenu est repris dans la 0.8.4.
- **v0.8.4** (2026-10-22) : build local, **non publié**. Le tag
  v0.8.4 n'est pas créé. Le contenu est repris dans la 0.8.5.
  Exe local : 37469168 octets, SHA-256
  `EA70113C659FE8A5A8955BB278FFF59F3F71D18D09BC76C416F6FC010FF96A15`.
- **v0.8.5** (2026-10-26, **Latest** publiée) : tag `v0.8.5` sur
  `fc44307`. Elle reprend la 0.8.3 et la 0.8.4 (lot, métadonnées, carte, sync, tableur, export)
  et ajoute le seuil « Confiance min. » de l'onglet Activité (#12),
  le raccourci TERMINE / FINI dans l'envoi groupé (#14), et le fond
  OSM identifié comme ChiroTool. Une seule
  instance. `version.py` = 0.8.5. Asset : 37474903 octets,
  FileVersion 0.8.5.0, SHA-256
  `8759593FA5C0A6FA95CEE4A67C0FC68D84B93E6570673264A73C198079EC9502`
  ([v0.8.5](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.5)).

| Document | Rôle |
|----------|------|
| [`docs/SPEC_v06_parcours.md`](docs/SPEC_v06_parcours.md) | **Source de vérité** (v0.8.5 Latest publiée, §0.8 à §0.10 ; pré-release 0.8.2 §0.7 ; v0.8.1 ancienne Latest ; les 0.8.3 et 0.8.4 ne sont pas publiées ; §0.1 #4 ; §0.2 #7 ; §0.3 #8 ; §0.4 #9/#10 ; §0.5 #11 ; §0.6 batch Préparer ; D14 une seule instance) |
| [`CHANGELOG.md`](CHANGELOG.md) | Versions publiées + *Suite possible* |
| [`docs/RELEASE_v0.6.0.md`](docs/RELEASE_v0.6.0.md) | Note de release GitHub v0.6 |
| [`docs/RELEASE_v0.7.0.md`](docs/RELEASE_v0.7.0.md) | Note de release GitHub v0.7 |
| [`docs/RELEASE_v0.7.1.md`](docs/RELEASE_v0.7.1.md) | Note de pre-release GitHub v0.7.1 (issue #7, remplacée) |
| [`docs/RELEASE_v0.7.2.md`](docs/RELEASE_v0.7.2.md) | Note de release GitHub v0.7.2 (remplacée par 0.8.1) |
| [`docs/RELEASE_v0.8.0.md`](docs/RELEASE_v0.8.0.md) | Note de pre-release GitHub v0.8.0 (2026-09-09, remplacée par 0.8.1) |
| [`docs/RELEASE_v0.8.1.md`](docs/RELEASE_v0.8.1.md) | Note de release GitHub v0.8.1 (ancienne Latest, 2026-09-19, SHA exe) |
| [`docs/RELEASE_v0.8.2.md`](docs/RELEASE_v0.8.2.md) | Note de pré-release GitHub v0.8.2 (2026-09-24, SHA exe) |
| [`docs/RELEASE_v0.8.3.md`](docs/RELEASE_v0.8.3.md) | Note locale v0.8.3, non publiée (contenu repris en 0.8.4) |
| [`docs/RELEASE_v0.8.4.md`](docs/RELEASE_v0.8.4.md) | Note locale v0.8.4, non publiée (contenu repris en 0.8.5) |
| [`docs/RELEASE_v0.8.5.md`](docs/RELEASE_v0.8.5.md) | Note de release GitHub v0.8.5 (Latest, 2026-10-26, SHA exe) |
| [`docs/TUTORIEL.md`](docs/TUTORIEL.md) | Guide utilisateur (pick, Synthèse, CSV optionnel pour le logiciel externe, repair) |
| [`docs/ChiroTool-Tutoriel.pdf`](docs/ChiroTool-Tutoriel.pdf) | PDF généré via `python docs/build_pdf.py` |
| [`docs/sitemap.xml`](docs/sitemap.xml) | Dates (`lastmod`) de la page et du PDF publiés. À avancer quand l'un des deux change. |
| [`samples/issue3_benjamin/`](samples/issue3_benjamin/) | Fixtures CSV multi-nuits + `_Vu` (issue #3) |
| [`tests/fixtures/titley_log_overnight.csv`](tests/fixtures/titley_log_overnight.csv) | Log Titley de test (CI). Le log terrain `samples/issue4_mickael/` n'est pas versionné. |

En cas de doute d’implémentation, la **SPEC prime**. Tout écart = amendement
explicite du §8 de la SPEC avant merge. Le détail tutoriel des features livrées
se met à jour **après** chaque vague, pas avant. Régénérer le PDF après
modification de `TUTORIEL.md`.

## Proposer du code

1. *Forkez* le dépôt et créez une branche (`git checkout -b fix/mon-correctif`).
2. Gardez les changements ciblés et commentés (le code est en français).
3. Vérifiez que les tests passent : `python -m pytest`.
4. Ouvrez une *pull request* en expliquant le pourquoi du changement.
5. Si le changement touche carte / meta / logiciel externe : alignez-vous sur la SPEC
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
