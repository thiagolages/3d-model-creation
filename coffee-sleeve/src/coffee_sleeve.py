#!/usr/bin/env python3
"""
Parametric coffee sleeve generator (v2).

Cup-style sleeve with a CLOSED bottom and two integrated paper pockets,
each with an outer window so the paper is visible:
  - pocket1: tall main pocket on one side, paper visible through a
             3-sided window/frame, open at top, near full height.
  - pocket2: smaller info pocket on the opposite side, top region.

The remaining cylindrical wall carries a hex/pentagon/triangle pattern
of through-holes.

Output: a single watertight STL ready for 3D printing.
"""

import os, sys, math
import numpy as np
import yaml
import trimesh
from trimesh.creation import cylinder, extrude_polygon
from shapely.geometry import Polygon, Point, box

# ============================================================
# PARAMETERS - edit these to customize
# ============================================================


# --- Cylinder body ---
inner_diameter          = 105.25
sleeve_height           = 108.0 # Define short, medium, tall here
wall_thickness          = 2.0
bottom_thickness        = 2.0     # mm, thickness of the closed floor

# --- Model Type (short/medium/tall) ---
if sleeve_height < 50.0:
    raise ValueError(f"sleeve_height={sleeve_height} is too short (<50mm)")
elif sleeve_height < 90:
    model_type = "short"
elif sleeve_height < 115:
    model_type = "medium"
elif sleeve_height < 155:
    model_type = "tall"
else:
    raise ValueError(f"sleeve_height={sleeve_height} is too tall (>155mm)")

# --- Output naming ---
base_name               = "coffee_sleeve_" + model_type

# --- Paper (shared by both pockets) ---
paper_thickness         = 0.25
paper_pocket_clearance  = 0.2

# --- Pocket 1: main, +X side, runs near floor to top ---
pocket1_enabled         = True
pocket1_theta_deg       = 0.0
pocket1_paper_width     = 95.0
pocket1_paper_height    = None    # None = auto from floor margin to top
pocket1_back_wall       = 1.2    # ≥2 FDM perimeters
pocket1_frame_side      = 8.0     # frame margin left/right of window
pocket1_frame_bottom    = 3.0     # frame margin below window
pocket1_bottom_clearance = 2.0    # gap between paper bottom and sleeve floor

# --- Pocket 2: smaller info pocket, opposite side, top region ---
pocket2_enabled         = True
pocket2_theta_deg       = 180.0
pocket2_paper_width     = pocket1_paper_width # same as paper1
pocket2_frame_bottom    = 3.0
pocket2_paper_height    = 35.0 + pocket2_frame_bottom  # height from the top
pocket2_back_wall       = 1.2    # ≥2 FDM perimeters
pocket2_frame_side      = 8.0

# --- Hole pattern on the cylinder wall ---
pattern_shape           = "hexagon"   # hexagon | pentagon | triangle
pattern_size            = 10.0
pattern_spacing         = 1.5
pattern_margin_top      = 1.5
pattern_margin_bottom   = 8.0
pattern_through_pockets = False   # let the wall pattern cut through pockets 1 & 2

# --- Side openings: two vertical peek windows flanking pocket 1 ---
side_openings_enabled     = True
side_opening_width        = 16.0   # arc-length mm, clamped to gap
side_opening_height       = np.inf #70.0   # mm, clamped to band
side_opening_top_clear    = 6.0    # gap from sleeve top
side_opening_bottom_clear = 8.0    # gap from sleeve bottom
side_opening_pocket_gap   = 2.0    # clearance from pocket 1 boss edge
# Opening + raised bezel frame
side_opening_shape         = "rectangular"  # rectangular | round (ellipse)
side_opening_frame_width   = 2.0   # bezel band thickness L/R (arc), beyond opening
side_opening_frame_height  = 2.0   # bezel band thickness top/bottom (z), beyond opening
side_opening_frame_relief  = 1.0   # radial protrusion of the raised bezel
side_opening_frame_fillet  = 8.0   # corner radius (rectangular only)

# --- Bottom floor pattern ---
bottom_pattern_enabled  = True
bottom_pattern_margin   = 0.0     # mm gap between holes and inner bore wall

# --- Base border ring (transitions floor ↔ cylindrical wall) ---
base_border_enabled     = True
base_border_height      = 3.5     # mm; ring height at the base
base_border_thickness   = 2.0     # mm; extra radius beyond R_out

# --- Tessellation / boolean engine ---
CYL_SECTIONS            = 128
ENGINE                  = "manifold"
# ============================================================

R_in  = inner_diameter / 2.0
R_out = R_in + wall_thickness


# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------
def annular_sector_polygon(r_in, r_out, theta_c, half_arc, n_seg=96):
    angles = np.linspace(theta_c - half_arc, theta_c + half_arc, n_seg)
    outer_pts = [(r_out * math.cos(a), r_out * math.sin(a)) for a in angles]
    inner_pts = [(r_in  * math.cos(a), r_in  * math.sin(a)) for a in reversed(angles)]
    return Polygon(outer_pts + inner_pts)


def build_cup():
    """Closed-bottom cup: outer cylinder minus inner cylinder above floor."""
    outer = cylinder(radius=R_out, height=sleeve_height, sections=CYL_SECTIONS)
    outer.apply_translation([0, 0, sleeve_height / 2.0])
    inner_h = sleeve_height - bottom_thickness + 1.0
    inner = cylinder(radius=R_in, height=inner_h, sections=CYL_SECTIONS)
    inner.apply_translation([0, 0, bottom_thickness + inner_h / 2.0 - 0.5])
    return trimesh.boolean.difference([outer, inner], engine=ENGINE)


# ----------------------------------------------------------
# Pocket
# ----------------------------------------------------------
class Pocket:
    def __init__(self, theta_deg, paper_w, back_wall,
                 frame_side, frame_bottom, cavity_bot_z, cavity_top_z):
        self.theta = math.radians(theta_deg)
        self.paper_w      = paper_w
        self.back_wall    = back_wall
        self.frame_side   = frame_side
        self.frame_bottom = frame_bottom
        self.cavity_bot_z = cavity_bot_z
        self.cavity_top_z = cavity_top_z

        self.paper_R_in  = R_in + back_wall
        self.paper_R_out = self.paper_R_in + paper_thickness + paper_pocket_clearance
        self.boss_R_out  = self.paper_R_out + wall_thickness

        struct_side   = 2.0
        struct_bottom = 2.0
        self.boss_arc_width = paper_w + 2 * struct_side
        self.boss_z_bottom  = max(0.0, cavity_bot_z - struct_bottom)
        self.boss_z_top     = min(sleeve_height, cavity_top_z)

    def boss(self):
        half_arc = (self.boss_arc_width / R_out) / 2.0
        poly = annular_sector_polygon(R_out - 0.1, self.boss_R_out,
                                      self.theta, half_arc, 128)
        m = extrude_polygon(poly, self.boss_z_top - self.boss_z_bottom)
        m.apply_translation([0, 0, self.boss_z_bottom])
        return m

    def cavity(self):
        half_arc = (self.paper_w / self.paper_R_in) / 2.0
        poly = annular_sector_polygon(self.paper_R_in - 0.01,
                                      self.paper_R_out + 0.01,
                                      self.theta, half_arc, 96)
        m = extrude_polygon(poly, self.cavity_top_z - self.cavity_bot_z)
        m.apply_translation([0, 0, self.cavity_bot_z])
        return m

    def window(self):
        window_w  = self.paper_w - 2 * self.frame_side
        win_bot_z = self.cavity_bot_z + self.frame_bottom
        win_top_z = self.cavity_top_z
        half_arc  = (window_w / self.paper_R_out) / 2.0
        poly = annular_sector_polygon(self.paper_R_out - 0.05,
                                      self.boss_R_out + 1.0,
                                      self.theta, half_arc, 96)
        m = extrude_polygon(poly, win_top_z - win_bot_z)
        m.apply_translation([0, 0, win_bot_z])
        return m


def make_pocket1():
    cav_bot = bottom_thickness + pocket1_bottom_clearance
    if pocket1_paper_height is None:
        cav_top = sleeve_height + 1.0
    else:
        cav_top = cav_bot + pocket1_paper_height + 1.0
    return Pocket(pocket1_theta_deg, pocket1_paper_width, pocket1_back_wall,
                  pocket1_frame_side, pocket1_frame_bottom, cav_bot, cav_top)


def make_pocket2():
    cav_top = sleeve_height + 1.0
    cav_bot = sleeve_height - pocket2_paper_height
    return Pocket(pocket2_theta_deg, pocket2_paper_width, pocket2_back_wall,
                  pocket2_frame_side, pocket2_frame_bottom, cav_bot, cav_top)


# ----------------------------------------------------------
# Pattern
# ----------------------------------------------------------
def hex_polygon(cx, cy, flat_to_flat):
    R = flat_to_flat / math.sqrt(3)
    pts = [(cx + R * math.cos(math.pi/6 + i*math.pi/3),
            cy + R * math.sin(math.pi/6 + i*math.pi/3)) for i in range(6)]
    return Polygon(pts)

def pent_polygon(cx, cy, size):
    R = size / 2.0
    pts = [(cx + R * math.cos(math.pi/2 + i*2*math.pi/5),
            cy + R * math.sin(math.pi/2 + i*2*math.pi/5)) for i in range(5)]
    return Polygon(pts)

def tri_polygon(cx, cy, size, flipped=False):
    R = size / math.sqrt(3)
    start = math.pi/2 if not flipped else -math.pi/2
    pts = [(cx + R * math.cos(start + i*2*math.pi/3),
            cy + R * math.sin(start + i*2*math.pi/3)) for i in range(3)]
    return Polygon(pts)


def generate_pattern_polygons():
    circumference = 2 * math.pi * R_out
    v_min = bottom_thickness + pattern_margin_bottom
    v_max = sleeve_height - pattern_margin_top
    polygons = []

    if pattern_shape == "hexagon":
        flat = pattern_size
        R = flat / math.sqrt(3)
        dx = flat + pattern_spacing
        dy = 1.5 * R + pattern_spacing * (math.sqrt(3) / 2.0)
        ncols = max(1, int(round(circumference / dx)))
        dx_actual = circumference / ncols
        v = v_min + R; row = 0
        while v + R <= v_max:
            offset = (dx_actual / 2.0) if (row % 2) else 0.0
            for col in range(ncols):
                u = (offset + col * dx_actual) % circumference
                polygons.append(hex_polygon(u, v, flat))
            v += dy; row += 1

    elif pattern_shape == "pentagon":
        size = pattern_size
        dx = size + pattern_spacing
        dy = size + pattern_spacing
        ncols = max(1, int(round(circumference / dx)))
        dx_actual = circumference / ncols
        v = v_min + size/2.0; row = 0
        while v + size/2.0 <= v_max:
            offset = (dx_actual / 2.0) if (row % 2) else 0.0
            for col in range(ncols):
                u = (offset + col * dx_actual) % circumference
                polygons.append(pent_polygon(u, v, size))
            v += dy; row += 1

    elif pattern_shape == "triangle":
        size = pattern_size
        h = size * math.sqrt(3) / 2.0
        dy = h + pattern_spacing
        ncols = max(1, int(round(circumference / (size + pattern_spacing))))
        dx_actual = circumference / ncols
        v = v_min + h/2.0; row = 0
        while v + h/2.0 <= v_max:
            for col in range(ncols):
                u = (col * dx_actual + dx_actual/2.0) % circumference
                flipped = ((row + col) % 2 == 1)
                polygons.append(tri_polygon(u, v, size * 0.85, flipped=flipped))
            v += dy; row += 1
    else:
        raise ValueError(f"Unknown pattern_shape: {pattern_shape}")

    return polygons, circumference


def mask_pocket_regions(polygons, circumference, pockets):
    buffer = max(pattern_spacing * 1.5, 3.0)

    def overlaps_boss(poly, p):
        pminx, pminy, pmaxx, pmaxy = poly.bounds
        if pmaxy < p.boss_z_bottom - buffer or pminy > p.boss_z_top + buffer:
            return False
        u_c = p.theta * R_out
        half = p.boss_arc_width / 2.0 + buffer
        for shift in (-circumference, 0.0, circumference):
            a, b = pminx + shift, pmaxx + shift
            if not (b < u_c - half or a > u_c + half):
                return True
        return False

    def inside_keep_rect(poly, p):
        """True if the hole is fully within the pocket's interior keep-rect
        (window area minus frame margins) — wrap-aware in u."""
        pminx, pminy, pmaxx, pmaxy = poly.bounds
        z_lo = p.cavity_bot_z + p.frame_bottom
        z_hi = min(p.cavity_top_z, sleeve_height) - p.frame_bottom
        if pminy < z_lo or pmaxy > z_hi:
            return False
        u_c = p.theta * R_out
        u_half = p.paper_w / 2.0 - p.frame_side
        if u_half <= 0:
            return False
        for shift in (-circumference, 0.0, circumference):
            if (pminx + shift) >= u_c - u_half and (pmaxx + shift) <= u_c + u_half:
                return True
        return False

    def masked(poly, p):
        if not overlaps_boss(poly, p):
            return False
        if pattern_through_pockets and inside_keep_rect(poly, p):
            return False   # keep interior holes → they cut through the pocket
        return True

    return [pg for pg in polygons if not any(masked(pg, p) for p in pockets)]


def build_pattern_cutters(polygons, max_boss_R):
    cutters = []
    # R_drill_in penetrates a full wall_thickness past the inner surface so
    # manifold3d reliably cuts holes visible from inside the sleeve.
    R_drill_in  = R_in - wall_thickness
    R_drill_out = max(R_out, max_boss_R) + wall_thickness
    for poly in polygons:
        coords = list(poly.exterior.coords)[:-1]
        verts = []
        for i, (u, v) in enumerate(coords):
            theta = u / R_out
            c, s = math.cos(theta), math.sin(theta)
            verts.append([R_drill_in  * c, R_drill_in  * s, v])
            verts.append([R_drill_out * c, R_drill_out * s, v])
            # midpoint of each edge for a tighter convex-hull approximation
            u2, v2 = coords[(i + 1) % len(coords)]
            theta_m = ((u + u2) / 2) / R_out
            cm, sm = math.cos(theta_m), math.sin(theta_m)
            vm = (v + v2) / 2
            verts.append([R_drill_in  * cm, R_drill_in  * sm, vm])
            verts.append([R_drill_out * cm, R_drill_out * sm, vm])
        try:
            cutters.append(trimesh.convex.convex_hull(np.array(verts)))
        except Exception as exc:
            print(f"  ! convex_hull failed: {exc}", file=sys.stderr)
    return cutters


# ----------------------------------------------------------
# Bottom floor pattern
# ----------------------------------------------------------
def build_bottom_pattern_cutters():
    """Hexagonal through-holes in the bottom floor disc."""
    if not bottom_pattern_enabled:
        return []
    flat    = pattern_size
    R_hex   = flat / math.sqrt(3)      # hex circumradius
    dx      = flat + pattern_spacing
    dy      = 1.5 * R_hex + pattern_spacing * (math.sqrt(3) / 2.0)
    R_max   = R_in - bottom_pattern_margin   # max hole-centre radius
    height  = bottom_thickness + 2.0         # cutter taller than the floor

    cutters = []
    row = 0
    y = -R_max + R_hex
    while y + R_hex <= R_max:
        x_off = (dx / 2.0) if (row % 2) else 0.0
        x = -R_max + x_off + R_hex
        while x + R_hex <= R_max:
            if math.hypot(x, y) + R_hex <= R_max:
                poly = hex_polygon(x, y, flat)
                try:
                    m = extrude_polygon(poly, height)
                    m.apply_translation([0, 0, -1.0])
                    cutters.append(m)
                except Exception as exc:
                    print(f"  ! bottom hex: {exc}", file=sys.stderr)
            x += dx
        y += dy
        row += 1
    return cutters


# ----------------------------------------------------------
# Base border ring
# ----------------------------------------------------------
def build_base_border():
    """Additive ring around the outer base: visually separates floor from
    cylinder and reinforces the floor-wall junction from the outside."""
    if not base_border_enabled:
        return None
    outer_r = R_out + base_border_thickness
    ring_2d = (Point(0, 0).buffer(outer_r,    resolution=CYL_SECTIONS // 4)
               .difference(
               Point(0, 0).buffer(R_out - 0.1, resolution=CYL_SECTIONS // 4)))
    return extrude_polygon(ring_2d, base_border_height)


# ----------------------------------------------------------
# Side openings (two vertical peek windows flanking pocket 1)
# ----------------------------------------------------------
def _ellipse_poly(cu, cz, a, b, n=72):
    ts = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return Polygon([(cu + a * math.cos(t), cz + b * math.sin(t)) for t in ts])


def _rrect_poly(cu, cz, width, height, fillet, res=16):
    f = max(0.0, min(fillet, width / 2.0 - 1e-3, height / 2.0 - 1e-3))
    if f <= 0:
        return box(cu - width / 2, cz - height / 2, cu + width / 2, cz + height / 2)
    inner = box(cu - width / 2 + f, cz - height / 2 + f,
                cu + width / 2 - f, cz + height / 2 - f)
    return inner.buffer(f, resolution=res, join_style=1)   # round corners


def _opening_and_frame_profiles(w, h, z_c):
    """Opening + frame outlines in unrolled (u, z) space, centered at u=0.
    Frame extends side_opening_frame_width/height beyond the opening."""
    fw, fh, fil = side_opening_frame_width, side_opening_frame_height, side_opening_frame_fillet
    if side_opening_shape == "round":
        opening = _ellipse_poly(0, z_c, w / 2.0, h / 2.0)
        frame   = _ellipse_poly(0, z_c, w / 2.0 + fw, h / 2.0 + fh)
    else:
        opening = _rrect_poly(0, z_c, w, h, fil)
        frame   = _rrect_poly(0, z_c, w + 2 * fw, h + 2 * fh, fil)
    return opening, frame


def _warp_profile_to_cylinder(profile, r_in, r_out, theta_c):
    """Map a 2D (u, z) profile to a curved radial prism on the cylinder:
    u -> angle offset (about theta_c), extrusion -> radial thickness."""
    m = extrude_polygon(profile, r_out - r_in)   # polygon in (u, z); extrude along +axis
    V = m.vertices
    u, z, t = V[:, 0], V[:, 1], V[:, 2]
    r = r_in + t
    theta = theta_c + u / R_out                  # constant-angle columns -> clean radial cut
    m.vertices = np.column_stack([r * np.cos(theta), r * np.sin(theta), z])
    return m


def build_side_openings(pockets):
    """Two vertical peek windows adjacent to pocket 1's boss edges, each with a
    raised bezel frame. Returns (opening_cutters, bezels, specs); each spec =
    (theta_c, u_half_frame, z_bot_frame, z_top_frame) masks the wall pattern so
    it stays clear of the bezel footprint."""
    if not side_openings_enabled or not pockets:
        return [], [], []
    p1 = pockets[0]
    p2 = pockets[1] if len(pockets) > 1 else None
    ha1 = (p1.boss_arc_width / R_out) / 2.0
    theta1 = p1.theta
    if p2 is not None:
        theta2 = p2.theta
        ha2 = (p2.boss_arc_width / R_out) / 2.0
    else:
        theta2 = theta1 + math.pi   # virtual far boundary
        ha2 = 0.0

    fw, fh = side_opening_frame_width, side_opening_frame_height
    relief = side_opening_frame_relief

    # vertical band: frame (opening + top/bottom bands) must fit within clearances
    band_lo = side_opening_bottom_clear
    band_hi = sleeve_height - side_opening_top_clear
    avail   = band_hi - band_lo
    h = min(side_opening_height, avail - 2 * fh)
    if h <= 0:
        print("  ! side openings skipped: no vertical room", file=sys.stderr)
        return [], [], []
    frame_h = h + 2 * fh
    z_frame_bot = band_lo + (avail - frame_h) / 2.0
    z_bot = z_frame_bot + fh           # opening bottom
    z_top = z_bot + h                  # opening top
    z_c   = (z_bot + z_top) / 2.0

    opening_cutters, bezels, specs = [], [], []
    for s in (+1, -1):
        # angular gap between p1's near edge and p2's near edge on this side
        edge1 = theta1 + s * ha1
        edge2 = theta2 - s * ha2
        gap_arc = abs(edge2 - edge1) * R_out
        # opening + both frame bands + a pocket_gap clearance at each end
        max_w = gap_arc - 2 * side_opening_pocket_gap - 2 * fw
        w = min(side_opening_width, max_w)
        if w <= 0:
            print(f"  ! side opening (s={s}) skipped: no room (gap_arc={gap_arc:.1f})",
                  file=sys.stderr)
            continue
        # place frame near-edge a pocket_gap away from pocket 1's boss edge
        theta_c = theta1 + s * (ha1 + (side_opening_pocket_gap + fw + w / 2.0) / R_out)

        opening_poly, frame_poly = _opening_and_frame_profiles(w, h, z_c)
        # raised bezel: frame slab from just inside the wall out to R_out + relief
        bezels.append(_warp_profile_to_cylinder(frame_poly, R_out - 0.6,
                                                R_out + relief, theta_c))
        # through-cut: pierces wall + bezel
        opening_cutters.append(_warp_profile_to_cylinder(opening_poly, R_in - 1.0,
                                                         R_out + relief + 1.0, theta_c))
        specs.append((theta_c, w / 2.0 + fw + 1.0,
                      z_bot - fh - 1.0, z_top + fh + 1.0))
    return opening_cutters, bezels, specs


def mask_opening_regions(polygons, circumference, specs):
    """Drop pattern holes overlapping a side-opening frame rect so the opening
    keeps a clean solid border (no undercut by adjacent holes)."""
    def overlaps(poly, spec):
        theta_c, u_half, z_lo, z_hi = spec
        pminx, pminy, pmaxx, pmaxy = poly.bounds
        if pmaxy < z_lo or pminy > z_hi:
            return False
        u_c = theta_c * R_out
        for shift in (-circumference, 0.0, circumference):
            a, b = pminx + shift, pmaxx + shift
            if not (b < u_c - u_half or a > u_c + u_half):
                return True
        return False
    return [pg for pg in polygons if not any(overlaps(pg, sp) for sp in specs)]


# ----------------------------------------------------------
# Output naming + metadata
# ----------------------------------------------------------
def collect_params():
    """Snapshot all module-level scalar parameters into a plain dict."""
    out = {}
    for k, v in globals().items():
        if k.startswith("_"):
            continue
        if isinstance(v, (int, float, str, bool)) or v is None:
            out[k] = v
    return out


def next_model_paths(out_dir):
    models_dir = os.path.normpath(os.path.join(out_dir, "..", "models"))
    models_dir = os.path.join(models_dir, model_type) # short/medium/tall

    print(f"  next_model_paths: models_dir={models_dir}")

    meta_dir = os.path.join(models_dir, "metadata")
    img_dir = os.path.join(models_dir, "images")
    os.makedirs(meta_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)
    existing = [f for f in os.listdir(models_dir)
                if f.endswith(".stl") and base_name in f]
    ID = len(existing) + 1
    name = f"v{ID}_{base_name}_{inner_diameter:g}d_{sleeve_height:g}h"
    return (os.path.join(models_dir, name + ".stl"),
            os.path.join(meta_dir, name + ".yaml"),
            os.path.join(img_dir, name + ".png"))


# ----------------------------------------------------------
# Main build
# ----------------------------------------------------------
def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    print("[1/10] Cup body (closed bottom)...")
    sleeve = build_cup()

    if base_border_enabled:
        print("[2/10] Base border ring...")
        border = build_base_border()
        if border is not None:
            sleeve = trimesh.boolean.union([sleeve, border], engine=ENGINE)

    pockets = []
    if pocket1_enabled: pockets.append(make_pocket1())
    if pocket2_enabled: pockets.append(make_pocket2())

    if pockets:
        print(f"[3/10] Union {len(pockets)} pocket boss(es)...")
        sleeve = trimesh.boolean.union([sleeve] + [p.boss() for p in pockets], engine=ENGINE)
        print("[4/10] Subtract pocket cavities...")
        sleeve = trimesh.boolean.difference([sleeve] + [p.cavity() for p in pockets], engine=ENGINE)
        print("[5/10] Subtract pocket windows...")
        sleeve = trimesh.boolean.difference([sleeve] + [p.window() for p in pockets], engine=ENGINE)

    print("[6/10] Side openings...")
    side_cutters, side_bezels, opening_specs = build_side_openings(pockets)
    print(f"      {len(side_cutters)} opening(s), {len(side_bezels)} bezel(s)")

    print("[7/10] Wall pattern...")
    polys, circumference = generate_pattern_polygons()
    print(f"      generated {len(polys)} candidate polygons")
    polys = mask_pocket_regions(polys, circumference, pockets)
    print(f"      {len(polys)} after pocket mask")
    polys = mask_opening_regions(polys, circumference, opening_specs)
    print(f"      {len(polys)} after opening mask")
    max_boss_R = max((p.boss_R_out for p in pockets), default=R_out)
    cutters = build_pattern_cutters(polys, max_boss_R)
    print(f"      {len(cutters)} 3D cutters")
    if cutters:
        print("[8/10] Subtract wall pattern...")
        sleeve = trimesh.boolean.difference([sleeve] + cutters, engine=ENGINE)

    if side_bezels:
        print("      Union side-opening bezels...")
        sleeve = trimesh.boolean.union([sleeve] + side_bezels, engine=ENGINE)
    if side_cutters:
        print("      Subtract side openings...")
        sleeve = trimesh.boolean.difference([sleeve] + side_cutters, engine=ENGINE)

    bottom_cutters = build_bottom_pattern_cutters()
    print(f"[9/10] Bottom floor pattern ({len(bottom_cutters)} holes)...")
    if bottom_cutters:
        sleeve = trimesh.boolean.difference([sleeve] + bottom_cutters, engine=ENGINE)

    sleeve.process(validate=True)
    print(f"[10/10] is_watertight={sleeve.is_watertight}  "
          f"verts={len(sleeve.vertices)}  faces={len(sleeve.faces)}  "
          f"volume={sleeve.volume:.1f} mm^3")

    # Save outputs: STL, YAML metadata, PNG preview

    stl_path, yaml_path, png_path = next_model_paths(out_dir)
    
    sleeve.export(stl_path)
    print(f"Wrote {stl_path}")
    
    with open(yaml_path, "w") as f:
        yaml.safe_dump(collect_params(), f, sort_keys=False)
    print(f"Wrote {yaml_path}")

    render_preview(sleeve, png_path)
    # Will print 'wrote' inside render_preview() if successful
    
    return sleeve


def render_preview(mesh, png_path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        views = [(18, -55, "pocket 1 (main)"), (18, 125, "pocket 2 (info)")]
        fig = plt.figure(figsize=(14, 7), dpi=130)
        for i, (elev, azim, title) in enumerate(views, 1):
            ax = fig.add_subplot(1, 2, i, projection="3d")
            tris = mesh.vertices[mesh.faces]
            normals = mesh.face_normals
            light = np.array([0.4, 0.5, 0.8]); light /= np.linalg.norm(light)
            shade = 0.35 + 0.65 * np.clip(normals @ light, 0, 1)
            face_colors = np.stack([shade * 0.78, shade * 0.58, shade * 0.40], axis=-1)
            coll = Poly3DCollection(tris, facecolors=face_colors,
                                    edgecolors=(0,0,0,0.05), linewidths=0.05)
            ax.add_collection3d(coll)
            ax.view_init(elev=elev, azim=azim)
            b = mesh.bounds
            m = (b[1] + b[0]) / 2
            r = (b[1] - b[0]).max() / 2 * 1.05
            ax.set_xlim(m[0]-r, m[0]+r); ax.set_ylim(m[1]-r, m[1]+r); ax.set_zlim(m[2]-r, m[2]+r)
            ax.set_box_aspect((1,1,1)); ax.set_axis_off(); ax.set_title(title, fontsize=11)
        plt.tight_layout()
        plt.savefig(png_path, dpi=130, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        print(f"Wrote {png_path}")
        return True
    except Exception as exc:
        print(f"  matplotlib render error: {exc}", file=sys.stderr)
        return False


if __name__ == "__main__":
    main()
