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


if __name__ == "__main__":
    # Permet de lancer directement : python tests/test_core.py
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
