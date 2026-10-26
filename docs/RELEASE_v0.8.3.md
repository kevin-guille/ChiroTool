# ChiroTool v0.8.3 : lot, métadonnées, carte

Non publiée. Le tag v0.8.3 n'est pas créé. Le contenu est repris
dans [v0.8.4](RELEASE_v0.8.4.md).

Pré-release locale du 2026-10-18. À cette date, la Latest était la
[v0.8.1](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.1).
La Latest est maintenant la
[v0.8.5](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.5).

`ChiroTool.exe`, 37463806 octets, SHA-256
`15AE87D81D04FF7F29116878625EF0C935E397194127E7FCA03AB4A0CBB80D33`.

On remplace l'exe. Dossiers, registre (schéma 3), Suivi, WAV et
participations déjà créées restent. L'exe 0.8.2 n'a pas ces gardes.

- Un fichier déjà nommé Pass2 n'est plus réécrit Pass1. Le passage
  n'est plus pré-coché à 1. Sans passage choisi, ou repris du Suivi,
  le lot ignore la nuit. Le journal nomme chaque nuit ignorée.
- Un `Data_k` vide n'est plus un envoi réussi. Aucune participation
  n'est créée. Une préparation qui laisse le `Data_k` vide n'est pas
  un succès non plus.
- Un jeton expiré arrête le lot. Les fichiers pas encore partis ne
  partent pas. Les nuits suivantes ne démarrent pas.
- La fenêtre de suivi ne bloque plus les autres nuits. Une seule
  instance. Les nuits cochées restent prises jusqu'à la fermeture
  de cette fenêtre.
- Métadonnées : heure de début, heure de fin, deux températures,
  vent, couverture. Re-deviner relit le log ou le Summary pour les
  heures et les températures. Le vent saisi reste. Le lot envoie ces
  valeurs sans ouvrir de formulaire. Deux nuits déjà renseignées
  restent distinctes.
- Carte : un carré créé par quelqu'un d'autre apparaît s'il porte une
  de mes participations, ou s'il est déjà mémorisé. Ces points sont
  violets, cliquables dans les 5 km. Les miens restent verts.

Le saut de comparaison des WAV, quand le portail dit la nuit déjà
analysée, reste dans Vérifier / Réparer. Il n'est pas dans l'envoi
groupé. Pas de seuil de confiance sur l'onglet Activité.

Pour ce type d'analyse, se reporter à ChiroSurf.
La relecture d'un `_Vu` ne change pas.
