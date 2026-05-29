"""
Exact plot geometry via Shapely.
Builds the plot polygon (from explicit corner points, or a rectangle from width x depth)
and computes the buildable polygon by offsetting each edge inward by its setback
(front / side / rear) using half-plane intersection. Robust for convex plots; a good
approximation for mildly concave ones.
"""
from __future__ import annotations
import math
from shapely.geometry import Polygon, LineString


def rect_coords(width: float, depth: float) -> list[list[float]]:
    """Rectangle with the FRONT edge at the bottom (edge index 0)."""
    return [[0.0, 0.0], [width, 0.0], [width, depth], [0.0, depth]]


def _ensure_ccw(coords):
    p = Polygon(coords)
    if p.exterior.is_ccw:
        return coords
    return coords[::-1]


def _inward_normal(p1, p2, centroid):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    L = math.hypot(dx, dy) or 1e-9
    n1 = (-dy / L, dx / L)
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    # pick normal pointing toward centroid (inward)
    if (centroid[0] - mx) * n1[0] + (centroid[1] - my) * n1[1] < 0:
        return (-n1[0], -n1[1])
    return n1


def _clip_halfplane(poly: Polygon, p1, p2, normal, dist: float) -> Polygon:
    if dist <= 0:
        return poly
    BIG = 1e5
    ax, ay = p1[0] + normal[0] * dist, p1[1] + normal[1] * dist
    bx, by = p2[0] + normal[0] * dist, p2[1] + normal[1] * dist
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1e-9
    ux, uy = dx / L, dy / L
    a2 = (ax - ux * BIG, ay - uy * BIG)
    b2 = (bx + ux * BIG, by + uy * BIG)
    a3 = (a2[0] + normal[0] * BIG, a2[1] + normal[1] * BIG)
    b3 = (b2[0] + normal[0] * BIG, b2[1] + normal[1] * BIG)
    half = Polygon([a2, b2, b3, a3])
    return poly.intersection(half)


def buildable(coords, front_idx: int, fsb: float, ssb: float, rsb: float, sides: str = "either"):
    """Return (buildable_coords, area_sqm, plot_area_sqm). front_idx = edge abutting road.
    sides='one' applies the side setback to a single side edge only (narrow-plot rule)."""
    coords = _ensure_ccw([list(c) for c in coords])
    plot = Polygon(coords)
    cen = (plot.centroid.x, plot.centroid.y)
    n = len(coords)
    edges = [(coords[i], coords[(i + 1) % n]) for i in range(n)]
    # rear edge = the one whose midpoint is farthest from the front edge midpoint
    fmid = ((edges[front_idx][0][0] + edges[front_idx][1][0]) / 2,
            (edges[front_idx][0][1] + edges[front_idx][1][1]) / 2)
    def mid(e): return ((e[0][0] + e[1][0]) / 2, (e[0][1] + e[1][1]) / 2)
    dists = [math.dist(fmid, mid(e)) for e in edges]
    rear_idx = max(range(n), key=lambda i: dists[i])
    side_idxs = [i for i in range(n) if i not in (front_idx, rear_idx)]
    one_side_idx = side_idxs[0] if side_idxs else None

    region = plot
    for i, (p1, p2) in enumerate(edges):
        if i == front_idx:
            d = fsb
        elif i == rear_idx:
            d = rsb
        else:
            d = ssb if (sides == "either" or i == one_side_idx) else 0.0
        normal = _inward_normal(p1, p2, cen)
        region = _clip_halfplane(region, p1, p2, normal, d)
        if region.is_empty:
            return [], 0.0, round(plot.area, 2)

    if region.geom_type != "Polygon" or region.is_empty:
        return [], 0.0, round(plot.area, 2)
    bcoords = [[round(x, 3), round(y, 3)] for x, y in region.exterior.coords[:-1]]
    return bcoords, round(region.area, 2), round(plot.area, 2)


def edge_setbacks(plot_coords, building_coords, front_idx: int) -> dict:
    """Provided setbacks (margins) = gap from the building polygon to each plot edge.
    Returns {front, side, rear, per_edge:[...]} in metres."""
    coords = _ensure_ccw([list(c) for c in plot_coords])
    plot = Polygon(coords)
    bld = Polygon(building_coords)
    n = len(coords)
    edges = [(coords[i], coords[(i + 1) % n]) for i in range(n)]
    fmid = ((edges[front_idx][0][0] + edges[front_idx][1][0]) / 2,
            (edges[front_idx][0][1] + edges[front_idx][1][1]) / 2)
    def mid(e): return ((e[0][0] + e[1][0]) / 2, (e[0][1] + e[1][1]) / 2)
    rear_idx = max(range(n), key=lambda i: math.dist(fmid, mid(edges[i])))
    per = [round(bld.distance(LineString(e)), 3) for e in edges]
    side_idxs = [i for i in range(n) if i not in (front_idx, rear_idx)]
    return {
        "front": per[front_idx], "rear": per[rear_idx],
        "side": round(min(per[i] for i in side_idxs), 3) if side_idxs else 0.0,
        "per_edge": per, "rear_idx": rear_idx,
        "building_inside_plot": plot.contains(bld) or plot.buffer(0.05).contains(bld),
    }
