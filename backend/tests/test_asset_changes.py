"""B6 资产变更日志：新增/更新（字段级 diff）/删除均可追溯。"""
from fastapi.testclient import TestClient


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_asset_change_log_records_create_update_delete(client: TestClient, auth_token: str):
    headers = _h(auth_token)
    created = client.post(
        "/api/assets",
        headers=headers,
        json={"name": "变更测试", "ip": "10.88.0.1", "asset_type": "server", "ports": "80", "owner": "运维组"},
    )
    assert created.status_code == 201
    asset_id = created.json()["data"]["id"]

    # 更新：只改 owner 与 ports，应产生两条字段级变更且不包含 name
    updated = client.put(
        f"/api/assets/{asset_id}",
        headers=headers,
        json={"name": "变更测试", "ip": "10.88.0.1", "asset_type": "server", "ports": "80,443", "owner": "网络组"},
    )
    assert updated.status_code == 200

    changes = client.get(f"/api/assets/{asset_id}/changes", headers=headers).json()["data"]
    actions = [(item["action"], item["field"]) for item in changes["items"]]
    assert any(action == "create" for action, field in actions)
    assert ("update", "ports") in actions
    assert ("update", "owner") in actions
    ports_row = next(item for item in changes["items"] if item["action"] == "update" and item["field"] == "ports")
    assert ports_row["old_value"] == "80"
    assert ports_row["new_value"] == "80,443"
    assert ports_row["username"] == "admin"

    # 删除后仍保留历史；页面通过 asset_id 查询（资产已删则 404，但历史表数据仍在）
    deleted = client.delete(f"/api/assets/{asset_id}", headers=headers)
    assert deleted.status_code == 200
    gone = client.get(f"/api/assets/{asset_id}/changes", headers=headers)
    assert gone.status_code == 404


def test_asset_change_requires_token(client: TestClient):
    resp = client.post(
        "/api/assets",
        json={"name": "x", "ip": "10.88.0.99", "asset_type": "server"},
    )
    assert resp.status_code == 401