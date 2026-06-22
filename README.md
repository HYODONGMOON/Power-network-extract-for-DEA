# 🔌 대한민국 전력망 추출기 (KR Power Network Extractor)

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

OpenStreetMap(OSM) 데이터를 기반으로 **대한민국 송전망 네트워크**를 자동으로 추출하고 분석하는 Python 도구입니다.

## ✨ 주요 기능

- 📍 **OSM 기반 송전선 자동 추출**: 전국 송전선(line/cable)과 변전소 데이터 수집
- 🗺️ **시·도별 통계 집계**: 17개 광역지자체 단위로 송전선 길이 및 용량 통계 산출
- 🔗 **지역 간 연결 분석**: 시·도 간 송전선 연결 관계 및 전압 등급별 통계
- ⚡ **회선·킬로미터(c.km) 계산**: 실무에서 사용하는 정확한 회선km 지표 산출
- 📊 **PyPSA 호환 포맷**: 전력망 시뮬레이션 도구(PyPSA) 입력 데이터 자동 생성
- 🚀 **대용량 처리 최적화**: 타일 분할 다운로드로 전국 데이터 빠르게 처리

## 🎯 사용 사례

- 전력망 연구 및 분석
- 에너지 시스템 모델링 (PyPSA, GESI 등)
- 송전 인프라 현황 파악
- 지역별 전력망 통계 산출

## 📦 설치 방법

### 1. 저장소 클론
```bash
git clone https://github.com/HYODONGMOON/kr-power-network-extract.git
cd kr-power-network-extract
```

### 2. 필수 패키지 설치
```bash
pip install -r requirements.txt
```

**권장 환경**: Anaconda/Miniconda (GeoPandas 의존성 관리가 용이)

```bash
conda create -n power-network python=3.9
conda activate power-network
conda install -c conda-forge geopandas osmnx
pip install -r requirements.txt
```

## 🚀 빠른 시작

### 기본 사용법 (대한민국 전체)
```bash
python "power network extract.py"
```

실행 후 `./output` 폴더에 결과 파일이 생성됩니다.

### 주요 옵션

```bash
# 특정 지역만 추출 (예: 서울)
python "power network extract.py" --area "Seoul"

# 경계박스로 영역 지정 (WGS84 좌표)
python "power network extract.py" --bbox "124.5,33.0,132.0,39.5"

# 대용량 처리 최적화 (3x3 타일 분할)
python "power network extract.py" --tiles 3

# 빠른 모드 (변전소 제외)
python "power network extract.py" --quick

# Overpass API 타임아웃 조정 (초)
python "power network extract.py" --timeout 600
```

## 📊 출력 데이터

실행 후 `./output` 폴더에 다음 파일들이 생성됩니다:

### CSV 파일
| 파일명 | 설명 |
|--------|------|
| `kr_power_lines_summary.csv` | 전체 송전선 요약 (전압, 회선수, 길이 등) |
| `kr_length_by_province.csv` | 시·도별 송전선 총 길이 및 통계 |
| `kr_province_connections.csv` | 시·도 간 연결 수 |
| `kr_province_connections_by_voltage.csv` | 시·도 간 전압별 상세 통계 (**c.km 포함**) |
| `kr_province_connections_simple.csv` | 시·도 간 요약 통계 (**회선km 포함**) |
| `kr_province_intra_by_voltage.csv` | 시·도 내부 전압별 통계 |
| `pypsa_lines.csv` / `.xlsx` | PyPSA 호환 포맷 (**circuit_km 포함**) |

### GIS 파일 (QGIS/ArcGIS 확인용)
- `kr_power_lines.gpkg`: 송전선 레이어
- `kr_power_substations.gpkg`: 변전소 레이어
- `kr_admin_lv4.gpkg`: 시·도 경계 레이어

## 📖 상세 문서

- [**설치 가이드**](docs/installation.md) - 상세 설치 방법 및 문제 해결
- [**사용 가이드**](docs/usage.md) - 다양한 사용 예제
- [**데이터 구조**](docs/data_structure.md) - 출력 데이터 상세 설명
- [**알고리즘 설명**](docs/algorithm.md) - 처리 과정 및 계산 방법
- [**FAQ**](docs/faq.md) - 자주 묻는 질문

## 🔍 주요 개념

### 회선·킬로미터 (circuit-km, c.km)

송전선의 실제 용량을 나타내는 지표로, 다음과 같이 계산됩니다:

```
c.km = Σ (각 송전선의 길이 × 회선수)
```

**예시**: 강원특별자치도 ↔ 경기도 간 154kV 송전선
- 총 길이: 69.23 km
- 라인 수: 12개
- 회선 합: 22
- **회선km**: 126.9 c.km (정확한 값은 라인별 계산 후 합산)

### 용량 지표 (capacity_proxy)

OSM 데이터에는 실제 송전용량(MW)이 없어, 다음 근사식을 사용합니다:

```
capacity_proxy = 전압(kV) × 회선수
```

⚠️ **주의**: 이는 상대 비교용 지표이며, 실제 전송용량(MW/MVA)과는 다릅니다.

## 🛠️ 기술 스택

- **Python 3.9+**
- **GeoPandas**: 공간 데이터 처리
- **OSMnx**: OpenStreetMap 데이터 추출
- **Shapely**: 기하학 연산
- **Pandas**: 데이터 집계 및 분석

## ⚠️ 제한사항

- **OSM 데이터 한계**: 커버리지와 정확성이 100%가 아닐 수 있습니다
- **용량 근사치**: 실제 송전용량이 아닌 proxy 지표만 제공됩니다
- **처리 시간**: 전국 데이터 처리 시 10~30분 소요 (네트워크 속도에 따라 변동)

## 🤝 기여하기

버그 리포트, 기능 제안, Pull Request를 환영합니다!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이선스

MIT License - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 📧 문의

프로젝트 관련 문의사항은 [Issues](https://github.com/HYODONGMOON/kr-power-network-extract/issues)에 등록해 주세요.

## 🙏 감사의 말

- [OpenStreetMap](https://www.openstreetmap.org/) 커뮤니티
- [OSMnx](https://github.com/gboeing/osmnx) 프로젝트
- [PyPSA](https://pypsa.org/) 프로젝트 