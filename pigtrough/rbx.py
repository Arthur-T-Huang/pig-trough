"""Describe Roblox instances in Python and serialize them as Rojo `.model.json` files.

Encodings were checked against Rojo 7.7: most properties use Rojo's implicit
JSON form (Vector3 -> [x, y, z], Color3 -> [r, g, b] in 0..1, enums -> item
name, Tags -> list of strings), but CFrame and UDim2 must use the explicit
form and attributes live in a top-level `attributes` key, not in `properties`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

Vec3 = tuple[float, float, float]


def num(x: float) -> float | int:
    """Round for stable, readable JSON (ints stay ints, -0.0 becomes 0)."""
    v = round(float(x), 4)
    if v == 0:
        return 0
    return int(v) if v.is_integer() else v


def vec(v) -> list:
    return [num(c) for c in v]


def rotation_rows(rx: float, ry: float, rz: float) -> list[list[float]]:
    """Row-major rotation matrix matching Roblox `CFrame.Angles(rx, ry, rz)` (degrees)."""
    rx, ry, rz = (math.radians(a) for a in (rx, ry, rz))
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    # CFrame.Angles applies Z, then Y, then X: R = Rx * Ry * Rz
    return [
        vec((cy * cz, -cy * sz, sy)),
        vec((cx * sz + sx * sy * cz, cx * cz - sx * sy * sz, -sx * cy)),
        vec((sx * sz - cx * sy * cz, sx * cz + cx * sy * sz, cx * cy)),
    ]


def cframe(position: Vec3, rotation: Vec3 = (0, 0, 0)) -> dict:
    return {"CFrame": {"position": vec(position), "orientation": rotation_rows(*rotation)}}


def udim2(x_scale: float, x_offset: float, y_scale: float, y_offset: float) -> dict:
    """UDim2 has no implicit form in Rojo; it must be explicit."""
    return {"UDim2": [[num(x_scale), num(x_offset)], [num(y_scale), num(y_offset)]]}


def vector3(v: Vec3) -> dict:
    """Explicit Vector3, required for attribute values."""
    return {"Vector3": vec(v)}


def _encode(value: Any) -> Any:
    if isinstance(value, bool) or isinstance(value, str) or value is None:
        return value
    if isinstance(value, (int, float)):
        return num(value)
    if isinstance(value, (tuple, list)):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    raise TypeError(f"Cannot encode {type(value).__name__} as a Rojo value")


@dataclass
class Instance:
    class_name: str
    name: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    children: list[Instance] = field(default_factory=list)

    def add(self, child: Instance) -> Instance:
        self.children.append(child)
        return child

    def descendants(self):
        for child in self.children:
            yield child
            yield from child.descendants()

    def to_model_json(self, root: bool = False) -> dict:
        """Serialize to Rojo's model.json shape. The root takes its name from the file."""
        out: dict[str, Any] = {}
        if not root:
            out["name"] = self.name or self.class_name
        out["className"] = self.class_name
        props = dict(self.properties)
        if self.tags:
            props["Tags"] = list(self.tags)
        if props:
            out["properties"] = _encode(props)
        if self.attributes:
            out["attributes"] = _encode(self.attributes)
        if self.children:
            out["children"] = [c.to_model_json() for c in self.children]
        return out


def model(name: str, *children: Instance) -> Instance:
    return Instance("Model", name, children=list(children))


def folder(name: str, *children: Instance) -> Instance:
    return Instance("Folder", name, children=list(children))


def part(
    name: str,
    size: Vec3,
    position: Vec3,
    color: list[float],
    material: str = "SmoothPlastic",
    rotation: Vec3 = (0, 0, 0),
    class_name: str = "Part",
    tags: list[str] | None = None,
    attributes: dict[str, Any] | None = None,
    **properties: Any,
) -> Instance:
    """An anchored part centred at `position` (override with Anchored=False)."""
    props = {
        "Anchored": True,
        "Size": size,
        "CFrame": cframe(position, rotation),
        "Color": color,
        "Material": material,
    }
    props.update(properties)
    return Instance(class_name, name, props, dict(attributes or {}), list(tags or []))


def pad(name: str, size: Vec3, top_center: Vec3, color, material="SmoothPlastic", **kw) -> Instance:
    """A part positioned by the centre of its top face, the natural anchor for walkable surfaces."""
    x, y, z = top_center
    return part(name, size, (x, y - size[1] / 2, z), color, material, **kw)
