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

## Proposer du code

1. *Forkez* le dépôt et créez une branche (`git checkout -b fix/mon-correctif`).
2. Gardez les changements ciblés et commentés (le code est en français).
3. Vérifiez que les tests passent : `python -m pytest`.
4. Ouvrez une *pull request* en expliquant le pourquoi du changement.

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
