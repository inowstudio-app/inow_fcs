"""Demo: run the feasibility engine on the sample FMB plot under two road-width scenarios."""
from engine.feasibility import Plot, run_feasibility


def fmt(report):
    s = report["setbacks_m"]
    b = report["buildable_footprint"]
    m = report["max_built_up_area_sqm"]
    side = f'{s["side_each_m"]}m ({s["side_applies"]} side)'
    lines = [
        f'  Category        : {report["category"]}',
        f'  Assumed height  : {report["assumed_height_m"]} m',
        f'  Permissible FSI : {report["fsi_max"]}',
        f'  Setbacks        : front {s["front_m"]}m | side {side} | rear {s["rear_m"]}m',
        f'  Buildable area  : {b["width_m"]} x {b["depth_m"]} m = {b["area_sqm"]} sqm  (coverage {b["coverage_pct"]}%)',
        f'  Max built-up    : {m["governing"]} sqm  (FSI cap {m["fsi_limit"]} / physical {m["physical_limit_footprint_x_floors"]} over {m["max_floors_assumed"]} floors)',
    ]
    if report["flags"]:
        lines.append("  Flags           : " + "; ".join(report["flags"]))
    return "\n".join(lines)


# Sample plot from the uploaded FMB: Survey 77/1B2, Siruvanur(R), 218 sqm, ~12.2 x 17.8
base = dict(area_sqm=218.0, width_m=12.2, depth_m=17.8, use="residential",
            dwellings=1, proposed_height_m=11.0, survey_no="77/1B2", village="Siruvanur(R)")

for rw in (7.5, 12.0, 20.0):
    plot = Plot(abutting_road_width_m=rw, **base)
    rep = run_feasibility(plot)
    print(f"\n=== Survey 77/1B2 | GF+2F house | abutting road {rw} m ===")
    print(fmt(rep))

print("\nPending (rules not yet extracted): ")
for p in run_feasibility(Plot(abutting_road_width_m=12.0, **base))["pending"]:
    print("  -", p)
