# 알고리즘 설명

이 문서는 KR Power Network Extractor의 내부 처리 과정과 알고리즘을 상세히 설명합니다.

## 전체 처리 흐름

```
1. 영역 정의
   ↓
2. OSM 데이터 다운로드
   ↓
3. 시·도 경계 다운로드 및 정규화
   ↓
4. 좌표계 변환 (WGS84 → EPSG:5179)
   ↓
5. 전압/회선수 파싱
   ↓
6. 시·도별 길이 집계 (Overlay Intersection)
   ↓
7. 시·도 간 연결 분석
   ↓
8. 결과 저장
```

## 1. 영역 정의

### 방법 A: 지오코딩 (--area)

```python
# OSMnx를 사용한 지오코딩
country_gdf = ox.geocode_to_gdf("South Korea")
country_poly = country_gdf.to_crs("EPSG:4326").iloc[0].geometry
```

### 방법 B: 경계박스 (--bbox)

```python
# WGS84 좌표로 직접 지정
minx, miny, maxx, maxy = 124.5, 33.0, 132.0, 39.5
country_poly = shapely_box(minx, miny, maxx, maxy)
```

## 2. OSM 데이터 다운로드

### Overpass API 쿼리

```python
tags_power = {
    "power": ["line", "cable", "substation", "switching_station"]
}
power_gdf = ox.features_from_polygon(country_poly, tags_power)
```

### 타일 분할 최적화

대용량 영역 처리 시 NxN 타일로 분할하여 순차 다운로드:

```python
def features_from_polygon_tiled(polygon, tags, tiles=3):
    minx, miny, maxx, maxy = polygon.bounds
    dx = (maxx - minx) / tiles
    dy = (maxy - miny) / tiles
    
    frames = []
    for i in range(tiles):
        for j in range(tiles):
            tile_poly = shapely_box(
                minx + i*dx, miny + j*dy,
                minx + (i+1)*dx, miny + (j+1)*dy
            )
            clip_poly = polygon.intersection(tile_poly)
            gdf = ox.features_from_polygon(clip_poly, tags)
            frames.append(gdf)
    
    return pd.concat(frames).drop_duplicates()
```

**장점**:
- 요청 크기 감소 → 타임아웃 방지
- 병렬 처리 가능 (향후 구현 예정)
- 메모리 사용량 분산

## 3. 시·도 경계 처리

### 3-1. admin_level=4 다운로드

```python
tags_admin = {
    "boundary": "administrative",
    "admin_level": "4"
}
admin_gdf = ox.features_from_polygon(country_poly, tags_admin)
```

### 3-2. 이름 정규화

17개 광역지자체로 표준화:

```python
ALIASES = {
    "서울": "서울특별시",
    "강원": "강원특별자치도",
    "강원도": "강원특별자치도",
    # ... 등
}

admin_gdf["province_name"] = admin_gdf["name:ko"].apply(normalize_province)
```

### 3-3. Dissolve (병합)

동일 이름의 다중 피처를 하나로 통합:

```python
admin_gdf = admin_gdf.dissolve(by="province_name", as_index=False)
```

**결과**: 정확히 17개의 폴리곤

## 4. 좌표계 변환

### WGS84 → EPSG:5179

길이 계산의 정확도를 위해 미터 단위 투영 좌표계로 변환:

```python
lines_5179 = lines.to_crs("EPSG:5179")
admin_5179 = admin_gdf.to_crs("EPSG:5179")
```

**EPSG:5179 특징**:
- 한국 측지계 2000 (Korea 2000)
- 단위: 미터 (m)
- 한반도 영역에서 왜곡 최소화

## 5. 전압/회선수 파싱

### 전압 파싱

OSM의 `voltage` 태그는 다양한 형식으로 저장됨:

```python
def parse_voltage_to_kv(v: str) -> float:
    # 예시: "765000;345000" → 765.0 (첫 번째 값만 사용)
    # 예시: "345000" → 345.0
    # 예시: "345 kV" → 345.0
    
    first = v.split(";")[0].strip()
    digits = re.findall(r"\d+", first)
    val_v = float("".join(digits))  # 볼트 단위
    return val_v / 1000.0  # kV로 변환
```

### 회선수 파싱

```python
def parse_int(val: str) -> int:
    # 예시: "2" → 2
    # 예시: "double" → None (미인식)
    # 미기재 시 1로 가정
    
    digits = re.findall(r"\d+", val)
    return int(digits[0]) if digits else 1
```

### 전압 스냅

보고용으로 표준 전압 등급으로 반올림:

```python
def snap_voltage_kv(voltage_kv: float) -> int:
    candidates = [765, 500, 345, 220, 154, 110, 66, 33]
    diffs = [abs(voltage_kv - c) for c in candidates]
    return candidates[np.argmin(diffs)]

# 예시:
# 350 kV → 345 kV
# 160 kV → 154 kV
```

## 6. 시·도별 길이 집계

### Overlay Intersection

송전선과 시·도 경계의 정확한 교차 계산:

```python
intersection = gpd.overlay(lines_5179, admin_5179, how="intersection")
```

**작동 원리**:
1. 각 송전선을 시·도 경계로 자름
2. 경계를 넘는 송전선은 여러 세그먼트로 분할
3. 각 세그먼트는 하나의 시·도에만 속함

**예시**:
```
송전선 A: 서울 → 경기 (총 100km)
  ├─ 서울 구간: 30km
  └─ 경기 구간: 70km
```

### 길이 재계산

분할된 세그먼트의 길이를 재계산:

```python
intersection["seg_length_km"] = intersection.geometry.length / 1000.0
```

### 시·도별 합산

```python
len_by_province = (
    intersection.groupby("province_name")
    .agg(total_length_km=("seg_length_km", "sum"))
)
```

## 7. 시·도 간 연결 분석

### 7-1. 라인별 포함 시·도 파악

```python
line_provinces = (
    intersection.groupby("line_id")["province_name"]
    .apply(lambda s: sorted(set(s)))
)
```

**예시**:
```
line_id  province_name
1        [경기도, 서울특별시]
2        [강원특별자치도, 경기도, 서울특별시]
3        [경기도]  # 내부 라인
```

### 7-2. 엣지 생성

두 개 이상의 시·도를 포함하는 라인에서 모든 조합 생성:

```python
for line_id, provs in line_provinces.items():
    if len(provs) >= 2:
        for a, b in combinations(provs, 2):
            edges.append((a, b))
```

**예시**:
```
line_id=2, provs=[강원, 경기, 서울]
→ 엣지: (강원, 경기), (강원, 서울), (경기, 서울)
```

### 7-3. 전압별 집계

각 라인에 대해 시·도 쌍별 길이 proxy 계산:

```python
for line_id, df_line in seg_info.groupby("line_id"):
    kv = df_line["voltage_kV"].iloc[0]
    circuits = df_line["circuits_n"].iloc[0]
    
    per_prov = df_line.groupby("province_name")["seg_length_km"].sum()
    
    for a, b in combinations(per_prov.index, 2):
        len_a = per_prov[a]
        len_b = per_prov[b]
        pair_len_proxy = min(len_a, len_b)  # 보수적 추정
        
        pair_rows.append({
            "province_u": a,
            "province_v": b,
            "voltage_kV": kv,
            "circuits_n": circuits,
            "pair_length_km": pair_len_proxy,
            "circuit_km": pair_len_proxy * circuits  # c.km
        })
```

**길이 proxy 계산 이유**:
- 송전선이 두 지역을 연결하는 실제 길이는 min(len_a, len_b)에 가까움
- 예: 서울 10km + 경기 50km → 연결 길이 ≈ 10km

### 7-4. 회선·킬로미터 계산

라인별로 계산 후 합산:

```python
# 라인 단위
circuit_km = pair_length_km × circuits_n

# 그룹 합계
sum_circuit_km = Σ circuit_km
```

**정확한 계산**:
```
송전선 A: 50km, 2회선 → 100 c.km
송전선 B: 30km, 3회선 → 90 c.km
합계: 190 c.km
```

**근사 계산 (집계 데이터만 있을 때)**:
```
total_length_km = 80km
sum_circuits = 5
평균 길이 = 80 / 2 = 40km
근사 c.km = 40 × 5 = 200 c.km  # 실제와 차이 발생
```

## 8. 지자체 내부 집계

### 방법 A: 모든 세그먼트 포함

해당 지자체 내에 존재하는 모든 송전선 세그먼트 집계:

```python
intra_by_voltage = (
    intersection.groupby(["province_name", "voltage_kV_snapped"])
    .agg(total_length_km=("seg_length_km", "sum"))
)
```

### 방법 B: 완전 내부 라인만

다른 지자체와 연결되지 않은 송전선만 집계:

```python
prov_count = intersection.groupby("line_id")["province_name"].nunique()
single_line_ids = prov_count[prov_count == 1].index

intersection_only_internal = intersection[
    intersection["line_id"].isin(single_line_ids)
]
```

**차이점**:
- 방법 A: 경계 넘는 송전선의 일부 구간도 포함
- 방법 B: 완전히 내부에만 있는 송전선만 포함

## 성능 최적화

### 1. 타일 분할

```python
# 3x3 타일 = 9개 영역으로 분할
# 각 타일의 데이터 크기 = 전체 / 9
# 타임아웃 위험 감소
```

### 2. 캐싱

OSMnx는 다운로드한 데이터를 자동 캐싱:

```python
ox.settings.use_cache = True
ox.settings.cache_folder = "./osm_cache"
```

재실행 시 캐시 재사용 → 속도 향상

### 3. 메모리 관리

```python
# 불필요한 컬럼 제거
power_gdf = power_gdf[keep_cols + ["geometry"]]

# 중복 제거
power_gdf = power_gdf.drop_duplicates()

# 타입 최적화
lines_5179["circuits_n"] = lines_5179["circuits_n"].astype("int16")
```

## 정확도 및 한계

### 길이 계산 정확도

- **좌표계**: EPSG:5179 사용으로 한반도 영역에서 ±0.1% 이내 오차
- **경계 처리**: Overlay intersection으로 정확한 분절 길이 산출
- **곡선 처리**: LineString의 모든 꼭짓점 고려

### OSM 데이터 한계

1. **커버리지**: 일부 지역/등급의 송전선 누락 가능
2. **태그 불완전**: voltage, circuits 태그 미기재 빈번
3. **업데이트 지연**: 최신 송전선 반영 지연

### 용량 지표 한계

```python
capacity_proxy = voltage_kV × circuits
```

**고려하지 않는 요소**:
- 도체 굵기 (ACSR, ACCC 등)
- 선로 구성 (단도체, 복도체 등)
- 열용량 (Thermal rating)
- 안정도 한계 (Stability limit)

**실제 용량 환산 예시**:
```python
# 문헌 기반 환산 (참고용)
capacity_mw = {
    (765, 2): 7000,  # 765kV 2회선
    (345, 2): 1800,  # 345kV 2회선
    (154, 2): 350,   # 154kV 2회선
}
```

## 알고리즘 복잡도

- **다운로드**: O(N) - N: 영역 크기
- **좌표 변환**: O(M) - M: 피처 개수
- **Overlay**: O(M × P) - P: 폴리곤 개수 (17개)
- **집계**: O(M log M)

**전체**: O(M × P + M log M) ≈ O(M × P)

전국 데이터 기준:
- M ≈ 10,000~50,000 (송전선 개수)
- P = 17 (시·도 개수)
- 처리 시간: 10~30분 (네트워크 속도 포함)

## 다음 단계

- [FAQ](faq.md)
- [데이터 구조](data_structure.md)

