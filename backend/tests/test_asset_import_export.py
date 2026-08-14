"""B2 资产批量导入/导出 CSV。"""
import io

from fastapi.testclient import TestClient


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_export_csv_contains_assets(client: TestClient, auth_token: str):
    resp = client.get("/api/assets/export", headers=_h(auth_token))
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    text = resp.content.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].startswith("name,ip")
    assert any("正常Web服务" in line for line in lines)
    assert any("demo-web-ok" in line for line in lines)


def test_import_csv_creates_assets_and_reports_skips(client: TestClient, auth_token: str):
    h = _h(auth_token)
    csv_text = (
        "name,ip,asset_type,ports,status,location\n"
        "批量资产A,10.99.0.1,server,80,online,机房A\n"
        "批量资产B,10.99.0.2,web_service,443,unknown,机房A\n"
        ",10.99.0.3,server,,\n"
        "重复IP,10.99.0.1,server,80,,\n"
    )
    resp = client.post(
        "/api/assets/import",
        headers=h,
        files={"file": ("assets.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["imported"] == 2
    assert data["skipped"] == 2

    listing = client.get("/api/assets", headers=h, params={"page_size": 100}).json()["data"]
    names = {item["name"] for item in listing["items"]}
    assert {"批量资产A", "批量资产B"}.issubset(names)
    asset_a = next(item for item in listing["items"] if item["name"] == "批量资产A")
    assert asset_a["status"] == "online"


def test_import_requires_csv_and_required_fields(client: TestClient, auth_token: str):
    h = _h(auth_token)
    bad_type = client.post("/api/assets/import", headers=h, files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")})
    assert bad_type.status_code == 422

    missing_fields = client.post(
        "/api/assets/import",
        headers=h,
        files={"file": ("a.csv", io.BytesIO("only_name,value\n".encode()), "text/csv")},
    )
    assert missing_fields.status_code == 422