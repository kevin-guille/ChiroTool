# chirotool_fast — extension Rust de ChiroTool

Accélère les opérations IO-lourdes (TE×10 + split 5s) via une implémentation
Rust parallélisée avec Rayon et memory-mapping des WAV.

## Gains attendus — **le type de disque compte énormément**

Les gains Rust ne se matérialisent que si **le CPU est le goulot**. Dans le
cas de ChiroTool (copie de bytes WAV avec juste un header modifié), le CPU
ne fait quasi rien — le disque est le vrai bottleneck.

### Sur **NVMe local** (M.2 PCIe 4.0, 3000+ MB/s)

| Dataset | Python | Rust (4 threads) | Rust (16 threads) |
|---|---|---|---|
| Nuit test (15 GB, 4631 segments) | ~50 s | ~15 s | ~5 s |

Le parallélisme paie car le SSD supporte 16 flux simultanés.

### Sur **SSD externe USB** (Samsung T9, clé USB, etc.)

| Dataset | Python | Rust (4 threads) | Rust (16 threads) |
|---|---|---|---|
| Nuit test sur SSD externe | ~15 min | ~10-12 min | ~18 min (!) |

Le contrôleur USB + le firmware du SSD externe n'aiment pas les 16 flux
parallèles — le débit chute par thrashing. Python séquentiel fait parfois
mieux. **Le défaut est 4 threads** pour éviter ce piège.

### Sur **HDD mécanique**

Aucun parallélisme n'aide. Rust ≈ Python. Les deux sont bornés par la
vitesse mécanique des têtes de lecture (~150 MB/s).

## Recommandation pratique

- **Stockage transitoire terrain** (clé USB, T9, HDD externe) : le gain Rust
  est marginal voire négatif. Python fait très bien le job.
- **Stockage bureau** (NVMe interne) : Rust donne un gain réel, ×3-10 selon
  la machine. C'est là que ça vaut le coup.
- **Pour de gros traitements batch** (350 nuits d'un coup) : copier depuis
  le disque terrain sur NVMe local, lancer Rust, renvoyer les résultats.

## Ce que fait l'extension

- Parse minimal RIFF/WAVE (fmt + data chunks)
- **Copie raw** des octets de samples PCM (pas de décodage/encodage)
- Header de sortie recalculé (sample_rate ÷ factor)
- **Memory-mapping** du fichier source (zéro copie en lecture)
- **Rayon** : 1 thread par fichier source, répartition auto sur les cœurs
- Écriture atomique (tmp + rename)
- **Équivalence bit-à-bit** avec la version Python existante (et Kaleidoscope)

## Build (développeur)

### 1. Installer le toolchain Rust

**Windows** (option recommandée) :

```powershell
# Installer rustup (gestionnaire officiel)
winget install Rustlang.Rustup
# Puis ouvrir un nouveau terminal et :
rustup default stable
```

Alternative : télécharger https://rustup.rs/ et suivre.

### 2. Installer maturin (builder PyO3)

```powershell
python -m pip install maturin
```

### 3. Compiler + installer en mode développement

Depuis le dossier `_tool/rust_ext/` :

```powershell
cd E:\Chiroptere_test\_tool\rust_ext
maturin develop --release
```

- `--release` : optimisations activées (indispensable pour les perfs)
- Cette commande compile le crate et installe le `.pyd` dans le Python courant
- Durée : ~30 s la première fois (pyo3 + rayon à compiler), ~5 s les fois suivantes

### 4. Vérifier l'installation

```powershell
cd E:\Chiroptere_test\_tool
python -c "import chirotool_fast; print(chirotool_fast.__version__)"
```

Puis tester :

```powershell
python te10.py "E:/.../une-session" --dry-run
# La sortie doit afficher "Backend : Rust (chirotool_fast v0.1.0)"
```

## Build pour distribution

Pour produire un wheel (`.whl`) distribuable :

```powershell
maturin build --release
# Le .whl atterrit dans ./target/wheels/
pip install target/wheels/chirotool_fast-*.whl
```

## Benchmark comparatif

```powershell
cd chemin/vers/ChiroTool

# Rust (défaut si compilé)
Measure-Command { python te10.py "D:/Chiros/MonContrat/MaNuit" "D:/tmp/out_rust" --overwrite }

# Python pur (pour comparaison)
Measure-Command { python te10.py "D:/Chiros/MonContrat/MaNuit" "D:/tmp/out_py" --overwrite --force-python }
```

## Organisation du code

```
rust_ext/
├── Cargo.toml         # manifest Rust + dépendances (pyo3, rayon, memmap2)
├── pyproject.toml     # manifest Python (maturin comme backend de build)
├── src/
│   └── lib.rs         # tout le code Rust (WAV parser + timestamp shift + process)
└── README.md          # ce fichier
```

## Extensions futures envisageables

- `scan_dir(root)` : walk parallèle + lecture header WAV (pour workspaces avec 100 000+ fichiers)
- `verify_cleanup(session)` : parsing xlsx rapide via `calamine`
- Support `.w4v` (décompression Wildlife Acoustics)

## Fallback automatique

Si `chirotool_fast` n'est pas installé, `te10.py` utilise sa version Python pure.
Aucune action requise — le moteur reste 100 % fonctionnel sans Rust.

Pour forcer le fallback Python (benchmarks, debug) :

```powershell
python te10.py <session> --force-python
```
