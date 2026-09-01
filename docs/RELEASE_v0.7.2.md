# ChiroTool v0.7.2 : nuit biologique + barre d'actions

Release courante. Inclut le correctif ChiroSurf de la
[#7](https://github.com/kevin-guille/ChiroTool/issues/7) (pre-release 0.7.1)
plus les retours de test.

## 🔧 Corrections (depuis 0.7.0)

- **▶ ChiroSurf** : le CSV nuit est copié à côté des WAV (`Data_k/`) avant
  ouverture (évite le plantage Tcl *no files matched glob pattern*).
- **`_Vu` hors ChiroTool** : `Nuit1_…`, `Nuit_1_…` et `Nuit_1-…` reconnus.
- **Barre d'actions** : une seule ligne ; glissement vers la droite si l'écran
  est étroit (molette ou curseur). Dans **ChiroSurf nuits**, ▶ / 📈 / Synthèse
  sont sous le libellé.
- **Nuit biologique** : une pose **21 h → 6 h** = **une** nuit (coupure à
  **midi**, jamais à minuit). Le menu Nuit n'apparaît que s'il y a **plusieurs
  soirs**. Deux soirs réels restent deux nuits.

## 📦 Installation

Téléchargez `ChiroTool.exe` ci-dessous (portable, Windows). Remplacez
l'exe 0.7.0 / 0.7.1 : les sessions déjà préparées sont conservées.

Tutoriel : [https://kevin-guille.github.io/ChiroTool/](https://kevin-guille.github.io/ChiroTool/)

## ⚠️ Avertissement

Outil indépendant, compatible avec le protocole Vigie-Chiro Point Fixe via son
API publique. Ce n'est pas un outil officiel du MNHN.

---

SHA-256 (`ChiroTool.exe`) : `5972A88B6969075C11492182A2F2C8E863724EAC16BCB9A67398C4AAA97DD3BD`
