from adult_media_flagger.config import Thresholds


def test_decision_for_score():
    thresholds = Thresholds(safe_max=0.35, adult_min=0.8)
    assert thresholds.decision_for_score(0.1) == "safe"
    assert thresholds.decision_for_score(0.35) == "review"
    assert thresholds.decision_for_score(0.79) == "review"
    assert thresholds.decision_for_score(0.8) == "adult_likely"
    assert thresholds.decision_for_score(None) == "error"

