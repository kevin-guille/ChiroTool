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

- Stable publiée : tag GitHub Latest `v0.8.1` (exe du 2026-09-19,
  SHA-256 `14C620BC40BC1E2DB9059653B6830E5B107A1726DCF0107DB3D16BD4123B19AE`).
- Pré-release publiée le 2026-09-24 : tag `v0.8.2`, pas Latest.
  Asset `ChiroTool.exe`, 37465004 octets, SHA-256
  `5106C7F58CFE1741962454FF1EC1F218B123805328EC65002567E44BD5AB7CEB`.
  `origin/main` est `a140a94`. Le tag `v0.8.2` pointe sur `a767aef`
  (trois commits plus tôt : `924cbe2`, `f1d4e2c`, `a140a94`, scan et pastille).
  L'exe publié correspond à `a140a94`, pas à l'arbre du tag.
  Ne pas déplacer ce tag sans demande explicite.
- Release stable locale **0.8.5** (build 2026-10-26), prévue en Latest,
  pas en pré-release. `version.py` = `0.8.5`. Les builds 0.8.3 et 0.8.4
  ne sont pas publiés. Le tag GitHub `v0.8.5` et l'asset ne sont pas
  publiés tant que Kevin ne le demande pas. Latest publiée reste
  `v0.8.1`. L'asset publié reste celui de la 0.8.2 tant que cette
  release n'est pas créée.
  Ce binaire reprend le contenu prévu pour la 0.8.3 et la 0.8.4
  (journal des nuits ignorées, `Data_k` vide en erreur, heures et
  météo, points violets, sync API, tableur de validation, export vers
  un autre compte) plus le seuil « Confiance min. » de l'onglet Activité
  (#12) et le raccourci TERMINE / FINI dans l'envoi groupé (#14).
  L'exe local 0.8.4 du 2026-10-22 (37469168 octets, SHA-256
  `EA70113C659FE8A5A8955BB278FFF59F3F71D18D09BC76C416F6FC010FF96A15`)
  n'est plus le binaire courant. L'exe 0.8.3 du 2026-10-18
  (37463806 octets, SHA-256
  `15AE87D81D04FF7F29116878625EF0C935E397194127E7FCA03AB4A0CBB80D33`)
  non plus. L'exe local 0.8.5 du 2026-10-26 fait 37471903 octets,
  FileVersion 0.8.5.0, SHA-256
  `5653D4FC53D646820AF8B378A2A44BFFAC45C9999B627BA37852068C6E414B4B`.
- Un `Data_k` déjà rempli n'est plus « incomplet » s'il manque des
  tranches de 5 s. Ne pas rétablir ce contrôle sur la pastille, Upload,
  Vérifier / Réparer ou Valider. Une nuit dont le manifest a `renamed`
  et `te10_done` n'est pas retraitée.
- Remplacer l'exe ne migre pas les dossiers déjà en cours. Schéma du
  registre : version 3, inchangé depuis 0.8.1. `feed_from_scan` met à jour
  les pastilles. Il ne réécrit pas l'identifiant de participation, l'état
  portail ni le compteur d'identifications. L'historique live ne touche
  pas le registre.
- Vérifier `git status`, `origin/main` et le tag avant d'affirmer qu'un
  correctif est dans l'exe publié. Le tag et l'asset peuvent diverger.
- Ne pas pousser, taguer, publier une release, ni reconstruire l'exe
  sans demande explicite de Kevin. C'est lui qui lance `git push`.
- Ne pas réécrire l'historique.
- Ne pas committer `samples/issue4_mickael/`, `samples/issue8_mickael/`,
  `samples/issue9_10/` (journaux terrain, packets d'audit).
- Tests : `python -m pytest tests/ -q`.

## Issues (ne pas relire le premier message comme un backlog)

Déjà tranché dans la SPEC : #4 §0.1, #7 §0.2, #8 §0.3, #9 et #10 §0.4.
#8, #9 et #10 sont fermées. #11 est fermée depuis le 2026-10-08 (§0.5).

Relues le 2026-10-18. #12 et #13 sont confirmées par Benjamin
sur l'exe 0.8.2. Le seuil de confiance demandé ensuite est dans l'exe
local 0.8.5. #13 reste ouverte, comme il l'a demandé. Aucune n'oppose
le cadre ChiroSurf.

| Issue | Sujet | Piste |
|---|---|---|
| #12 | Seuil de confiance sur l'onglet Activité, données non validées. | Dans l'exe local 0.8.5, pas encore publié. Menu « Confiance min. ». Les lignes déjà identifiées restent. « Interprétation _Vu » ignore ce menu et ne change pas de calcul. | 
| #14 | Vérifier / Réparer listait tous les WAV sur une nuit déjà analysée. Le correctif 0.8.2 est validé. Suite : un lot de 40 à 50 nuits, jeton expiré en cours d'envoi. | L'envoi groupé de l'exe local 0.8.5 saute aussi le listing si l'état est TERMINE ou FINI. Un jeton mort arrête le lot. Les nuits suivantes ne sont pas lancées. |
| #15 | Heures, températures et météo avant l'envoi groupé. | Dans l'exe local 0.8.5, pas dans l'exe publié 0.8.2. Les 0.8.3 et 0.8.4 ne sont pas publiées. Le formulaire de métadonnées porte les heures, les températures, le vent et la couverture. Re-deviner relit le log sans effacer le vent saisi. L'envoi groupé envoie ces valeurs sans ouvrir de formulaire et sans lister les WAV. Chaque nuit déjà renseignée garde son carré, son point et ses conditions. |
| #16 | Pastille verte, participation absente du portail (carré 430827, 12 août 2026). | La pastille lit le disque. Un `Data_k` vide n'est plus un envoi réussi. Ne pas relancer cette nuit. |
| #17 | Plusieurs exe pendant un upload de plusieurs jours. | **Non.** D14, une instance. Le suivi de lot ne prend pas les clics : les autres nuits restent consultables. |
| #18 | Trente nuits d'un contrat renommées Pass1, le CSV Tadarida dit Pass2. | Si les WAV ont déjà un `PassN` différent de la méta, aucun fichier n'est renommé. |
| #19 | La carte ne montre pas les points des carrés créés par quelqu'un d'autre. | Dans l'exe local 0.8.5, pas dans l'exe publié 0.8.2. Les 0.8.3 et 0.8.4 ne sont pas publiées. La carte affiche les carrés où j'ai une participation, même si quelqu'un d'autre a créé le carré. En choix de point, ces points restent cliquables dans les 5 km. |

Batch Préparer (SPEC §0.6, pas d'issue GitHub, exe 0.8.2) : une nuit
ignorée n'est pas un succès. Log Titley : pas de listing WAV, horaire
du log conservé même si le Suivi a une autre nuit pour la même série.
Suivi ouvert une fois. Nuit déjà renommée et expansée : non retraitée,
comptée OK. Erreur de lecture du manifest ou du Suivi : `chirotool.log`.

## Gardes (lot, et agents)

Un lot n'a pas de formulaire. Une garde qui échoue est un refus, pas un
succès : passage déjà écrit dans les noms et différent de la méta,
`Data_k` vide, jeton Vigie-Chiro expiré. Une exception pendant le listing
des fichiers du portail n'est pas une liste vide, et elle n'autorise pas
à marquer la nuit envoyée.

Le formulaire de métadonnées porte les heures et la météo. Le lot ne
l'ouvre pas : il reprend ce qui est enregistré, le log ou le Summary,
sans lister les WAV. Une heure vide n'est pas remplacée par 20:00 dans
le cache. Chaque nuit déjà renseignée garde son carré, son point et ses
conditions. Le dernier point créé ne remplit une nuit que si le carré
ou le point manque encore, et seulement à l'ouverture du formulaire.
Le tutoriel le dit dans « Nouveautés v0.8.5 », et le parcours
étape par étape décrit cet exe.

Le formulaire de métadonnées ne pré-coche plus le passage 1. Tant que le
passage n'est pas choisi, ou repris du Suivi, le lot ignore la nuit.
Le journal nomme chaque nuit ignorée. Une préparation qui laisse
`Data_k` sans WAV est une erreur, pas un succès.

La pastille verte reste lue sur le disque. Ne pas la faire dépendre d'un
appel portail à chaque scan. Ne pas rétablir le contrôle « tranches de
5 s manquantes ».

Une seule instance. Pendant un lot, la fenêtre de suivi reste ouverte
sans bloquer la fenêtre principale. Une nuit déjà dans ce lot ne se
relance pas. Les autres nuits (activité, validation, synthèse, autre
dossier) restent utilisables.

## Gardes (sync, tableur, export)

Dans l'exe 0.8.5. SPEC §0.9. Les 0.8.3 et 0.8.4 ne sont pas publiées.
Ne pas les retirer du tutoriel, du PDF ou de la note 0.8.5.

Sync API (`gui_registry.SyncPreviewDialog`, `registry.sync_from_api`) :
le fil réseau n'appelle pas Tk. Le compteur est un entier lu sur le
fil de l'interface, toutes les 200 ms. Pages de 99. Fermer la fenêtre
annule sans écrire. Appliquer appelle `apply_sync_result` sur le diff
déjà affiché. Une participation seulement sur le portail garde
`vigiechiro_participation_id` et `api_etat`. Un scan local ne les efface
pas.

Tableur de validation (`gui_validation._save`) : un enregistrement
réécrit `participation-<id>-observations_<initiales>.xlsx`. Les
initiales se retirent après le marqueur `-observations`, pas dans
l'identifiant. Une chaîne à deux suffixes ou plus est retirée après
cet enregistrement s'il existe un tableur plus simple. Le téléchargement
et une copie à un seul suffixe restent. Vérifier / Réparer écrit le
nom canonique et n'ajoute pas de copie si un tableur est déjà là.
Ne pas rétablir l'empilement. Ne pas effacer ces fichiers au scan.

Export (`export_sessions`, `pipeline.run_phase_upload`) : le manifeste
est copié tel quel. Ne pas retirer `vigiechiro_participation_id` à
l'export. À l'envoi, 403, 404 ou un autre observateur : écarter
l'identifiant et créer la participation sur le compte qui envoie.
Réseau illisible ou jeton expiré : garder l'identifiant. Sans
identifiant dans le manifeste, ce contrôle ne change rien.

Ne pas installer un harness tiers. Ne pas modifier les profils Grok Bot.
Ne pas répondre au widget t6s6. Pas de nouvel agent.
Dernier brief SuperBot lisible : 26 octobre 2026 (t11s1).
Ces briefs servent à ces gardes, pas à élargir une flotte de bots.
La piste du 12 octobre (l'approbation se reverrouille) est morte
depuis le 19 octobre (t9s2). Une garde qui échoue reste un refus.
Le dépôt harness 1.0 (25 octobre) n'est plus une référence à suivre.
La ligne SRID du 22 octobre (t11s0) et les cartes brouillon de la
v0.75.5 visent d'autres dossiers, pas celui-ci.

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
