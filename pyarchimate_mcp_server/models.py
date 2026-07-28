from pydantic import BaseModel, Field


class ElementDetail(BaseModel):
    id: str = Field(..., description="Unique identifier of the ArchiMate element.")
    name: str = Field(..., description="Name of the ArchiMate element.")
    type: str = Field(..., description="Standardized ArchiMate type of the element.")
    description: str | None = Field(
        None,
        description="Textual description of the element.",
    )
    properties: dict[str, str] = Field(
        default_factory=dict,
        description="Key-value pairs of custom properties.",
    )
    folder: str | None = Field(None, description="Conceptual folder path.")
    incoming_relationship_ids: list[str] = Field(default_factory=list)
    outgoing_relationship_ids: list[str] = Field(default_factory=list)


class RelationshipDetail(BaseModel):
    id: str = Field(..., description="Unique identifier of the relationship.")
    name: str | None = Field(None, description="Name of the relationship.")
    type: str = Field(
        ...,
        description="Standardized ArchiMate type of the relationship.",
    )
    description: str | None = Field(None, description="Textual description.")
    properties: dict[str, str] = Field(
        default_factory=dict,
        description="Key-value pairs of custom properties.",
    )
    access_type: str | None = Field(
        None,
        description="Access relationship modifier, such as Read or ReadWrite.",
    )
    influence_strength: str | None = Field(
        None,
        description="Influence relationship strength, such as ++ or 7.",
    )
    is_directed: bool | None = Field(
        None,
        description="Association relationship directedness flag.",
    )
    source_element_id: str = Field(...)
    target_element_id: str = Field(...)


class ViewNode(BaseModel):
    id: str = Field(..., description="Unique ID of this visual node.")
    element_id: str | None = Field(None, description="ID of the ArchiMate element.")
    element_name: str | None = Field(None, description="Name of the ArchiMate element.")
    element_type: str | None = Field(None, description="Type of the ArchiMate element.")
    parent_node_id: str | None = Field(
        None,
        description="Parent visual node ID when this node is nested in a group.",
    )
    note_text: str | None = Field(
        None,
        description="Text of a diagram-only note node; None for element nodes.",
    )
    x: int
    y: int
    width: int
    height: int


class ViewConnection(BaseModel):
    id: str = Field(..., description="Unique ID of this visual connection.")
    relationship_id: str | None = Field(
        None,
        description="ID of the ArchiMate relationship.",
    )
    relationship_type: str | None = Field(
        None,
        description="Type of the ArchiMate relationship.",
    )
    source_node_id: str
    target_node_id: str


class ViewDetail(BaseModel):
    id: str
    name: str
    description: str | None = None
    properties: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, str | bool | list[str]] = Field(default_factory=dict)
    primary_viewpoint: str | None = None
    nodes: list[ViewNode]
    connections: list[ViewConnection]
