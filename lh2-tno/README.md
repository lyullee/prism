# PRISM — Python 패키지

**Process Risk Integration and Scenario Modeling / v0.6.0**

상세 시스템 설명·설치·실행·입력·빈도·설비/센서 연결·결과 해석은 [저장소 README](../README.md)에 있습니다.

```powershell
# 저장소 루트에서 실행
python -m pip install -e "./lh2-tno[test]"
python prism.py --describe-modes
python prism.py --mode lh2 lh2-tno/examples/lh2_frequency_facility.json --frequency-plan lh2-tno/examples/lh2_frequency_plan.json --output events.json
```

배포 이름은 `prism-risk`, 명령은 `prism`입니다. 폴더 `lh2-tno`, import `lh2_tno`, host `tno_host`와 과거 명령은 호환성을 위해 유지합니다.
기본 `standard`는 외부 기존 QRA, 선택형 `lh2`는 상세 액화수소 연동입니다. 실패 시 자동 모드 전환은 없습니다.

방출부터 최종 피해까지 진단 실행과 문헌 빈도 생성은 구현했습니다. 전체 LH2 시설 IR/F-N, 모든 LOC 자동 결합, 전체 설비 동적 피드백과 신규 계산 1 Hz는 미완료/미검증입니다.
154개 portable 검사와 과거 실제 모델 연결 기록은 독립 물리/현장 검증을 뜻하지 않습니다.
현장 사고빈도 자료 없이 문헌 기본선과 불확실성·민감도로 개발합니다.

[현재 상태](CURRENT_STATUS.json) / [v0.6.0 기록](docs/PRISM_v060_명칭과사용안내_20261008.md) / [IJHE 프로토콜](docs/IJHE_연구프로토콜.md).
이전 TNO-LH2 명칭의 v0.3/0.4/0.5 문서는 당시 검증 이력을 보존한 것입니다.
