from pydantic import BaseModel


class TopologyNode(BaseModel):
    id: str
    label: str
    category: str
    status: str
    color: str


class TopologyLink(BaseModel):
    source: str
    target: str


class TopologyOut(BaseModel):
    nodes: list[TopologyNode]
    links: list[TopologyLink]
