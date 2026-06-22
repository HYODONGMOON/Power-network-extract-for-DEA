#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
빠른 시작 예제: 서울 지역 송전망 추출 및 분석

이 스크립트는 KR Power Network Extractor의 기본 사용법을 보여줍니다.
"""

import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import os

# 1. 서울 지역 송전망 데이터 추출
print("=" * 60)
print("1단계: 서울 지역 송전망 데이터 추출 중...")
print("=" * 60)

cmd = [
    "python", 
    "power network extract.py",
    "--area", "Seoul",
    "--quick"  # 빠른 모드 (변전소 제외)
]

# 실행
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print("오류 발생:", result.stderr)
    exit(1)

print("\n✓ 데이터 추출 완료!\n")

# 2. 결과 파일 로드 및 분석
print("=" * 60)
print("2단계: 결과 분석")
print("=" * 60)

# 시·도별 통계
province_stats = pd.read_csv('output/kr_length_by_province.csv')
print("\n[시·도별 송전선 통계]")
print(province_stats.to_string(index=False))

# 시·도 간 연결
connections = pd.read_csv('output/kr_province_connections_simple.csv')
print("\n[시·도 간 연결 (상위 10개)]")
top10 = connections.nlargest(10, '회선km')
print(top10[['시작지역', '종료지역', '전압_kV', '회선km']].to_string(index=False))

# 3. 간단한 시각화
print("\n" + "=" * 60)
print("3단계: 시각화")
print("=" * 60)

# 전압별 송전선 길이
voltage_stats = connections.groupby('전압_kV')['길이_km'].sum().sort_values(ascending=False)

plt.figure(figsize=(10, 6))
voltage_stats.plot(kind='bar', color='steelblue')
plt.title('전압 등급별 송전선 총 길이', fontsize=14, fontweight='bold')
plt.xlabel('전압 (kV)', fontsize=12)
plt.ylabel('길이 (km)', fontsize=12)
plt.xticks(rotation=0)
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()

output_path = 'output/voltage_distribution.png'
plt.savefig(output_path, dpi=150)
print(f"\n✓ 그래프 저장: {output_path}")

# 4. 요약 통계
print("\n" + "=" * 60)
print("4단계: 요약 통계")
print("=" * 60)

total_length = province_stats['total_length_km'].sum()
total_capacity = province_stats['sum_capacity_proxy'].sum()
avg_voltage = province_stats['avg_voltage_kV'].mean()

print(f"""
📊 전체 통계 요약:
  • 총 송전선 길이: {total_length:,.1f} km
  • 평균 전압: {avg_voltage:.1f} kV
  • 용량 지표 합계: {total_capacity:,.0f}
  • 분석 지역 수: {len(province_stats)}개
  • 지역 간 연결 수: {len(connections)}개
""")

print("=" * 60)
print("✓ 분석 완료!")
print("=" * 60)
print(f"\n모든 결과 파일은 './output' 폴더에 저장되었습니다.")
print("\n다음 단계:")
print("  1. QGIS에서 kr_power_lines.gpkg 파일을 열어 시각화")
print("  2. pypsa_lines.xlsx를 PyPSA 모델 입력으로 사용")
print("  3. CSV 파일을 Excel/Python으로 추가 분석")

