# ChiroTool : consignes pour les agents

Le dépôt Git est ce dossier (GitHub `kevin-guille/ChiroTool`).
Le dossier parent du clone, hors git (`CLAUDE.md`, `ROADMAP.md`), est un classeur
historique. En cas d'écart, ce fichier et la SPEC gagnent.

## Source de vérité

1. `docs/SPEC_v06_parcours.md` (parcours livré, décisions D1 à D14, issues).
2. `CONTRIBUTING.md` (formulation publique et périmètre).
3. `CHANGELOG.md` et `version.py` (version réellement publiée).

Il n'y a pas de `docs/CHARTE_PRODUIT.md`, `docs/BACKLOG.md` ni `docs/DECISIONS.md`.
Ne pas les inventer. Le §0 et le §8 de la SPEC tiennent ce rôle.

## Produit

ChiroTool prépare, envoie, suit, archive et produit une synthèse de campagne.
Pour la validation Vigie-Chiro ou la relecture fine d'un `_Vu`, une seule phrase :
« Pour ce type d'analyse, se reporter à ChiroSurf. »
Ailleurs : logiciel externe, fichier `_Vu`, CSV par nuit, Interprétation `_Vu`.

Libellés : case « Interprétation _Vu », barre « CSV nuits », bouton CSV « Ouvrir le CSV »,
écoute « Ouvrir le son », préférences « Logiciel externe pour écouter ».

Ne pas présenter la méthode du MNHN comme une fonction, ni ajouter de formule
d'interdiction ou de publicité. Ne pas réintroduire Acer.
Conserver `chirosurf/` et les noms de code (`compute_mnhn_synthesis`,
`iter_mnhn_contacts`, `use_mnhn`). Ne pas changer la logique, les assertions
ni les scénarios de test pour une question de libellé.

La colonne Activité de la Synthèse (classes du référentiel contacts/nuit,
`activity_reference.py`) reste. L'onglet Activité relit un `_Vu` ou le tableur.
Ce n'est pas l'évaluation d'activité du logiciel externe.

Validation contact par contact dans ChiroTool : optionnelle, distincte (SPEC D9).
Ne pas en faire le prochain chantier par défaut.

Écrire en français. Pas de tiret cadratin, demi-cadratin, ni double tiret
dans un texte lu par un humain. Voix « je » sur le contenu public.

## Version et git

- Stable publiée : tag GitHub Latest `v0.8.1` (exe du 2026-09-19).
- Pré-release locale : `version.py` = 0.8.2, build 2026-09-24, exe
  `dist/ChiroTool.exe` (SHA-256
  `5106C7F58CFE1741962454FF1EC1F218B123805328EC65002567E44BD5AB7CEB`).
  Ce n'est pas la Latest tant que Kevin ne promeut pas la pré-release.
- Remplacer l'exe ne migre pas les dossiers déjà en cours. Schéma du
  registre : version 3, inchangé depuis 0.8.1. `feed_from_scan` met à jour
  les pastilles. Il ne réécrit pas l'identifiant de participation, l'état
  portail ni le compteur d'identifications. L'historique live ne touche
  pas le registre. Une nuit dont le manifest a `renamed` et `te10_done`
  n'est pas retraitée.
- Vérifier `git status` et les tags avant d'affirmer qu'un correctif est
  en ligne. `origin/main` peut être en retard sur le commit de pré-release.
- Ne pas pousser, taguer, publier une release, ni reconstruire l'exe
  sans demande explicite de Kevin. C'est lui qui lance `git push`.
- Ne pas réécrire l'historique.
- Ne pas committer `samples/issue4_mickael/`, `samples/issue8_mickael/`,
  `samples/issue9_10/` (journaux terrain, packets d'audit).
- Tests : `python -m pytest tests/ -q`.

## Issues (ne pas relire le premier message comme un backlog)

Déjà tranché dans la SPEC : #4 §0.1, #7 §0.2, #8 §0.3, #9 et #10 §0.4.
#8, #9 et #10 sont fermées. #11 reste ouverte (§0.5).

Ouvertes au 2026-09-24, sans opposition au cadre ChiroSurf :

| Issue | Sujet | Piste |
|---|---|---|
| #11 | Suivi d'upload. Après fermeture du suivi batch, l'interface ne recevait plus les clics. | **0.8.2** : `grab_release`, dialogue batch enregistré, confirmation à la fermeture de l'exe, historique rafraîchi toutes les 4 s. |
| #12 | Activité : graphe vide alors que les fichiers sont lus. Case « Méthode MNHN » dans l'exe 0.8.1. | **0.8.2** : message si les taxons cochés ne sont pas dans la sélection. Calcul inchangé. Case « Interprétation _Vu ». |
| #13 | « Choisir sur la carte » disait « Onglet Carte indisponible ». | **0.8.2** : le wizard remonte jusqu'à la fenêtre qui a `map_panel`. |
| #14 | Vérifier / Réparer listait tous les WAV sur une nuit déjà analysée. | **0.8.2** : si l'état est TERMINE ou FINI, pas de listing portail. Tableur manquant téléchargé. Miroir le plus fourni. Un Data_k déjà rempli n'est plus « incomplet » s'il manque des tranches de 5 s. Pas de `trigger_compute` si déjà analysé. |

Batch Préparer (SPEC §0.6, pas d'issue GitHub, exe 0.8.2) : une nuit
ignorée n'est pas un succès. Log Titley : pas de listing WAV, horaire
du log conservé même si le Suivi a une autre nuit pour la même série.
Suivi ouvert une fois. Nuit déjà renommée et expansée : non retraitée,
comptée OK. Erreur de lecture du manifest ou du Suivi : `chirotool.log`.

## Astra (Codex)

Binaire : `%LOCALAPPDATA%\Programs\OpenAI\Codex\bin\codex.exe`.
Modèle : `gpt-6-astra`. Vérifié le 2026-09-24 : Codex CLI 0.154.0, le modèle
est dans le cache local du 2026-09-22.

Invocation qui marche avec cette CLI (ne pas combiner `--sandbox` et
`--approve-for-me`) :

```text
codex exec -m gpt-6-astra --ephemeral --skip-git-repo-check -C <racine du dépôt> --sandbox workspace-write -c "approval_policy=\"never\""
```

Les `run_astra*.ps1` sous `samples/` envoient déjà la formulation de cette page,
puis un packet d'audit historique (#4, #8, #9, #10). Ce ne sont pas le backlog
courant. Astra ne commit pas, ne pousse pas, ne rebase pas, ne reconstruit pas l'exe.
