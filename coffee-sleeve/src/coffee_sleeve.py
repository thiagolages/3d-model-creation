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
import trimesh
from trimesh.creation import cylinder, extrude_polygon
from shapely.geometry import Polygon, Point

# ============================================================
# PARAMETERS - edit these to customize
# ============================================================

# --- Cylinder body ---
inner_diameter          = 105.25
sleeve_height           = 108.0
wall_thickness          = 2.0
bottom_thickness        = 2.0     # mm, thickness of the closed floor

# --- Paper (shared by both pockets) ---
paper_thickness         = 0.25
paper_pocket_clearance  = 0.2

# --- Pocket 1: main, +X side, runs near floor to top ---
pocket1_enabled         = True
pocket1_theta_deg       = 0.0
pocket1_paper_width     = 93.0
pocket1_paper_height    = None    # None = auto from floor margin to top
pocket1_back_wall       = 1.2    # ≥2 FDM perimeters
pocket1_frame_side      = 10.0     # frame margin left/right of window
pocket1_frame_bottom    = 3.0     # frame margin below window
pocket1_bottom_clearance = 2.0    # gap between paper bottom and sleeve floor

# --- Pocket 2: smaller info pocket, opposite side, top region ---
pocket2_enabled         = True
pocket2_theta_deg       = 180.0
pocket2_paper_width     = pocket1_paper_width # same as paper1
pocket2_paper_height    = 36.0    # height from the top
pocket2_back_wall       = 1.2    # ≥2 FDM perimeters
pocket2_frame_side      = 10.0
pocket2_frame_bottom    = 2.0

# --- Hole pattern on the cylinder wall ---
pattern_shape           = "hexagon"   # hexagon | pentagon | triangle
pattern_size            = 5.5
pattern_spacing         = 1.5
pattern_margin_top      = 2.0
pattern_margin_bottom   = 4.0

# --- Bottom floor pattern ---
bottom_pattern_enabled  = True
bottom_pattern_margin   = 3.0     # mm gap between holes and inner bore wall

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
    def overlaps(poly, p):
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
    return [pg for pg in polygons if not any(overlaps(pg, p) for p in pockets)]


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
# Main build
# ----------------------------------------------------------
def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    print("[1/9] Cup body (closed bottom)...")
    sleeve = build_cup()

    if base_border_enabled:
        print("[2/9] Base border ring...")
        border = build_base_border()
        if border is not None:
            sleeve = trimesh.boolean.union([sleeve, border], engine=ENGINE)

    pockets = []
    if pocket1_enabled: pockets.append(make_pocket1())
    if pocket2_enabled: pockets.append(make_pocket2())

    if pockets:
        print(f"[3/9] Union {len(pockets)} pocket boss(es)...")
        sleeve = trimesh.boolean.union([sleeve] + [p.boss() for p in pockets], engine=ENGINE)
        print("[4/9] Subtract pocket cavities...")
        sleeve = trimesh.boolean.difference([sleeve] + [p.cavity() for p in pockets], engine=ENGINE)
        print("[5/9] Subtract pocket windows...")
        sleeve = trimesh.boolean.difference([sleeve] + [p.window() for p in pockets], engine=ENGINE)

    print("[6/9] Wall pattern...")
    polys, circumference = generate_pattern_polygons()
    print(f"      generated {len(polys)} candidate polygons")
    polys = mask_pocket_regions(polys, circumference, pockets)
    print(f"      {len(polys)} after pocket mask")
    max_boss_R = max((p.boss_R_out for p in pockets), default=R_out)
    cutters = build_pattern_cutters(polys, max_boss_R)
    print(f"      {len(cutters)} 3D cutters")
    if cutters:
        print("[7/9] Subtract wall pattern...")
        sleeve = trimesh.boolean.difference([sleeve] + cutters, engine=ENGINE)

    bottom_cutters = build_bottom_pattern_cutters()
    print(f"[8/9] Bottom floor pattern ({len(bottom_cutters)} holes)...")
    if bottom_cutters:
        sleeve = trimesh.boolean.difference([sleeve] + bottom_cutters, engine=ENGINE)

    sleeve.process(validate=True)
    print(f"[9/9] is_watertight={sleeve.is_watertight}  "
          f"verts={len(sleeve.vertices)}  faces={len(sleeve.faces)}  "
          f"volume={sleeve.volume:.1f} mm^3")
    # if not sleeve.is_watertight:
    #     print("  ! not watertight, attempting fill_holes ...")
    #     sleeve.fill_holes()
    #     sleeve.process(validate=True)
    #     print(f"    after repair: is_watertight={sleeve.is_watertight}")

    stl_path = os.path.join(out_dir, "coffee_sleeve.stl")
    sleeve.export(stl_path)
    print(f"Wrote {stl_path}")

    png_path = os.path.join(out_dir, "coffee_sleeve_preview.png")
    render_preview(sleeve, png_path)
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
