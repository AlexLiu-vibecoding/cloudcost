"""Tests for anomaly detection."""

from cloudcost.core.anomaly import AnomalyDetector


def test_generate_daily_costs():
    detector = AnomalyDetector()
    data = detector.generate_daily_costs(monthly_cost=3000, days=30)

    assert len(data) == 30 * 5  # 30 days × 5 services
    assert all("date" in d for d in data)
    assert all("cost" in d for d in data)
    assert all("service" in d for d in data)
    assert all(d["cost"] >= 0 for d in data)


def test_detect_no_anomalies():
    detector = AnomalyDetector(zscore_threshold=5.0)
    data = detector.generate_daily_costs(monthly_cost=1000, days=30)
    anomalies = detector.detect(data)

    # With high threshold, should be few or no anomalies
    assert len(anomalies) < 5  # Very few with z=5 threshold


def test_detect_with_anomalies():
    detector = AnomalyDetector(zscore_threshold=2.0)
    data = detector.generate_daily_costs(
        monthly_cost=5000,
        days=30,
        anomaly_days=[10, 11],
        anomaly_multiplier=5.0,
    )
    anomalies = detector.detect(data)

    # Should detect the injected anomalies
    assert len(anomalies) > 0
    # Check anomaly structure
    for a in anomalies:
        assert "date" in a
        assert "service" in a
        assert "cost" in a
        assert "expected_cost" in a
        assert "method" in a
        assert "severity" in a
        assert "estimated_monthly_savings_usd" in a


def test_stddev():
    detector = AnomalyDetector()
    std = detector._stddev([1.0, 2.0, 3.0], 2.0)
    assert std == 1.0  # Known result
