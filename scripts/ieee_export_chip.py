#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# KianV RISC-V Linux/XV6 SoC
# RISC-V SoC/ASIC Design
#
# Copyright (c) 2025 Hirosh Dabui <hirosh@dabui.de>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
IEEE-style GDS renderer using gdstk + matplotlib.

Features:
  - Selectable resolution:       --res 2000 / 4000 / 8000 / ...
  - Selectable color palette:    --palette classic | clean | intel
  - Optional core-only crop:     --core-only
  - Optional extra bbox inset:   --crop-margin <layout units>
  - Selectable layer mode:       --layers full | metal
  - Supersampling/downsampling:  --downsample <factor>
  - Optional legend overlay:     --legend

Examples:
  python ieee_export.py
  python ieee_export.py --res 8000 --palette clean
  python ieee_export.py --res 4000 --palette intel --core-only
  python ieee_export.py --res 6000 --crop-margin 50 --legend
  python ieee_export.py --res 4000 --downsample 2 --palette classic
"""

import argparse
import io
from typing import Dict, List, Tuple

import gdstk
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
import numpy as np

try:
    from PIL import Image  # for downsample
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ---------------------------------------------------------
# Palettes: GF180 layer → color (hex RGB)
# ---------------------------------------------------------

IEEE_CLASSIC = {
    34: "#00FFC8",   # MET1 – turquoise
    36: "#0099FF",   # MET2 – blue
    42: "#FF00FF",   # MET3 – magenta
    30: "#FF4040",   # POLY – red
    22: "#FFD600",   # DIFF/ACTIVE – yellow
    40: "#AA55FF",   # NWELL – violet
    41: "#AA55FF",   # PWELL – violet
}

IEEE_CLEAN = {
    34: "#66FFE0",   # MET1 – soft turquoise
    36: "#3399FF",   # MET2 – mid blue
    42: "#CC33FF",   # MET3 – purple
    30: "#FF6666",   # POLY – soft red
    22: "#FFCC33",   # DIFF – golden yellow
    40: "#9966FF",   # NWELL – softer violet
    41: "#9966FF",   # PWELL
}

INTEL_STYLE = {
    34: "#00CCFF",   # MET1
    36: "#0088FF",   # MET2
    42: "#0044FF",   # MET3
    30: "#FF5544",   # POLY
    22: "#FFBB33",   # DIFF
    40: "#8822EE",   # NWELL
    41: "#8822EE",   # PWELL
}

PALETTES: Dict[str, Dict[int, str]] = {
    "classic": IEEE_CLASSIC,
    "clean":   IEEE_CLEAN,
    "intel":   INTEL_STYLE,
}

# ---------------------------------------------------------
# Defaults
# ---------------------------------------------------------

GDS_PATH_DEFAULT = "final/gds/chip_top.gds"
OUT_IMG_DEFAULT  = "chip.png"

# Minimum polygon area in layout units^2 (higher = faster, less tiny noise)
AREA_MIN = 0.5

# Name hints for core cell when using --core-only
CORE_NAME_HINTS = ["i_chip_core", "chip_core", "core"]

# ---------------------------------------------------------


def choose_bbox(top: gdstk.Cell, core_only: bool, crop_margin: float) -> Tuple[float, float, float, float]:
    """Determine bounding box (minx, miny, maxx, maxy)."""
    if core_only:
        print("==> Searching for core cell...")
        bbox = None
        for ref in top.references:
            cell_name = ref.cell.name.lower()
            if any(hint in cell_name for hint in CORE_NAME_HINTS):
                print(f"    Found core candidate: {ref.cell.name}")
                bbox = ref.cell.bounding_box()
                break
        if bbox is None:
            print("WARNING: No core cell found. Using full topcell bounding box.")
            bbox = top.bounding_box()
    else:
        bbox = top.bounding_box()

    (minx, miny), (maxx, maxy) = bbox

    if crop_margin > 0.0:
        minx += crop_margin
        miny += crop_margin
        maxx -= crop_margin
        maxy -= crop_margin
        if maxx <= minx or maxy <= miny:
            raise RuntimeError("Crop margin too large, bounding box collapsed.")

    return minx, miny, maxx, maxy


def compute_pixel_size(w: float, h: float, target_res: int) -> Tuple[int, int]:
    """Compute image width/height in pixels given aspect and target long side."""
    aspect = w / h if h != 0 else 1.0
    if aspect >= 1.0:
        width_px = target_res
        height_px = int(target_res / aspect)
    else:
        height_px = target_res
        width_px = int(target_res * aspect)
    return width_px, height_px


def add_legend(ax, palette_name: str, layer_colors: Dict[int, str], mode_layers: str) -> None:
    """Draw a small legend in the top-left corner."""
    import matplotlib.patches as mpatches

    entries: List[Tuple[str, str]] = []

    def add(label: str, layer: int):
        if layer in layer_colors:
            entries.append((label, layer_colors[layer]))

    # Only metals if mode_layers == "metal"
    metals_only = (mode_layers == "metal")

    add("MET1", 34)
    add("MET2", 36)
    add("MET3", 42)
    if not metals_only:
        add("POLY", 30)
        add("DIFF", 22)
        add("WELL", 40)  # 40/41 share color

    # Legend box
    legend_ax = ax.inset_axes([0.02, 0.75, 0.22, 0.23])  # [x0, y0, w, h] in axes fraction
    legend_ax.set_facecolor("black")
    legend_ax.set_xticks([])
    legend_ax.set_yticks([])
    legend_ax.set_title(f"Palette: {palette_name}", color="white", fontsize=8)

    for i, (label, color) in enumerate(entries):
        y = 1.0 - (i + 1) * 0.18
        rect = mpatches.Rectangle((0.05, y), 0.25, 0.14, facecolor=color, edgecolor="white", linewidth=0.3,
                                  transform=legend_ax.transAxes, clip_on=False)
        legend_ax.add_patch(rect)
        legend_ax.text(0.35, y + 0.02, label, color="white", fontsize=7,
                       transform=legend_ax.transAxes, va="bottom")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IEEE-style GDS renderer (gdstk + matplotlib)."
    )
    parser.add_argument(
        "--gds", default=GDS_PATH_DEFAULT,
        help=f"Path to GDS file (default: {GDS_PATH_DEFAULT})",
    )
    parser.add_argument(
        "--out", default=OUT_IMG_DEFAULT,
        help=f"Output PNG file (default: {OUT_IMG_DEFAULT})",
    )
    parser.add_argument(
        "--res", type=int, default=4000,
        help="Target resolution: longer image side in pixels "
             "(e.g. 2000, 4000, 8000). Default: 4000",
    )
    parser.add_argument(
        "--core-only", action="store_true",
        help="Try to crop to core region only (searches for a core cell).",
    )
    parser.add_argument(
        "--crop-margin", type=float, default=0.0,
        help="Additional inset from chosen bounding box (layout units). "
             "Use this to shave off padframe edges.",
    )
    parser.add_argument(
        "--palette", choices=PALETTES.keys(), default="classic",
        help="Color palette: classic | clean | intel (default: classic)",
    )
    parser.add_argument(
        "--layers", choices=["full", "metal"], default="full",
        help="Which layers to render: 'full' (metals+poly+diff+wells) or 'metal' (MET1..3 only).",
    )
    parser.add_argument(
        "--downsample", type=int, default=1,
        help="Supersampling factor: render at res*factor and downsample. "
             "Requires pillow. Default: 1 (no downsampling).",
    )
    parser.add_argument(
        "--legend", action="store_true",
        help="Draw a small color legend in the top-left corner.",
    )

    args = parser.parse_args()

    gds_path     = args.gds
    out_path     = args.out
    target_res   = max(512, args.res)
    palette_name = args.palette
    crop_margin  = max(0.0, args.crop_margin)
    mode_layers  = args.layers
    downsample   = max(1, args.downsample)

    layer_colors = PALETTES[palette_name].copy()

    if mode_layers == "metal":
        # Strip non-metal entries from palette
        for k in list(layer_colors.keys()):
            if k not in (34, 36, 42):
                del layer_colors[k]

    interesting_layers = set(layer_colors.keys())

    print(f"==> Palette       : {palette_name}")
    print(f"==> Layer mode    : {mode_layers}")
    print(f"==> GDS file      : {gds_path}")
    print(f"==> Output file   : {out_path}")
    print(f"==> Target res    : {target_res} px (longer side)")
    print(f"==> Core only     : {args.core_only}")
    print(f"==> Crop margin   : {crop_margin}")
    print(f"==> Downsample    : {downsample}x (render at res*{downsample})")

    if downsample > 1 and not PIL_AVAILABLE:
        raise RuntimeError("downsample > 1 requires pillow (pip install pillow).")

    # -----------------------------------------------------
    # Load GDS
    # -----------------------------------------------------
    lib = gdstk.read_gds(gds_path)
    top_cells = lib.top_level()
    if not top_cells:
        raise RuntimeError("No top-level cell found in GDS.")
    top = top_cells[0]
    print(f"Topcell: {top.name}")

    polygons = top.get_polygons(True)
    print(f"==> Total polygons: {len(polygons):,}")

    # -----------------------------------------------------
    # Determine bounding box
    # -----------------------------------------------------
    minx, miny, maxx, maxy = choose_bbox(
        top,
        core_only=args.core_only,
        crop_margin=crop_margin,
    )
    w = maxx - minx
    h = maxy - miny
    print(f"==> Bounding box  : w={w:.0f}, h={h:.0f} (layout units)")

    # -----------------------------------------------------
    # Compute pixel size (with supersampling)
    # -----------------------------------------------------
    base_width_px, base_height_px = compute_pixel_size(w, h, target_res)
    width_px  = base_width_px * downsample
    height_px = base_height_px * downsample
    print(f"==> Render size   : {width_px} x {height_px} px")

    dpi       = 100
    fig_w_in  = width_px / dpi
    fig_h_in  = height_px / dpi

    # -----------------------------------------------------
    # Filter polygons and group by layer
    # -----------------------------------------------------
    polys_by_layer: Dict[int, List[np.ndarray]] = {l: [] for l in interesting_layers}
    layers_seen = set()

    print("==> Filtering polygons...")
    for i, p in enumerate(polygons):
        layer = p.layer
        datatype = p.datatype
        layers_seen.add((layer, datatype))

        if layer not in interesting_layers:
            continue

        pts = p.points
        if pts.shape[0] < 3:
            continue

        # Quick bounding-box reject outside our window
        if (
            pts[:, 0].max() < minx
            or pts[:, 0].min() > maxx
            or pts[:, 1].max() < miny
            or pts[:, 1].min() > maxy
        ):
            continue

        # Shoelace formula for polygon area
        x = pts[:, 0]
        y = pts[:, 1]
        area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
        if area < AREA_MIN:
            continue

        polys_by_layer[layer].append(pts)

        if (i + 1) % 1_000_000 == 0:
            print(f"  ... processed {i + 1:,} polygons")

    print("==> Seen (layer, datatype) pairs:")
    for layer, dt in sorted(layers_seen):
        print(f"  layer={layer}, datatype={dt}")

    print("==> Polygons kept per layer:")
    total_kept = 0
    for l in interesting_layers:
        n = len(polys_by_layer[l])
        total_kept += n
        print(f"  layer {l}: {n:,}")
    print(f"==> Total kept polygons: {total_kept:,}")

    # -----------------------------------------------------
    # Rendering using PolyCollections
    # -----------------------------------------------------
    print("==> Rendering...")
    fig, ax = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=dpi)
    ax.set_facecolor("black")
    fig.patch.set_facecolor("black")

    for layer in interesting_layers:
        polys = polys_by_layer[layer]
        if not polys:
            continue
        shifted = [np.column_stack((p[:, 0] - minx, p[:, 1] - miny)) for p in polys]
        color = layer_colors.get(layer, "#808080")
        coll = PolyCollection(shifted, facecolor=color, edgecolor="none", linewidth=0)
        ax.add_collection(coll)

    ax.set_aspect("equal", "box")
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")

    if args.legend:
        add_legend(ax, palette_name, layer_colors, mode_layers)

    plt.tight_layout(pad=0)

    # -----------------------------------------------------
    # Save image (optionally with downsample)
    # -----------------------------------------------------
    if downsample == 1:
        print(f"==> Writing PNG: {out_path}")
        plt.savefig(
            out_path,
            dpi=dpi,
            facecolor="black",
            bbox_inches="tight",
            pad_inches=0,
        )
    else:
        print("==> Rendering to in-memory buffer for downsampling...")
        buf = io.BytesIO()
        plt.savefig(
            buf,
            format="png",
            dpi=dpi,
            facecolor="black",
            bbox_inches="tight",
            pad_inches=0,
        )
        buf.seek(0)
        img = Image.open(buf)
        target_size = (base_width_px, base_height_px)
        print(f"==> Downsampling to {target_size[0]} x {target_size[1]} px")
        img = img.resize(target_size, Image.LANCZOS)
        img.save(out_path)
        buf.close()
        print(f"==> Writing PNG: {out_path}")

    print("==> DONE ✓")


if __name__ == "__main__":
    main()

