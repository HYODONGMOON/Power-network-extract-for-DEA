# Korea Power Grid Map — DEA Analysis

OpenStreetMap(OSM) 기반 한국 전력망 데이터 추출 및 **지도 시각화** 도구  
DEA(Data Envelopment Analysis) 연구의 기초 인프라 데이터 구축을 목적으로 개발

---

## 📌 주요 기능

| 기능 | 파일 |
|------|------|
| 전력망 지도 시각화 (현황 + 계획) | `kr_grid_map.py` ⭐ |
| 원시 데이터 추출 및 지역별 집계 | `power network extract.py` |

---

## 🗺️ 지도 시각화 (`kr_grid_map.py`)

[openinframap.org](https://openinframap.org/#6.7/35.64/127.158) 스타일로 한국 전력망을 시각화합니다.

### 표시 레이어

| 레이어 | 색상 | 설명 |
|--------|------|------|
| 765 kV | 🔴 빨강 | 초고압 송전선 |
| 345 kV | 🟠 주황 | 고압 송전선 |
| 154 kV | 🔵 하늘 | 표준 송전선 |
| HVDC   | 🟣 보라 (점선) | 직류 송전선 |
| 변전소 | 전압별 기호 | 154kV 이상 변전소 |

### 출력 파일

```
output/
├── kr_grid_map_current.png        ← 정적 지도 (현황)
├── kr_grid_map_interactive.html   ← 인터랙티브 지도 (레이어 on/off 가능)
├── kr_grid_data.xlsx              ← 전압별 라인/변전소 데이터
└── kr_grid_lines.gpkg             ← GIS 파일 (QGIS/ArcGIS용)
```

### 실행 방법

```bash
# 기본 실행 (전체 한국, 모든 레이어)
python kr_grid_map.py

# 빠른 테스트 (변전소 생략)
python kr_grid_map.py --quick

# HTML 지도 생략
python kr_grid_map.py --no-html

# 특정 지역만 (bbox: minLon,minLat,maxLon,maxLat)
python kr_grid_map.py --bbox 126.0,34.0,130.0,38.5

# 계획망 오버레이 (2030/2038 계획선로 표시)
python kr_grid_map.py --overlay planned_grid.xlsx
```

---

## 📊 계획망 오버레이 기능

현황 지도 위에 정부 계획(제11차 장기 송변전설비계획 등)을 덧씌울 수 있습니다.

### 사용 방법

1. `kr_grid_data.xlsx`의 `planned_lines_template` 시트를 복사
2. 아래 컬럼에 계획 데이터 입력:

| 컬럼 | 설명 |
|------|------|
| `name` | 선로명 |
| `from_substation` | 시작 변전소 |
| `to_substation` | 종료 변전소 |
| `voltage_kV` | 전압 등급 |
| `from_lon`, `from_lat` | 시작점 좌표 |
| `to_lon`, `to_lat` | 종료점 좌표 |
| `year_planned` | 계획 연도 (2030 / 2038) |
| `status` | `planned` / `under_construction` / `completed` |

3. 파일 저장 후 실행:

```bash
python kr_grid_map.py --overlay planned_grid.xlsx
```

→ `kr_grid_map_2030.png`, `kr_grid_map_2038.png` 자동 생성

---

## 🔬 연구 배경

### 2. Existing Transmission Backbone
- **현황 지도**: 765kV, 345kV, 154kV, HVDC, 주요 변전소 시각화
- 출처: OpenStreetMap → `kr_grid_map.py`

### 4. Grid Expansion Overview
- **계획망 지도**: 에너지 하이웨이, 제11차 장기 송변전설비계획, HVDC 사업 등
- 현황 지도 위에 계획 선로/변전소 오버레이 → `--overlay` 옵션 활용

### 3. Evidence of Bottlenecks (추후 추가)
- 지역별 재생에너지 설비 집중도
- 지역 간 송전용량 (c.km)
- 주요 해상풍력 예정지와 계통 접속점

---

## 🛠️ 설치

```bash
pip install -r requirements.txt
pip install folium          # 인터랙티브 HTML 지도용 (선택)
```

### 주요 의존성

```
geopandas>=0.12
osmnx>=1.3
matplotlib>=3.5
shapely>=2.0
folium>=0.14       # HTML 지도 (선택)
openpyxl>=3.0
```

---

## 📁 프로젝트 구조

```
Power-network-extract-for-DEA/
├── kr_grid_map.py              # 메인: 전력망 지도 시각화
├── power network extract.py    # 원본: 지역별 집계/분석
├── README.md
├── requirements.txt
├── output/                     # 결과 파일 (자동 생성)
│   ├── kr_grid_map_current.png
│   ├── kr_grid_map_interactive.html
│   ├── kr_grid_data.xlsx
│   └── kr_grid_lines.gpkg
└── docs/
    ├── algorithm.md
    ├── data_structure.md
    └── ...
```

---

## 📄 라이선스

MIT License — 연구/교육 목적 자유 사용  
OSM 데이터: [ODbL License](https://www.openstreetmap.org/copyright)

---

## 🔗 관련 링크

- [OpenInfraMap](https://openinframap.org/#6.7/35.64/127.158) — 데이터 소스 시각화 참조
- [PyPSA_GESI_Test](https://github.com/HYODONGMOON/PyPSA_GESI_Test) — 전력 시스템 최적화 모델
- [Power-network-extract](https://github.com/HYODONGMOON/Power-network-extract) — 원본 추출 코드
