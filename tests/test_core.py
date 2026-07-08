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

    def test_partial_upload_not_done(self, tmp_path):
        """Régression reprise d'upload : une action 'partial' NE DOIT PAS marquer
        l'étape comme faite (sinon le 2e clic court-circuite l'upload et les WAV
        manquants ne repartent jamais)."""
        from manifest import Manifest
        session = tmp_path / "sess_partial"
        session.mkdir()
        m = Manifest.load_or_create(session)
        m.record_action("upload", status="partial", tool_version="test")
        assert m.flags.get("uploaded", False) is False
        assert m.is_done("upload") is False            # le bug corrigé
        # une fois l'upload complet réussi → l'étape est faite
        m.record_action("upload", status="ok", tool_version="test")
        assert m.is_done("upload") is True

    def test_is_done_unknown_type_needs_ok(self, tmp_path):
        """Type sans flag dédié : seule une action 'ok' compte comme faite."""
        from manifest import Manifest
        session = tmp_path / "sess_unknown"
        session.mkdir()
        m = Manifest.load_or_create(session)
        m.record_action("customstep", status="partial", tool_version="test")
        assert m.is_done("customstep") is False
        m.record_action("customstep", status="ok", tool_version="test")
        assert m.is_done("customstep") is True


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


# =========================================================================
# synthesis : récap par espèce d'une nuit
# =========================================================================

class TestSynthesis:
    HEADERS = ["nom du fichier", "tadarida_taxon", "observateur_taxon"]

    def _rows(self):
        return [
            ["f1.wav", "Pippip", None],      # Tadarida chiros
            ["f1.wav", "Pippip", None],      # même espèce, même fichier
            ["f2.wav", "Nycnoc", "Pippip"],  # validé Pippip → écrase Nycnoc
            ["f3.wav", "noise", None],       # bruit
            ["f4.wav", None, None],          # aucune espèce → ignoré
            ["f5.wav", "", ""],              # vide → ignoré
        ]

    def test_counts_and_totals(self):
        from synthesis import compute_night_synthesis
        res = compute_night_synthesis(self.HEADERS, self._rows())
        by_taxon = {s["taxon"]: s for s in res["species"]}

        # Pippip : 3 contacts (2 Tadarida + 1 validé), 2 fichiers (f1, f2)
        assert by_taxon["Pippip"]["n_contacts"] == 3
        assert by_taxon["Pippip"]["n_fichiers"] == 2
        assert by_taxon["Pippip"]["validated"] is True
        assert by_taxon["Pippip"]["groupe"] == "chiros"

        # Nycnoc écrasé par la validation observateur → absent
        assert "Nycnoc" not in by_taxon

        # noise compté à part
        assert by_taxon["noise"]["n_contacts"] == 1

        assert res["total_contacts"] == 4          # 3 Pippip + 1 noise
        assert res["total_fichiers"] == 3          # f1, f2, f3
        assert res["by_group"]["chiros"] == 3
        assert res["by_group"]["noise"] == 1

    def test_sorted_desc(self):
        from synthesis import compute_night_synthesis
        res = compute_night_synthesis(self.HEADERS, self._rows())
        counts = [s["n_contacts"] for s in res["species"]]
        assert counts == sorted(counts, reverse=True)

    def test_missing_columns_graceful(self):
        from synthesis import compute_night_synthesis
        res = compute_night_synthesis(["a", "b"], [[1, 2], [3, 4]])
        assert res["species"] == []
        assert res["total_contacts"] == 0
        assert res["total_fichiers"] == 0

    def test_empty_rows(self):
        from synthesis import compute_night_synthesis
        res = compute_night_synthesis(self.HEADERS, [])
        assert res["total_contacts"] == 0


# =========================================================================
# validation : filtrage pur + menu taxons dynamique
# =========================================================================

class TestValidationFilters:
    CI = {"nom du fichier": 0, "tadarida_taxon": 1,
          "tadarida_probabilite": 2, "observateur_taxon": 3}

    def _rows(self):
        # [fichier, tadarida, proba, observateur]
        return [
            ["f1.wav", "Pippip", 0.9, None],
            ["f2.wav", "Pippip", 0.3, None],
            ["f3.wav", "Nycnoc", 0.8, None],
            ["f4.wav", "barbar", 0.2, "barbar"],   # patrimonial + validé
            ["f5.wav", "noise", 0.95, None],
        ]

    def test_proba_filter(self):
        from gui_validation import row_passes_filters as rp
        r = ["f", "Pippip", 0.3, None]
        assert rp(r, self.CI, proba_min=0.0) is True
        assert rp(r, self.CI, proba_min=0.5) is False

    def test_taxon_filter(self):
        from gui_validation import row_passes_filters as rp
        r = ["f", "Pippip", 0.9, None]
        assert rp(r, self.CI, taxon_filter="Pippip") is True
        assert rp(r, self.CI, taxon_filter="Nycnoc") is False
        assert rp(r, self.CI, taxon_filter="Tous") is True

    def test_hide_cleaned(self):
        from gui_validation import row_passes_filters as rp
        r = ["f", "Pippip", 0.9, None]
        assert rp(r, self.CI, hide_cleaned=True, wav_present=True) is True
        assert rp(r, self.CI, hide_cleaned=True, wav_present=False) is False
        assert rp(r, self.CI, hide_cleaned=False, wav_present=False) is True

    def test_only_unvalidated(self):
        from gui_validation import row_passes_filters as rp
        assert rp(["f", "Pippip", 0.9, "Pippip"], self.CI,
                  only_unvalidated=True) is False
        assert rp(["f", "Pippip", 0.9, None], self.CI,
                  only_unvalidated=True) is True

    def test_only_patrimonial(self):
        from gui_validation import row_passes_filters as rp, PATRIMONIAL_CODES
        assert rp(["f", "barbar", 0.9, None], self.CI, only_patrimonial=True,
                  patrimonial_codes=PATRIMONIAL_CODES) is True
        assert rp(["f", "Pippip", 0.9, None], self.CI, only_patrimonial=True,
                  patrimonial_codes=PATRIMONIAL_CODES) is False

    def test_eligible_taxons_all(self):
        from gui_validation import eligible_taxons
        t = eligible_taxons(self._rows(), self.CI, proba_min=0.0)
        assert set(t) == {"Pippip", "Nycnoc", "barbar", "noise"}

    def test_eligible_taxons_reflects_proba(self):
        from gui_validation import eligible_taxons
        # proba ≥ 0.5 : barbar (0.2) et Pippip/f2 (0.3) sortent ; Pippip reste (f1=0.9)
        t = eligible_taxons(self._rows(), self.CI, proba_min=0.5)
        assert set(t) == {"Pippip", "Nycnoc", "noise"}
        assert "barbar" not in t

    def test_eligible_taxons_reflects_hide_cleaned(self):
        from gui_validation import eligible_taxons
        # f3 (Nycnoc) supprimé au nettoyage → disparaît de la liste
        wav_present = [True, True, False, True, True]
        t = eligible_taxons(self._rows(), self.CI, hide_cleaned=True,
                            wav_present=wav_present)
        assert "Nycnoc" not in t
        assert "Pippip" in t


# =========================================================================
# activity_graph : cascade des filtres (site → point → passage → nuit)
# =========================================================================

class TestActivityCascade:
    def _agg(self):
        # clé = (site, point, passage, night, taxon) -> bins
        return {
            ("212097", "Z1", 1, "2026-06-01", "Pippip"): [1],
            ("212097", "Z2", 1, "2026-06-01", "Nycnoc"): [1],
            ("212097", "Z1", 2, "2026-06-02", "Pippip"): [1],
            ("999999", "A1", 1, "2026-05-01", "Barbar"): [1],
        }

    def test_no_selection_all_options(self):
        from activity_graph import cascade_options
        o = cascade_options(self._agg())
        assert o["sites"] == ["212097", "999999"]
        assert set(o["points"]) == {"Z1", "Z2", "A1"}
        assert o["passages"] == [1, 2]
        assert o["nights"] == ["2026-05-01", "2026-06-01", "2026-06-02"]

    def test_cascade_by_site(self):
        from activity_graph import cascade_options
        o = cascade_options(self._agg(), sel_sites={"212097"})
        assert set(o["points"]) == {"Z1", "Z2"}     # A1 exclu (autre site)
        assert o["passages"] == [1, 2]
        assert o["nights"] == ["2026-06-01", "2026-06-02"]  # 2026-05-01 exclu

    def test_cascade_by_site_and_point(self):
        from activity_graph import cascade_options
        o = cascade_options(self._agg(), sel_sites={"212097"}, sel_points={"Z1"})
        # passages/nuits limités à Z1 du site 212097
        assert o["passages"] == [1, 2]
        assert o["nights"] == ["2026-06-01", "2026-06-02"]

    def test_cascade_full_chain(self):
        from activity_graph import cascade_options
        o = cascade_options(self._agg(), sel_sites={"212097"},
                            sel_points={"Z1"}, sel_passages={1})
        # Z1 + passage 1 => uniquement la nuit du 2026-06-01
        assert o["nights"] == ["2026-06-01"]

    def test_placeholder_ordering(self):
        from activity_graph import cascade_options
        agg = {
            ("212097", "Z1", 1, "2026-06-01", "Pippip"): [1],
            ("?", "?", None, "2026-06-01", "noise"): [1],
        }
        o = cascade_options(agg)
        assert o["sites"] == ["212097", "?"]          # "?" repoussé en fin
        assert o["points"] == ["Z1", "?"]
        assert o["passages"] == [1, None]             # None en fin


# =========================================================================
# te10 : robustesse backend Python (statuts, erreurs, pas d'avortement)
# =========================================================================

class TestTe10Robustness:
    def _wav(self, path, frames=100, sr=384000):
        import wave
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(b"\x01\x02" * frames)

    def test_write_segment_states(self, tmp_path):
        from te10 import write_segment, plan_file
        src = tmp_path / "s_20250101_000000.wav"
        self._wav(src)
        out = tmp_path / "out"
        plans = plan_file(src, out, 10, 5.0)
        assert plans
        st, _ = write_segment(plans[0])
        assert st == "written"
        assert plans[0].dst.is_file()
        st2, _ = write_segment(plans[0])   # existe déjà
        assert st2 == "skipped"

    def test_write_segment_error_never_raises(self, tmp_path):
        """Une source illisible renvoie 'error' — jamais d'exception (sinon tout
        le lot avorterait)."""
        from te10 import write_segment, SegmentPlan
        bad = tmp_path / "bad.wav"
        bad.write_text("pas un wav")
        plan = SegmentPlan(src=bad, dst=tmp_path / "out" / "x_000.wav",
                           start_frame=0, n_frames=10, sr_te=38400)
        st, msg = write_segment(plan)      # ne doit pas lever
        assert st == "error"
        assert not plan.dst.exists()

    def test_process_folder_counts_errors_not_skipped(self, tmp_path):
        """Backend Python : un WAV corrompu est compté en 'errors' (pas 'skipped')
        et n'avorte PAS la session ; le WAV valide est bien produit."""
        from te10 import process_folder
        src = tmp_path / "src"
        src.mkdir()
        self._wav(src / "a_20250101_000000.wav")           # valide
        (src / "b_20250101_000100.wav").write_text("corrompu")  # illisible
        stats = process_folder(src, tmp_path / "out", jobs=1, force_python=True)
        assert stats["written"] >= 1        # le valide est traité malgré l'autre
        assert stats["errors"] >= 1         # le corrompu compté en erreur
        assert stats["engine"] == "python"


# =========================================================================
# pipeline : fenetre temporelle de participation (bug date_fin a minuit)
# =========================================================================

class TestParticipationWindow:
    def test_midnight_becomes_night(self):
        from pipeline import _participation_window
        d0, d1 = _participation_window(datetime(2026, 6, 23))   # minuit
        assert d0 == datetime(2026, 6, 23, 20, 0)     # décalé à 20:00
        assert d1 == datetime(2026, 6, 24, 6, 0)      # fin le lendemain 06:00
        assert d1 > d0

    def test_evening_start_ends_next_morning(self):
        from pipeline import _participation_window
        dd = datetime(2026, 6, 23, 21, 30)
        d0, d1 = _participation_window(dd)
        assert d0 == dd
        assert d1 == datetime(2026, 6, 24, 6, 0)

    def test_explicit_date_fin_untouched(self):
        from pipeline import _participation_window
        dd = datetime(2026, 6, 23)
        df = datetime(2026, 6, 24, 5, 0)
        assert _participation_window(dd, df) == (dd, df)

    def test_early_morning_same_day_end(self):
        from pipeline import _participation_window
        dd = datetime(2026, 6, 23, 2, 0)
        d0, d1 = _participation_window(dd)
        assert d0 == dd
        assert d1 == datetime(2026, 6, 23, 6, 0)      # 06:00 le jour même > 02:00
        assert d1 > d0

    def test_none_date_debut(self):
        from pipeline import _participation_window
        assert _participation_window(None) == (None, None)


# =========================================================================
# cleanup : appariement WAV<->xlsx insensible a la casse (regression)
# =========================================================================

class TestCleanupCaseInsensitive:
    def _wav(self, path, frames=50):
        import wave
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(38400)
            w.writeframes(b"\x01\x02" * frames)

    def test_norm_stem_lowercases(self):
        from cleanup import _norm_stem
        assert _norm_stem("2MU08078_X.wav") == _norm_stem("2mu08078_x")

    def test_case_divergent_wav_kept(self, tmp_path):
        """Un WAV dont la casse diffère entre le xlsx et le disque, mais porteur
        d'un contact 'kept', NE DOIT PAS être supprimé (avant : il tombait dans
        silent_files → supprimé avec silent_policy='delete'). 3 WAV pour que le
        divergent soit minoritaire (le garde-fou mass-delete ne le protège pas)."""
        from cleanup import cleanup_session
        session = tmp_path / "sess"
        dk = session / "Data_k"
        dk.mkdir(parents=True)
        self._wav(dk / "a_20250101_210000_000.wav")
        self._wav(dk / "b_20250101_210100_000.wav")
        self._wav(dk / "2MU_20250101_210200_000.wav")     # disque : MAJUSCULES
        csv_path = session / "participation-test-observations.csv"
        csv_path.write_text(
            "nom du fichier,tadarida_taxon,tadarida_probabilite\n"
            "a_20250101_210000_000.wav,Pippip,0.9\n"
            "b_20250101_210100_000.wav,Pippip,0.9\n"
            "2mu_20250101_210200_000.wav,Pippip,0.9\n",   # xlsx : minuscules
            encoding="utf-8",
        )
        res = cleanup_session(
            session,
            thresholds={"chiros": 0.5, "orthos": 0.5,
                        "micromam": 0.5, "oiseaux": 0.5},
            disabled=set(), silent_policy="delete", dry_run=False,
        )
        assert not res.get("errors"), res.get("errors")
        # Les 3 WAV portent un contact kept → aucun ne doit être supprimé.
        assert (dk / "2MU_20250101_210200_000.wav").exists()
        assert (dk / "a_20250101_210000_000.wav").exists()
        assert (dk / "b_20250101_210100_000.wav").exists()


# =========================================================================
# securite : stockage token (fallback) + base_url https
# =========================================================================

class TestCredentialsFallback:
    TOKEN = "ABCD1234ABCD1234ABCD1234ABCD1234"

    def test_fallback_roundtrip_and_not_plaintext(self, tmp_path, monkeypatch):
        import os as _os

        import credentials as cr
        monkeypatch.setattr(cr, "_try_keyring", lambda: None)   # force le fichier
        monkeypatch.setattr(cr, "_fallback_dir", lambda: tmp_path)

        assert cr.save_token(self.TOKEN) == "file"
        assert cr.load_token() == self.TOKEN

        content = (tmp_path / "credentials.json").read_text(encoding="utf-8")
        if _os.name == "nt":
            # Sous Windows, DPAPI doit avoir chiffré : pas de token en clair.
            assert self.TOKEN not in content
            assert "token_dpapi" in content

        assert cr.delete_token() is True
        assert cr.load_token() is None

    def test_legacy_plaintext_still_readable(self, tmp_path, monkeypatch):
        """Compat : un ancien credentials.json en clair reste lisible."""
        import json

        import credentials as cr
        monkeypatch.setattr(cr, "_try_keyring", lambda: None)
        monkeypatch.setattr(cr, "_fallback_dir", lambda: tmp_path)
        (tmp_path / "credentials.json").write_text(
            json.dumps({"token": self.TOKEN}), encoding="utf-8")
        assert cr.load_token() == self.TOKEN


class TestApiBaseUrlSecurity:
    TOKEN = "A" * 32

    def test_rejects_http_non_localhost(self):
        from vigiechiro_api import VigieChiroClient
        with pytest.raises(ValueError):
            VigieChiroClient(self.TOKEN,
                             base_url="http://vigiechiro.example.com/api/v1")

    def test_allows_http_localhost(self):
        from vigiechiro_api import VigieChiroClient
        c = VigieChiroClient(self.TOKEN, base_url="http://localhost:8080/api/v1")
        assert c.base_url.startswith("http://localhost")

    def test_allows_https(self):
        from vigiechiro_api import VigieChiroClient
        c = VigieChiroClient(self.TOKEN,
                             base_url="https://vigiechiro.example.com/api/v1")
        assert c.base_url.startswith("https://")


# =========================================================================
# rename : mode compatible antivirus (_av_safe_pace via variable d'env)
# =========================================================================

class TestAvSafePace:
    def test_env_activation(self, monkeypatch):
        import rename
        # Valeurs explicites via env : prioritaires (independant du marqueur).
        monkeypatch.setenv("CHIROTOOL_AV_SAFE", "1")
        assert rename._av_safe_pace() == (40, 0.25)
        monkeypatch.setenv("CHIROTOOL_AV_SAFE", "25:400")
        assert rename._av_safe_pace() == (25, 0.4)
        monkeypatch.setenv("CHIROTOOL_AV_SAFE", "0")   # desactivation explicite
        assert rename._av_safe_pace() is None


# =========================================================================
# coherence : User-Agent Nominatim derive de version.py
# =========================================================================

class TestNominatimUserAgent:
    def test_ua_reflects_version(self):
        import gui_map
        from version import __version__
        assert gui_map.NOMINATIM_UA.startswith("ChiroTool/")
        assert __version__ in gui_map.NOMINATIM_UA


# =========================================================================
# carte : points sur carres d'autres observateurs (sites externes)
# =========================================================================

class TestMapExternalSites:
    def test_points_from_raw_latlon_order(self):
        import gui_map
        raw = {"localites": [
            {"nom": "Z1", "geometries": {"geometries": [
                {"type": "Point", "coordinates": [45.5, 4.2]}]}},   # [lat, lon]
            {"nom": "Z2", "geometries": {"geometries": [
                {"type": "LineString", "coordinates": [[1, 2], [3, 4]]}]}},
        ]}
        pts = gui_map._points_from_raw(raw)
        assert pts == [{"nom": "Z1", "lat": 45.5, "lon": 4.2}]

    def test_external_site_ids_persist(self, tmp_path, monkeypatch):
        import gui_map
        monkeypatch.setattr(gui_map, "_external_sites_path",
                            lambda: tmp_path / "external_sites.json")
        assert gui_map._load_external_site_ids() == []
        gui_map._remember_external_site_id("abc123")
        gui_map._remember_external_site_id("abc123")   # idempotent
        gui_map._remember_external_site_id("def456")
        assert gui_map._load_external_site_ids() == ["abc123", "def456"]


# =========================================================================
# version : selection de la release (liste + /latest, anti-cache-obsolete)
# =========================================================================

class TestBestRelease:
    def test_latest_beats_stale_list(self):
        """Cas reel : la LISTE est servie en cache obsolete (max = 0.3.1) mais
        /releases/latest est a jour (0.4.0). Le combine doit renvoyer 0.4.0."""
        from version import _best_release
        candidates = [
            {"tag_name": "v0.3.1", "prerelease": False, "html_url": "u/031"},
            {"tag_name": "V0.3.0", "prerelease": False, "html_url": "u/030"},
            {"tag_name": "v0.4.0", "prerelease": False, "html_url": "u/040"},  # /latest
        ]
        best = _best_release(candidates)
        assert best["tag"] == "v0.4.0"
        assert best["prerelease"] is False

    def test_ignores_drafts(self):
        from version import _best_release
        candidates = [
            {"tag_name": "v0.4.0", "draft": True, "html_url": "u/040"},   # brouillon
            {"tag_name": "v0.3.1", "prerelease": False, "html_url": "u/031"},
        ]
        assert _best_release(candidates)["tag"] == "v0.3.1"

    def test_empty(self):
        from version import _best_release
        assert _best_release([]) is None


# =========================================================================
# AudioMoth : format date_time sans serie (issue #1)
# =========================================================================

class TestAudioMoth:
    """Format AudioMoth (issue #1). Validé sur de vrais fichiers CEREMA/TWAV_splitter :
    l'EXPANDÉ `date_time_ms.WAV` est traité ; le BRUT `date_time T.WAV` (déclenché,
    concaténé) est refusé (il doit d'abord être expandé)."""

    def _meta(self):
        from naming import SessionMeta
        return SessionMeta(
            date_debut=datetime(2022, 7, 21), n_site_tadarida="430658",
            n_point_fixe="Z1", n_passage=1, n_enregistreur=5,
            n_serie="24F319", nom_contrat="T")

    # --- format EXPANDÉ (date_time_ms) : traité ---
    def test_expanded_timestamp(self):
        from naming import extract_timestamp_from_name
        ts = extract_timestamp_from_name("20220721_033014_451.WAV")   # avec ms
        assert ts is not None and ts[0] == datetime(2022, 7, 21, 3, 30, 14)
        ts2 = extract_timestamp_from_name("20260615_212501.WAV")      # sans ms
        assert ts2 is not None and ts2[0] == datetime(2026, 6, 15, 21, 25, 1)

    def test_expanded_classified_raw_no_serial(self):
        from chiro_core import classify_wav_name
        from naming import extract_serial_from_name
        assert classify_wav_name("20220721_033014_451.WAV") == "raw"
        assert extract_serial_from_name("20220721_033014_451.WAV") is None

    def test_expanded_canonical_preserves_ms(self):
        from naming import compute_new_wav_name
        new = compute_new_wav_name(self._meta(), "20220721_033014_451.WAV")
        assert new == "Car430658-2022-Pass1-Z1-24F319_20220721_033014_451.wav"

    # --- format BRUT T.WAV : détecté et refusé ---
    def test_raw_twav_detected_not_processed(self):
        from chiro_core import classify_wav_name, is_audiomoth_twav
        from naming import extract_timestamp_from_name
        n = "20260615_212501T.WAV"
        assert is_audiomoth_twav(n) is True
        assert classify_wav_name(n) == "audiomoth_twav"
        assert extract_timestamp_from_name(n) is None   # PAS traité tel quel

    def test_rename_refuses_raw_twav(self, tmp_path):
        from rename import rename_session
        d = tmp_path / "sess" / "Data"
        d.mkdir(parents=True)
        (d / "20260615_212501T.WAV").write_bytes(b"RIFFxxxxWAVE")   # dummy
        res = rename_session(tmp_path / "sess", self._meta(),
                             dry_run=False, rename_folder=False)
        assert res.get("audiomoth_twav_raw") == 1
        assert res.get("errors")                       # refus explicite
        assert (d / "20260615_212501T.WAV").exists()   # non renommé

    def test_wildlife_still_works(self):
        """Non-régression : le format Wildlife (série en tête) reste géré."""
        from naming import compute_new_wav_name, extract_serial_from_name
        assert extract_serial_from_name("2MU08078_20260623_211115.wav") == "2MU08078"
        new = compute_new_wav_name(self._meta(), "2MU08078_20260623_211115.wav")
        assert "_20260623_211115" in new and new.startswith("Car430658-2022-Pass1-Z1-")


class TestObservationSidecar:
    """Lot 1 — sidecar de synchro (donnee_id + index natif) écrit à l'export.
    L'xlsx reste inchangé ; le mapping serveur vit dans <stem>.sync.json."""

    def _fake_client(self, donnees):
        from vigiechiro_api import VigieChiroClient
        c = VigieChiroClient("A" * 32)

        def fake_iter(pid, on_progress=None, **kw):
            for d in donnees:
                yield d
        c.iter_donnees = fake_iter
        return c

    def test_sidecar_maps_native_index(self, tmp_path):
        from vigiechiro_api import load_observation_sidecar
        donnees = [
            {"_id": "d1", "titre": "Car-001_x.wav", "observations": [
                {"_id": "o0", "temps_debut": 1.0, "tadarida_taxon": "pippip"},
                {"_id": "o1", "temps_debut": 2.0, "tadarida_taxon": "barbar"},
                {"_id": "o2", "temps_debut": 3.0, "tadarida_taxon": "nyclei"},
            ]},
            {"_id": "d2", "titre": "Car-002_silent.wav", "observations": []},
        ]
        c = self._fake_client(donnees)
        dst = tmp_path / "participation-abc-observations.xlsx"
        stats = c.download_observations_as_xlsx("abc", dst)
        assert (stats["n_files"], stats["n_contacts"], stats["n_silent_files"]) == (2, 3, 1)
        entries = load_observation_sidecar(dst)["entries"]
        assert len(entries) == 3                       # rien pour la donnée silencieuse
        assert [e["obs_index"] for e in entries] == [0, 1, 2]
        assert [e["donnee_id"] for e in entries] == ["d1", "d1", "d1"]
        assert [e["row"] for e in entries] == [2, 3, 4]   # header=1 → contacts 2,3,4
        assert entries[0]["nom_fichier"] == "Car-001_x.wav"
        assert entries[0]["temps_debut"] == 1.0
        assert load_observation_sidecar(dst)["sync"] == {}

    def test_xlsx_unchanged_11_columns(self, tmp_path):
        import openpyxl
        donnees = [{"_id": "d1", "titre": "f.wav", "observations": [
            {"temps_debut": 1.0, "tadarida_taxon": "pippip"}]}]
        c = self._fake_client(donnees)
        dst = tmp_path / "participation-abc-observations.xlsx"
        c.download_observations_as_xlsx("abc", dst)
        ws = openpyxl.load_workbook(dst).active
        header = [cell.value for cell in next(ws.iter_rows())]
        assert len(header) == 11
        assert header[0] == "nom du fichier"
        assert header[7] == "observateur_taxon"
        assert header[10] == "validateur_probabilite"

    def test_sidecar_canonical_fallback(self, tmp_path):
        """Après sauvegarde en ..._KG.xlsx, le mapping reste résoluble."""
        from vigiechiro_api import load_observation_sidecar
        donnees = [{"_id": "d1", "titre": "f.wav", "observations": [{"temps_debut": 1.0}]}]
        c = self._fake_client(donnees)
        c.download_observations_as_xlsx("abc", tmp_path / "participation-abc-observations.xlsx")
        saved = tmp_path / "participation-abc-observations_KG.xlsx"
        side = load_observation_sidecar(saved)
        assert len(side["entries"]) == 1 and side["entries"][0]["donnee_id"] == "d1"

    def test_missing_sidecar_tolerated(self, tmp_path):
        from vigiechiro_api import load_observation_sidecar
        assert load_observation_sidecar(tmp_path / "nope.xlsx") == {"entries": [], "sync": {}}


class TestResolveTaxon:
    """Lot 2 — résolution libelle_court → ObjectId + cache + bypass 24-hex."""

    def _client(self, taxons, counter=None):
        from vigiechiro_api import VigieChiroClient
        c = VigieChiroClient("A" * 32)

        def fake_iter(page_size=99):
            if counter is not None:
                counter.append(1)
            for t in taxons:
                yield t
        c.iter_taxons = fake_iter
        return c

    def test_maps_case_insensitive(self):
        c = self._client([{"_id": "a" * 24, "libelle_court": "Barbar"}])
        assert c.resolve_taxon_id("barbar") == "a" * 24
        assert c.resolve_taxon_id("BARBAR") == "a" * 24

    def test_cache_single_fetch(self):
        calls = []
        c = self._client([{"_id": "a" * 24, "libelle_court": "pippip"}], counter=calls)
        c.resolve_taxon_id("pippip")
        c.resolve_taxon_id("pippip")
        assert len(calls) == 1                      # /taxons balayé une seule fois

    def test_unknown_raises(self):
        from vigiechiro_api import NotFoundError
        c = self._client([{"_id": "a" * 24, "libelle_court": "pippip"}])
        with pytest.raises(NotFoundError):
            c.resolve_taxon_id("zzzzzz")

    def test_bypass_objectid(self):
        calls = []
        c = self._client([], counter=calls)
        oid = "5aef012345678901234567ab"
        assert c.resolve_taxon_id(oid) == oid
        assert c.resolve_taxon_id(oid.upper()) == oid   # normalisé en minuscule
        assert len(calls) == 0                      # aucun appel /taxons pour un id direct

    def test_collision_keeps_first_and_warns(self):
        c = self._client([
            {"_id": "a" * 24, "libelle_court": "dupdup"},
            {"_id": "b" * 24, "libelle_court": "dupdup"},
        ])
        with pytest.warns(UserWarning):
            assert c.resolve_taxon_id("dupdup") == "a" * 24


class TestPushObservation:
    """Lot 3 — PATCH d'une observation + gardes + typage des erreurs 403/422."""

    def _client(self):
        from vigiechiro_api import VigieChiroClient
        return VigieChiroClient("A" * 32)

    def test_payload_and_params(self):
        c = self._client()
        captured = {}

        def fake_request(method, path, **kw):
            captured.update(method=method, path=path, **kw)
            return {"ok": True}
        c._request = fake_request
        oid = "a" * 24
        c.push_observation("d1", 2, oid, "SUR")
        assert captured["method"] == "PATCH"
        assert captured["path"] == "/donnees/d1/observations/2"
        assert captured["json"] == {"observateur_taxon": oid, "observateur_probabilite": "SUR"}
        assert "validateur_taxon" not in captured["json"]       # jamais de validateur_*
        assert "validateur_probabilite" not in captured["json"]
        assert captured["params"] == {"no_bilan": "true"}
        assert captured["source"] == "foreground"

    def test_no_bilan_false_triggers_bilan(self):
        c = self._client()
        captured = {}
        c._request = lambda method, path, **kw: captured.update(kw) or {}
        c.push_observation("d1", 0, "a" * 24, "POSSIBLE", no_bilan=False)
        assert captured["params"] is None                       # bilan déclenché

    def test_guard_bad_enum(self):
        c = self._client()
        c._request = lambda *a, **k: {}
        with pytest.raises(ValueError):
            c.push_observation("d1", 0, "a" * 24, "possible")   # minuscule refusée

    def test_guard_bad_id(self):
        c = self._client()
        c._request = lambda *a, **k: {}
        with pytest.raises(ValueError):
            c.push_observation("d1", 0, "barbar", "SUR")        # pas un ObjectId

    def test_request_classifies_403_and_422(self):
        from vigiechiro_api import ForbiddenError, ValidationError

        class FakeResp:
            def __init__(self, code):
                self.status_code, self.text, self.content, self.headers = code, "x", b"x", {}
        for code, exc in ((403, ForbiddenError), (422, ValidationError)):
            c = self._client()
            c.session.request = lambda *a, _c=code, **k: FakeResp(_c)
            with pytest.raises(exc):
                c._request("PATCH", "/donnees/d/observations/0", json={})


class TestSyncState:
    """Lot 4 — machine à états de synchro + mapping ligne↔serveur (pur)."""

    def test_is_sendable(self):
        from sync_state import is_sendable
        assert is_sendable("barbar", "SUR")
        assert not is_sendable("barbar", "")      # sans confiance → non envoyable
        assert not is_sendable("", "SUR")

    def test_sync_label(self):
        from sync_state import sync_label, SYNC_SYNCED, SYNC_TO_RETRACT
        assert sync_label(SYNC_SYNCED)             # libellé non vide (tooltip)
        assert sync_label(SYNC_TO_RETRACT)
        assert sync_label(None) is None            # pas d'état → pas d'infobulle
        assert sync_label("bogus") is None

    def test_pending_when_validated_never_pushed(self):
        from sync_state import next_sync_state, SYNC_PENDING
        assert next_sync_state("barbar", "SUR", None) == SYNC_PENDING
        assert next_sync_state("barbar", "SUR", {}) == SYNC_PENDING

    def test_none_when_not_sendable_never_pushed(self):
        from sync_state import next_sync_state
        assert next_sync_state("", "", None) is None
        assert next_sync_state("barbar", "", None) is None    # taxon sans confiance

    def test_synced_and_modified(self):
        from sync_state import next_sync_state, SYNC_SYNCED, SYNC_MODIFIED
        rec = {"pushed_taxon": "barbar", "pushed_conf": "SUR"}
        assert next_sync_state("barbar", "SUR", rec) == SYNC_SYNCED
        assert next_sync_state("pippip", "SUR", rec) == SYNC_MODIFIED
        assert next_sync_state("barbar", "PROBABLE", rec) == SYNC_MODIFIED

    def test_modified_back_to_synced(self):
        from sync_state import next_sync_state, SYNC_SYNCED
        rec = {"pushed_taxon": "barbar", "pushed_conf": "SUR", "state": "modified"}
        assert next_sync_state("barbar", "SUR", rec) == SYNC_SYNCED

    def test_to_retract_when_cleared_after_push(self):
        from sync_state import next_sync_state, SYNC_TO_RETRACT
        rec = {"pushed_taxon": "barbar", "pushed_conf": "SUR"}
        assert next_sync_state("", "", rec) == SYNC_TO_RETRACT
        assert next_sync_state("barbar", "", rec) == SYNC_TO_RETRACT   # non-envoyable

    def test_build_row_key_map(self):
        from sync_state import build_row_key_map
        col_idx = {"nom du fichier": 0, "temps_debut": 1}
        rows = [["f1.wav", 1.0], ["f1.wav", 2.0], ["f2.wav", 0.5]]
        entries = [
            {"donnee_id": "d1", "obs_index": 0, "nom_fichier": "f1.wav", "temps_debut": 1.0},
            {"donnee_id": "d1", "obs_index": 1, "nom_fichier": "f1.wav", "temps_debut": 2.0},
        ]
        row_keys, n_unmapped = build_row_key_map(rows, col_idx, entries)
        assert row_keys == {0: "d1#0", 1: "d1#1"}
        assert n_unmapped == 1                     # f2.wav non présent dans entries

    def test_build_row_key_map_no_entries(self):
        from sync_state import build_row_key_map
        rk, n = build_row_key_map([["f.wav", 1.0]],
                                  {"nom du fichier": 0, "temps_debut": 1}, [])
        assert rk == {} and n == 1

    def test_build_row_key_map_collision_excluded(self):
        """Sécurité anti-corruption : 2 obs partageant (nom, deb, fin) → EXCLUES
        (non mappées) au lieu d'écrire toutes deux sur l'index 0 côté serveur."""
        from sync_state import build_row_key_map
        col_idx = {"nom du fichier": 0, "temps_debut": 1, "temps_fin": 2}
        rows = [["f.wav", 1.0, 2.0], ["f.wav", 1.0, 2.0], ["g.wav", 5.0, 6.0]]
        entries = [
            {"donnee_id": "d1", "obs_index": 0, "nom_fichier": "f.wav", "temps_debut": 1.0, "temps_fin": 2.0},
            {"donnee_id": "d1", "obs_index": 1, "nom_fichier": "f.wav", "temps_debut": 1.0, "temps_fin": 2.0},
            {"donnee_id": "d2", "obs_index": 0, "nom_fichier": "g.wav", "temps_debut": 5.0, "temps_fin": 6.0},
        ]
        row_keys, n_unmapped = build_row_key_map(rows, col_idx, entries)
        assert row_keys == {2: "d2#0"}       # seule la ligne non ambiguë est mappée
        assert n_unmapped == 2

    def test_build_row_key_map_temps_fin_disambiguates(self):
        """Même temps_debut mais temps_fin différent → restent appariables."""
        from sync_state import build_row_key_map
        col_idx = {"nom du fichier": 0, "temps_debut": 1, "temps_fin": 2}
        rows = [["f.wav", 1.0, 2.0], ["f.wav", 1.0, 3.0]]
        entries = [
            {"donnee_id": "d1", "obs_index": 0, "nom_fichier": "f.wav", "temps_debut": 1.0, "temps_fin": 2.0},
            {"donnee_id": "d1", "obs_index": 1, "nom_fichier": "f.wav", "temps_debut": 1.0, "temps_fin": 3.0},
        ]
        row_keys, n_unmapped = build_row_key_map(rows, col_idx, entries)
        assert row_keys == {0: "d1#0", 1: "d1#1"} and n_unmapped == 0


class TestRegistryRollup:
    """Lot 6 — rollup envoi identifications (schéma v3), sans perte pour l'existant."""

    def _reg(self, tmp_path):
        from registry import Registry
        return Registry(tmp_path)

    def _add(self, reg, tmp_path, sid="s1"):
        reg.upsert_session({"id": sid, "canonical_name": sid,
                            "session_path": str(tmp_path / sid)})
        return sid

    def test_columns_default_zero_and_writable(self, tmp_path):
        reg = self._reg(tmp_path)
        sid = self._add(reg, tmp_path)
        row = reg.get_session(sid)
        assert row["ident_pushed"] == 0 and row["ident_total"] == 0
        reg.update_fields(sid, {"ident_pushed": 3, "ident_total": 5})
        row = reg.get_session(sid)
        assert row["ident_pushed"] == 3 and row["ident_total"] == 5

    def test_rescan_does_not_reset_rollup(self, tmp_path):
        reg = self._reg(tmp_path)
        sid = self._add(reg, tmp_path)
        reg.update_fields(sid, {"ident_pushed": 4, "ident_total": 6})
        self._add(reg, tmp_path)                    # re-scan (upsert existant)
        row = reg.get_session(sid)
        assert row["ident_pushed"] == 4 and row["ident_total"] == 6

    def test_migration_idempotent_preserves_data(self, tmp_path):
        from registry import Registry
        reg = self._reg(tmp_path)
        self._add(reg, tmp_path)
        reg2 = Registry(tmp_path)                   # ré-ouverture → migration idempotente
        cols = {r[1] for r in reg2._get_conn().execute("PRAGMA table_info(sessions)")}
        assert {"ident_pushed", "ident_total"} <= cols
        assert reg2.get_session("s1") is not None    # données préservées


class TestActivityReference:
    """Référentiel d'activité Vigie-Chiro (Bas et al. 2020) — combiné + repli."""

    def test_load_real_reference(self):
        from activity_reference import load_reference
        ref = load_reference()
        row = ref[("national", "toutes", "pippip")]   # clé (referentiel, saison, code)
        assert row["q25"] == 13 and row["q98"] == 3737

    def test_classify_boundaries(self):
        from activity_reference import classify
        row = {"q25": 13, "q75": 411, "q98": 3737}
        assert classify(5, row) == "Faible"
        assert classify(13, row) == "Moyenne"        # ≥ Q25
        assert classify(411, row) == "Forte"         # ≥ Q75
        assert classify(3737, row) == "Très forte"   # ≥ Q98

    def test_region_from_dept_and_site(self):
        from activity_reference import region_for_dept, region_for_site
        assert region_for_dept("34") == "Occitanie"
        assert region_for_dept("2A") == "Corse"
        assert region_for_dept("1") == "Auvergne-Rhone-Alpes"   # zero-pad
        assert region_for_site("340123") == "Occitanie"          # 2 premiers = dept
        assert region_for_dept("999") is None

    def test_season_from_date(self):
        from datetime import datetime
        from activity_reference import season_for_date
        assert season_for_date(datetime(2026, 5, 1)) == "printemps"
        assert season_for_date(datetime(2026, 7, 15)) == "ete"
        assert season_for_date(datetime(2026, 10, 1)) == "automne"
        assert season_for_date(datetime(2026, 12, 25)) == "toutes"   # hors fenêtres
        assert season_for_date(None) == "toutes"

    def test_activity_for_real_region(self):
        from activity_reference import load_reference, activity_for
        ref = load_reference()
        a = activity_for("Pippip", 100, ref, saison="automne", region="Occitanie")
        assert a["referentiel"] == "region:Occitanie"   # Occitanie automne = fiable
        assert a["classe"] == "Forte"                    # Q75=87 ≤ 100 < Q98=1999
        assert activity_for("zzzzzz", 10, ref) is None   # code hors référentiel

    def test_fallback_prefers_reliable_national_over_weak_region(self):
        from activity_reference import activity_for
        # région peu fiable ('Faible') vs national fiable : on garde le national.
        ref = {
            ("region:Corse", "automne", "barbar"):
                {"q25": 1, "q75": 5, "q98": 50, "nbocc": 10, "confiance": "Faible"},
            ("national", "automne", "barbar"):
                {"q25": 2, "q75": 16, "q98": 181, "nbocc": 4000, "confiance": "Tres bonne"},
        }
        a = activity_for("barbar", 20, ref, saison="automne", region="Corse")
        assert a["referentiel"] == "national" and a["fiable"] is True

    def test_annotate_synthesis_with_context(self):
        from activity_reference import load_reference, annotate_synthesis
        ref = load_reference()
        synth = {"species": [
            {"taxon": "pippip", "groupe": "chiros", "n_contacts": 5000},
            {"taxon": "noise", "groupe": "noise", "n_contacts": 999},
        ]}
        annotate_synthesis(synth, ref, saison="ete", region="Occitanie")
        assert synth["species"][0]["activite"]["classe"] in (
            "Faible", "Moyenne", "Forte", "Très forte")
        assert synth["species"][1]["activite"] is None   # non-chiro

    def test_missing_reference_degrades(self, tmp_path):
        from activity_reference import load_reference
        assert load_reference(tmp_path / "nope.csv") == {}


class TestSynthesisValidatedTotal:
    """Enrichissement synthèse : contacts validés vs total + richesse."""

    def test_validated_vs_total_and_richesse(self):
        from synthesis import compute_night_synthesis
        headers = ["nom du fichier", "tadarida_taxon", "observateur_taxon"]
        rows = [
            ["f1.wav", "pippip", "pippip"],   # validé
            ["f2.wav", "pippip", ""],          # non validé (Tadarida seul)
            ["f3.wav", "barbar", "barbar"],    # validé
            ["f4.wav", "noise", ""],           # bruit
        ]
        s = compute_night_synthesis(headers, rows)
        assert s["total_contacts"] == 4
        assert s["validated_contacts"] == 2       # f1 + f3
        assert s["richesse_chiros"] == 2           # pippip + barbar
        assert s["richesse_totale"] == 2           # noise exclu


if __name__ == "__main__":
    # Permet de lancer directement : python tests/test_core.py
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
