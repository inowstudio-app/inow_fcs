"""Precise architectural sun-path diagram — deterministic solar geometry.

No guesswork: given a latitude (and optionally the plot's North orientation),
this computes the sun's altitude/azimuth through the day using standard solar
equations and renders a clean, legible horizontal (polar) sun-path diagram as
an SVG. Used by the Neufert assistant via tool-use so answers are exact.

Solar model: Cooper's declination + hour-angle in SOLAR (local apparent) time,
which is the convention for architectural sun-path charts — so only latitude and
date are needed, not longitude/timezone/equation-of-time. Northern or southern
latitudes both work.
"""
from __future__ import annotations
import math
from datetime import date as _date

# A few Tamil Nadu / South India reference latitudes (deg N) the model can use
# when the user names a city. Not exhaustive — the tool also accepts a raw latitude.
TN_CITY_LAT = {
    "chennai": 13.08, "coimbatore": 11.02, "madurai": 9.92, "tiruchirappalli": 10.79,
    "trichy": 10.79, "salem": 11.66, "tirunelveli": 8.71, "tiruppur": 11.11,
    "erode": 11.34, "vellore": 12.92, "thoothukudi": 8.76, "thanjavur": 10.79,
    "dindigul": 10.36, "kanyakumari": 8.09, "nagercoil": 8.18, "ooty": 11.41,
    "pondicherry": 11.93, "puducherry": 11.93, "bangalore": 12.97, "bengaluru": 12.97,
}

_KEY_DATES = [
    ("Jun 21 (summer solstice)", 172, "#d9534f"),
    ("Mar/Sep 21 (equinox)", 80, "#0f8a4f"),
    ("Dec 21 (winter solstice)", 355, "#1668b3"),
]


def declination(day_of_year: int) -> float:
    """Solar declination (deg), Cooper's equation."""
    return 23.45 * math.sin(math.radians(360.0 * (284 + day_of_year) / 365.0))


def sun_altaz(lat_deg: float, decl_deg: float, hour_solar: float):
    """Return (altitude_deg, azimuth_deg_from_north_CW) for a solar-time hour."""
    lat = math.radians(lat_deg)
    decl = math.radians(decl_deg)
    H = math.radians(15.0 * (hour_solar - 12.0))   # hour angle
    sin_alt = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(H)
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.asin(sin_alt)
    cos_alt = math.cos(alt)
    if abs(cos_alt) < 1e-9:
        az = 0.0
    else:
        cos_az = (math.sin(decl) - math.sin(alt) * math.sin(lat)) / (cos_alt * math.cos(lat))
        cos_az = max(-1.0, min(1.0, cos_az))
        az = math.degrees(math.acos(cos_az))       # 0..180 from North
        if H > 0:                                   # afternoon -> west side
            az = 360.0 - az
    return math.degrees(alt), az


def _day_of_year(d: _date) -> int:
    return d.timetuple().tm_yday


def summarize(lat_deg: float):
    """Key design figures per date: sunrise/sunset (solar time), noon altitude, noon azimuth."""
    out = []
    for label, doy, _ in _KEY_DATES:
        decl = declination(doy)
        # sunrise hour angle
        lat = math.radians(lat_deg); dec = math.radians(decl)
        cosH0 = -math.tan(lat) * math.tan(dec)
        if cosH0 >= 1:      # polar night
            rise = sett = None
        elif cosH0 <= -1:   # polar day
            rise, sett = 0.0, 24.0
        else:
            H0 = math.degrees(math.acos(cosH0))
            rise = 12.0 - H0 / 15.0
            sett = 12.0 + H0 / 15.0
        noon_alt, noon_az = sun_altaz(lat_deg, decl, 12.0)
        out.append({"date": label, "declination": round(decl, 1),
                    "sunrise_solar": _hm(rise), "sunset_solar": _hm(sett),
                    "noon_altitude": round(noon_alt, 1),
                    "noon_azimuth": round(noon_az, 1),
                    "day_length_h": round((sett - rise), 1) if rise is not None else None})
    return out


def _hm(h):
    if h is None:
        return None
    h = max(0.0, min(24.0, h))
    hh = int(h); mm = int(round((h - hh) * 60))
    if mm == 60:
        hh += 1; mm = 0
    return f"{hh:02d}:{mm:02d}"


def sun_path_svg(lat_deg: float, place: str = "", north_offset_deg: float = 0.0,
                 extra_date: str = None) -> str:
    """Render a clean horizontal sun-path diagram (equidistant polar projection).

    north_offset_deg rotates the compass clockwise so the chart's 'up' can match
    the user's plot North (0 = geographic North up).
    """
    W, Hh = 760, 720
    cx, cy, R = 380.0, 372.0, 300.0
    off = math.radians(north_offset_deg)

    def project(alt, az):
        r = R * (90.0 - alt) / 90.0                    # horizon at rim, zenith at centre
        a = math.radians(az) + off
        return cx + r * math.sin(a), cy - r * math.cos(a)

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {Hh}" '
                 f'font-family="Segoe UI, Arial, sans-serif">')
    parts.append(f'<rect x="0" y="0" width="{W}" height="{Hh}" fill="#ffffff"/>')
    # title
    ttl = "Sun-path diagram"
    sub = (f"{place} · " if place else "") + f"latitude {lat_deg:.2f}°"
    parts.append(f'<text x="{cx}" y="34" text-anchor="middle" font-size="20" '
                 f'font-weight="700" fill="#1d2733">{_esc(ttl)}</text>')
    parts.append(f'<text x="{cx}" y="56" text-anchor="middle" font-size="13" '
                 f'fill="#66758a">{_esc(sub)}</text>')

    # altitude rings + labels
    for alt in range(0, 91, 15):
        r = R * (90 - alt) / 90.0
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" '
                     f'stroke="{"#9aa7b6" if alt==0 else "#e2e8f0"}" stroke-width="{1.4 if alt==0 else 1}"/>')
        if 0 < alt < 90:
            parts.append(f'<text x="{cx+4}" y="{cy - r + 12:.1f}" font-size="10" '
                         f'fill="#9aa7b6">{alt}°</text>')

    # azimuth spokes every 30°, compass labels every 45°
    compass = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}
    for az in range(0, 360, 15):
        a = math.radians(az) + off
        x2, y2 = cx + R * math.sin(a), cy - R * math.cos(a)
        major = az % 45 == 0
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x2:.1f}" y2="{y2:.1f}" '
                     f'stroke="{"#cdd6e0" if major else "#eef2f7"}" stroke-width="1"/>')
        if major:
            lx, ly = cx + (R + 22) * math.sin(a), cy - (R + 22) * math.cos(a)
            parts.append(f'<text x="{lx:.1f}" y="{ly+4:.1f}" text-anchor="middle" '
                         f'font-size="13" font-weight="700" fill="#334155">{compass[az]}</text>')

    # date curves
    curves = list(_KEY_DATES)
    if extra_date:
        try:
            d = _date.fromisoformat(extra_date)
            curves.append((f"{d.strftime('%d %b')} (your date)", _day_of_year(d), "#7a3ff2"))
        except Exception:
            pass

    legend = []
    for label, doy, col in curves:
        decl = declination(doy)
        pts = []
        t = 3.0
        while t <= 21.0001:
            alt, az = sun_altaz(lat_deg, decl, t)
            if alt >= -0.5:
                x, y = project(max(alt, 0), az)
                pts.append(f"{x:.1f},{y:.1f}")
            t += 0.1667   # ~10-min steps for a smooth arc
        if pts:
            parts.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                         f'stroke="{col}" stroke-width="2.4"/>')
        legend.append((label, col))

    # hour lines (figure-8 style): connect the same solar hour across the date curves
    for hr in range(5, 20):
        hp = []
        for _, doy, _ in curves:
            decl = declination(doy)
            alt, az = sun_altaz(lat_deg, decl, float(hr))
            if alt >= 0:
                hp.append(project(alt, az))
        if len(hp) >= 2:
            d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in hp)
            parts.append(f'<path d="{d}" fill="none" stroke="#b8c2cf" '
                         f'stroke-width="0.9" stroke-dasharray="2,3"/>')
        # label the hour once, at its position on the FIRST (summer) curve, nudged outward
        decl0 = declination(curves[0][1])
        alt0, az0 = sun_altaz(lat_deg, decl0, float(hr))
        if alt0 > 2:
            x, y = project(alt0, az0)
            dx, dy = (x - cx), (y - cy)
            L = math.hypot(dx, dy) or 1
            lx, ly = x + dx / L * 13, y + dy / L * 13
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" fill="#d9534f"/>')
            parts.append(f'<text x="{lx:.1f}" y="{ly+3:.1f}" text-anchor="middle" '
                         f'font-size="9.5" fill="#8a93a0">{hr}h</text>')

    # legend (top-left, clear of the circle)
    ly = 86
    parts.append(f'<text x="28" y="{ly}" font-size="12" font-weight="700" fill="#1d2733">Sun paths (solar time)</text>')
    for label, col in legend:
        ly += 20
        parts.append(f'<line x1="28" y1="{ly-4}" x2="52" y2="{ly-4}" stroke="{col}" stroke-width="3"/>')
        parts.append(f'<text x="58" y="{ly}" font-size="11.5" fill="#46586b">{_esc(label)}</text>')

    # footer note
    parts.append(f'<text x="{cx}" y="{Hh-14}" text-anchor="middle" font-size="10.5" fill="#9aa7b6">'
                 f'Rings = sun altitude (0° rim → 90° centre). Spokes = compass bearing. '
                 f'Dashed = solar-hour lines.</text>')
    parts.append('</svg>')
    return "".join(parts)


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def compute(latitude: float = None, place: str = "", city: str = "",
            north_offset_deg: float = 0.0, date: str = None) -> dict:
    """Tool entry-point: returns {svg, summary, latitude, place}.

    Accepts a numeric latitude OR a known city name. Raises ValueError if neither
    yields a usable latitude (so the assistant must ask the user)."""
    lat = latitude
    label = place or ""
    if lat is None and city:
        key = city.strip().lower()
        if key in TN_CITY_LAT:
            lat = TN_CITY_LAT[key]
            label = label or city.title()
    if lat is None:
        raise ValueError("latitude required (or a recognised city name)")
    lat = float(lat)
    if not -66.5 <= lat <= 66.5:
        # still works mathematically, but flag extreme/polar latitudes
        pass
    svg = sun_path_svg(lat, place=label, north_offset_deg=float(north_offset_deg or 0), extra_date=date)
    return {"svg": svg, "summary": summarize(lat), "latitude": round(lat, 3), "place": label}
