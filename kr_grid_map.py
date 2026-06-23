# filename: kr_grid_map.py
# -*- coding: utf-8 -*-
"""
대한민국 전력망 지도 시각화 (OSM 기반)
- 765kV, 345kV, 154kV 송전선 레이어
- HVDC 케이블 레이어
- 주요 변전소 (345kV 이상) 포인트
- 정적 PNG + 인터랙티브 HTML 출력
- 향후 계획망(2030/2038) 오버레이 기능 내장

사용법:
  python kr_grid_map.py               # 전체 한국
  python kr_grid_map.py --quick       # 변전소 생략(빠른 테스트)
  python kr_grid_map.py --no-html     # HTML 지도 생략
"""

import os
import sys
import re
import math
import warnings
from typing import Optional

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)

# PROJ/GDAL 경로 자동 설정
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
    os.environ.setdefault("PROJ_NETWORK", "ON")
except Exception:
    pass

os.environ["GEOPANDAS_IO_ENGINE"] = "fiona"

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point, Polygon, MultiPolygon
from shapely.ops import unary_union
import osmnx as ox
from shapely.geometry import box as shapely_box

import matplotlib
matplotlib.use("Agg")  # 헤드리스 환경 대응
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import matplotlib.patheffects as pe
import argparse
import contextily as ctx

# 한글 폰트 설정 (Windows: 맑은 고딕 / 없으면 NanumGothic 시도)
import matplotlib.font_manager as fm
def _set_korean_font():
    candidates = ["Malgun Gothic", "맑은 고딕", "NanumGothic", "NanumBarunGothic",
                  "AppleGothic", "UnDotum"]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            break
    matplotlib.rcParams["axes.unicode_minus"] = False  # 마이너스 기호 깨짐 방지

_set_korean_font()

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
ox.settings.use_cache = True
ox.settings.cache_folder = "./osm_cache"
os.makedirs(ox.settings.cache_folder, exist_ok=True)
ox.settings.timeout = 300
ox.settings.overpass_rate_limit = True

OUT_DIR = "./output"
os.makedirs(OUT_DIR, exist_ok=True)

WGS84   = "EPSG:4326"
LEN_CRS = "EPSG:5179"   # 한국 투영 좌표계 (미터)

# ─────────────────────────────────────────────
# 지도 색상 설정 (Netreference 스타일: 흰 육지 + 하늘색 바다)
# ─────────────────────────────────────────────
MAP_BG_SEA      = "#C5DCE8"   # 바다 (하늘색)
MAP_BG_LAND     = "#F8F8F5"   # 육지 (거의 흰색)
MAP_BORDER      = "#AAAAAA"   # 시·도 경계선 (연한 회색)
MAP_BORDER_W    = 0.5

# 송전선 스타일 (밝은 배경에 맞게 조정)
LAYER_STYLE = {
    "765kV":  {"color": "#CC0000", "linewidth": 2.8, "zorder": 5, "label": "765 kV"},
    "345kV":  {"color": "#E05000", "linewidth": 1.6, "zorder": 4, "label": "345 kV"},
    "154kV":  {"color": "#444499", "linewidth": 0.7, "zorder": 3, "label": "154 kV"},
    "HVDC":   {"color": "#009999", "linewidth": 2.2, "zorder": 6, "label": "HVDC",
               "linestyle": "--"},
}

# 변전소 스타일
SUB_STYLE = {
    "765kV": {"color": "#CC0000", "marker": "s", "markersize": 9,  "zorder": 7,
              "markeredgecolor": "#880000", "markeredgewidth": 0.8},
    "345kV": {"color": "#CC0000", "marker": "o", "markersize": 6,  "zorder": 6,
              "markeredgecolor": "#880000", "markeredgewidth": 0.6},
    "154kV": {"color": "#333333", "marker": "o", "markersize": 3,  "zorder": 5,
              "markeredgecolor": "#333333", "markeredgewidth": 0.4},
}

# 계획망 오버레이 스타일 (향후 사용)
PLANNED_STYLE = {
    "new":      {"color": "#007700", "linewidth": 2.0, "zorder": 8, "linestyle": "-",
                 "label": "신규 송전선"},
    "upgraded": {"color": "#BB7700", "linewidth": 2.0, "zorder": 8, "linestyle": "-.",
                 "label": "증설/업그레이드"},
    "new_sub":  {"color": "#007700", "marker": "*", "markersize": 10, "zorder": 9},
}

# 수도권 클로즈업 범위 (WGS84)
CAPITAL_BBOX_WGS = (126.35, 36.95, 127.85, 37.85)  # minLon, minLat, maxLon, maxLat

# ─────────────────────────────────────────────
# 인자 파서
# ─────────────────────────────────────────────
parser = argparse.ArgumentParser(description="KR power grid map (OSM)")
parser.add_argument("--area",    type=str, default="South Korea")
parser.add_argument("--bbox",    type=str, default=None)
parser.add_argument("--tiles",   type=int, default=1)
parser.add_argument("--quick",   action="store_true", help="변전소 생략")
parser.add_argument("--no-html", action="store_true", help="인터랙티브 HTML 생략")
parser.add_argument("--overlay", type=str, default=None,
                    help="계획망 오버레이용 Excel 파일 경로 (planned_lines, planned_subs 시트)")
args, _ = parser.parse_known_args()

# ─────────────────────────────────────────────
# 유틸 함수
# ─────────────────────────────────────────────
def parse_voltage_to_kv(v: Optional[str]) -> Optional[float]:
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

def parse_int(val) -> int:
    if val is None:
        return 1
    if isinstance(val, (int, float)) and not math.isnan(float(val)):
        return int(val)
    if isinstance(val, str):
        d = re.findall(r"\d+", val)
        if d:
            return int(d[0])
    return 1

def to_lines(g):
    if isinstance(g, (LineString, MultiLineString)):
        return g
    return None

def to_point(g):
    """Polygon/Point → 중심점 반환"""
    if g is None:
        return None
    if isinstance(g, Point):
        return g
    if isinstance(g, (Polygon, MultiPolygon)):
        return g.centroid
    return None

def classify_voltage(kv: Optional[float]) -> Optional[str]:
    if kv is None or kv <= 0:
        return None
    if kv >= 700:
        return "765kV"
    if kv >= 300:
        return "345kV"
    if kv >= 130:
        return "154kV"
    return None  # 154kV 미만은 표시 안 함

def is_hvdc(row) -> bool:
    """OSM 태그 기반 HVDC 판별"""
    freq = str(row.get("frequency", "") or "").strip()
    dc   = str(row.get("dc", "") or "").strip().lower()
    name = str(row.get("name", "") or "").lower()
    tags = str(row.get("tags", "") or "").lower()
    # frequency=0 이면 DC
    if freq == "0":
        return True
    # dc=yes 태그
    if dc in ("yes", "true", "1"):
        return True
    # 이름에 HVDC/hvdc/직류 포함
    if any(k in name for k in ("hvdc", "직류", "dc line")):
        return True
    return False

def features_from_polygon_tiled(poly, tags, tiles=1):
    if tiles <= 1:
        return ox.features_from_polygon(poly, tags)
    minx, miny, maxx, maxy = poly.bounds
    dx = (maxx - minx) / tiles
    dy = (maxy - miny) / tiles
    frames = []
    for i in range(tiles):
        for j in range(tiles):
            tile = shapely_box(minx+i*dx, miny+j*dy, minx+(i+1)*dx, miny+(j+1)*dy)
            clip = poly.intersection(tile)
            if clip.is_empty:
                continue
            try:
                gdf = ox.features_from_polygon(clip, tags)
                if not gdf.empty:
                    frames.append(gdf)
            except Exception:
                continue
    if not frames:
        return gpd.GeoDataFrame(columns=["geometry"])
    out = pd.concat(frames)
    return out[~out.index.duplicated(keep="first")]

# ─────────────────────────────────────────────
# 1. 대한민국 경계 폴리곤
# ─────────────────────────────────────────────
print("=" * 60)
print("한국 전력망 지도 생성 시작")
print("=" * 60)

print("\n[1] 대한민국 경계 로드 중...")
if args.bbox:
    minx, miny, maxx, maxy = [float(v) for v in args.bbox.split(",")]
    country_poly = shapely_box(minx, miny, maxx, maxy)
else:
    country_gdf  = ox.geocode_to_gdf(args.area)
    country_poly = country_gdf.to_crs(WGS84).iloc[0].geometry
print("  [OK]")

# ─────────────────────────────────────────────
# 2. 시·도 경계
# ─────────────────────────────────────────────
print("[2] 시·도 경계 다운로드 중...")
admin_gdf = features_from_polygon_tiled(
    country_poly,
    {"boundary": "administrative", "admin_level": "4"},
    tiles=args.tiles
)
admin_gdf = admin_gdf[admin_gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
admin_gdf = admin_gdf.set_crs(WGS84, allow_override=True)

ALIASES = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시",
    "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
    "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도",
    "강원": "강원특별자치도", "강원도": "강원특별자치도",
    "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도특별자치도", "전라북도": "전라북도특별자치도",
    "전북특별자치도": "전라북도특별자치도",
    "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도", "제주도": "제주특별자치도",
}
PROVINCES_17 = set(ALIASES.values())

def norm_prov(nm):
    if not isinstance(nm, str):
        return "Unknown"
    k = nm.strip()
    return ALIASES.get(k, k)

admin_gdf["province_name"] = admin_gdf.get("name:ko", admin_gdf.get("name", "Unknown"))
admin_gdf["province_name"] = admin_gdf["province_name"].apply(norm_prov)
admin_gdf = admin_gdf[admin_gdf["province_name"].isin(PROVINCES_17)].copy()
admin_gdf = admin_gdf.dissolve(by="province_name", as_index=False)
admin_5179 = admin_gdf.to_crs(LEN_CRS)
print(f"  [OK] {len(admin_gdf)}개 시·도")

# ─────────────────────────────────────────────
# 3. 전력 인프라 다운로드
# ─────────────────────────────────────────────
print("[3] 전력 인프라 다운로드 중 (시간 소요)...")
tags_power = {"power": ["line", "cable", "substation", "switching_station"]}
power_raw = features_from_polygon_tiled(country_poly, tags_power, tiles=args.tiles)

# frequency / dc 컬럼 확보
for col in ["power", "name", "voltage", "circuits", "frequency", "dc", "operator", "ref"]:
    if col not in power_raw.columns:
        power_raw[col] = None
power_raw = power_raw.set_crs(WGS84, allow_override=True)

# ─────────────────────────────────────────────
# 4. 레이어 분리
# ─────────────────────────────────────────────
print("[4] 레이어 분리 중...")

# ── 4-a. 송전선 (line / cable)
lines_raw = power_raw[power_raw["power"].isin(["line", "cable"])].copy()
lines_raw["geometry"] = lines_raw["geometry"].apply(to_lines)
lines_raw = lines_raw.dropna(subset=["geometry"])
lines_raw = lines_raw.explode(index_parts=False, ignore_index=True)

lines_raw["voltage_kV"] = lines_raw["voltage"].apply(parse_voltage_to_kv)
lines_raw["circuits_n"] = lines_raw["circuits"].apply(parse_int)
lines_raw["hvdc"]       = lines_raw.apply(is_hvdc, axis=1)
lines_raw["vclass"]     = lines_raw["voltage_kV"].apply(classify_voltage)

# HVDC는 별도 레이어로
hvdc_lines  = lines_raw[lines_raw["hvdc"] == True].copy()
ac_lines    = lines_raw[(lines_raw["hvdc"] == False) & (lines_raw["vclass"].notna())].copy()

lines_765   = ac_lines[ac_lines["vclass"] == "765kV"].copy()
lines_345   = ac_lines[ac_lines["vclass"] == "345kV"].copy()
lines_154   = ac_lines[ac_lines["vclass"] == "154kV"].copy()

print(f"  765kV 라인: {len(lines_765)}개")
print(f"  345kV 라인: {len(lines_345)}개")
print(f"  154kV 라인: {len(lines_154)}개")
print(f"  HVDC  라인: {len(hvdc_lines)}개")

# ── 4-b. 변전소
if not args.quick:
    subs_raw = power_raw[power_raw["power"].isin(["substation", "switching_station"])].copy()
    subs_raw["voltage_kV"] = subs_raw["voltage"].apply(parse_voltage_to_kv)
    subs_raw["vclass"]     = subs_raw["voltage_kV"].apply(classify_voltage)
    subs_raw["geometry"]   = subs_raw["geometry"].apply(to_point)
    subs_raw = subs_raw.dropna(subset=["geometry", "vclass"]).copy()
    subs_raw = gpd.GeoDataFrame(subs_raw, geometry="geometry", crs=WGS84)
    print(f"  변전소 (154kV+): {len(subs_raw)}개")
else:
    subs_raw = gpd.GeoDataFrame(columns=["geometry", "vclass", "name", "voltage_kV"])
    print("  변전소: 생략(--quick)")

# ─────────────────────────────────────────────
# 5. 좌표계 변환 (LEN_CRS)
# ─────────────────────────────────────────────
print("[5] 좌표계 변환 중...")
def to_proj(gdf):
    if gdf.empty:
        return gdf
    return gdf.to_crs(LEN_CRS)

l765 = to_proj(lines_765)
l345 = to_proj(lines_345)
l154 = to_proj(lines_154)
hvdc = to_proj(hvdc_lines)
subs = to_proj(subs_raw) if not subs_raw.empty else subs_raw
print("  [OK]")

# ─────────────────────────────────────────────
# 6. 결과 저장 (Excel + CSV)
# ─────────────────────────────────────────────
print("[6] 결과 저장 중...")

def lines_to_df(gdf, vclass_name):
    if gdf.empty:
        return pd.DataFrame()
    df = gdf[["name", "voltage", "voltage_kV", "circuits_n", "operator", "ref"]].copy()
    df["voltage_class"] = vclass_name
    df["length_km"] = gdf.to_crs(LEN_CRS).geometry.length / 1000.0 if gdf.crs != LEN_CRS else gdf.geometry.length / 1000.0
    return df

df_765  = lines_to_df(l765, "765kV")
df_345  = lines_to_df(l345, "345kV")
df_154  = lines_to_df(l154, "154kV")
df_hvdc = lines_to_df(hvdc, "HVDC")
df_all  = pd.concat([df_765, df_345, df_154, df_hvdc], ignore_index=True)

# 변전소 데이터
if not subs.empty:
    df_subs = subs[["name", "voltage", "voltage_kV", "vclass", "operator"]].copy() if not subs.empty else pd.DataFrame()
else:
    df_subs = pd.DataFrame()

# Excel 저장
excel_path = os.path.join(OUT_DIR, "kr_grid_data.xlsx")
with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
    df_all.to_excel(writer, sheet_name="all_lines",       index=False)
    df_765.to_excel(writer,  sheet_name="lines_765kV",    index=False)
    df_345.to_excel(writer,  sheet_name="lines_345kV",    index=False)
    df_154.to_excel(writer,  sheet_name="lines_154kV",    index=False)
    df_hvdc.to_excel(writer, sheet_name="lines_HVDC",     index=False)
    if not df_subs.empty:
        df_subs.to_excel(writer, sheet_name="substations", index=False)

    # 계획망 입력 템플릿 시트 (향후 사용)
    tpl = pd.DataFrame(columns=[
        "name", "from_substation", "to_substation",
        "voltage_kV", "circuits", "length_km",
        "year_planned", "status",  # planned / under_construction / completed
        "from_lon", "from_lat", "to_lon", "to_lat",
        "note"
    ])
    tpl.to_excel(writer, sheet_name="planned_lines_template", index=False)
    tpl_sub = pd.DataFrame(columns=[
        "name", "voltage_kV", "lon", "lat",
        "year_planned", "status", "note"
    ])
    tpl_sub.to_excel(writer, sheet_name="planned_subs_template", index=False)

print(f"  [OK] {excel_path}")

# GPKG 저장 (GIS용)
try:
    for gdf, name in [(l765, "lines_765kV"), (l345, "lines_345kV"),
                      (l154, "lines_154kV"), (hvdc, "lines_HVDC")]:
        if not gdf.empty:
            gdf.to_file(os.path.join(OUT_DIR, "kr_grid_lines.gpkg"),
                        layer=name, driver="GPKG", engine="fiona")
    if not subs.empty:
        subs.to_file(os.path.join(OUT_DIR, "kr_grid_lines.gpkg"),
                     layer="substations", driver="GPKG", engine="fiona")
    admin_5179.to_file(os.path.join(OUT_DIR, "kr_grid_lines.gpkg"),
                       layer="admin_provinces", driver="GPKG", engine="fiona")
    print("  [OK] kr_grid_lines.gpkg")
except Exception as e:
    print(f"  [경고] GPKG 저장 건너뜀: {e}")

# ─────────────────────────────────────────────
# 7. 정적 지도 생성 (PNG)
# ─────────────────────────────────────────────
print("[7] 정적 지도 생성 중...")

# 대한민국 지도 범위 고정 (WGS84 → EPSG:5179)
# — admin.dissolve() 폴리곤은 영해를 포함해 넓게 퍼지므로
#   실제 대한민국 지리 좌표로 직접 지정
from pyproj import Transformer
_tr_sk = Transformer.from_crs(WGS84, LEN_CRS, always_xy=True)
_SK_WGS84 = (124.5, 33.0, 132.0, 38.7)   # (서경, 남위, 동경, 북위)
_skx0, _sky0 = _tr_sk.transform(_SK_WGS84[0], _SK_WGS84[1])
_skx1, _sky1 = _tr_sk.transform(_SK_WGS84[2], _SK_WGS84[3])
_pad_x = (_skx1 - _skx0) * 0.03
_pad_y = (_sky1 - _sky0) * 0.03
KOREA_XLIM = (_skx0 - _pad_x, _skx1 + _pad_x)
KOREA_YLIM = (_sky0 - _pad_y, _sky1 + _pad_y)

# 수도권 bbox (LEN_CRS 변환)
_tr = Transformer.from_crs(WGS84, LEN_CRS, always_xy=True)
_x0, _y0 = _tr.transform(CAPITAL_BBOX_WGS[0], CAPITAL_BBOX_WGS[1])
_x1, _y1 = _tr.transform(CAPITAL_BBOX_WGS[2], CAPITAL_BBOX_WGS[3])
CAPITAL_BBOX_5179 = (_x0, _y0, _x1, _y1)


def _plot_layers(ax, l765, l345, l154, hvdc, subs, show_154kv_sub=True,
                 overlay_lines=None, overlay_subs=None):
    """공통 레이어 그리기 (ax에 직접 그림)"""
    # 154kV
    if not l154.empty:
        s = LAYER_STYLE["154kV"]
        l154.plot(ax=ax, color=s["color"], linewidth=s["linewidth"],
                  zorder=s["zorder"], alpha=0.75)
    # 345kV
    if not l345.empty:
        s = LAYER_STYLE["345kV"]
        l345.plot(ax=ax, color=s["color"], linewidth=s["linewidth"],
                  zorder=s["zorder"], alpha=0.95)
    # 765kV
    if not l765.empty:
        s = LAYER_STYLE["765kV"]
        l765.plot(ax=ax, color=s["color"], linewidth=s["linewidth"], zorder=s["zorder"])
    # HVDC
    if not hvdc.empty:
        s = LAYER_STYLE["HVDC"]
        hvdc.plot(ax=ax, color=s["color"], linewidth=s["linewidth"],
                  linestyle=s.get("linestyle", "-"), zorder=s["zorder"])
    # 변전소
    # geopandas.plot()은 내부적으로 scatter()를 사용하므로
    # markeredgecolor 대신 edgecolors, markeredgewidth 대신 linewidths 사용
    if not subs.empty:
        layers = ["765kV", "345kV"] + (["154kV"] if show_154kv_sub else [])
        for vclass in layers:
            style = SUB_STYLE[vclass]
            sub_v = subs[subs["vclass"] == vclass]
            if not sub_v.empty:
                sub_v.plot(ax=ax,
                           color=style["color"],
                           marker=style["marker"],
                           markersize=style["markersize"],
                           edgecolors=style.get("markeredgecolor", style["color"]),
                           linewidths=style.get("markeredgewidth", 0.5),
                           zorder=style["zorder"], alpha=0.95)
    # 계획망 오버레이
    if overlay_lines is not None and not overlay_lines.empty:
        ps = PLANNED_STYLE["new"]
        overlay_lines.plot(ax=ax, color=ps["color"], linewidth=ps["linewidth"],
                           linestyle=ps["linestyle"], zorder=ps["zorder"])
    if overlay_subs is not None and not overlay_subs.empty:
        ps = PLANNED_STYLE["new_sub"]
        overlay_subs.plot(ax=ax, color=ps["color"], marker=ps["marker"],
                          markersize=ps["markersize"], zorder=ps["zorder"])


def _style_ax(ax, xlim=None, ylim=None):
    """
    축 공통 스타일
    — CartoDB Positron 타일 배경 (HTML 인터랙티브 지도와 동일)
      → 정확한 해안선, 흰 육지, 회색 바다
    """
    # 범위 먼저 설정 (contextily가 이 범위의 타일을 가져옴)
    if xlim:
        ax.set_xlim(xlim)
    if ylim:
        ax.set_ylim(ylim)
    ax.set_aspect("equal")

    # CartoDB Positron 타일 배경
    ctx.add_basemap(
        ax,
        crs=LEN_CRS,
        source=ctx.providers.CartoDB.Positron,
        zoom="auto",
        attribution=False,
    )

    # 시·도 행정경계 (옅은 점선) - 육지 위에 올려서 도 경계만 표시
    if not admin_5179.empty:
        admin_5179.boundary.plot(
            ax=ax, color=MAP_BORDER, linewidth=MAP_BORDER_W,
            linestyle=":", zorder=2, alpha=0.6,
        )

    ax.tick_params(labelsize=7, color="#666666", labelcolor="#444444")
    for spine in ax.spines.values():
        spine.set_edgecolor("#AAAAAA")
        spine.set_linewidth(0.6)


def _legend_handles(show_154kv_sub=True, overlay_label=None):
    """범례 핸들 목록 반환 (axes에 독립 배치 가능)"""
    els = [
        Line2D([0], [0], color=LAYER_STYLE["765kV"]["color"],
               linewidth=2.5, label="765 kV 송전선"),
        Line2D([0], [0], color=LAYER_STYLE["345kV"]["color"],
               linewidth=1.6, label="345 kV 송전선"),
        Line2D([0], [0], color=LAYER_STYLE["154kV"]["color"],
               linewidth=0.8, label="154 kV 송전선"),
        Line2D([0], [0], color=LAYER_STYLE["HVDC"]["color"],
               linewidth=2.0, linestyle="--", label="HVDC"),
        Line2D([0], [0], marker="s", color="none",
               markerfacecolor=SUB_STYLE["765kV"]["color"],
               markeredgecolor=SUB_STYLE["765kV"].get("markeredgecolor","#880000"),
               markersize=10, linestyle="None", label="변전소 765kV"),
        Line2D([0], [0], marker="o", color="none",
               markerfacecolor=SUB_STYLE["345kV"]["color"],
               markeredgecolor=SUB_STYLE["345kV"].get("markeredgecolor","#880000"),
               markersize=8, linestyle="None", label="변전소 345kV"),
    ]
    if show_154kv_sub:
        els.append(
            Line2D([0], [0], marker="o", color="none",
                   markerfacecolor=SUB_STYLE["154kV"]["color"],
                   markeredgecolor="#333333",
                   markersize=5, linestyle="None", label="변전소 154kV")
        )
    if overlay_label:
        els.append(Line2D([0], [0], color=PLANNED_STYLE["new"]["color"],
                          linewidth=2.0, label=f"{overlay_label} 신규선"))
    return els


def _make_legend(ax, show_154kv_sub=True, overlay_label=None):
    """수도권 단독 클로즈업 지도용 (axes에 직접 추가)"""
    ax.legend(handles=_legend_handles(show_154kv_sub, overlay_label),
              loc="lower left", fontsize=11,
              framealpha=0.92, facecolor="white", edgecolor="#AAAAAA",
              title="범 례", title_fontsize=12)


def draw_grid_map(
    admin_gdf_proj, l765, l345, l154, hvdc, subs,
    title="대한민국 전력망 현황",
    output_path=None,
    show_154kv_sub=True,
    show_capital_inset=True,
    overlay_lines=None,
    overlay_subs=None,
    overlay_label=None,
    figsize=(16, 16),
):
    """
    전력망 지도를 그리고 PNG 저장.
    - 수도권 클로즈업: 왼쪽 배치
    - 전국 지도: 오른쪽 배치
    - 빨간 테두리 사각형 없음 (분리 배치로 불필요)
    """
    fig = plt.figure(figsize=figsize, facecolor="white")

    # ── 전국 지도 (우측 이동)
    ax_main = fig.add_axes([0.30, 0.04, 0.68, 0.89])
    _style_ax(ax_main, xlim=KOREA_XLIM, ylim=KOREA_YLIM)
    _plot_layers(ax_main, l765, l345, l154, hvdc, subs,
                 show_154kv_sub=show_154kv_sub,
                 overlay_lines=overlay_lines, overlay_subs=overlay_subs)
    ax_main.set_title(title, fontsize=13, fontweight="bold",
                      color="#222222", pad=10)
    ax_main.set_xlabel("경도 (°E)", fontsize=8, color="#555555")
    ax_main.set_ylabel("위도 (°N)", fontsize=8, color="#555555")

    if show_capital_inset:
        # ── 수도권 클로즈업 (좌측 상단 — 서울 위치 높이에 맞춤)
        ax_inset = fig.add_axes([0.02, 0.58, 0.26, 0.33])
        _style_ax(ax_inset,
                  xlim=(CAPITAL_BBOX_5179[0], CAPITAL_BBOX_5179[2]),
                  ylim=(CAPITAL_BBOX_5179[1], CAPITAL_BBOX_5179[3]))
        _plot_layers(ax_inset, l765, l345, l154, hvdc, subs,
                     show_154kv_sub=show_154kv_sub)
        ax_inset.set_title("수도권 (확대)", fontsize=10, fontweight="bold",
                            color="#222222", pad=5)
        ax_inset.tick_params(labelsize=6)
        for spine in ax_inset.spines.values():
            spine.set_edgecolor("#CC0000")
            spine.set_linewidth(1.5)

        # ── 범례 (좌측 하단 — 인셋 아래)
        ax_leg = fig.add_axes([0.02, 0.06, 0.26, 0.48])
        ax_leg.axis("off")
        ax_leg.legend(handles=_legend_handles(show_154kv_sub, overlay_label),
                      loc="upper left", fontsize=11,
                      framealpha=0.95, facecolor="white", edgecolor="#AAAAAA",
                      title="범 례", title_fontsize=12, frameon=True,
                      borderpad=1.0, labelspacing=0.8)

    plt.savefig(output_path, dpi=180, bbox_inches="tight",
                facecolor="white")
    print(f"  [OK] {output_path}")
    plt.close(fig)


# ── 버전 1: 모든 변전소 포함
draw_grid_map(
    admin_5179, l765, l345, l154, hvdc, subs,
    title="대한민국 전력망 현황 — 전체 변전소 (154kV 이상)",
    output_path=os.path.join(OUT_DIR, "kr_grid_map_all_substations.png"),
    show_154kv_sub=True,
    show_capital_inset=True,
)

# ── 버전 2: 주요 변전소만 (345kV 이상)
draw_grid_map(
    admin_5179, l765, l345, l154, hvdc, subs,
    title="대한민국 전력망 현황 — 주요 변전소 (345kV 이상)",
    output_path=os.path.join(OUT_DIR, "kr_grid_map_major_substations.png"),
    show_154kv_sub=False,
    show_capital_inset=True,
)

# ── 수도권 단독 클로즈업 (별도 파일)
def draw_capital_map(
    admin_gdf_proj, l765, l345, l154, hvdc, subs,
    output_path=None,
    show_154kv_sub=True,
    figsize=(10, 9),
):
    fig, ax = plt.subplots(figsize=figsize, facecolor=MAP_BG_SEA)
    _style_ax(ax,
              xlim=(CAPITAL_BBOX_5179[0], CAPITAL_BBOX_5179[2]),
              ylim=(CAPITAL_BBOX_5179[1], CAPITAL_BBOX_5179[3]))
    _plot_layers(ax, l765, l345, l154, hvdc, subs, show_154kv_sub=show_154kv_sub)
    _make_legend(ax, show_154kv_sub=show_154kv_sub)
    title_suf = "전체 변전소" if show_154kv_sub else "주요 변전소 (345kV+)"
    ax.set_title(f"수도권 전력망 현황 ({title_suf})", fontsize=12,
                 fontweight="bold", color="#222222", pad=8)
    ax.set_xlabel("경도 (°E)", fontsize=8, color="#555555")
    ax.set_ylabel("위도 (°N)", fontsize=8, color="#555555")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"  [OK] {output_path}")
    plt.close(fig)

draw_capital_map(
    admin_5179, l765, l345, l154, hvdc, subs,
    output_path=os.path.join(OUT_DIR, "kr_grid_map_capital_all.png"),
    show_154kv_sub=True,
)
draw_capital_map(
    admin_5179, l765, l345, l154, hvdc, subs,
    output_path=os.path.join(OUT_DIR, "kr_grid_map_capital_major.png"),
    show_154kv_sub=False,
)

# ─────────────────────────────────────────────
# 8. 계획망 오버레이 (--overlay 지정 시)
# ─────────────────────────────────────────────
if args.overlay:
    print(f"[8] 계획망 오버레이 로드: {args.overlay}")
    try:
        xl = pd.ExcelFile(args.overlay)

        for scenario, sheet_name, label in [
            ("2030", "planned_lines_2030", "2030 계획"),
            ("2038", "planned_lines_2038", "2038 계획"),
        ]:
            if sheet_name not in xl.sheet_names:
                print(f"  [{scenario}] 시트 없음 ({sheet_name}) - 건너뜀")
                continue
            df_plan = pd.read_excel(args.overlay, sheet_name=sheet_name)
            # 좌표 기반 GeoDataFrame 생성
            geoms = []
            for _, row in df_plan.iterrows():
                try:
                    geoms.append(LineString([
                        (float(row["from_lon"]), float(row["from_lat"])),
                        (float(row["to_lon"]),   float(row["to_lat"])),
                    ]))
                except Exception:
                    geoms.append(None)
            plan_gdf = gpd.GeoDataFrame(df_plan, geometry=geoms, crs=WGS84).dropna(subset=["geometry"])
            plan_gdf = plan_gdf.to_crs(LEN_CRS)

            # 신규 변전소
            plan_subs_gdf = None
            sub_sheet = f"planned_subs_{scenario}"
            if sub_sheet in xl.sheet_names:
                df_psub = pd.read_excel(args.overlay, sheet_name=sub_sheet)
                s_geoms = [Point(float(r["lon"]), float(r["lat"])) for _, r in df_psub.iterrows()]
                plan_subs_gdf = gpd.GeoDataFrame(df_psub, geometry=s_geoms, crs=WGS84).to_crs(LEN_CRS)

            draw_grid_map(
                admin_5179, l765, l345, l154, hvdc, subs,
                title=f"대한민국 전력망 {scenario}년 계획 ({label})",
                output_path=os.path.join(OUT_DIR, f"kr_grid_map_{scenario}.png"),
                overlay_lines=plan_gdf,
                overlay_subs=plan_subs_gdf,
                overlay_label=label,
            )
    except Exception as e:
        print(f"  [경고] 계획망 오버레이 오류: {e}")

# ─────────────────────────────────────────────
# 9. 인터랙티브 HTML 지도 (folium)
# ─────────────────────────────────────────────
if not args.no_html:
    print("[9] 인터랙티브 HTML 지도 생성 중...")
    try:
        import folium

        m = folium.Map(
            location=[36.5, 127.8],
            zoom_start=7,
            tiles="CartoDB positron",   # 밝은 배경 (육지 흰색, 바다 하늘색)
        )

        # ── 송전선 레이어 그룹 (색상 사각형 아이콘 포함)
        fg_154  = folium.FeatureGroup(
            name="<span style='color:#444499;font-weight:bold'>■</span> 154 kV", show=True)
        fg_345  = folium.FeatureGroup(
            name="<span style='color:#E05000;font-weight:bold'>■</span> 345 kV", show=True)
        fg_765  = folium.FeatureGroup(
            name="<span style='color:#CC0000;font-weight:bold'>■</span> 765 kV", show=True)
        fg_hvdc = folium.FeatureGroup(
            name="<span style='color:#009999;font-weight:bold'>■</span> HVDC (직류)", show=True)

        # ── 변전소 레이어 그룹 — 345kV 이상 / 154kV 분리
        fg_sub_major = folium.FeatureGroup(
            name="<span style='color:#CC0000;font-weight:bold'>●</span> 변전소 (345kV 이상)",
            show=True)
        fg_sub_154   = folium.FeatureGroup(
            name="<span style='color:#333333;font-weight:bold'>●</span> 변전소 (154kV)",
            show=True)

        def add_lines_to_fg(gdf, fg, color, weight, dash=""):
            if gdf.empty:
                return
            gdf_wgs = gdf.to_crs(WGS84)
            for _, row in gdf_wgs.iterrows():
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

        add_lines_to_fg(l154,  fg_154,  LAYER_STYLE["154kV"]["color"], 1.2)
        add_lines_to_fg(l345,  fg_345,  LAYER_STYLE["345kV"]["color"], 2.2)
        add_lines_to_fg(l765,  fg_765,  LAYER_STYLE["765kV"]["color"], 3.2)
        add_lines_to_fg(hvdc,  fg_hvdc, LAYER_STYLE["HVDC"]["color"],  2.8, dash="8 4")

        # ── 변전소 추가 (크기 50% 축소: 765kV=4, 345kV=3, 154kV=2)
        if not subs.empty:
            subs_wgs = subs.to_crs(WGS84)
            for _, row in subs_wgs.iterrows():
                vc = row.get("vclass", "154kV")
                pt = row.geometry
                if pt is None:
                    continue
                name_str = str(row.get("name") or "변전소")
                tooltip  = f"{name_str} ({vc})"

                if vc in ("345kV", "765kV"):
                    radius = 4 if vc == "765kV" else 3
                    folium.CircleMarker(
                        location=[pt.y, pt.x],
                        radius=radius,
                        color="#CC0000",
                        fill=True, fill_color="#CC0000",
                        fill_opacity=0.85, weight=0.8,
                        tooltip=tooltip,
                    ).add_to(fg_sub_major)
                elif vc == "154kV":
                    folium.CircleMarker(
                        location=[pt.y, pt.x],
                        radius=2,
                        color="#333333",
                        fill=True, fill_color="#333333",
                        fill_opacity=0.80, weight=0.5,
                        tooltip=tooltip,
                    ).add_to(fg_sub_154)

        # ── 레이어 지도에 추가 (154kV 먼저 → 주요 레이어가 위로)
        for fg in [fg_154, fg_345, fg_765, fg_hvdc, fg_sub_154, fg_sub_major]:
            fg.add_to(m)

        # LayerControl (HTML 이름 태그 허용)
        folium.LayerControl(collapsed=False).add_to(m)

        html_path = os.path.join(OUT_DIR, "kr_grid_map_interactive.html")
        m.save(html_path)
        print(f"  [OK] {html_path}")
    except ImportError:
        print("  [건너뜀] folium 미설치. pip install folium 으로 설치 후 재실행.")
    except Exception as e:
        print(f"  [경고] HTML 지도 오류: {e}")

# ─────────────────────────────────────────────
# 완료
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[완료] 생성된 파일 목록:")
print("=" * 60)
print("  [정적 지도 (PNG)]")
print("  output/kr_grid_map_all_substations.png   ← 전체 변전소 포함 (전국)")
print("  output/kr_grid_map_major_substations.png ← 주요 변전소만 (345kV+, 전국)")
print("  output/kr_grid_map_capital_all.png       ← 수도권 클로즈업 (전체 변전소)")
print("  output/kr_grid_map_capital_major.png     ← 수도권 클로즈업 (주요 변전소)")
print()
print("  [데이터]")
print("  output/kr_grid_data.xlsx         ← 전압별 라인/변전소 + 계획망 템플릿")
print("  output/kr_grid_lines.gpkg        ← GIS 파일 (QGIS용)")
print("  output/kr_grid_map_interactive.html ← 인터랙티브 지도 (레이어 on/off)")
print()
print("[계획망 오버레이 방법 (2030/2038)]")
print("  1. kr_grid_data.xlsx 의 'planned_lines_template' 시트 복사 → 데이터 입력")
print("  2. python kr_grid_map.py --overlay planned_grid.xlsx")
print("  → kr_grid_map_2030.png, kr_grid_map_2038.png 자동 생성")
print()
print("[통계 요약]")
print(f"  765kV: {len(l765)}개  |  345kV: {len(l345)}개  |  154kV: {len(l154)}개  |  HVDC: {len(hvdc)}개")
if not subs.empty:
    n765 = len(subs[subs["vclass"]=="765kV"])
    n345 = len(subs[subs["vclass"]=="345kV"])
    n154 = len(subs[subs["vclass"]=="154kV"])
    print(f"  변전소: 765kV {n765}개 | 345kV {n345}개 | 154kV {n154}개 (합계 {len(subs)}개)")
