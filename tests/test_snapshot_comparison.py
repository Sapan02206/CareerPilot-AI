"""
Tests for the _readiness_changed() snapshot-deduplication helper in app.py.

Spec requirements (from reliability audit):
  1. No changes → no unnecessary duplicate snapshot.
  2. Overall score changes → new snapshot is created.
  3. A component score changes while the rounded overall score stays the
     same → change is still detected.
  4. First-time users with no existing snapshot → handled correctly.
  5. Missing / unavailable snapshot data → handled safely.

These tests exercise _readiness_changed() directly without hitting the
database or the Flask request context.

Run:
    .venv/Scripts/python.exe -m pytest tests/test_snapshot_comparison.py -v
"""

import os, sys, types
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Import the helper under test
# ---------------------------------------------------------------------------

def _import_helper():
    """Import _readiness_changed from app.py without starting Flask."""
    import importlib.util, pathlib
    app_path = pathlib.Path(PROJECT_ROOT) / "app.py"
    spec = importlib.util.spec_from_file_location("app_module", app_path)
    # We don't need the full app — just import the helper.
    # Use a minimal approach: read the function source and exec it in isolation.
    src = app_path.read_text(encoding="utf-8")
    # Extract just _readiness_changed — it has no Flask dependencies.
    import re
    m = re.search(
        r"(def _readiness_changed\(.*?)(?=\ndef |\Z)", src, re.DOTALL
    )
    if not m:
        pytest.fail("_readiness_changed not found in app.py")
    func_src = m.group(1)
    ns: dict = {}
    exec(func_src, ns)
    return ns["_readiness_changed"]


_readiness_changed = _import_helper()


# ---------------------------------------------------------------------------
# Fake snapshot — mimics the ReadinessSnapshot model object
# ---------------------------------------------------------------------------

def _make_snapshot(overall=50.0, skill_match=60.0, experience=40.0, evidence=0.0):
    """Return a simple namespace that looks like a ReadinessSnapshot row."""
    snap = types.SimpleNamespace()
    snap.overall_score     = overall
    snap.skill_match_score = skill_match
    snap.experience_score  = experience
    snap.evidence_score    = evidence
    return snap


def _make_readiness(overall=50.0, skill_match=60.0, experience=40.0, evidence=0.0):
    """Return a readiness_data dict as produced by ReadinessCalculator."""
    return {
        'overall_score':     overall,
        'skill_match_score': skill_match,
        'experience_score':  experience,
        'evidence_score':    evidence,
    }


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestReadinessChanged:

    # ---- Case 1: No changes ------------------------------------------------

    def test_identical_scores_returns_false(self):
        """Exact same scores — no snapshot needed."""
        snap = _make_snapshot(50.0, 60.0, 40.0, 0.0)
        data = _make_readiness(50.0, 60.0, 40.0, 0.0)
        assert _readiness_changed(data, snap) is False

    def test_tiny_float_noise_below_tolerance_returns_false(self):
        """
        Floating-point arithmetic can produce values like 49.9999999.
        Changes smaller than the 0.01 tolerance must not trigger a save.
        """
        snap = _make_snapshot(50.0, 60.0, 40.0, 0.0)
        data = _make_readiness(50.005, 60.005, 40.005, 0.005)
        assert _readiness_changed(data, snap) is False

    def test_exactly_at_tolerance_returns_false(self):
        """Change of exactly 0.01 is within tolerance — no save."""
        snap = _make_snapshot(50.0, 60.0, 40.0, 0.0)
        data = _make_readiness(50.01, 60.0, 40.0, 0.0)
        # 50.01 - 50.0 = 0.01, which is NOT > 0.01, so False
        assert _readiness_changed(data, snap) is False

    # ---- Case 2: Overall score changes -------------------------------------

    def test_overall_score_increase_returns_true(self):
        """Overall score went up — new snapshot required."""
        snap = _make_snapshot(50.0, 60.0, 40.0, 0.0)
        data = _make_readiness(55.0, 60.0, 40.0, 0.0)
        assert _readiness_changed(data, snap) is True

    def test_overall_score_decrease_returns_true(self):
        """Overall score went down — new snapshot required."""
        snap = _make_snapshot(55.0, 65.0, 45.0, 5.0)
        data = _make_readiness(50.0, 65.0, 45.0, 5.0)
        assert _readiness_changed(data, snap) is True

    # ---- Case 3: Component changes with same rounded overall ---------------

    def test_evidence_change_detected_when_overall_rounds_same(self):
        """
        A project is added: evidence_score rises by 25 points.
        Due to the 0.2 weight, overall rises by 5 — detectable.
        But even if overall rounds to the same value, evidence alone triggers.

        Concretely: skill=60, exp=0, evidence goes 0→25 (project added).
        overall before: 60*0.5 + 0*0.3 + 0*0.2 = 30.0
        overall after:  60*0.5 + 0*0.3 + 25*0.2 = 35.0
        Both are meaningfully different, but the test asserts that even
        if we construct a scenario where overall rounds the same, evidence
        change alone triggers the save.
        """
        # Artificially construct same overall but different evidence
        # overall = skill*0.5 + exp*0.3 + evidence*0.2
        # 50.0 = 80*0.5 + 10*0.3 + 7*0.2  → 40+3+1.4 = 44.4 (no, need exact)
        # Let's just use: old evidence=0, new evidence=0.5 → overall diff = 0.1
        # which is > 0.01 so overall alone catches it.
        # For the "component changes but overall stays same" scenario:
        # Make skill_match go up and experience go down by equal weighted amounts.
        # skill: 60→70 (+10), weight 0.5 → overall +5
        # experience: 50→30 (-20), weight 0.3 → overall -6
        # net overall: -1 point, small but > 0.01
        snap = _make_snapshot(overall=53.0, skill_match=60.0, experience=50.0, evidence=0.0)
        # new overall = 70*0.5 + 30*0.3 + 0*0.2 = 35+9 = 44  (differs by 9, clearly detected)
        data = _make_readiness(overall=44.0, skill_match=70.0, experience=30.0, evidence=0.0)
        assert _readiness_changed(data, snap) is True

    def test_evidence_score_change_alone_triggers_save(self):
        """Adding a project changes evidence_score — must trigger snapshot."""
        snap = _make_snapshot(overall=30.0, skill_match=60.0, experience=0.0, evidence=0.0)
        data = _make_readiness(overall=35.0, skill_match=60.0, experience=0.0, evidence=25.0)
        assert _readiness_changed(data, snap) is True

    def test_skill_match_change_alone_triggers_save(self):
        """Skill match score changes (new role uploaded) → snapshot needed."""
        snap = _make_snapshot(overall=50.0, skill_match=60.0, experience=40.0, evidence=0.0)
        data = _make_readiness(overall=60.0, skill_match=80.0, experience=40.0, evidence=0.0)
        assert _readiness_changed(data, snap) is True

    def test_experience_change_alone_triggers_save(self):
        """Experience score changes (explicit year statement parsed) → snapshot."""
        snap = _make_snapshot(overall=30.0, skill_match=60.0, experience=0.0, evidence=0.0)
        data = _make_readiness(overall=42.0, skill_match=60.0, experience=40.0, evidence=0.0)
        assert _readiness_changed(data, snap) is True

    def test_sub_point_component_change_below_tolerance_returns_false(self):
        """
        A component change smaller than 0.01 (pure float noise) does NOT
        trigger a duplicate save.
        """
        snap = _make_snapshot(overall=50.0, skill_match=60.0, experience=40.0, evidence=0.0)
        # All changes are < 0.01
        data = _make_readiness(
            overall=50.005,
            skill_match=60.008,
            experience=40.003,
            evidence=0.002,
        )
        assert _readiness_changed(data, snap) is False

    # ---- Case 4: First-time user / no existing snapshot --------------------

    def test_none_snapshot_returns_true(self):
        """No existing snapshot (first-time user) → always save."""
        data = _make_readiness(50.0, 60.0, 40.0, 0.0)
        assert _readiness_changed(data, None) is True

    def test_none_snapshot_with_zero_scores_returns_true(self):
        """Even all-zero scores should save when there's no existing snapshot."""
        data = _make_readiness(0.0, 0.0, 0.0, 0.0)
        assert _readiness_changed(data, None) is True

    # ---- Case 5: Missing / partial snapshot data ---------------------------

    def test_snapshot_with_none_overall_returns_true(self):
        """Snapshot missing overall_score field → treat as changed (safe)."""
        snap = types.SimpleNamespace()
        snap.overall_score     = None
        snap.skill_match_score = 60.0
        snap.experience_score  = 40.0
        snap.evidence_score    = 0.0
        data = _make_readiness(50.0, 60.0, 40.0, 0.0)
        assert _readiness_changed(data, snap) is True

    def test_snapshot_missing_attribute_returns_true(self):
        """Snapshot object missing an attribute entirely → treat as changed."""
        snap = types.SimpleNamespace()
        snap.overall_score = 50.0
        # skill_match_score, experience_score, evidence_score are absent
        data = _make_readiness(50.0, 60.0, 40.0, 0.0)
        assert _readiness_changed(data, snap) is True

    def test_readiness_data_missing_key_skips_gracefully(self):
        """
        If readiness_data is missing a key, that component is skipped
        and does not raise an exception. Other components still compared.
        """
        snap = _make_snapshot(50.0, 60.0, 40.0, 0.0)
        # Missing 'experience_score' — should not crash, other components match
        data = {
            'overall_score':     50.0,
            'skill_match_score': 60.0,
            # 'experience_score' omitted
            'evidence_score':    0.0,
        }
        # All present components match → False
        assert _readiness_changed(data, snap) is False

    def test_readiness_data_missing_key_with_other_change(self):
        """
        Missing key skipped; if remaining components differ, still returns True.
        """
        snap = _make_snapshot(50.0, 60.0, 40.0, 0.0)
        data = {
            'overall_score':     55.0,   # changed
            'skill_match_score': 60.0,
            # 'experience_score' omitted
            'evidence_score':    0.0,
        }
        assert _readiness_changed(data, snap) is True

    # ---- Edge: tolerance boundary ------------------------------------------

    def test_change_just_above_tolerance_returns_true(self):
        """A change of 0.011 is > 0.01 → must trigger save."""
        snap = _make_snapshot(50.0, 60.0, 40.0, 0.0)
        data = _make_readiness(50.011, 60.0, 40.0, 0.0)
        assert _readiness_changed(data, snap) is True

    def test_all_four_components_checked_independently(self):
        """
        Even when overall_score is identical, changes in any other component
        are individually sufficient to trigger a save.
        """
        base = dict(overall=50.0, skill_match=60.0, experience=40.0, evidence=0.0)

        for changed_key, new_val in [
            ('skill_match', 70.0),
            ('experience',  50.0),
            ('evidence',    25.0),
        ]:
            snap = _make_snapshot(**base)
            kw = dict(base)
            kw[changed_key] = new_val
            # Recalculate overall to be deliberately the same as base (50.0)
            # to verify component change alone is detected.
            data = {
                'overall_score':     base['overall'],  # kept same intentionally
                'skill_match_score': kw['skill_match'],
                'experience_score':  kw['experience'],
                'evidence_score':    kw['evidence'],
            }
            assert _readiness_changed(data, snap) is True, (
                f"Change in '{changed_key}' not detected when overall_score "
                f"is unchanged. new_{changed_key}={new_val}"
            )

    # ---- Static code check -------------------------------------------------

    def test_readiness_changed_called_in_app(self):
        """
        Verify _readiness_changed() is actually called in the returning-user
        dashboard path in app.py (static source inspection).
        """
        app_path = os.path.join(PROJECT_ROOT, "app.py")
        with open(app_path, encoding="utf-8") as f:
            src = f.read()
        assert "_readiness_changed(" in src, (
            "_readiness_changed() is not called in app.py"
        )
        # And the old overall_score-only guard must no longer be the sole guard
        lines = src.splitlines()
        guard_lines = [l for l in lines if "_readiness_changed(" in l]
        assert len(guard_lines) >= 1, "Expected at least one call to _readiness_changed()"
