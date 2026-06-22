# 설치 가이드

이 문서는 KR Power Network Extractor의 상세 설치 방법을 안내합니다.

## 시스템 요구사항

- **운영체제**: Windows, macOS, Linux
- **Python**: 3.9 이상
- **메모리**: 최소 4GB RAM (전국 데이터 처리 시 8GB 권장)
- **디스크**: 약 1GB 여유 공간

## 설치 방법

### 방법 1: Anaconda/Miniconda 사용 (권장)

GeoPandas와 관련 라이브러리의 의존성 관리가 가장 쉬운 방법입니다.

```bash
# 1. 가상환경 생성
conda create -n power-network python=3.9
conda activate power-network

# 2. GeoPandas 및 OSMnx 설치
conda install -c conda-forge geopandas osmnx

# 3. 저장소 클론
git clone https://github.com/HYODONGMOON/kr-power-network-extract.git
cd kr-power-network-extract

# 4. 나머지 패키지 설치
pip install -r requirements.txt
```

### 방법 2: pip만 사용

```bash
# 1. 저장소 클론
git clone https://github.com/HYODONGMOON/kr-power-network-extract.git
cd kr-power-network-extract

# 2. 가상환경 생성 (선택사항이지만 권장)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 패키지 설치
pip install -r requirements.txt
```

⚠️ **주의**: pip만 사용할 경우 GDAL, GEOS, PROJ 등의 시스템 라이브러리가 미리 설치되어 있어야 합니다.

### 방법 3: Docker 사용 (향후 지원 예정)

```bash
# Docker 이미지 빌드 및 실행 (준비 중)
docker build -t kr-power-network .
docker run -v $(pwd)/output:/app/output kr-power-network
```

## 설치 확인

설치가 완료되면 다음 명령으로 확인할 수 있습니다:

```bash
python "power network extract.py" --help
```

정상적으로 설치되었다면 사용 가능한 옵션 목록이 표시됩니다.

## 문제 해결

### Windows에서 GDAL 오류

**증상**: `ImportError: DLL load failed` 또는 GDAL 관련 오류

**해결방법**:
1. Anaconda 사용을 권장합니다
2. 또는 [OSGeo4W](https://trac.osgeo.org/osgeo4w/)를 설치하세요

### macOS에서 설치 오류

**증상**: `clang: error` 또는 컴파일 오류

**해결방법**:
```bash
# Homebrew로 필수 라이브러리 설치
brew install gdal geos proj

# 환경변수 설정
export CPLUS_INCLUDE_PATH=/usr/local/include
export C_INCLUDE_PATH=/usr/local/include
```

### Linux에서 의존성 오류

**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev
sudo apt-get install -y gdal-bin libgdal-dev
sudo apt-get install -y libgeos-dev libproj-dev
```

**CentOS/RHEL**:
```bash
sudo yum install -y python3-devel
sudo yum install -y gdal gdal-devel
sudo yum install -y geos geos-devel proj proj-devel
```

### OSMnx 타임아웃 오류

**증상**: `TimeoutError` 또는 Overpass API 관련 오류

**해결방법**:
```bash
# 타임아웃 시간을 늘려서 실행
python "power network extract.py" --timeout 600

# 또는 타일 분할로 요청 크기 줄이기
python "power network extract.py" --tiles 3
```

### 메모리 부족 오류

**증상**: `MemoryError` 또는 프로세스 강제 종료

**해결방법**:
1. 특정 지역만 추출: `--area "Seoul"`
2. 경계박스로 영역 축소: `--bbox "126.5,37.2,127.5,37.8"`
3. 빠른 모드 사용: `--quick`

## 패키지 버전 호환성

테스트된 주요 패키지 버전:

```
geopandas==0.14.1
osmnx==1.9.0
pandas==2.1.4
shapely==2.0.2
pyproj==3.6.1
```

다른 버전에서도 작동할 수 있지만, 문제 발생 시 위 버전으로 다운그레이드를 권장합니다.

## 다음 단계

설치가 완료되었다면 [사용 가이드](usage.md)를 참조하세요.

