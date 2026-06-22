# filename: kr_power_network_extract.py
# -*- coding: utf-8 -*-
"""
대한민국 전력망 (OSM 기반) 추출/집계 스크립트
- 전력선(line/cable) 길이 산출
- 시·도별(length by province) 길이 집계
- 시·도 간 연결 엣지(province-to-province) 도출
- voltage/circuits 기반 proxy 용량 지표 산출 (참고용)
- 표준 송전용량(capacity_mw) 산출 (154kV: 150MW/회선, 345kV: 800MW/회선, 765kV: 3500MW/회선)

주의:
- OSM 데이터는 커버리지/정확성이 100%가 아닐 수 있음
- 'capacity_proxy'는 상대 비교용 지표 (kV × 회선수)
- 'capacity_mw'는 문헌 기반 표준 송전용량 (보수적 추정치)
"""

import os
import sys
import re
import math
import warnings
from itertools import combinations
from typing import List, Tuple, Optional
import argparse

import pandas as pd
import numpy as np
from tqdm import tqdm

warnings.filterwarnings("ignore", category=UserWarning)
# PROJ/GDAL 경로 자동 설정(윈도우/conda 환경 대응)
try:
    import pyproj
    from pyproj.datadir import get_data_dir, set_data_dir
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

# GeoPandas가 Fiona 엔진을 사용하도록 설정
os.environ["GEOPANDAS_IO_ENGINE"] = "fiona"

# PROJ 설정 이후에 지오스택 임포트
import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point, MultiPoint
from shapely.ops import unary_union
import osmnx as ox
from shapely.geometry import box as shapely_box

# OSMnx 설정(캐시/타임아웃/레이트리밋)
ox.settings.use_cache = True
ox.settings.cache_folder = "./osm_cache"
os.makedirs(ox.settings.cache_folder, exist_ok=True)
ox.settings.timeout = 300
ox.settings.overpass_rate_limit = True
ox.settings.nominatim_sleep = 1

# ------------------------------
# 설정
# ------------------------------
OUT_DIR = "./output"
os.makedirs(OUT_DIR, exist_ok=True)

# 좌표계: 길이 계산을 위한 한국 투영 좌표계 (미터 단위)
# EPSG:5179 (Korea 2000 / Unified CS)
LEN_CRS = "EPSG:5179"
WGS84 = "EPSG:4326"

# 시·도 경계 필터
ADMIN_LEVEL_TARGET = "4"   # admin_level=4 (광역지자체)

# ------------------------------
# 인자 파서
# ------------------------------
parser = argparse.ArgumentParser(description="KR power network extractor (OSM)")
parser.add_argument("--area", type=str, default="South Korea", help="지오코딩 영역 이름(예: 'Seoul', 기본: South Korea)")
parser.add_argument("--bbox", type=str, default=None, help="WGS84 bbox 'minx,miny,maxx,maxy' 형식. 지정 시 area 무시")
parser.add_argument("--tiles", type=int, default=1, help="Overpass 타일 분할 수(NxN). 넓은 영역에서 시간 단축에 도움")
parser.add_argument("--overpass-endpoint", type=str, default=None, help="Overpass API 엔드포인트 URL")
parser.add_argument("--timeout", type=int, default=300, help="Overpass 타임아웃(초)")
parser.add_argument("--quick", action="store_true", help="빠른 모드: 변전소 다운로드 생략")
args, _ = parser.parse_known_args()

# 사용자 설정 적용
if args.overpass_endpoint:
    ox.settings.overpass_endpoint = args.overpass_endpoint
if args.timeout:
    ox.settings.timeout = int(args.timeout)

# ------------------------------
# 유틸 함수
# ------------------------------
def parse_voltage_to_kv(v: Optional[str]) -> Optional[float]:
    """
    OSM voltage 태그는 '765000;345000'처럼 세미콜론 구분 또는 단일값(볼트)일 수 있음.
    - 첫 번째 값을 사용하고 V->kV로 변환
    - 숫자만 추출
    """
    if not v or not isinstance(v, str):
        return None
    # 첫 번째 세그먼트만
    first = v.split(";")[0].strip()
    digits = re.findall(r"\d+", first)
    if not digits:
        return None
    try:
        val_v = float("".join(digits))  # '765000' -> 765000
        return val_v / 1000.0  # kV
    except Exception:
        return None


def parse_int(val: Optional[str]) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, float) and not math.isnan(val):
        return int(val)
    if isinstance(val, str):
        digits = re.findall(r"\d+", val)
        if digits:
            return int(digits[0])
    return None


def to_lines(g):
    """LineString/MultiLineString 외의 geometry는 None으로."""
    if g is None:
        return None
    if isinstance(g, (LineString, MultiLineString)):
        return g
    return None


def explode_multilines(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """MultiLineString을 개별 LineString으로 분리."""
    if gdf.empty:
        return gdf
    return gdf.explode(index_parts=False, ignore_index=True)


def safe_length_km(geom: LineString) -> float:
    """길이(m) -> km (투영 좌표계에서 계산)"""
    return float(geom.length) / 1000.0


def features_from_polygon_tiled(target_polygon, tags, tiles: int) -> gpd.GeoDataFrame:
    """큰 폴리곤을 NxN 타일로 나눠 순차 요청 후 병합."""
    if tiles is None or tiles <= 1:
        return ox.features_from_polygon(target_polygon, tags)
    minx, miny, maxx, maxy = target_polygon.bounds
    dx = (maxx - minx) / tiles
    dy = (maxy - miny) / tiles
    frames = []
    for i in range(tiles):
        for j in range(tiles):
            tile_poly = shapely_box(minx + i*dx, miny + j*dy, minx + (i+1)*dx, miny + (j+1)*dy)
            clip_poly = target_polygon.intersection(tile_poly)
            if clip_poly.is_empty:
                continue
            try:
                gdf = ox.features_from_polygon(clip_poly, tags)
                if not gdf.empty:
                    frames.append(gdf)
            except Exception:
                continue
    if not frames:
        return gpd.GeoDataFrame(columns=["geometry"])  # empty
    out = pd.concat(frames)
    out = out[~out.index.duplicated(keep="first")]
    return out

# ------------------------------
# 1) 대한민국 폴리곤 가져오기
# ------------------------------
print("1) 대한민국 경계 폴리곤 불러오는 중...")
if args.bbox:
    try:
        minx, miny, maxx, maxy = [float(v) for v in args.bbox.split(",")]
        country_poly = shapely_box(minx, miny, maxx, maxy)
    except Exception:
        raise ValueError("--bbox 형식은 'minx,miny,maxx,maxy' 입니다.")
else:
    country_gdf = ox.geocode_to_gdf(args.area)
    country_poly = country_gdf.to_crs(WGS84).iloc[0].geometry

# ------------------------------
# 2) 전력 인프라 다운로드 (OSM)
# ------------------------------
print("2) 전력 인프라(선/변전소) 다운로드 중... (시간 소요)")
tags_power = {
    "power": ["line", "cable", "substation", "switching_station"]
}
power_gdf = features_from_polygon_tiled(country_poly, tags_power, tiles=int(args.tiles))

# 필요한 컬럼만 정리
keep_cols = [
    "power", "name", "voltage", "circuits", "operator",
    "rating", "frequency", "ref", "source", "layer"
]
for c in keep_cols:
    if c not in power_gdf.columns:
        power_gdf[c] = None

power_gdf = power_gdf[keep_cols + ["geometry"]].copy()
power_gdf = power_gdf.set_crs(WGS84, allow_override=True)

# 전력선만 분리 (line/cable)
lines = power_gdf[power_gdf["power"].isin(["line", "cable"])].copy()
lines["geometry"] = lines["geometry"].apply(to_lines)
lines = lines.dropna(subset=["geometry"])
lines = explode_multilines(lines)

# 변전소/개폐소
subs = gpd.GeoDataFrame(columns=power_gdf.columns)
if not args.quick:
    subs = power_gdf[power_gdf["power"].isin(["substation", "switching_station"])].copy()

# ------------------------------
# 3) 시·도 경계(admin_level=4) 가져오기
# ------------------------------
print("3) 시·도(admin_level=4) 경계 다운로드 중...")
tags_admin = {
    "boundary": "administrative",
    "admin_level": ADMIN_LEVEL_TARGET
}
admin_gdf = features_from_polygon_tiled(country_poly, tags_admin, tiles=max(1, int(args.tiles)//2))
# 폴리곤만 필터
admin_gdf = admin_gdf[admin_gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
admin_gdf = admin_gdf[["name", "name:en", "name:ko", "admin_level", "geometry"]].copy()
admin_gdf = admin_gdf.set_crs(WGS84, allow_override=True)

# admin_level=4 강제 필터링
admin_gdf["admin_level"] = admin_gdf["admin_level"].astype(str)
admin_gdf = admin_gdf[admin_gdf["admin_level"] == str(ADMIN_LEVEL_TARGET)].copy()

# 시·도 이름 표준화 컬럼 생성 (ko > name > en 우선)
admin_gdf["province_name"] = admin_gdf.get("name:ko")
if "province_name" in admin_gdf.columns:
    admin_gdf["province_name"] = admin_gdf["province_name"].fillna(admin_gdf.get("name"))
    admin_gdf["province_name"] = admin_gdf["province_name"].fillna(admin_gdf.get("name:en"))
else:
    admin_gdf["province_name"] = admin_gdf.get("name")
    admin_gdf["province_name"] = admin_gdf["province_name"].fillna(admin_gdf.get("name:en"))
admin_gdf["province_name"] = admin_gdf["province_name"].fillna("Unknown")

# 17개 광역지자체 이름 정규화(이명/약칭 매핑)
PROVINCES_17 = {
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시",
    "세종특별자치시", "경기도", "강원특별자치도", "충청북도", "충청남도",
    "전라북도특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도"
}
ALIASES = {
    "서울": "서울특별시", "서울시": "서울특별시",
    "부산": "부산광역시", "부산시": "부산광역시",
    "대구": "대구광역시", "대구시": "대구광역시",
    "인천": "인천광역시", "인천시": "인천광역시",
    "광주": "광주광역시", "광주시": "광주광역시",
    "대전": "대전광역시", "대전시": "대전광역시",
    "울산": "울산광역시", "울산시": "울산광역시",
    "세종": "세종특별자치시", "세종시": "세종특별자치시", "세종특별자치시": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도", "강원도": "강원특별자치도",
    "충북": "충청북도", "충청북도": "충청북도",
    "충남": "충청남도", "충청남도": "충청남도",
    "전북": "전라북도특별자치도", "전라북도": "전라북도특별자치도", "전북특별자치도": "전라북도특별자치도",
    "전남": "전라남도", "전라남도": "전라남도",
    "경북": "경상북도", "경상북도": "경상북도",
    "경남": "경상남도", "경상남도": "경상남도",
    "제주": "제주특별자치도", "제주도": "제주특별자치도"
}

def normalize_province(nm: str) -> str:
    if not isinstance(nm, str):
        return "Unknown"
    key = nm.strip()
    return ALIASES.get(key, key)

admin_gdf["province_name"] = admin_gdf["province_name"].apply(normalize_province)
# 대한민국/Unknown 등 제거 + 17개만 유지
admin_gdf = admin_gdf[admin_gdf["province_name"].isin(PROVINCES_17)].copy()

# 동명 다중 피처를 하나로 병합(dissolve)하여 정확히 17개로 통일
admin_gdf = admin_gdf.dissolve(by="province_name", as_index=False)

# ------------------------------
# 4) 길이 계산을 위한 투영 (EPSG:5179)
# ------------------------------
print("4) 좌표계 변환 및 길이 계산 준비...")
lines_5179 = lines.to_crs(LEN_CRS)
admin_5179 = admin_gdf.to_crs(LEN_CRS)

# 전압/회선수 파싱 + proxy 용량지표
print("   전압/회선수 파싱 및 proxy 지표 계산...")
lines_5179["voltage_kV"] = lines_5179["voltage"].apply(parse_voltage_to_kv)
lines_5179["circuits_n"] = lines_5179["circuits"].apply(parse_int)
lines_5179["voltage_kV"] = lines_5179["voltage_kV"].fillna(0)
lines_5179["circuits_n"] = lines_5179["circuits_n"].fillna(1)  # 미기재는 1회선 가정

# 간단한 proxy: kV * circuits (상대 비교용 지표, 단위 없음)
lines_5179["capacity_proxy"] = lines_5179["voltage_kV"] * lines_5179["circuits_n"]

# 표준 송전용량 (MW per circuit) - 문헌 및 전력거래소 기준
STANDARD_CAPACITY_MW = {
    15: 5,      # 15kV 배전선
    22: 10,     # 22kV 배전선
    23: 10,     # 22.9kV 배전선
    33: 10,     # 33kV
    66: 50,     # 66kV
    110: 100,   # 110kV
    145: 80,    # 145kV
    150: 100,   # 150kV
    154: 150,   # 154kV (한국 표준)
    180: 200,   # 180kV
    220: 300,   # 220kV
    250: 400,   # 250kV
    345: 800,   # 345kV (한국 표준)
    380: 1000,  # 380kV
    500: 2000,  # 500kV
    765: 3500,  # 765kV (한국 표준, 회선당)
}

# 표준 용량 계산 (MW)
def get_standard_capacity_mw(voltage_kv: float, circuits: int) -> float:
    """전압과 회선수를 기반으로 표준 송전용량(MW) 계산"""
    if voltage_kv is None or np.isnan(voltage_kv) or voltage_kv <= 0:
        return 0.0
    # 가장 가까운 표준 전압 찾기
    candidates = list(STANDARD_CAPACITY_MW.keys())
    diffs = [abs(voltage_kv - c) for c in candidates]
    closest_kv = candidates[int(np.argmin(diffs))]
    capacity_per_circuit = STANDARD_CAPACITY_MW[closest_kv]
    return float(capacity_per_circuit * circuits)

lines_5179["capacity_mw"] = lines_5179.apply(
    lambda row: get_standard_capacity_mw(row["voltage_kV"], row["circuits_n"]),
    axis=1
)

# 길이(km)
lines_5179["length_km"] = lines_5179.geometry.length / 1000.0

# ------------------------------
# 5) 시·도별 길이 집계 (정확한 교차 길이 산출)
#    - overlay(intersection)로 경계 따라 라인 분절 후 길이 합산
# ------------------------------
print("5) 시·도별 길이 집계(overlay 교차) 중... (시간 다소 소요)")
# 성능 개선: admin dissolve 없음(이미 개별 시·도)
# 라인과 폴리곤 교차 전, 라인에 고유 ID 부여(overlay에서 보존)
lines_5179 = lines_5179.reset_index(drop=False).rename(columns={"index": "line_id"})
# 라인과 폴리곤 교차
intersection = gpd.overlay(lines_5179, admin_5179, how="intersection")

# 교차 결과 길이 재계산
intersection["seg_length_km"] = intersection.geometry.length / 1000.0

# 시·도별 총 길이
len_by_province = (
    intersection.groupby("province_name", as_index=False)
    .agg(
        total_length_km=("seg_length_km", "sum"),
        avg_voltage_kV=("voltage_kV", "mean"),
        avg_circuits=("circuits_n", "mean"),
        sum_capacity_proxy=("capacity_proxy", "sum"),
        sum_capacity_mw=("capacity_mw", "sum")
    )
    .sort_values("total_length_km", ascending=False)
)

# ------------------------------
# 6) 시·도 간 연결 엣지 도출
#    아이디어:
#      - 원본 라인별로 교차 결과의 시·도 집합을 보고,
#        두 개 이상의 시·도에 걸치면 모든 조합을 엣지로 기록
#      - 엣지 길이는 경계 걸친 라인의 시·도별 분절 길이를
#        '한 라인 내에서' 최소값/평균 등으로 요약할 수 있으나,
#        실무에선 단순 '연결 있음(카운트)'를 흔히 사용
# ------------------------------
print("6) 시·도 간 연결 엣지 계산 중...")
# overlay 결과 정리
intersection = intersection.reset_index(drop=True)

# 각 라인별 포함 시·도 목록
line_provinces = (
    intersection.groupby("line_id")["province_name"]
    .apply(lambda s: sorted(set([str(x) for x in s if pd.notnull(x)])))
    .reset_index()
)

edges = []
for _, row in line_provinces.iterrows():
    provs = row["province_name"]
    if len(provs) >= 2:
        for a, b in combinations(provs, 2):
            edges.append((a, b))

edges_df = pd.DataFrame(edges, columns=["province_a", "province_b"])
# 무방향 엣지 정렬(서울-경기 == 경기-서울)
edges_df[["p_min", "p_max"]] = np.sort(edges_df[["province_a", "province_b"]].values, axis=1)
edges_agg = (
    edges_df.groupby(["p_min", "p_max"])
    .size()
    .reset_index(name="line_cross_count")
    .rename(columns={"p_min": "province_u", "p_max": "province_v"})
    .sort_values("line_cross_count", ascending=False)
)

# ------------------------------
# 6-b) 시·도 간 전압별 길이/회선/용량 집계
# ------------------------------

def classify_voltage_kv(voltage_kv: float) -> str:
    if voltage_kv is None or np.isnan(voltage_kv) or voltage_kv <= 0:
        return "unknown"
    # 한국 전력망 대표 등급 중심으로 구간화
    if voltage_kv >= 700:
        return ">=765kV"
    if voltage_kv >= 300:
        return "345kV"
    if voltage_kv >= 150:
        return "154kV"
    if voltage_kv >= 60:
        return "66kV"
    return "<60kV"

def snap_voltage_kv(voltage_kv: float) -> Optional[int]:
    if voltage_kv is None or np.isnan(voltage_kv) or voltage_kv <= 0:
        return None
    candidates = [765, 500, 345, 220, 154, 110, 66, 33]
    diffs = [abs(voltage_kv - c) for c in candidates]
    return int(candidates[int(np.argmin(diffs))])

# 라인-시도 분절 정보
seg_cols = ["line_id", "province_name", "seg_length_km", "voltage_kV", "circuits_n", "capacity_mw"]
seg_info = intersection[seg_cols].copy()

pair_rows = []
for line_id, df_line in seg_info.groupby("line_id"):
    # 라인 단위 속성(전압/회선): 세그먼트 간 상이할 수 있으나 일반적으로 동일하므로 대표값 사용
    kv = float(df_line["voltage_kV"].dropna().iloc[0]) if df_line["voltage_kV"].notna().any() else 0.0
    circuits = int(df_line["circuits_n"].dropna().iloc[0]) if df_line["circuits_n"].notna().any() else 1
    capacity_mw_val = float(df_line["capacity_mw"].dropna().iloc[0]) if df_line["capacity_mw"].notna().any() else 0.0
    # 시도별 총 길이
    per_prov = df_line.groupby("province_name", as_index=False)["seg_length_km"].sum()
    provs = sorted(per_prov["province_name"].tolist())
    if len(provs) < 2:
        continue
    # 모든 조합에 대해 길이 proxy = min(len in A, len in B)
    for i in range(len(provs)):
        for j in range(i+1, len(provs)):
            a, b = provs[i], provs[j]
            len_a = float(per_prov.loc[per_prov["province_name"] == a, "seg_length_km"].iloc[0])
            len_b = float(per_prov.loc[per_prov["province_name"] == b, "seg_length_km"].iloc[0])
            pair_len_proxy = min(len_a, len_b)
            p_u, p_v = sorted([a, b])
            pair_rows.append({
                "province_u": p_u,
                "province_v": p_v,
                "voltage_kV": kv,
                "voltage_kV_snapped": snap_voltage_kv(kv),
                "voltage_class": classify_voltage_kv(kv),
                "pair_length_km": pair_len_proxy,
                "circuits_n": circuits,
                "capacity_proxy": kv * circuits,
                "capacity_mw": capacity_mw_val
            })

edges_by_voltage = pd.DataFrame(pair_rows)
if not edges_by_voltage.empty:
    edges_by_voltage_agg = (
        edges_by_voltage
        .groupby(["province_u", "province_v", "voltage_class"], as_index=False)
        .agg(
            total_length_km=("pair_length_km", "sum"),
            sum_circuits=("circuits_n", "sum"),
            sum_capacity_proxy=("capacity_proxy", "sum"),
            sum_capacity_mw=("capacity_mw", "sum"),
            num_lines=("voltage_kV", "count")
        )
        .sort_values(["province_u", "province_v", "voltage_class"]) 
    )
    # 간단 출력용: 전압[kV] 스냅 기반 집계
    edges_simple = (
        edges_by_voltage
        .dropna(subset=["voltage_kV_snapped"]) 
        .groupby(["province_u", "province_v", "voltage_kV_snapped"], as_index=False)
        .agg(
            길이_km=("pair_length_km", "sum"),
            회선합=("circuits_n", "sum"),
            용량_proxy=("capacity_proxy", "sum"),
            용량_MW=("capacity_mw", "sum"),
            라인수=("voltage_kV", "count")
        )
        .rename(columns={
            "province_u": "시작지역",
            "province_v": "종료지역",
            "voltage_kV_snapped": "전압_kV"
        })
        .sort_values(["시작지역", "종료지역", "전압_kV"]) 
    )
else:
    edges_by_voltage_agg = pd.DataFrame(columns=[
        "province_u", "province_v", "voltage_class", "total_length_km", "sum_circuits", "sum_capacity_proxy", "sum_capacity_mw", "num_lines"
    ])
    edges_simple = pd.DataFrame(columns=["시작지역", "종료지역", "전압_kV", "용량_proxy", "용량_MW", "길이_km", "회선합", "라인수"])

# ------------------------------
# 6-c) 지자체 내부(노드) 전압별 집계
# ------------------------------
# 스냅 전압 부여
intersection["voltage_kV_snapped"] = intersection["voltage_kV"].apply(snap_voltage_kv)

# (1) 모든 세그먼트 포함: 각 지자체 내에 존재하는 라인 세그먼트 기준 집계
intra_by_voltage = (
    intersection.dropna(subset=["voltage_kV_snapped"]).groupby(["province_name", "voltage_kV_snapped"], as_index=False)
    .agg(
        total_length_km=("seg_length_km", "sum"),
        sum_circuits=("circuits_n", "sum"),
        sum_capacity_proxy=("capacity_proxy", "sum"),
        sum_capacity_mw=("capacity_mw", "sum"),
        num_lines=("line_id", "nunique")
    )
    .rename(columns={"province_name": "province", "voltage_kV_snapped": "v_nom_kv"})
    .sort_values(["province", "v_nom_kv"])
)

# (2) 완전 내부 라인만: 한 라인이 단 하나의 지자체에만 속한 경우에 한해 집계
_prov_count = (
    intersection.groupby("line_id")["province_name"].nunique().reset_index().rename(columns={"province_name": "prov_count"})
)
_single_line_ids = set(_prov_count.loc[_prov_count["prov_count"] == 1, "line_id"].tolist())
intersection_only_internal = intersection[intersection["line_id"].isin(_single_line_ids)].copy()

intra_by_voltage_only_internal = (
    intersection_only_internal.dropna(subset=["voltage_kV_snapped"]).groupby(["province_name", "voltage_kV_snapped"], as_index=False)
    .agg(
        total_length_km=("seg_length_km", "sum"),
        sum_circuits=("circuits_n", "sum"),
        sum_capacity_proxy=("capacity_proxy", "sum"),
        sum_capacity_mw=("capacity_mw", "sum"),
        num_lines=("line_id", "nunique")
    )
    .rename(columns={"province_name": "province", "voltage_kV_snapped": "v_nom_kv"})
    .sort_values(["province", "v_nom_kv"])
)

# 저장
intra_by_voltage.to_csv(os.path.join(OUT_DIR, "kr_province_intra_by_voltage.csv"), index=False, encoding="utf-8-sig")
intra_by_voltage_only_internal.to_csv(os.path.join(OUT_DIR, "kr_province_intra_only_fully_contained.csv"), index=False, encoding="utf-8-sig")

# ------------------------------
# 7) 산출물 저장
# ------------------------------
print("7) 결과 저장 중...")

# (a) 전체 라인 어트리뷰트 (요약)
lines_export = lines_5179[
    ["name", "operator", "voltage", "voltage_kV", "circuits", "circuits_n", "capacity_proxy", "capacity_mw", "length_km", "power"]
].copy()
lines_export.to_csv(os.path.join(OUT_DIR, "kr_power_lines_summary.csv"), index=False, encoding="utf-8-sig")

# (b) 시·도별 길이 집계
len_by_province.to_csv(os.path.join(OUT_DIR, "kr_length_by_province.csv"), index=False, encoding="utf-8-sig")

# (c) 시·도 간 연결 엣지
edges_agg.to_csv(os.path.join(OUT_DIR, "kr_province_connections.csv"), index=False, encoding="utf-8-sig")

# (c-2) 시·도 간 전압별 집계
edges_by_voltage_agg.to_csv(os.path.join(OUT_DIR, "kr_province_connections_by_voltage.csv"), index=False, encoding="utf-8-sig")

# (c-3) 간단 출력용(요구 포맷)
edges_simple.to_csv(os.path.join(OUT_DIR, "kr_province_connections_simple.csv"), index=False, encoding="utf-8-sig")

# (c-4) PyPSA_KOREA_GESI lines 시트 호환 포맷
pypsa_lines = (
    edges_simple.rename(columns={
        "시작지역": "bus0",
        "종료지역": "bus1",
        "전압_kV": "v_nom_kv",
        "길이_km": "length_km",
        "회선합": "circuits",
        "용량_proxy": "capacity_proxy",
        "용량_MW": "capacity_mw",
        "라인수": "num_lines"
    })
    .groupby(["bus0", "bus1", "v_nom_kv"], as_index=False)
    .agg(
        length_km=("length_km", "sum"),
        circuits=("circuits", "sum"),
        capacity_proxy=("capacity_proxy", "sum"),
        capacity_mw=("capacity_mw", "sum"),
        num_lines=("num_lines", "sum")
    )
    .sort_values(["bus0", "bus1", "v_nom_kv"])
)
pypsa_lines.to_csv(os.path.join(OUT_DIR, "pypsa_lines.csv"), index=False, encoding="utf-8-sig")
try:
    with pd.ExcelWriter(os.path.join(OUT_DIR, "pypsa_lines.xlsx"), engine="openpyxl") as writer:
        pypsa_lines.to_excel(writer, sheet_name="lines", index=False)
except Exception:
    pass

# (d) 지오패키지 저장 (GIS 확인용)
try:
    gpd.GeoDataFrame(lines_5179, geometry="geometry", crs=LEN_CRS).to_file(
        os.path.join(OUT_DIR, "kr_power_lines.gpkg"), layer="lines", driver="GPKG", engine="fiona"
    )
    gpd.GeoDataFrame(subs.to_crs(LEN_CRS), geometry="geometry", crs=LEN_CRS).to_file(
        os.path.join(OUT_DIR, "kr_power_substations.gpkg"), layer="substations", driver="GPKG", engine="fiona"
    )
    gpd.GeoDataFrame(admin_5179, geometry="geometry", crs=LEN_CRS).to_file(
        os.path.join(OUT_DIR, "kr_admin_lv4.gpkg"), layer="admin_lv4", driver="GPKG", engine="fiona"
    )
except Exception as e:
    print(f"[경고] GPKG 저장을 건너뜀: {e}")

print("\n완료!\n- ./output/kr_power_lines_summary.csv"
      "\n- ./output/kr_length_by_province.csv"
      "\n- ./output/kr_province_connections.csv"
      "\n- ./output/kr_province_connections_by_voltage.csv"
      "\n- ./output/kr_province_connections_simple.csv"
      "\n- ./output/kr_province_intra_by_voltage.csv (지자체 내부 전압별 집계)"
      "\n- ./output/kr_province_intra_only_fully_contained.csv (완전 내부 라인만 기준 지자체 내부 전압별 집계)"
      "\n- ./output/pypsa_lines.csv (PyPSA_KOREA_GESI 호환)"
      "\n- ./output/pypsa_lines.xlsx (PyPSA_KOREA_GESI 호환)"
      "\n- ./output/*.gpkg (QGIS/ArcGIS 확인용)\n")

print("※ 해석 팁:")
print(" - 'capacity_proxy'는 전압[kV] * 회선수로 만든 상대 지표입니다(공식 용량 아님).")
print(" - 'capacity_mw'는 전압등급별 표준 송전용량(MW)을 적용한 실제 송전용량입니다.")
print("   (154kV: 150MW/회선, 345kV: 800MW/회선, 765kV: 3500MW/회선)")
print(" - 시·도 간 'line_cross_count'는 경계를 횡단하는 라인 수(무방향 엣지)입니다.")
print(" - 보다 정확한 용량 계산을 위해서는 조류계산(load flow) 및 N-1 기준이 필요합니다.")
