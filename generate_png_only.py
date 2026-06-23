# filename: generate_png_only.py
# -*- coding: utf-8 -*-
"""
정적 PNG 지도 생성 (기존 GPKG 파일 재활용 - OSM 다운로드 없음)

생성 파일:
  output/kr_grid_map_all_substations.png    전국 + 전체 변전소 (154kV+) + 수도권 인셋
  output/kr_grid_map_major_substations.png  전국 + 주요 변전소 (345kV+) + 수도권 인셋
  output/kr_grid_map_capital_all.png        수도권 클로즈업 (전체 변전소)
  output/kr_grid_map_capital_major.png      수도권 클로즈업 (주요 변전소)

사용법:
  python generate_png_only.py
  python generate_png_only.py --gpkg ./output/kr_grid_lines.gpkg
"""

import os
import sys
import re
import warnings
warnings.filterwarnings("ignore")

# PROJ 경로 설정
try:
    import pyproj
    from pyproj.datadir import set_data_dir
    conda_prefix = os.environ.get("CONDA_PREFIX") or sys.prefix
    proj_path = os.path.join(conda_prefix, "Library", "share", "proj")
    gdal_path = os.path.join(conda_prefix, "Library", "share", "gdal")
    if os.path.isdir(proj_path):
        os.environ["PROJ_LIB"] = proj_path
        os.environ["PROJ_DATA"] = proj_path
        try:
            set_data_dir(proj_path)
        except Exception:
            pass
    if os.path.isdir(gdal_path):
        os.environ["GDAL_DATA"] = gdal_path
except Exception:
    pass

os.environ["GEOPANDAS_IO_ENGINE"] = "fiona"

import argparse
import geopandas as gpd
import numpy as np
from shapely.ops import unary_union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.gridspec import GridSpec
from pyproj import Transformer

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--gpkg", default="./output/kr_grid_lines.gpkg")
parser.add_argument("--outdir", default="./output")
args, _ = parser.parse_known_args()

os.makedirs(args.outdir, exist_ok=True)

WGS84   = "EPSG:4326"
LEN_CRS = "EPSG:5179"

# 지도 색상 (Netreference 스타일)
MAP_BG_SEA   = "#C5DCE8"
MAP_BG_LAND  = "#F8F8F5"
MAP_BORDER   = "#AAAAAA"
MAP_BORDER_W = 0.5

# 송전선 스타일
LAYER_STYLE = {
    "765kV": {"color": "#CC0000", "linewidth": 2.8, "zorder": 5},
    "345kV": {"color": "#E05000", "linewidth": 1.6, "zorder": 4},
    "154kV": {"color": "#444499", "linewidth": 0.7, "zorder": 3},
    "HVDC":  {"color": "#009999", "linewidth": 2.2, "zorder": 6, "linestyle": "--"},
}

# 변전소 스타일 (edgecolors / linewidths 사용 → geopandas scatter 호환)
SUB_STYLE = {
    "765kV": {"color": "#CC0000", "marker": "s", "markersize": 9,
              "edgecolors": "#880000", "linewidths": 0.8, "zorder": 7},
    "345kV": {"color": "#CC0000", "marker": "o", "markersize": 6,
              "edgecolors": "#880000", "linewidths": 0.6, "zorder": 6},
    "154kV": {"color": "#333333", "marker": "o", "markersize": 3,
              "edgecolors": "#333333", "linewidths": 0.4, "zorder": 5},
}

# 수도권 클로즈업 bbox (WGS84)
CAPITAL_BBOX_WGS = (126.35, 36.95, 127.85, 37.85)

# ─────────────────────────────────────────────
# 1. GPKG 데이터 로드
# ─────────────────────────────────────────────
print(f"[1] GPKG 로드: {args.gpkg}")

def load_layer(layer_name):
    try:
        gdf = gpd.read_file(args.gpkg, layer=layer_name).to_crs(LEN_CRS)
        print(f"    {layer_name}: {len(gdf)}개")
        return gdf
    except Exception as e:
        print(f"    {layer_name}: 없음 ({e})")
        return gpd.GeoDataFrame(geometry=[], crs=LEN_CRS)

l765   = load_layer("lines_765kV")
l345   = load_layer("lines_345kV")
l154   = load_layer("lines_154kV")
hvdc   = load_layer("lines_HVDC")
subs   = load_layer("substations")
admin  = load_layer("admin_provinces")

# ─────────────────────────────────────────────
# 2. 변전소 등급 컬럼 확보
# ─────────────────────────────────────────────
def parse_voltage_to_kv(v):
    if not v or not isinstance(v, str):
        return None
    first = v.split(";")[0].strip()
    digits = re.findall(r"\d+", first)
    if not digits:
        return None
    try:
        return float("".join(digits)) / 1000.0
    except Exception:
        return None

def classify_voltage(kv):
    if kv is None or kv <= 0:
        return None
    if kv >= 700:
        return "765kV"
    if kv >= 300:
        return "345kV"
    if kv >= 130:
        return "154kV"
    return None

if not subs.empty:
    if "vclass" not in subs.columns:
        subs["voltage_kV"] = subs["voltage"].apply(parse_voltage_to_kv)
        subs["vclass"] = subs["voltage_kV"].apply(classify_voltage)
    subs = subs.dropna(subset=["vclass"])
    n765 = len(subs[subs.vclass == "765kV"])
    n345 = len(subs[subs.vclass == "345kV"])
    n154 = len(subs[subs.vclass == "154kV"])
    print(f"    변전소 분류: 765kV={n765}  345kV={n345}  154kV={n154}")

# ─────────────────────────────────────────────
# 3. 보조 데이터 준비
# ─────────────────────────────────────────────

# 한국 육지 폴리곤 (시·도 합집합)
if not admin.empty:
    land_union = admin.dissolve().geometry.iloc[0]
    korea_land_gdf = gpd.GeoDataFrame(geometry=[land_union], crs=LEN_CRS)
else:
    korea_land_gdf = gpd.GeoDataFrame(geometry=[], crs=LEN_CRS)

# 수도권 bbox → LEN_CRS
_tr = Transformer.from_crs(WGS84, LEN_CRS, always_xy=True)
_x0, _y0 = _tr.transform(CAPITAL_BBOX_WGS[0], CAPITAL_BBOX_WGS[1])
_x1, _y1 = _tr.transform(CAPITAL_BBOX_WGS[2], CAPITAL_BBOX_WGS[3])
CAPITAL_BBOX_5179 = (_x0, _y0, _x1, _y1)

# ─────────────────────────────────────────────
# 4. 공통 그리기 함수
# ─────────────────────────────────────────────

def _style_ax(ax, xlim=None, ylim=None):
    """배경(바다·육지·시도 경계) 세팅"""
    ax.set_facecolor(MAP_BG_SEA)               # 바다: 하늘색
    if not korea_land_gdf.empty:
        korea_land_gdf.plot(ax=ax, color=MAP_BG_LAND, zorder=0)   # 육지: 흰색
    if not admin.empty:
        admin.boundary.plot(ax=ax, color=MAP_BORDER,
                            linewidth=MAP_BORDER_W, zorder=1)     # 시·도 경계
    if xlim:
        ax.set_xlim(xlim)
    if ylim:
        ax.set_ylim(ylim)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7, color="#666666", labelcolor="#444444")
    for sp in ax.spines.values():
        sp.set_edgecolor("#AAAAAA")
        sp.set_linewidth(0.6)


def _draw_layers(ax, show_154kv_sub=True):
    """송전선 + 변전소를 ax에 그림"""
    for gdf, key in [(l154, "154kV"), (l345, "345kV"), (l765, "765kV"), (hvdc, "HVDC")]:
        if gdf.empty:
            continue
        s = LAYER_STYLE[key]
        gdf.plot(ax=ax, color=s["color"], linewidth=s["linewidth"],
                 linestyle=s.get("linestyle", "-"), zorder=s["zorder"],
                 alpha=0.85 if key == "154kV" else 0.95)

    if subs.empty:
        return
    layers = ["765kV", "345kV"] + (["154kV"] if show_154kv_sub else [])
    for vclass in layers:
        s = SUB_STYLE[vclass]
        sub_v = subs[subs["vclass"] == vclass]
        if sub_v.empty:
            continue
        sub_v.plot(ax=ax,
                   color=s["color"],
                   marker=s["marker"],
                   markersize=s["markersize"],
                   edgecolors=s["edgecolors"],
                   linewidths=s["linewidths"],
                   zorder=s["zorder"],
                   alpha=0.95)


def _make_legend(ax, show_154kv_sub=True):
    els = [
        Line2D([0], [0], color="#CC0000", linewidth=2.8, label="765 kV 송전선"),
        Line2D([0], [0], color="#E05000", linewidth=1.6, label="345 kV 송전선"),
        Line2D([0], [0], color="#444499", linewidth=0.8, label="154 kV 송전선"),
        Line2D([0], [0], color="#009999", linewidth=2.2, linestyle="--", label="HVDC"),
        Line2D([0], [0], marker="s", color="none",
               markerfacecolor="#CC0000", markeredgecolor="#880000",
               markersize=8, linestyle="None", label="변전소 765kV"),
        Line2D([0], [0], marker="o", color="none",
               markerfacecolor="#CC0000", markeredgecolor="#880000",
               markersize=6, linestyle="None", label="변전소 345kV"),
    ]
    if show_154kv_sub:
        els.append(
            Line2D([0], [0], marker="o", color="none",
                   markerfacecolor="#333333", markeredgecolor="#333333",
                   markersize=4, linestyle="None", label="변전소 154kV")
        )
    ax.legend(handles=els, loc="lower left", fontsize=7.5,
              framealpha=0.95, facecolor="white", edgecolor="#AAAAAA",
              title="범 례", title_fontsize=8)


# ─────────────────────────────────────────────
# 5. 전국 지도 + 수도권 인셋
# ─────────────────────────────────────────────

def draw_national_map(output_path, title, show_154kv_sub=True, figsize=(13, 16)):
    print(f"  그리는 중: {output_path}")
    fig = plt.figure(figsize=figsize, facecolor=MAP_BG_SEA)

    # 메인 지도 (전국)
    ax_main = fig.add_axes([0.04, 0.04, 0.92, 0.89])
    _style_ax(ax_main)
    _draw_layers(ax_main, show_154kv_sub=show_154kv_sub)
    _make_legend(ax_main, show_154kv_sub=show_154kv_sub)
    ax_main.set_title(title, fontsize=12, fontweight="bold",
                      color="#222222", pad=10)
    ax_main.set_xlabel("경도 (°E)", fontsize=8, color="#555555")
    ax_main.set_ylabel("위도 (°N)", fontsize=8, color="#555555")

    # 수도권 인셋 (우하단)
    ax_ins = fig.add_axes([0.62, 0.05, 0.33, 0.30])
    _style_ax(ax_ins,
              xlim=(CAPITAL_BBOX_5179[0], CAPITAL_BBOX_5179[2]),
              ylim=(CAPITAL_BBOX_5179[1], CAPITAL_BBOX_5179[3]))
    _draw_layers(ax_ins, show_154kv_sub=show_154kv_sub)
    ax_ins.set_title("수도권 (확대)", fontsize=8, fontweight="bold",
                     color="#222222", pad=4)
    ax_ins.tick_params(labelsize=6)
    for sp in ax_ins.spines.values():
        sp.set_edgecolor("#CC0000")
        sp.set_linewidth(1.5)

    # 메인 지도에 수도권 사각형 표시
    x0, y0, x1, y1 = CAPITAL_BBOX_5179
    rect = Rectangle((x0, y0), x1 - x0, y1 - y0,
                     linewidth=1.2, edgecolor="#CC0000",
                     facecolor="none", zorder=10)
    ax_main.add_patch(rect)
    ax_main.text(x1 + 8000, y0, "수도권\n(확대)",
                 fontsize=7, color="#CC0000", va="bottom")

    plt.savefig(output_path, dpi=180, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"    [OK] {output_path}")


# ─────────────────────────────────────────────
# 6. 수도권 단독 클로즈업
# ─────────────────────────────────────────────

def draw_capital_map(output_path, title, show_154kv_sub=True, figsize=(10, 9)):
    print(f"  그리는 중: {output_path}")
    fig, ax = plt.subplots(figsize=figsize, facecolor=MAP_BG_SEA)
    _style_ax(ax,
              xlim=(CAPITAL_BBOX_5179[0], CAPITAL_BBOX_5179[2]),
              ylim=(CAPITAL_BBOX_5179[1], CAPITAL_BBOX_5179[3]))
    _draw_layers(ax, show_154kv_sub=show_154kv_sub)
    _make_legend(ax, show_154kv_sub=show_154kv_sub)
    ax.set_title(title, fontsize=11, fontweight="bold", color="#222222", pad=8)
    ax.set_xlabel("경도 (°E)", fontsize=8, color="#555555")
    ax.set_ylabel("위도 (°N)", fontsize=8, color="#555555")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"    [OK] {output_path}")


# ─────────────────────────────────────────────
# 7. 4종 지도 생성
# ─────────────────────────────────────────────
print("\n[2] 지도 생성 중...")

draw_national_map(
    os.path.join(args.outdir, "kr_grid_map_all_substations.png"),
    "대한민국 전력망 현황 — 전체 변전소 (154kV 이상)",
    show_154kv_sub=True,
)

draw_national_map(
    os.path.join(args.outdir, "kr_grid_map_major_substations.png"),
    "대한민국 전력망 현황 — 주요 변전소 (345kV 이상)",
    show_154kv_sub=False,
)

draw_capital_map(
    os.path.join(args.outdir, "kr_grid_map_capital_all.png"),
    "수도권 전력망 현황 — 전체 변전소 (154kV 이상)",
    show_154kv_sub=True,
)

draw_capital_map(
    os.path.join(args.outdir, "kr_grid_map_capital_major.png"),
    "수도권 전력망 현황 — 주요 변전소 (345kV 이상)",
    show_154kv_sub=False,
)

# ─────────────────────────────────────────────
# 완료
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[완료] 생성된 PNG 파일:")
print("=" * 60)
print(f"  {args.outdir}/kr_grid_map_all_substations.png   (전국, 전체 변전소)")
print(f"  {args.outdir}/kr_grid_map_major_substations.png (전국, 주요 변전소)")
print(f"  {args.outdir}/kr_grid_map_capital_all.png       (수도권, 전체 변전소)")
print(f"  {args.outdir}/kr_grid_map_capital_major.png     (수도권, 주요 변전소)")
