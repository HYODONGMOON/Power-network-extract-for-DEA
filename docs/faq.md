# 자주 묻는 질문 (FAQ)

## 일반 질문

### Q1. 이 도구는 무엇을 하나요?

OpenStreetMap 데이터를 기반으로 대한민국의 송전망 네트워크를 자동으로 추출하고 분석합니다. 시·도별 통계, 지역 간 연결 관계, 전압 등급별 집계 등을 제공합니다.

### Q2. 누가 사용하나요?

- 전력망 연구자
- 에너지 시스템 모델러 (PyPSA, GESI 등)
- 인프라 분석가
- 정책 입안자

### Q3. 상업적으로 사용할 수 있나요?

네, MIT 라이선스로 배포되어 상업적 사용이 가능합니다. 단, OpenStreetMap 데이터는 ODbL 라이선스를 따르므로 출처 표기가 필요합니다.

## 설치 및 실행

### Q4. 설치가 안 돼요 (GDAL 오류)

**Windows**: Anaconda 사용을 권장합니다.
```bash
conda create -n power-network python=3.9
conda activate power-network
conda install -c conda-forge geopandas osmnx
```

**macOS/Linux**: 시스템 라이브러리를 먼저 설치하세요.
```bash
# macOS
brew install gdal geos proj

# Ubuntu
sudo apt-get install gdal-bin libgdal-dev libgeos-dev libproj-dev
```

자세한 내용은 [설치 가이드](installation.md)를 참조하세요.

### Q5. 실행 시 타임아웃 오류가 발생해요

Overpass API 서버가 과부하 상태일 수 있습니다.

**해결 방법**:
1. 타임아웃 시간 증가: `--timeout 600`
2. 타일 분할 사용: `--tiles 3`
3. 다른 서버 사용: `--overpass-endpoint "https://overpass.kumi.systems/api/interpreter"`
4. 시간대 변경 (한국 시간 기준 새벽 2~6시 권장)

### Q6. 처리 시간이 너무 오래 걸려요

전국 데이터는 10~30분 정도 소요됩니다.

**속도 향상 방법**:
- 타일 분할: `--tiles 3` (권장)
- 특정 지역만: `--area "Seoul"`
- 빠른 모드: `--quick` (변전소 제외)
- 캐시 활용: 재실행 시 자동으로 캐시 사용

## 데이터 관련

### Q7. 데이터가 정확한가요?

OpenStreetMap 데이터를 기반으로 하므로 **참고용**으로 사용하세요.

**한계**:
- 일부 송전선 누락 가능
- 전압/회선수 태그 불완전
- 최신 송전선 반영 지연

**정확도 향상 팁**:
- 한국전력공사 공개 데이터와 교차 검증
- 지역별로 QGIS에서 시각적 확인
- 의심스러운 데이터는 OSM에 직접 기여

### Q8. 실제 송전용량(MW)을 알 수 있나요?

이 도구는 `capacity_proxy` (전압 × 회선수)만 제공합니다.

**실제 용량 환산 (참고)**:
```python
# 문헌 기반 근사치
capacity_mw = {
    (765, 2): 7000,   # 765kV 2회선
    (345, 2): 1800,   # 345kV 2회선
    (154, 2): 350,    # 154kV 2회선
    (66, 2): 100,     # 66kV 2회선
}
```

정확한 값은 한국전력공사 자료를 참조하세요.

### Q9. 회선·킬로미터(c.km)는 무엇인가요?

송전선의 실제 전송 능력을 나타내는 지표입니다.

**계산**:
```
c.km = Σ (각 송전선의 길이 × 회선수)
```

**예시**:
- 송전선 A: 50km, 2회선 → 100 c.km
- 송전선 B: 30km, 1회선 → 30 c.km
- 합계: 130 c.km

**활용**:
- 전력망 투자 규모 평가
- 지역 간 연계 강도 비교
- 국제 비교 (circuit-km는 국제 표준 지표)

### Q10. 시·도 간 길이가 이상해요

`total_length_km`는 각 라인의 min(시도A길이, 시도B길이)를 합산한 값입니다.

**예시**:
```
송전선 1: 서울 10km + 경기 50km → 연결 길이 10km
송전선 2: 서울 20km + 경기 30km → 연결 길이 20km
합계: 30km
```

이는 두 지역을 실제로 연결하는 송전선 길이의 보수적 추정치입니다.

## 출력 파일

### Q11. 어떤 파일을 사용해야 하나요?

**목적별 추천**:

| 목적 | 파일 |
|------|------|
| 시·도별 통계 | `kr_length_by_province.csv` |
| 지역 간 연결 분석 | `kr_province_connections_simple.csv` |
| PyPSA 모델 입력 | `pypsa_lines.xlsx` |
| GIS 시각화 | `kr_power_lines.gpkg` |
| 상세 분석 | `kr_province_connections_by_voltage.csv` |

### Q12. Excel에서 한글이 깨져요

CSV 파일은 UTF-8 BOM 인코딩으로 저장됩니다.

**Excel에서 열기**:
1. Excel 실행
2. 데이터 → 텍스트/CSV 가져오기
3. 파일 원본: "65001: Unicode (UTF-8)" 선택

또는 `pypsa_lines.xlsx` 파일을 사용하세요 (한글 정상 표시).

### Q13. QGIS에서 파일을 열 수 없어요

`.gpkg` 파일은 GeoPackage 형식입니다.

**QGIS에서 열기**:
1. 레이어 → 레이어 추가 → 벡터 레이어 추가
2. 소스 유형: 파일
3. `output/*.gpkg` 선택
4. 레이어 선택 (lines, substations, admin_lv4)

QGIS 3.0 이상이 필요합니다.

## 고급 사용

### Q14. 특정 전압 등급만 추출하고 싶어요

출력 파일을 후처리하세요:

```python
import pandas as pd

df = pd.read_csv('output/kr_province_connections_simple.csv')

# 345kV 이상만 필터링
high_voltage = df[df['전압_kV'] >= 345]
high_voltage.to_csv('output/high_voltage_only.csv', index=False)
```

### Q15. 시·군·구 단위로 집계하고 싶어요

현재는 시·도(admin_level=4)만 지원합니다.

**향후 지원 예정**: `--admin-level 5` 옵션으로 시·군·구 단위 집계

**현재 우회 방법**:
1. 스크립트 수정: `ADMIN_LEVEL_TARGET = "5"`
2. 시·군·구 경계 GeoJSON 별도 준비
3. 출력 파일을 Python/R로 재집계

### Q16. 변전소 용량도 알 수 있나요?

OSM에는 변전소 용량 정보가 거의 없습니다.

**대안**:
- 한국전력공사 공개 데이터 활용
- `kr_power_substations.gpkg`에서 변전소 위치 확인 후 수동 매칭

### Q17. 해저 케이블도 포함되나요?

네, `power=cable` 태그가 있는 송전선은 포함됩니다.

**확인 방법**:
```python
df = pd.read_csv('output/kr_power_lines_summary.csv')
cables = df[df['power'] == 'cable']
print(f"해저/지중 케이블: {len(cables)}개")
```

### Q18. 다른 나라에도 사용할 수 있나요?

네, `--area` 옵션으로 다른 국가 지정 가능합니다.

```bash
# 일본
python "power network extract.py" --area "Japan" --tiles 5

# 독일
python "power network extract.py" --area "Germany" --tiles 3
```

단, 시·도 정규화 로직은 한국 전용이므로 수정이 필요합니다.

## 오류 해결

### Q19. "Repository not found" 오류

GitHub 저장소가 아직 생성되지 않았습니다.

**해결**:
1. [GitHub에서 새 저장소 생성](https://github.com/new?name=kr-power-network-extract)
2. 로컬 저장소와 연결:
```bash
cd kr-power-network-extract
git remote add origin https://github.com/YOUR_USERNAME/kr-power-network-extract.git
git push -u origin main
```

### Q20. "PROJ_LIB" 또는 "GDAL_DATA" 오류

좌표계 변환 라이브러리 경로 문제입니다.

**해결**:
```bash
# Anaconda 환경에서
conda install -c conda-forge proj gdal

# 또는 환경변수 수동 설정
export PROJ_LIB=/path/to/conda/share/proj
export GDAL_DATA=/path/to/conda/share/gdal
```

스크립트는 자동으로 경로를 설정하지만, 실패 시 수동 설정이 필요합니다.

### Q21. 메모리 부족 오류

전국 데이터 처리 시 4~8GB RAM이 필요합니다.

**해결**:
1. 특정 지역만 추출: `--area "Seoul"`
2. 경계박스 축소: `--bbox "126.5,37.2,127.5,37.8"`
3. 빠른 모드: `--quick`
4. 64비트 Python 사용 확인

## 기여 및 지원

### Q22. 버그를 발견했어요

[GitHub Issues](https://github.com/HYODONGMOON/kr-power-network-extract/issues)에 등록해 주세요.

**포함할 정보**:
- 운영체제 및 Python 버전
- 실행 명령어
- 오류 메시지 전문
- 재현 방법

### Q23. 기능을 추가하고 싶어요

Pull Request를 환영합니다!

1. Fork the repository
2. Create feature branch: `git checkout -b feature/AmazingFeature`
3. Commit changes: `git commit -m 'Add AmazingFeature'`
4. Push to branch: `git push origin feature/AmazingFeature`
5. Open Pull Request

### Q24. 논문에 인용하고 싶어요

다음과 같이 인용해 주세요:

```
Moon, H. (2025). KR Power Network Extractor: OpenStreetMap-based 
Transmission Network Analysis Tool for South Korea. 
GitHub repository: https://github.com/HYODONGMOON/kr-power-network-extract
```

BibTeX:
```bibtex
@software{moon2025kr,
  author = {Moon, Hyodong},
  title = {KR Power Network Extractor},
  year = {2025},
  url = {https://github.com/HYODONGMOON/kr-power-network-extract}
}
```

## 추가 리소스

- [설치 가이드](installation.md)
- [사용 가이드](usage.md)
- [데이터 구조](data_structure.md)
- [알고리즘 설명](algorithm.md)
- [OpenStreetMap Wiki - Power](https://wiki.openstreetmap.org/wiki/Power)
- [PyPSA Documentation](https://pypsa.readthedocs.io/)

