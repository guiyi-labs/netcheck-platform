from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.schemas.common import Response
from app.schemas.topology import TopologyLink, TopologyNode, TopologyOut

router = APIRouter(
    prefix="/api/topology",
    tags=["topology"],
    dependencies=[Depends(get_current_user)],
)

STATUS_COLORS = {
    "online": "#16a34a",
    "offline": "#dc2626",
    "warning": "#f59e0b",
    "unknown": "#64748b",
}


@router.get("", response_model=Response[TopologyOut])
def get_topology(db: Session = Depends(get_db)) -> Response[TopologyOut]:
    assets = db.query(Asset).order_by(Asset.id).all()
    nodes = [TopologyNode(id="core-network", label="core-network", category="core", status="online", color="#2563eb")]
    links = []
    for asset in assets:
        node_id = f"asset-{asset.id}"
        nodes.append(
            TopologyNode(
                id=node_id,
                label=asset.name,
                category=asset.asset_type,
                status=asset.status,
                color=STATUS_COLORS.get(asset.status, STATUS_COLORS["unknown"]),
            )
        )
        links.append(TopologyLink(source="core-network", target=node_id))
    return Response(data=TopologyOut(nodes=nodes, links=links))
