# 데이터 구조 설명

이 문서는 KR Power Network Extractor가 생성하는 출력 파일의 구조를 상세히 설명합니다.

## 출력 디렉터리

모든 결과 파일은 `./output` 폴더에 저장됩니다.

```
output/
├── kr_power_lines_summary.csv
├── kr_length_by_province.csv
├── kr_province_connections.csv
├── kr_province_connections_by_voltage.csv
├── kr_province_connections_simple.csv
├── kr_province_intra_by_voltage.csv
├── kr_province_intra_only_fully_contained.csv
├── pypsa_lines.csv
├── pypsa_lines.xlsx
├── kr_power_lines.gpkg
├── kr_power_substations.gpkg
└── kr_admin_lv4.gpkg
```

## CSV 파일 상세

### 1. kr_power_lines_summary.csv

전체 송전선의 기본 정보를 담은 요약 파일입니다.

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `name` | string | 송전선 이름 (OSM 태그) |
| `operator` | string | 운영사 (예: 한국전력공사) |
| `voltage` | string | 원본 전압 태그 (예: "345000;154000") |
| `voltage_kV` | float | 파싱된 전압 (kV 단위) |
| `circuits` | string | 원본 회선수 태그 |
| `circuits_n` | int | 파싱된 회선수 |
| `capacity_proxy` | float | 용량 지표 (voltage_kV × circuits_n) |
| `length_km` | float | 송전선 길이 (km) |
| `power` | string | 송전선 유형 ("line" 또는 "cable") |

**예시**:
```csv
name,operator,voltage,voltage_kV,circuits,circuits_n,capacity_proxy,length_km,power
신가평-북수원,한국전력공사,345000,345.0,2,2,690.0,45.23,line
```

### 2. kr_length_by_province.csv

시·도별 송전선 통계입니다.

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `province_name` | string | 시·도 이름 (17개 광역지자체) |
| `total_length_km` | float | 해당 시·도 내 총 송전선 길이 (km) |
| `avg_voltage_kV` | float | 평균 전압 (kV) |
| `avg_circuits` | float | 평균 회선수 |
| `sum_capacity_proxy` | float | 용량 지표 합계 |

**예시**:
```csv
province_name,total_length_km,avg_voltage_kV,avg_circuits,sum_capacity_proxy
경기도,3245.67,187.5,1.8,548320.5
강원특별자치도,2134.89,165.2,1.6,356789.2
```

### 3. kr_province_connections.csv

시·도 간 송전선 연결 수 (단순 카운트)입니다.

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `province_u` | string | 시작 지역 (알파벳순 정렬) |
| `province_v` | string | 종료 지역 (알파벳순 정렬) |
| `line_cross_count` | int | 두 지역을 연결하는 송전선 수 |

**예시**:
```csv
province_u,province_v,line_cross_count
강원특별자치도,경기도,45
경기도,서울특별시,67
```

### 4. kr_province_connections_by_voltage.csv

시·도 간 연결을 전압 등급별로 집계한 상세 통계입니다.

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `province_u` | string | 시작 지역 |
| `province_v` | string | 종료 지역 |
| `voltage_class` | string | 전압 등급 (">=765kV", "345kV", "154kV", "66kV", "<60kV", "unknown") |
| `total_length_km` | float | 해당 등급의 총 길이 (km) |
| `sum_circuits` | int | 회선수 합계 |
| `sum_capacity_proxy` | float | 용량 지표 합계 |
| `sum_circuit_km` | float | **회선·킬로미터 (c.km)** |
| `num_lines` | int | 송전선 개수 |

**예시**:
```csv
province_u,province_v,voltage_class,total_length_km,sum_circuits,sum_capacity_proxy,sum_circuit_km,num_lines
강원특별자치도,경기도,154kV,69.23,22,3388.0,126.9,12
강원특별자치도,경기도,345kV,125.45,8,2760.0,251.8,4
```

### 5. kr_province_connections_simple.csv

시·도 간 연결을 전압(kV) 스냅 기준으로 요약한 파일입니다.

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `시작지역` | string | 시작 지역 (한글) |
| `종료지역` | string | 종료 지역 (한글) |
| `전압_kV` | int | 스냅된 전압 (765, 345, 220, 154, 110, 66, 33 중 하나) |
| `길이_km` | float | 총 길이 (km) |
| `회선합` | int | 회선수 합계 |
| `용량_proxy` | float | 용량 지표 합계 |
| `회선km` | float | **회선·킬로미터 (c.km)** |
| `라인수` | int | 송전선 개수 |

**예시**:
```csv
시작지역,종료지역,전압_kV,길이_km,회선합,용량_proxy,회선km,라인수
강원특별자치도,경기도,154,69.23,22,3388.0,126.9,12
강원특별자치도,경기도,345,125.45,8,2760.0,251.8,4
```

### 6. kr_province_intra_by_voltage.csv

시·도 내부의 전압별 송전선 통계입니다 (모든 세그먼트 포함).

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `province` | string | 시·도 이름 |
| `v_nom_kv` | int | 전압 (kV) |
| `total_length_km` | float | 총 길이 (km) |
| `sum_circuits` | int | 회선수 합계 |
| `sum_capacity_proxy` | float | 용량 지표 합계 |
| `num_lines` | int | 고유 송전선 개수 |

### 7. kr_province_intra_only_fully_contained.csv

시·도 내부의 전압별 송전선 통계입니다 (완전히 내부에만 있는 송전선만 포함).

구조는 `kr_province_intra_by_voltage.csv`와 동일하지만, 다른 시·도와 연결되지 않은 송전선만 집계합니다.

### 8. pypsa_lines.csv / pypsa_lines.xlsx

PyPSA 모델 입력용 포맷입니다.

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `bus0` | string | 시작 버스 (지역명) |
| `bus1` | string | 종료 버스 (지역명) |
| `v_nom_kv` | int | 정격 전압 (kV) |
| `length_km` | float | 송전선 길이 (km) |
| `circuits` | int | 회선수 |
| `circuit_km` | float | **회선·킬로미터 (c.km)** |
| `capacity_proxy` | float | 용량 지표 |
| `num_lines` | int | 집계된 송전선 개수 |

**예시**:
```csv
bus0,bus1,v_nom_kv,length_km,circuits,circuit_km,capacity_proxy,num_lines
강원특별자치도,경기도,154,69.23,22,126.9,3388.0,12
강원특별자치도,경기도,345,125.45,8,251.8,2760.0,4
```

## GIS 파일 (GPKG)

### kr_power_lines.gpkg

송전선 공간 데이터 (LineString)

**주요 속성**:
- `voltage_kV`: 전압 (kV)
- `circuits_n`: 회선수
- `capacity_proxy`: 용량 지표
- `length_km`: 길이 (km)
- `name`, `operator`: 송전선 정보

### kr_power_substations.gpkg

변전소 공간 데이터 (Point 또는 Polygon)

**주요 속성**:
- `name`: 변전소 이름
- `voltage`: 전압
- `operator`: 운영사

### kr_admin_lv4.gpkg

시·도 경계 (Polygon)

**주요 속성**:
- `province_name`: 표준화된 시·도 이름 (17개 광역지자체)

## 주요 개념 설명

### 회선·킬로미터 (circuit-km, c.km)

송전선의 실제 전송 능력을 나타내는 지표입니다.

**계산 방법**:
```
c.km = Σ (각 송전선의 길이 × 회선수)
```

**예시**:
- 송전선 A: 50km, 2회선 → 100 c.km
- 송전선 B: 30km, 1회선 → 30 c.km
- 합계: 130 c.km

**의미**: 
- 단순 길이보다 실제 전송 용량을 더 잘 반영
- 전력망 투자 규모 평가에 활용
- 국제적으로 통용되는 지표

### 용량 지표 (capacity_proxy)

실제 송전용량(MW)의 근사치입니다.

**계산 방법**:
```
capacity_proxy = 전압(kV) × 회선수
```

**한계**:
- OSM에는 실제 용량 정보가 없음
- 도체 굵기, 선로 구성 등을 고려하지 않음
- 상대 비교용으로만 사용 권장

**실제 용량 환산 (참고)**:
- 765kV 2회선: 약 6,000~8,000 MW
- 345kV 2회선: 약 1,500~2,000 MW
- 154kV 2회선: 약 300~400 MW

### 전압 등급 분류

한국 전력망의 대표적인 전압 등급:

| 등급 | 전압 범위 | 용도 |
|------|----------|------|
| `>=765kV` | 700kV 이상 | 초고압 장거리 송전 |
| `345kV` | 300~699kV | 고압 간선 송전 |
| `154kV` | 150~299kV | 1차 변전 및 배전 |
| `66kV` | 60~149kV | 2차 배전 |
| `<60kV` | 60kV 미만 | 저압 배전 |
| `unknown` | 정보 없음 | OSM 태그 누락 |

## 데이터 활용 예시

### Python으로 분석

```python
import pandas as pd
import matplotlib.pyplot as plt

# 시·도별 송전선 길이 시각화
df = pd.read_csv('output/kr_length_by_province.csv')
df.plot(x='province_name', y='total_length_km', kind='bar', figsize=(12, 6))
plt.title('시·도별 송전선 총 길이')
plt.xlabel('시·도')
plt.ylabel('길이 (km)')
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# 회선km 상위 10개 연결
connections = pd.read_csv('output/kr_province_connections_simple.csv')
top10 = connections.nlargest(10, '회선km')
print(top10[['시작지역', '종료지역', '전압_kV', '회선km']])
```

### SQL 쿼리 (DuckDB)

```sql
-- 345kV 이상 초고압 송전선 통계
SELECT 
    시작지역, 
    종료지역, 
    전압_kV,
    SUM(회선km) as total_circuit_km
FROM 'output/kr_province_connections_simple.csv'
WHERE 전압_kV >= 345
GROUP BY 시작지역, 종료지역, 전압_kV
ORDER BY total_circuit_km DESC;
```

## 다음 단계

- [알고리즘 상세 설명](algorithm.md)
- [FAQ](faq.md)

