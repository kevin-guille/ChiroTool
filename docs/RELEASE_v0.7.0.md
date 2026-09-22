# ChiroTool v0.7.0 : Synthèse par nuit, Titley, ChiroSurf optionnel

ChiroTool prépare, envoie et suit les enregistrements Vigie-Chiro Point
Fixe, du dossier brut jusqu'au tableur Tadarida, dans une application libre.
La validation Vigie-Chiro se fait dans ChiroSurf.

## ✨ La nouveauté de cette version

La **v0.7** répond aux issues
[#4](https://github.com/kevin-guille/ChiroTool/issues/4) (Titley, Valider),
[#5](https://github.com/kevin-guille/ChiroTool/issues/5) (démarrage) et
[#6](https://github.com/kevin-guille/ChiroTool/issues/6) (WAC).

**📊 Synthèse** est le récapitulatif ChiroTool (niveaux d'activité, choix
de nuit). **🌊 ChiroSurf nuits** prépare un CSV pour ceux qui valident
dans ChiroSurf. ChiroTool ne fait pas cette validation.

## 🧰 Ce qui arrive avec cette version

- **Synthèse** : sélecteur de nuit biologique (coupure midi) ; un `_Vu`
  déjà produit peut être lu ; ChiroSurf n'est pas requis pour ce récap
- **ChiroSurf nuits** : ouvrir le CSV brut dans ChiroSurf, rouvrir un `_Vu`.
  Optionnel. La validation se fait dans ChiroSurf.
- **Titley** Anabat Swift / Ranger (noms usine `YYYY-MM-DD HH-MM-SS`)
- **Valider** : tri des colonnes, filtres observateur / chiros, bilan `X / Y`
- **Démarrage** : plus de scan auto du dernier dossier (SSD EXFAT)
- **Dates** : si Summary ≠ WAV, les fichiers font foi
- **SM2 / `.wac`** : conversion Kaleidoscope Lite en amont, puis Préparer

## 📦 Installation

Téléchargez `ChiroTool.exe` ci-dessous. Application portable, aucune installation
(Windows).

Tutoriel : [https://kevin-guille.github.io/ChiroTool/](https://kevin-guille.github.io/ChiroTool/)

Changelog : [CHANGELOG.md](https://github.com/kevin-guille/ChiroTool/blob/main/CHANGELOG.md)

## ⚠️ Avertissement

Outil indépendant, compatible avec le protocole Vigie-Chiro Point Fixe via son
API publique. Ce n'est pas un outil officiel du MNHN.

---

SHA-256 (`ChiroTool.exe`) : `EC9345293BE7D6D5E8C845FE40525BECBC2FDA8CE13EA44541DB035C740B679E`
