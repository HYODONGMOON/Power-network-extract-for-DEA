# 사용 가이드

이 문서는 KR Power Network Extractor의 다양한 사용 예제를 제공합니다.

## 기본 사용법

### 대한민국 전체 송전망 추출

```bash
python "power network extract.py"
```

실행 시간: 약 10~30분 (네트워크 속도에 따라 변동)

### 특정 지역만 추출

```bash
# 서울특별시
python "power network extract.py" --area "Seoul"

# 경기도
python "power network extract.py" --area "Gyeonggi-do"

# 부산광역시
python "power network extract.py" --area "Busan"
```

### 경계박스로 영역 지정

WGS84 좌표계(경도, 위도)로 직접 영역을 지정할 수 있습니다:

```bash
# 수도권 지역 (서울+경기 일부)
python "power network extract.py" --bbox "126.5,37.2,127.5,37.8"

# 제주도
python "power network extract.py" --bbox "126.1,33.1,126.9,33.6"
```

형식: `--bbox "최소경도,최소위도,최대경도,최대위도"`

## 고급 옵션

### 대용량 처리 최적화

전국 데이터 처리 시 타일 분할을 사용하면 속도가 향상됩니다:

```bash
# 2x2 타일 분할 (4개 영역으로 나눠서 처리)
python "power network extract.py" --tiles 2

# 3x3 타일 분할 (9개 영역으로 나눠서 처리)
python "power network extract.py" --tiles 3
```

권장: 전국 데이터는 `--tiles 3`, 광역시는 `--tiles 1`

### Overpass API 설정

```bash
# 타임아웃 시간 조정 (기본: 300초)
python "power network extract.py" --timeout 600

# 다른 Overpass 서버 사용
python "power network extract.py" --overpass-endpoint "https://overpass.kumi.systems/api/interpreter"
```

### 빠른 모드

변전소 데이터가 필요 없을 때 사용하면 처리 시간이 단축됩니다:

```bash
python "power network extract.py" --quick
```

## 실전 예제

### 예제 1: 수도권 송전망 분석

```bash
# 1. 수도권 데이터 추출
python "power network extract.py" --bbox "126.5,37.0,127.5,38.0" --tiles 2

# 2. 결과 확인
cd output
ls -lh
```

생성된 파일:
- `kr_province_connections_simple.csv`: 서울↔경기 연결 통계
- `pypsa_lines.xlsx`: PyPSA 입력 데이터

### 예제 2: 특정 전압 등급 분석

Python으로 결과 파일을 후처리:

```python
import pandas as pd

# 시·도 간 연결 데이터 로드
df = pd.read_csv('output/kr_province_connections_simple.csv')

# 345kV 이상 초고압 송전선만 필터링
high_voltage = df[df['전압_kV'] >= 345]
print(high_voltage)

# 회선km 기준 상위 10개 연결
top10 = df.nlargest(10, '회선km')
print(top10[['시작지역', '종료지역', '전압_kV', '회선km']])
```

### 예제 3: PyPSA 모델 입력 데이터 생성

```bash
# 1. 전국 데이터 추출
python "power network extract.py" --tiles 3

# 2. PyPSA 입력 파일 확인
ls output/pypsa_lines.*
```

`pypsa_lines.xlsx`를 PyPSA 모델의 `lines` 시트로 직접 사용 가능합니다.

### 예제 4: QGIS에서 시각화

```bash
# 1. 데이터 추출
python "power network extract.py"

# 2. QGIS 실행 후 다음 파일 로드:
#    - output/kr_power_lines.gpkg (송전선)
#    - output/kr_power_substations.gpkg (변전소)
#    - output/kr_admin_lv4.gpkg (시·도 경계)
```

QGIS에서 전압별로 색상을 다르게 표시하면 송전망 구조를 한눈에 파악할 수 있습니다.

## 출력 데이터 활용

### CSV 파일 읽기 (Python)

```python
import pandas as pd

# 시·도별 통계
province_stats = pd.read_csv('output/kr_length_by_province.csv')
print(province_stats.head())

# 시·도 간 연결 (전압별)
connections = pd.read_csv('output/kr_province_connections_by_voltage.csv')

# 회선km 기준 정렬
connections_sorted = connections.sort_values('sum_circuit_km', ascending=False)
print(connections_sorted.head(10))
```

### Excel에서 열기

`pypsa_lines.xlsx` 파일을 Excel에서 바로 열어 확인할 수 있습니다:

- `bus0`, `bus1`: 연결된 두 지역
- `v_nom_kv`: 전압 등급 (kV)
- `length_km`: 총 길이 (km)
- `circuits`: 회선 수 합계
- `circuit_km`: 회선·킬로미터 (c.km)
- `capacity_proxy`: 용량 지표 (kV × 회선수)

### GIS 소프트웨어에서 활용

**QGIS**:
1. 레이어 → 레이어 추가 → 벡터 레이어 추가
2. `output/*.gpkg` 파일 선택
3. 속성 테이블에서 전압, 회선수 등 확인

**ArcGIS**:
1. Add Data → `output/*.gpkg`
2. Symbology에서 전압별 색상 구분

## 성능 최적화 팁

### 처리 시간 단축

1. **타일 분할 사용**: `--tiles 3` (전국 데이터)
2. **빠른 모드**: `--quick` (변전소 제외)
3. **영역 축소**: `--bbox` 또는 `--area`로 필요한 지역만 추출

### 메모리 사용량 줄이기

1. 특정 지역만 추출
2. 불필요한 프로그램 종료
3. 64비트 Python 사용

### 네트워크 오류 대응

Overpass API가 불안정할 때:

```bash
# 1. 타임아웃 증가
python "power network extract.py" --timeout 900

# 2. 다른 서버 사용
python "power network extract.py" --overpass-endpoint "https://overpass.kumi.systems/api/interpreter"

# 3. 재시도 (OSMnx 캐시 활용)
python "power network extract.py"  # 이전 다운로드 재사용
```

## 자주 사용하는 명령어 모음

```bash
# 전국 데이터 (최적화)
python "power network extract.py" --tiles 3 --timeout 600

# 수도권만 빠르게
python "power network extract.py" --bbox "126.5,37.0,127.5,38.0" --quick

# 특정 도시 상세 분석
python "power network extract.py" --area "Seoul"

# 네트워크 불안정 시
python "power network extract.py" --tiles 4 --timeout 900
```

## 다음 단계

- [데이터 구조 이해하기](data_structure.md)
- [알고리즘 상세 설명](algorithm.md)
- [FAQ](faq.md)

