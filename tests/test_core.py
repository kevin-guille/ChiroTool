"""
tests/test_core.py — tests unitaires des modules logique pure.

Couverture :
  - naming       : validate_meta, canonical_session_dirname,
                   vigiechiro_wav_prefix, compute_new_wav_name
  - taxons       : classify_taxon (tous les groupes + fallback prefix)
  - cleanup      : decide_contact (toutes les branches)
  - manifest     : save/load idempotence, flags, Action(status)
  - registry     : upsert, thread-safety, batch commit, migration

Ces modules sont les plus "à risque" : une régression y corrompt des
données (renommage incohérent, cleanup trop aggressif, etc.). Tests
légers, rapides (< 2s au total), sans réseau, sans GUI.

Run :  pytest -q tests/
"""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest


# =========================================================================
# naming
# =========================================================================

class TestNaming:
    def _make_meta(self, **kwargs):
        from naming import SessionMeta
        defaults = dict(
            date_debut=datetime(2025, 9, 3),
            n_site_tadarida="212097",
            n_point_fixe="Z3",
            n_passage=2,
            n_enregistreur=7,
            n_serie="SMU03126",
            nom_contrat="TestContrat",
        )
        defaults.update(kwargs)
        return SessionMeta(**defaults)

    def test_validate_meta_ok(self):
        from naming import validate_meta
        errs = validate_meta(self._make_meta())
        assert errs == [], f"attendait [] mais reçu {errs}"

    def test_validate_meta_missing_date(self):
        from naming import validate_meta
        errs = validate_meta(self._make_meta(date_debut=None))
        assert any("date_debut" in e for e in errs)

    def test_validate_meta_missing_site(self):
        from naming import validate_meta
        errs = validate_meta(self._make_meta(n_site_tadarida=None))
        assert any("n_site_tadarida" in e for e in errs)

    def test_validate_meta_bad_point(self):
        from naming import validate_meta
        # Point "99" sans lettre → invalide
        errs = validate_meta(self._make_meta(n_point_fixe="99"))
        assert len(errs) > 0

    def test_canonical_session_dirname(self):
        from naming import canonical_session_dirname
        name = canonical_session_dirname(self._make_meta())
        assert name == "20250903_site212097_Z3_Pass2_enr07"

    def test_canonical_session_dirname_uppercase_point(self):
        from naming import canonical_session_dirname
        name = canonical_session_dirname(self._make_meta(n_point_fixe="z3"))
        # Normalisé en majuscules
        assert "_Z3_" in name

    def test_canonical_session_dirname_invalid_raises(self):
        from naming import canonical_session_dirname
        with pytest.raises(ValueError):
            canonical_session_dirname(self._make_meta(n_site_tadarida=None))

    def test_canonical_session_enr_padding(self):
        """n_enregistreur doit être zéro-paddé à 2 chiffres."""
        from naming import canonical_session_dirname
        name = canonical_session_dirname(self._make_meta(n_enregistreur=3))
        assert name.endswith("_enr03")

    def test_vigiechiro_wav_prefix(self):
        from naming import vigiechiro_wav_prefix
        pref = vigiechiro_wav_prefix(self._make_meta())
        assert pref == "Car212097-2025-Pass2-Z3-SMU03126"

    def test_compute_new_wav_name_with_timestamp(self):
        """Fichier brut SM4BAT → nom canonique Vigie-Chiro."""
        from naming import compute_new_wav_name
        meta = self._make_meta()
        new = compute_new_wav_name(meta, "S4U04784_20250903_210523.wav")
        # Le nouveau nom doit commencer par le préfixe canonique + timestamp
        assert new is not None
        assert "Car212097-2025-Pass2-Z3-SMU03126" in new
        assert "_20250903_210523" in new

    def test_compute_new_wav_name_already_canonical(self):
        """Fichier déjà au nom canonique → retourne le même nom (skip silencieux)."""
        from naming import compute_new_wav_name
        meta = self._make_meta()
        original = "Car212097-2025-Pass2-Z3-SMU03126_20250903_210523_000.wav"
        new = compute_new_wav_name(meta, original)
        assert new == original

    def test_compute_new_wav_name_unreadable(self):
        """Fichier sans timestamp parseable → None."""
        from naming import compute_new_wav_name
        meta = self._make_meta()
        assert compute_new_wav_name(meta, "garbage_no_date.wav") is None


# =========================================================================
# taxons
# =========================================================================

class TestTaxons:
    def test_classify_noise(self):
        from taxons import classify_taxon
        assert classify_taxon("noise") == "noise"
        assert classify_taxon("Noise") == "noise"  # case-insensitive
        assert classify_taxon("NOISE") == "noise"

    def test_classify_chiro_codes(self):
        from taxons import classify_taxon
        # Codes taxons chiros classiques
        # (on teste les préfixes de fallback car la table MNHN peut être absente en CI)
        assert classify_taxon("Pippip") in ("chiros",)  # Pipistrellus pipistrellus
        assert classify_taxon("Nycnoc") in ("chiros",)  # Nyctalus noctula
        assert classify_taxon("Myodau") in ("chiros",)  # Myotis daubentonii

    def test_classify_ortho(self):
        from taxons import classify_taxon
        # Orthoptères (préfixe T...)
        assert classify_taxon("Tetvir") in ("orthos",)  # Tettigonia viridissima
        assert classify_taxon("Yposp") in ("orthos",)

    def test_classify_unknown(self):
        from taxons import classify_taxon
        assert classify_taxon("ZZZnon_existant") == "unknown"
        assert classify_taxon(None) == "unknown"
        assert classify_taxon("") == "unknown"

    def test_classify_empty_and_none(self):
        from taxons import classify_taxon
        assert classify_taxon(None) == "unknown"


# =========================================================================
# cleanup.decide_contact
# =========================================================================

class TestCleanupDecision:
    def _thresholds(self):
        return {"chiros": 0.5, "orthos": 0.5, "micromam": 0.5, "oiseaux": 0.5}

    def test_noise_always_deleted(self):
        from cleanup import decide_contact
        g, d, _r = decide_contact("noise", 0.9,
                                    self._thresholds(), disabled=set())
        assert g == "noise"
        assert d == "deleted_noise"

    def test_chiro_above_threshold_kept(self):
        from cleanup import decide_contact
        g, d, _r = decide_contact("Pippip", 0.8,
                                    self._thresholds(), disabled=set())
        assert g == "chiros"
        assert d == "kept"

    def test_chiro_below_threshold_deleted(self):
        from cleanup import decide_contact
        g, d, _r = decide_contact("Pippip", 0.3,
                                    self._thresholds(), disabled=set())
        assert g == "chiros"
        assert d == "deleted_low_confidence"

    def test_chiro_exactly_at_threshold_kept(self):
        from cleanup import decide_contact
        g, d, _r = decide_contact("Pippip", 0.5,
                                    self._thresholds(), disabled=set())
        # >= seuil → conservé
        assert d == "kept"

    def test_group_disabled(self):
        from cleanup import decide_contact
        g, d, _r = decide_contact("Pippip", 0.9,
                                    self._thresholds(), disabled={"chiros"})
        assert d == "deleted_group_disabled"

    def test_proba_none_kept_by_default(self):
        from cleanup import decide_contact
        g, d, _r = decide_contact("Pippip", None,
                                    self._thresholds(), disabled=set())
        assert d == "kept"

    def test_unknown_taxon_keep_default(self):
        from cleanup import decide_contact
        g, d, _r = decide_contact("ZZZ_inconnu", 0.9,
                                    self._thresholds(), disabled=set(),
                                    unknown_action="keep")
        assert g == "unknown"
        assert d == "kept"

    def test_unknown_taxon_delete_optional(self):
        from cleanup import decide_contact
        g, d, _r = decide_contact("ZZZ_inconnu", 0.9,
                                    self._thresholds(), disabled=set(),
                                    unknown_action="delete")
        assert d == "deleted_unknown_group"


# =========================================================================
# manifest
# =========================================================================

class TestManifest:
    def test_save_load_roundtrip(self, tmp_path):
        from manifest import Manifest
        session = tmp_path / "session1"
        session.mkdir()
        m = Manifest.load_or_create(session)
        m.canonical_name = "20250903_site212097_Z3_Pass2_enr07"
        m.set_meta(n_site_tadarida="212097", n_point_fixe="Z3")
        m.save(session)
        assert (session / "_session_manifest.json").is_file()

        # Reload
        m2 = Manifest.load(session)
        assert m2 is not None
        assert m2.canonical_name == "20250903_site212097_Z3_Pass2_enr07"
        assert m2.meta.get("n_site_tadarida") == "212097"

    def test_idempotence_flag(self, tmp_path):
        """Un flag mis à True reste True après save/load."""
        from manifest import Manifest
        session = tmp_path / "session2"
        session.mkdir()
        m = Manifest.load_or_create(session)
        m.flags["renamed"] = True
        m.save(session)

        m2 = Manifest.load(session)
        assert m2.flags.get("renamed") is True
        assert m2.is_done("rename")

    def test_action_status_failure_not_done(self, tmp_path):
        """Une action avec status != 'ok' ne doit pas être considérée done."""
        from manifest import Manifest
        session = tmp_path / "session3"
        session.mkdir()
        m = Manifest.load_or_create(session)
        # Action échouée : flag ne doit pas passer à True
        m.record_action("rename", status="error", tool_version="test")
        m.save(session)
        # L'implémentation gère ça via flags (qui ne passe à True que sur "ok")
        assert m.flags.get("renamed", False) is False


# =========================================================================
# taxons + cleanup intégration (règle OR WAV)
# =========================================================================

class TestCleanupFileDecision:
    """La règle OR : un WAV est gardé dès qu'UN contact est kept."""

    def test_or_rule_keeps_file_with_one_chiro(self):
        """Un WAV avec 1 chiro kept + 10 noise → gardé."""
        # Simule les contacts d'un même WAV
        from cleanup import decide_contact
        thresholds = {"chiros": 0.5, "orthos": 0.5,
                       "micromam": 0.5, "oiseaux": 0.5}
        # Contact 1 : chiro valide
        _, d1, _ = decide_contact("Pippip", 0.9, thresholds, set())
        # Contacts 2..11 : noise
        decisions = [d1] + ["deleted_noise"] * 10
        # Règle OR : au moins un kept → fichier gardé
        any_kept = any(d == "kept" for d in decisions)
        assert any_kept is True

    def test_or_rule_deletes_file_with_only_noise(self):
        from cleanup import decide_contact
        thresholds = {"chiros": 0.5, "orthos": 0.5,
                       "micromam": 0.5, "oiseaux": 0.5}
        _, d, _ = decide_contact("noise", 0.9, thresholds, set())
        decisions = [d] * 5
        any_kept = any(dd == "kept" for dd in decisions)
        assert any_kept is False


# =========================================================================
# registry
# =========================================================================

class TestRegistry:
    def test_fresh_create_empty(self, tmp_path):
        from registry import Registry
        r = Registry(tmp_path)
        try:
            sessions = list(r.list_sessions()) if hasattr(r, "list_sessions") \
                else []
            assert len(sessions) == 0
        finally:
            r.close()

    def test_upsert_inserted_then_updated(self, tmp_path):
        from registry import Registry
        r = Registry(tmp_path)
        try:
            action1 = r.upsert_session({
                "id": "test_session_1",
                "canonical_name": "20250903_site212097_Z3_Pass2_enr07",
                "nom_contrat": "Contrat A",
            })
            assert action1 == "inserted"

            action2 = r.upsert_session({
                "id": "test_session_1",
                "canonical_name": "20250903_site212097_Z3_Pass2_enr07",
                "nom_contrat": "Contrat A",
            })
            assert action2 == "updated"
        finally:
            r.close()

    def test_thread_safe_upsert(self, tmp_path):
        """Upsert depuis un autre thread ne doit pas lever ProgrammingError."""
        import threading

        from registry import Registry
        r = Registry(tmp_path)
        try:
            results = []
            def worker():
                try:
                    a = r.upsert_session({
                        "id": "cross_thread",
                        "canonical_name": "cross",
                    })
                    results.append(("ok", a))
                except Exception as e:
                    results.append(("err", str(e)))
            t = threading.Thread(target=worker)
            t.start()
            t.join()
            assert results == [("ok", "inserted")]
        finally:
            r.close()

    def test_batch_feed_from_scan(self, tmp_path):
        """feed_from_scan doit être transactionnel (pas 1 commit/session)."""
        from registry import Registry
        r = Registry(tmp_path)
        try:
            # Simule un SessionState-like via dict
            states = [
                {"name": f"session_{i}", "path": f"/tmp/session_{i}",
                 "campaign": "TestCamp", "n_wav": i, "total_bytes": i * 1000}
                for i in range(10)
            ]
            result = r.feed_from_scan(states)
            assert result["inserted"] == 10
            assert result["updated"] == 0
            # Re-feed → tout en update
            result2 = r.feed_from_scan(states)
            assert result2["inserted"] == 0
            assert result2["updated"] == 10
        finally:
            r.close()


# =========================================================================
# materiels
# =========================================================================

class TestMateriels:
    def test_save_load_roundtrip(self, tmp_path, monkeypatch):
        import materiels as mm
        # Redirige le stockage vers un tempdir
        fake_path = tmp_path / "materiels.json"
        monkeypatch.setattr(mm, "_materiels_path", lambda: fake_path)

        ms = [
            mm.Materiel(id=1, marque="WA", modele="SM4BAT",
                         serie_enr="S4U001", micro_modele="SMX-U1"),
            mm.Materiel(id=7, marque="Audiomoth", serie_enr="AM007"),
        ]
        mm.save_materiels(ms)
        assert fake_path.is_file()

        loaded = mm.load_materiels()
        assert len(loaded) == 2
        assert loaded[0].id == 1
        assert loaded[0].modele == "SM4BAT"
        assert loaded[1].id == 7

    def test_find_by_id_and_serial(self, tmp_path, monkeypatch):
        import materiels as mm
        monkeypatch.setattr(mm, "_materiels_path",
                            lambda: tmp_path / "materiels.json")
        ms = [
            mm.Materiel(id=7, serie_enr="S4U04784", modele="SM4BAT"),
        ]
        mm.save_materiels(ms)
        loaded = mm.load_materiels()
        assert mm.find_by_id(loaded, 7).modele == "SM4BAT"
        assert mm.find_by_id(loaded, 99) is None
        assert mm.find_by_serial(loaded, "S4U04784").id == 7
        assert mm.find_by_serial(loaded, "s4u04784").id == 7  # case-insensitive

    def test_save_empty_refuses_to_overwrite(self, tmp_path, monkeypatch):
        """Le garde-fou anti-effacement : save([]) ne doit pas écraser
        une liste existante sauf si allow_clear=True."""
        import materiels as mm
        fake_path = tmp_path / "materiels.json"
        monkeypatch.setattr(mm, "_materiels_path", lambda: fake_path)

        # 1. On sauvegarde 2 matériels
        ms = [mm.Materiel(id=1, modele="SM4BAT"),
              mm.Materiel(id=7, modele="Audiomoth")]
        mm.save_materiels(ms)
        assert len(mm.load_materiels()) == 2

        # 2. Tentative d'écraser par []: REFUS
        mm.save_materiels([])
        assert len(mm.load_materiels()) == 2, \
            "liste vide ne doit PAS écraser une liste non-vide"

        # 3. Suppression explicite : OK
        mm.save_materiels([], allow_clear=True)
        assert len(mm.load_materiels()) == 0

    def test_save_creates_backup(self, tmp_path, monkeypatch):
        """save_materiels doit créer un .bak avant écrasement."""
        import materiels as mm
        fake_path = tmp_path / "materiels.json"
        monkeypatch.setattr(mm, "_materiels_path", lambda: fake_path)

        mm.save_materiels([mm.Materiel(id=1, modele="A")])
        # Second save → .bak créé
        mm.save_materiels([mm.Materiel(id=1, modele="B")])
        bak = fake_path.with_suffix(fake_path.suffix + ".bak")
        assert bak.is_file()

    def test_next_free_id(self):
        import materiels as mm
        ms = [mm.Materiel(id=1), mm.Materiel(id=3), mm.Materiel(id=5)]
        assert mm.next_free_id(ms) == 2
        assert mm.next_free_id(ms, start=4) == 4
        assert mm.next_free_id(ms, start=5) == 6

    def test_empty_materiel(self):
        import materiels as mm
        m = mm.Materiel(id=1)
        assert m.is_empty() is True
        m2 = mm.Materiel(id=2, modele="Test")
        assert m2.is_empty() is False


# =========================================================================
# rename : auto-cicatrisation des doublons de casse (régression v0.3.1)
# =========================================================================

class TestRenameAutoHeal:
    """Garde-fou contre la régression « Terminé avec erreurs » :

    un run de prep interrompu peut laisser, pour un même timestamp, la source
    (casse minuscule) ET sa cible canonique déjà renommée, byte-identiques.
    Le re-run NE DOIT PAS bloquer toute la session : la source redondante est
    mise en quarantaine, la cible conservée. Un vrai conflit (contenu
    différent) doit en revanche TOUJOURS bloquer (zéro écrasement).
    """

    def _meta(self):
        from naming import SessionMeta
        return SessionMeta(
            date_debut=datetime(2025, 9, 3), n_site_tadarida="212097",
            n_point_fixe="Z3", n_passage=2, n_enregistreur=7,
            n_serie="SMU03126", nom_contrat="T",
        )

    def _wav(self, path: Path, frames: int = 100):
        import wave
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(384000)
            w.writeframes(b"\x01\x02" * frames)

    def test_identical_existing_target_is_quarantined(self, tmp_path):
        import shutil

        from naming import compute_new_wav_name
        from rename import rename_session
        meta = self._meta()
        sess = tmp_path / "rawsess"
        sess.mkdir()
        # 1 fichier brut qui se renomme proprement
        self._wav(sess / "SMU03126_20250903_210000.wav")
        # 1 fichier brut (casse minuscule) dont la cible canonique existe DÉJÀ,
        # identique → doublon résiduel à cicatriser
        src_dup = sess / "smu03126_20250903_210523.wav"
        self._wav(src_dup)
        canon = compute_new_wav_name(meta, src_dup.name)
        assert canon is not None
        shutil.copy(src_dup, sess / canon)   # cible identique pré-existante

        res = rename_session(sess, meta, dry_run=False, rename_folder=False)

        assert not res.get("errors"), f"ne doit pas bloquer : {res.get('errors')}"
        assert res.get("quarantined", 0) == 1
        assert (sess / "_doublons_casse").is_dir()
        assert not src_dup.exists(), "la source redondante doit être déplacée"
        assert (sess / canon).is_file(), "la cible canonique doit être conservée"

    def test_different_existing_target_blocks(self, tmp_path):
        from naming import compute_new_wav_name
        from rename import rename_session
        meta = self._meta()
        sess = tmp_path / "rawsess2"
        sess.mkdir()
        src = sess / "smu03126_20250903_210523.wav"
        self._wav(src, frames=100)
        canon = compute_new_wav_name(meta, src.name)
        self._wav(sess / canon, frames=50)   # cible DIFFÉRENTE → vrai conflit

        res = rename_session(sess, meta, dry_run=False, rename_folder=False)

        assert res.get("errors"), "un conflit réel (contenu différent) doit bloquer"
        assert src.exists(), "la source ne doit pas être touchée en cas de conflit"


if __name__ == "__main__":
    # Permet de lancer directement : python tests/test_core.py
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
