"""D2 Prometheus /metrics：无鉴权可抓取，覆盖资产/任务/运行/结果/告警核心指标。"""
from fastapi.testclient import TestClient


def test_health_requires_no_token(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_metrics_unauthenticated_and_text_format(client: TestClient):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    text = resp.text
    assert "# HELP netcheck_assets_total" in text
    assert "netcheck_assets_total 12" in text  # 12 条演示资产
    assert "# HELP netcheck_tasks_total" in text
    assert "# HELP netcheck_alerts_total" in text
    # Prometheus 标签语法：TYPE 用裸指标名，样例行携带 label
    assert '# TYPE netcheck_assets_by_status gauge' in text
    assert 'netcheck_assets_by_status{label="online"} ' in text
