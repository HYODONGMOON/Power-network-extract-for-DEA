# filename: generate_html_only.py
# -*- coding: utf-8 -*-
"""
인터랙티브 HTML 지도만 빠르게 재생성
(OSM 다운로드 없이 기존 GPKG 파일 재활용)

변경 사항:
  - 변전소 크기 50% 축소
  - 변전소 레이어를 2개로 분리:
      * "변전소 (345kV 이상)" - 빨간색 원
      * "변전소 (154kV)"     - 검은색 원
  - 각 레이어 개별 on/off 가능

사용법:
  python generate_html_only.py
  python generate_html_only.py --gpkg ./output/kr_grid_lines.gpkg
"""

import os
import sys
import argparse
import warnings
warnings.filterwarnings("ignore")

# PROJ 경로 설정
try:
    import pyproj
    from pyproj.datadir import set_data_dir
    conda_prefix = os.environ.get("CONDA_PREFIX") or sys.prefix
    proj_path = os.path.join(conda_prefix, "Library", "share", "proj")
    if os.path.isdir(proj_path):
        os.environ["PROJ_LIB"] = proj_path
        os.environ["PROJ_DATA"] = proj_path
        try:
            set_data_dir(proj_path)
        except Exception:
            pass
except Exception:
    pass

os.environ["GEOPANDAS_IO_ENGINE"] = "fiona"

import geopandas as gpd

parser = argparse.ArgumentParser()
parser.add_argument("--gpkg", type=str,
                    default="./output/kr_grid_lines.gpkg",
                    help="기존 GPKG 파일 경로")
parser.add_argument("--out", type=str,
                    default="./output/kr_grid_map_interactive.html",
                    help="출력 HTML 경로")
args, _ = parser.parse_known_args()

WGS84 = "EPSG:4326"

# ─────────────────────────────────────────────
# 1. GPKG에서 레이어 로드
# ─────────────────────────────────────────────
print(f"[1] GPKG 파일 로드: {args.gpkg}")

def load_layer(gpkg_path, layer_name):
    try:
        gdf = gpd.read_file(gpkg_path, layer=layer_name).to_crs(WGS84)
        print(f"    {layer_name}: {len(gdf)}개")
        return gdf
    except Exception as e:
        print(f"    {layer_name}: 없음 ({e})")
        return gpd.GeoDataFrame()

l765  = load_layer(args.gpkg, "lines_765kV")
l345  = load_layer(args.gpkg, "lines_345kV")
l154  = load_layer(args.gpkg, "lines_154kV")
hvdc  = load_layer(args.gpkg, "lines_HVDC")
subs  = load_layer(args.gpkg, "substations")

# ─────────────────────────────────────────────
# 2. 변전소 전압 등급 컬럼 확인/생성
# ─────────────────────────────────────────────
import re

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
    print(f"    변전소 분류: 765kV={len(subs[subs.vclass=='765kV'])}  "
          f"345kV={len(subs[subs.vclass=='345kV'])}  "
          f"154kV={len(subs[subs.vclass=='154kV'])}")

# ─────────────────────────────────────────────
# 3. 송전선 색상
# ─────────────────────────────────────────────
LINE_COLOR = {
    "765kV": "#CC0000",
    "345kV": "#E05000",
    "154kV": "#444499",
    "HVDC":  "#009999",
}

# ─────────────────────────────────────────────
# 4. HTML 지도 생성
# ─────────────────────────────────────────────
print("[2] HTML 지도 생성 중...")
import folium

m = folium.Map(
    location=[36.5, 127.8],
    zoom_start=7,
    tiles="CartoDB positron",  # 흰 육지 + 하늘색 바다
)

# ── 송전선 레이어 그룹
fg_154  = folium.FeatureGroup(name="<span style='color:#444499;font-weight:bold'>■</span> 154 kV",  show=True)
fg_345  = folium.FeatureGroup(name="<span style='color:#E05000;font-weight:bold'>■</span> 345 kV",  show=True)
fg_765  = folium.FeatureGroup(name="<span style='color:#CC0000;font-weight:bold'>■</span> 765 kV",  show=True)
fg_hvdc = folium.FeatureGroup(name="<span style='color:#009999;font-weight:bold'>■</span> HVDC (직류)", show=True)

# ── 변전소 레이어 그룹 (분리)
fg_sub_major = folium.FeatureGroup(
    name="<span style='color:#CC0000;font-weight:bold'>●</span> 변전소 (345kV 이상)", show=True
)
fg_sub_154   = folium.FeatureGroup(
    name="<span style='color:#333333;font-weight:bold'>●</span> 변전소 (154kV)", show=True
)

# ── 송전선 추가 함수
def add_lines(gdf, fg, color, weight, dash=""):
    if gdf.empty:
        return
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        parts = [geom] if geom.geom_type == "LineString" else list(geom.geoms)
        for part in parts:
            coords = [(y, x) for x, y in part.coords]
            if not coords:
                continue
            kw = dict(color=color, weight=weight, opacity=0.85)
            if dash:
                kw["dash_array"] = dash
            name_str = str(row.get("name") or "")
            volt_str = str(row.get("voltage") or "")
            tooltip  = f"{name_str} / {volt_str}".strip(" /")
            folium.PolyLine(coords, tooltip=tooltip or None, **kw).add_to(fg)

add_lines(l154,  fg_154,  LINE_COLOR["154kV"], weight=1.2)
add_lines(l345,  fg_345,  LINE_COLOR["345kV"], weight=2.2)
add_lines(l765,  fg_765,  LINE_COLOR["765kV"], weight=3.2)
add_lines(hvdc,  fg_hvdc, LINE_COLOR["HVDC"],  weight=2.8, dash="8 4")

# ── 변전소 추가
# 크기: 기존의 50% (765kV: 9→4, 345kV: 6→3, 154kV: 4→2)
RADIUS_MAJOR = {"765kV": 4, "345kV": 3}   # 345kV 이상
RADIUS_154   = 2                            # 154kV

COLOR_MAJOR  = "#CC0000"  # 빨간색 (345kV+)
COLOR_154    = "#333333"  # 검은색 (154kV)

if not subs.empty:
    for _, row in subs.iterrows():
        vc = row.get("vclass", "154kV")
        pt = row.geometry
        if pt is None:
            continue
        name_str = str(row.get("name") or "변전소")
        tooltip  = f"{name_str} ({vc})"

        if vc in ("345kV", "765kV"):
            folium.CircleMarker(
                location=[pt.y, pt.x],
                radius=RADIUS_MAJOR.get(vc, 3),
                color=COLOR_MAJOR,
                fill=True,
                fill_color=COLOR_MAJOR,
                fill_opacity=0.85,
                weight=0.8,
                tooltip=tooltip,
            ).add_to(fg_sub_major)
        elif vc == "154kV":
            folium.CircleMarker(
                location=[pt.y, pt.x],
                radius=RADIUS_154,
                color=COLOR_154,
                fill=True,
                fill_color=COLOR_154,
                fill_opacity=0.80,
                weight=0.5,
                tooltip=tooltip,
            ).add_to(fg_sub_154)

# ── 레이어 순서대로 지도에 추가
#    (154kV 먼저 → 위에 주요 선로/변전소가 덮임)
for fg in [fg_154, fg_345, fg_765, fg_hvdc, fg_sub_154, fg_sub_major]:
    fg.add_to(m)

# LayerControl (HTML 이름 태그 허용)
folium.LayerControl(collapsed=False).add_to(m)

# ─────────────────────────────────────────────
# 5. 저장
# ─────────────────────────────────────────────
os.makedirs(os.path.dirname(args.out) if os.path.dirname(args.out) else ".", exist_ok=True)
m.save(args.out)
print(f"[OK] 저장 완료: {args.out}")
print()
print("[레이어 목록]")
print("  [OK] 154 kV 송전선")
print("  [OK] 345 kV 송전선")
print("  [OK] 765 kV 송전선")
print("  [OK] HVDC (직류)")
print("  [OK] 변전소 (345kV 이상) - 빨간 원, 크기 50% 축소")
print("  [OK] 변전소 (154kV)      - 검은 원, 크기 50% 축소")
