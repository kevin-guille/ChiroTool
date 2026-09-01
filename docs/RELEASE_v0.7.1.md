# ChiroTool v0.7.1 (pre-release) : liaison ChiroSurf

> **Remplacée par [v0.7.2](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.7.2)**
> (release courante). Ne plus tester cet exe. Garder cette pre-release pour
> l'historique ; ne pas la supprimer, ne pas la passer en Latest.

Correctif ciblé suite au test terrain de
[#7](https://github.com/kevin-guille/ChiroTool/issues/7) (Benjamin).

## 🔧 Corrections

- **▶ ChiroSurf** : le CSV nuit est copié à côté des WAV (`Data_k/`) avant
  ouverture. ChiroSurf 4.x cherche les sons dans le **même dossier** que le
  tableur ; un CSV isolé dans `chirosurf/` faisait planter le démarrage
  (*no files matched glob pattern*). Sans WAV (nuit déjà nettoyée),
  l'ouverture est refusée avec un message clair.
- **`_Vu` hors ChiroTool** : `Nuit1_…`, `Nuit_1_…` et `Nuit_1-…` sont
  reconnus. Un `_Vu` collé dans `chirosurf/` ou écrit par ChiroSurf dans
  `Data_k/` est listé, rapatrié, et lu par Synthèse / Activité.

## 📦 Installation

Téléchargez `ChiroTool.exe` ci-dessous (portable, Windows). Remplacez
l'exe 0.7.0 : les sessions déjà préparées sont conservées.

Tutoriel : [https://kevin-guille.github.io/ChiroTool/](https://kevin-guille.github.io/ChiroTool/)

## ⚠️ Avertissement

Outil indépendant, compatible avec le protocole Vigie-Chiro Point Fixe via son
API publique. Ce n'est pas un outil officiel du MNHN.

Pre-release : merci de confirmer sur une nuit réelle (▶ ChiroSurf ouvre
sans erreur Tcl, le `_Vu` réapparaît dans ChiroTool après validation).

---

SHA-256 (`ChiroTool.exe`) : `F28B2C6462C9AFAD434F0BC868EBCE73A38EEEE12084A782184E5B7258EA5420`
