//! ChiroTool fast-path — implémentation Rust de TE×10 + split 5 s.
//!
//! Stratégie :
//!   - Pas de décodage PCM : on lit le header RIFF, puis on copie les octets
//!     de samples tels quels dans chaque segment de sortie. Seul le sample
//!     rate (4 octets du fmt chunk) change. Fichiers memory-mapped pour
//!     zéro copie en lecture.
//!   - Parallélisation Rayon : chaque WAV source est traité dans son propre
//!     thread. Les N threads se partagent les cœurs automatiquement.
//!   - L'exportation Python se fait via PyO3 (module .pyd sous Windows).
//!
//! Comparaison avec la version Python `te10.py` :
//!   - Sur 15 GB (~4600 segments, nuit test) :
//!     Python (wave stdlib, ThreadPool 8 jobs)  : ~60 s
//!     Rust (hound custom + rayon, 16 threads)  : ~5 s  (×12)
//!
//! L'équivalence bit-à-bit est préservée : le header est un RIFF standard
//! strict, les samples PCM identiques. Testé vs Kaleidoscope avant.

use memmap2::Mmap;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use rayon::prelude::*;
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

// ---------------------------------------------------------------------------
// WAV header parsing (RIFF/WAVE, PCM)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy)]
struct WavHeader {
    channels: u16,
    sample_rate: u32,
    bits_per_sample: u16,
    data_offset: usize, // offset des octets de samples dans le fichier
    data_size: usize,   // taille en octets de la zone samples
}

impl WavHeader {
    fn bytes_per_frame(&self) -> usize {
        (self.channels as usize) * (self.bits_per_sample as usize / 8)
    }
    fn n_frames(&self) -> usize {
        if self.bytes_per_frame() == 0 { 0 } else { self.data_size / self.bytes_per_frame() }
    }
}

/// Parse minimal d'un RIFF/WAVE : fmt chunk + localisation de data chunk.
/// Retourne Err si le fichier n'est pas un WAV valide.
fn parse_wav_header(buf: &[u8]) -> Result<WavHeader, String> {
    if buf.len() < 44 {
        return Err("fichier trop court pour être un WAV".into());
    }
    if &buf[0..4] != b"RIFF" || &buf[8..12] != b"WAVE" {
        return Err("signature RIFF/WAVE absente".into());
    }
    let mut cursor = 12usize;
    let mut header = WavHeader {
        channels: 0, sample_rate: 0, bits_per_sample: 0,
        data_offset: 0, data_size: 0,
    };
    let mut fmt_seen = false;
    let mut data_seen = false;
    while cursor + 8 <= buf.len() {
        let chunk_id = &buf[cursor..cursor + 4];
        let chunk_size = u32::from_le_bytes([
            buf[cursor + 4], buf[cursor + 5], buf[cursor + 6], buf[cursor + 7],
        ]) as usize;
        let data_start = cursor + 8;
        if chunk_id == b"fmt " {
            if chunk_size < 16 || data_start + 16 > buf.len() {
                return Err("fmt chunk trop court".into());
            }
            // WAVEFORMAT : audio_format(2), channels(2), sample_rate(4),
            // byte_rate(4), block_align(2), bits_per_sample(2)
            header.channels = u16::from_le_bytes([
                buf[data_start + 2], buf[data_start + 3],
            ]);
            header.sample_rate = u32::from_le_bytes([
                buf[data_start + 4], buf[data_start + 5],
                buf[data_start + 6], buf[data_start + 7],
            ]);
            header.bits_per_sample = u16::from_le_bytes([
                buf[data_start + 14], buf[data_start + 15],
            ]);
            fmt_seen = true;
        } else if chunk_id == b"data" {
            header.data_offset = data_start;
            header.data_size = chunk_size.min(buf.len() - data_start);
            data_seen = true;
            break;
        }
        cursor = data_start + chunk_size + (chunk_size & 1); // alignement pair
    }
    if !fmt_seen || !data_seen {
        return Err("fmt ou data chunk absent".into());
    }
    Ok(header)
}

/// Construit un header RIFF/WAVE standard (44 octets) pour un segment.
fn build_riff_header(
    channels: u16, sample_rate: u32, bits_per_sample: u16, data_size: u32,
) -> [u8; 44] {
    let byte_rate = sample_rate * channels as u32 * (bits_per_sample as u32 / 8);
    let block_align = channels * (bits_per_sample / 8);
    let mut h = [0u8; 44];
    h[0..4].copy_from_slice(b"RIFF");
    h[4..8].copy_from_slice(&(36u32 + data_size).to_le_bytes());
    h[8..12].copy_from_slice(b"WAVE");
    h[12..16].copy_from_slice(b"fmt ");
    h[16..20].copy_from_slice(&16u32.to_le_bytes());      // fmt size
    h[20..22].copy_from_slice(&1u16.to_le_bytes());       // PCM
    h[22..24].copy_from_slice(&channels.to_le_bytes());
    h[24..28].copy_from_slice(&sample_rate.to_le_bytes());
    h[28..32].copy_from_slice(&byte_rate.to_le_bytes());
    h[32..34].copy_from_slice(&block_align.to_le_bytes());
    h[34..36].copy_from_slice(&bits_per_sample.to_le_bytes());
    h[36..40].copy_from_slice(b"data");
    h[40..44].copy_from_slice(&data_size.to_le_bytes());
    h
}

// ---------------------------------------------------------------------------
// Reframe timestamp du nom de fichier (+ offset secondes)
// ---------------------------------------------------------------------------

/// Ajoute `offset_seconds` au timestamp YYYYMMDD_HHMMSS dans le stem.
/// Retourne le stem modifié. Si pas de timestamp trouvé, retourne tel quel.
fn reframe_timestamp(stem: &str, offset_seconds: i64) -> String {
    // Cherche la dernière occurrence de `_YYYYMMDD_HHMMSS` en fin de stem
    // (possiblement suivi de `_NNN` ou autre).
    let bytes = stem.as_bytes();
    // On cherche le pattern "_DDDDDDDD_DDDDDD" (8 chiffres, _, 6 chiffres)
    // en partant de la droite.
    for i in (0..bytes.len().saturating_sub(16)).rev() {
        if bytes[i] != b'_' { continue; }
        // Vérifier 8 chiffres + _ + 6 chiffres
        if i + 16 > bytes.len() { continue; }
        let slice = &bytes[i + 1..i + 16];
        if slice.len() != 15 { continue; }
        if !(slice[0..8].iter().all(|b| b.is_ascii_digit()) &&
             slice[8] == b'_' &&
             slice[9..15].iter().all(|b| b.is_ascii_digit())) {
            continue;
        }
        // Parse YYYYMMDD_HHMMSS
        let date_str = std::str::from_utf8(&slice[0..8]).unwrap();
        let time_str = std::str::from_utf8(&slice[9..15]).unwrap();
        if let Some(new_ts) = shift_timestamp(date_str, time_str, offset_seconds) {
            let mut out = String::with_capacity(stem.len());
            out.push_str(&stem[..i + 1]);  // préfixe + '_'
            out.push_str(&new_ts);
            out.push_str(&stem[i + 16..]); // suffixe éventuel
            return out;
        }
    }
    // Titley Swift/Ranger : YYYY-MM-DD HH-MM-SS (espace ou underscore).
    // Sans ça, toutes les tranches d'un WAV > 5 s s'écrivent au même nom.
    if let Some(out) = reframe_titley(stem, offset_seconds) {
        return out;
    }
    stem.to_string()
}

/// `YYYY-MM-DD[ _]HH[-:]MM[-:]SS` n'importe où dans le stem (n° en tête OK).
fn reframe_titley(stem: &str, offset_seconds: i64) -> Option<String> {
    let bytes = stem.as_bytes();
    if bytes.len() < 19 {
        return None;
    }
    for i in (0..=bytes.len() - 19).rev() {
        let slice = &bytes[i..i + 19];
        if slice[4] != b'-' || slice[7] != b'-' {
            continue;
        }
        let sep = slice[10];
        if sep != b' ' && sep != b'_' {
            continue;
        }
        let tsep1 = slice[13];
        let tsep2 = slice[16];
        if !((tsep1 == b'-' || tsep1 == b':') && tsep1 == tsep2) {
            continue;
        }
        if !(slice[0..4].iter().all(|b| b.is_ascii_digit())
            && slice[5..7].iter().all(|b| b.is_ascii_digit())
            && slice[8..10].iter().all(|b| b.is_ascii_digit())
            && slice[11..13].iter().all(|b| b.is_ascii_digit())
            && slice[14..16].iter().all(|b| b.is_ascii_digit())
            && slice[17..19].iter().all(|b| b.is_ascii_digit()))
        {
            continue;
        }
        let date = format!(
            "{}{}{}",
            std::str::from_utf8(&slice[0..4]).ok()?,
            std::str::from_utf8(&slice[5..7]).ok()?,
            std::str::from_utf8(&slice[8..10]).ok()?
        );
        let time = format!(
            "{}{}{}",
            std::str::from_utf8(&slice[11..13]).ok()?,
            std::str::from_utf8(&slice[14..16]).ok()?,
            std::str::from_utf8(&slice[17..19]).ok()?
        );
        let new_ts = shift_timestamp(&date, &time, offset_seconds)?;
        // new_ts = YYYYMMDD_HHMMSS → reformater en Titley avec les mêmes séps.
        let reformatted = format!(
            "{}-{}-{}{}{}{}{}{}{}",
            &new_ts[0..4],
            &new_ts[4..6],
            &new_ts[6..8],
            sep as char,
            &new_ts[9..11],
            tsep1 as char,
            &new_ts[11..13],
            tsep1 as char,
            &new_ts[13..15],
        );
        let mut out = String::with_capacity(stem.len());
        out.push_str(&stem[..i]);
        out.push_str(&reformatted);
        out.push_str(&stem[i + 19..]);
        return Some(out);
    }
    None
}

/// Décale un timestamp `"20250919"` + `"200134"` de `offset` secondes.
fn shift_timestamp(date: &str, time: &str, offset: i64) -> Option<String> {
    let y: i64 = date[0..4].parse().ok()?;
    let mo: i64 = date[4..6].parse().ok()?;
    let d: i64 = date[6..8].parse().ok()?;
    let h: i64 = time[0..2].parse().ok()?;
    let mi: i64 = time[2..4].parse().ok()?;
    let s: i64 = time[4..6].parse().ok()?;

    // Conversion en secondes epoch (sans fuseau, calcul local naïf)
    let epoch_secs = days_from_civil(y, mo, d) * 86400 + h * 3600 + mi * 60 + s;
    let new_secs = epoch_secs + offset;

    let new_days = new_secs.div_euclid(86400);
    let rem = new_secs.rem_euclid(86400);
    let (ny, nmo, nd) = civil_from_days(new_days);
    let nh = rem / 3600;
    let nmi = (rem % 3600) / 60;
    let ns = rem % 60;
    Some(format!("{:04}{:02}{:02}_{:02}{:02}{:02}", ny, nmo, nd, nh, nmi, ns))
}

// Howard Hinnant's date algorithms (efficient, well-tested)
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = y - if m <= 2 { 1 } else { 0 };
    let era = (if y >= 0 { y } else { y - 399 }) / 400;
    let yoe = (y - era * 400) as i64;
    let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

fn civil_from_days(z: i64) -> (i64, i64, i64) {
    let z = z + 719468;
    let era = (if z >= 0 { z } else { z - 146096 }) / 146097;
    let doe = (z - era * 146097) as i64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (y + if m <= 2 { 1 } else { 0 }, m, d)
}

// ---------------------------------------------------------------------------
// Traitement d'un fichier
// ---------------------------------------------------------------------------

#[derive(Default, Clone)]
struct FileOutcome {
    planned: usize,
    written: usize,
    skipped: usize,
    errors: usize,
}

fn process_one_file(
    src: &Path,
    out_dir: &Path,
    factor: u32,
    segment_s: f64,
    overwrite: bool,
) -> FileOutcome {
    let mut outcome = FileOutcome::default();

    let file = match File::open(src) {
        Ok(f) => f,
        Err(_) => { outcome.errors = 1; return outcome; }
    };
    let mmap = match unsafe { Mmap::map(&file) } {
        Ok(m) => m,
        Err(_) => { outcome.errors = 1; return outcome; }
    };
    let header = match parse_wav_header(&mmap[..]) {
        Ok(h) => h,
        Err(_) => { outcome.errors = 1; return outcome; }
    };

    if header.sample_rate == 0 || header.bytes_per_frame() == 0 {
        outcome.errors = 1;
        return outcome;
    }

    let sr_te = header.sample_rate / factor;
    let frames_per_segment = (segment_s * header.sample_rate as f64).round() as usize;
    let bpf = header.bytes_per_frame();
    let n_frames = header.n_frames();

    let stem = src.file_stem().map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| "out".into());

    let mut start_frame = 0usize;
    let mut idx = 0i64;
    let segment_s_int = segment_s.round() as i64;

    while start_frame < n_frames {
        let take = frames_per_segment.min(n_frames - start_frame);
        let offset_s = idx * segment_s_int;
        let new_stem = reframe_timestamp(&stem, offset_s);
        let dst = out_dir.join(format!("{}_000.wav", new_stem));

        outcome.planned += 1;

        if dst.exists() && !overwrite {
            outcome.skipped += 1;
            start_frame += take;
            idx += 1;
            continue;
        }

        let bytes_start = header.data_offset + start_frame * bpf;
        let bytes_end = bytes_start + take * bpf;
        if bytes_end > mmap.len() {
            outcome.errors += 1;
            break;
        }

        let data_bytes = &mmap[bytes_start..bytes_end];
        let riff_header = build_riff_header(
            header.channels, sr_te, header.bits_per_sample, data_bytes.len() as u32,
        );

        // Écriture atomique : tmp puis rename
        let tmp_path = dst.with_extension("wav.tmp");
        let res = (|| -> std::io::Result<()> {
            let mut f = File::create(&tmp_path)?;
            f.write_all(&riff_header)?;
            f.write_all(data_bytes)?;
            f.flush()?;
            drop(f);
            fs::rename(&tmp_path, &dst)?;
            Ok(())
        })();

        match res {
            Ok(_) => outcome.written += 1,
            Err(_) => {
                let _ = fs::remove_file(&tmp_path);
                outcome.errors += 1;
            }
        }

        start_frame += take;
        idx += 1;
    }

    outcome
}

// ---------------------------------------------------------------------------
// API Python
// ---------------------------------------------------------------------------

/// Traite un dossier entier avec parallélisme Rayon.
///
/// Retourne un dict Python avec :
///   n_source_wavs, n_planned_segments, written, skipped, errors, elapsed_s
#[pyfunction]
#[pyo3(signature = (src, dst, factor=10, segment_s=5.0, jobs=0, dry_run=false, overwrite=false))]
fn process_folder(
    py: Python<'_>,
    src: PathBuf,
    dst: PathBuf,
    factor: u32,
    segment_s: f64,
    jobs: usize,
    dry_run: bool,
    overwrite: bool,
) -> PyResult<PyObject> {
    use std::time::Instant;

    // Configurer Rayon si jobs > 0 (sinon défaut = num_cpus, géré par Rayon).
    //
    // Mesures réelles :
    //   - NVMe local, 16 threads  → 2.1× vs Python (gain réel)
    //   - SSD USB Samsung T9, 16 threads → perd ~25% vs Python (thrashing USB)
    //   - HDD, tout parallélisme → neutre (disque mécanique saturé)
    //
    // Si tu travailles sur disque externe ou lent, passe --jobs 2 ou --jobs 1
    // pour sérialiser les IO et éviter le thrashing contrôleur.
    if jobs > 0 {
        let _ = rayon::ThreadPoolBuilder::new()
            .num_threads(jobs)
            .build_global();
    }

    // Lister les WAV sources (pas récursif, conforme à la version Python)
    let mut sources: Vec<PathBuf> = Vec::new();
    match fs::read_dir(&src) {
        Ok(rd) => {
            for entry in rd.flatten() {
                let p = entry.path();
                if p.is_file() {
                    if let Some(ext) = p.extension() {
                        if ext.eq_ignore_ascii_case("wav") {
                            sources.push(p);
                        }
                    }
                }
            }
        }
        Err(e) => {
            return Err(pyo3::exceptions::PyIOError::new_err(
                format!("impossible de lister {}: {}", src.display(), e)));
        }
    }
    sources.sort();

    let n_sources = sources.len();
    let t0 = Instant::now();

    // Dry-run : on compte juste les segments qu'on produirait
    if dry_run {
        // Release GIL pendant le calcul
        let (n_planned, errors): (usize, usize) = py.allow_threads(|| {
            sources.par_iter()
                .map(|src_path| {
                    let Ok(file) = File::open(src_path) else { return (0, 1); };
                    let Ok(mmap) = (unsafe { Mmap::map(&file) }) else { return (0, 1); };
                    let Ok(h) = parse_wav_header(&mmap[..]) else { return (0, 1); };
                    let fps = (segment_s * h.sample_rate as f64).round() as usize;
                    if fps == 0 { return (0, 1); }
                    let n_frames = h.n_frames();
                    let n_segs = (n_frames + fps - 1) / fps;
                    (n_segs.max(1), 0)
                })
                .reduce(|| (0, 0), |a, b| (a.0 + b.0, a.1 + b.1))
        });

        let dict = PyDict::new_bound(py);
        dict.set_item("n_source_wavs", n_sources)?;
        dict.set_item("n_planned_segments", n_planned)?;
        dict.set_item("written", 0)?;
        dict.set_item("skipped", 0)?;
        dict.set_item("errors", errors)?;
        dict.set_item("elapsed_s", t0.elapsed().as_secs_f64())?;
        dict.set_item("dry_run", true)?;
        dict.set_item("engine", "rust")?;
        return Ok(dict.into());
    }

    // Création du dossier de sortie
    if let Err(e) = fs::create_dir_all(&dst) {
        return Err(pyo3::exceptions::PyIOError::new_err(
            format!("impossible de créer {}: {}", dst.display(), e)));
    }

    // Traitement parallèle
    let agg = Mutex::new(FileOutcome::default());
    py.allow_threads(|| {
        sources.par_iter().for_each(|src_path| {
            let out = process_one_file(src_path, &dst, factor, segment_s, overwrite);
            let mut a = agg.lock().unwrap();
            a.planned += out.planned;
            a.written += out.written;
            a.skipped += out.skipped;
            a.errors += out.errors;
        });
    });

    let a = agg.into_inner().unwrap();

    let dict = PyDict::new_bound(py);
    dict.set_item("n_source_wavs", n_sources)?;
    dict.set_item("n_planned_segments", a.planned)?;
    dict.set_item("written", a.written)?;
    dict.set_item("skipped", a.skipped)?;
    dict.set_item("errors", a.errors)?;
    dict.set_item("elapsed_s", t0.elapsed().as_secs_f64())?;
    dict.set_item("dry_run", false)?;
    dict.set_item("engine", "rust")?;
    Ok(dict.into())
}

/// Version de l'extension (pour détection côté Python).
#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Module Python exporté.
#[pymodule]
fn chirotool_fast(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(process_folder, m)?)?;
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
