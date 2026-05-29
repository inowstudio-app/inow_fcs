"""
PreDCR-style automatic scrutiny: from an imported plot + building polygon, auto-derive
the PROPOSED values (setbacks, footprint, coverage, built-up) and check them against the
permissible envelope -> a Required/Provided/Status scrutiny report.
"""
from __future__ import annotations
from shapely.geometry import Polygon

from .feasibility import Plot
from .compliance import Proposal, check_compliance
from .geometry import edge_setbacks


def run_scrutiny(plot_coords, building_coords, front_edge_idx: int, road_width_m: float,
                 height_m: float, floors: int, dwellings: int = 1,
                 use: str = "residential", area_class: str = "corporation_municipal") -> dict:
    plot_poly = Polygon(plot_coords)
    plot_area = round(plot_poly.area, 2)
    footprint = round(Polygon(building_coords).area, 2)
    sb = edge_setbacks(plot_coords, building_coords, front_edge_idx)
    built_up = round(footprint * max(1, floors), 2)
    minx, miny, maxx, maxy = plot_poly.bounds

    plot = Plot(area_sqm=plot_area, width_m=round(maxx - minx, 2), depth_m=round(maxy - miny, 2),
                abutting_road_width_m=road_width_m, use=use, parking_area_class=area_class,
                dwellings=dwellings, proposed_height_m=height_m,
                polygon=plot_coords, front_edge_idx=front_edge_idx)
    prop = Proposal(height_m=height_m, dwellings=dwellings,
                    front_setback_m=sb["front"], side_setback_m=sb["side"], rear_setback_m=sb["rear"],
                    built_up_area_sqm=built_up, footprint_area_sqm=footprint,
                    car_parking_provided=None)
    rep = check_compliance(plot, prop)
    rep["mode"] = "pre-dcr-scrutiny"
    rep["auto_derived"] = {
        "plot_area_sqm": plot_area, "footprint_sqm": footprint,
        "coverage_pct": round(100 * footprint / plot_area, 1) if plot_area else None,
        "built_up_sqm": built_up, "floors": floors, "setbacks_m": sb,
    }
    rep["geometry"] = {"plot": plot_coords, "building": building_coords, "front_edge_idx": front_edge_idx}
    if not sb["building_inside_plot"]:
        rep.setdefault("warnings", []).append("Building polygon is not fully inside the plot polygon — check the drawing.")
    return rep
