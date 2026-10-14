# PRISM에서 사용하는 DynamicLH2PoolX 물리 검증 근거

작성일: 2026-10-14  
산출물: `results/20261014/dynamiclh2poolx_evidence_audit.json`  
감사 스키마: `prism.dynamiclh2poolx_evidence_audit.v1`

## 확인한 외부 자료

`C:/Users/lyul/Desktop/DocuData/SLABx_LH2/.release-work/DynamicLH2PoolX-review`의
Stage-C 자료를 PRISM 감사 코드로 다시 읽었다. 자료에는 Stage-C 프로토콜,
JUEL-3155 물·알루미늄 풀 확산 관측점, HSE RR985 Test 6 반경 자료,
소스 manifest, 구현 파일 해시가 포함되어 있다.

감사 결과는 `RESTRICTED_COMPONENT_EVIDENCE_CURRENT_SOURCE_REPLAY_WITH_EXTERNAL_EVIDENCE_DRIFT`이다.
이는 다음 항목을 증거로 보존한다.

- 질량수지와 관측 연산자 점검(C0)
- 공간·결합 세분화 수렴 점검(C1)
- JUEL Trial 3·5 보정과 Trial 4·6 보류시험(C2)
- HSE Test 6의 제한된 반경 평가(C3)
- 보류시험 반경 관측점 19개(물 Trial 4 9개, 알루미늄 Trial 6 10개)
- 보정시험과 보류시험이 분리된 상태

외부 `stage_c_evidence.json`에 기록된 해시와 현재 작업공간의 프로토콜·소스
manifest·구현 파일 해시는 4건이 달랐다. 따라서 감사는 자료를 삭제하거나
깨끗한 재현으로 포장하지 않고, 현재 소스 재실행과 외부 증거 드리프트를
상태로 남긴다.

## PRISM에서 허용하는 의미

이 자료는 **지표에 도달한 액화수소 유입을 평탄하고 장애물이 없는 표면에
놓았을 때의 축대칭 풀 source-term 구성요소**에 대한 제한 근거다. 풀 반경,
증발·질량 장부, 수치 수렴을 점검하는 데 사용할 수 있다.

다음 주장은 이 자료만으로 허용하지 않는다.

- 탱크·배관·밸브·펌프의 사고 방출률 또는 방출 지속시간 검증
- 사고 시 차단과 재고 소진 검증
- 제트 충돌, 액적 분해, 지표 도달률, 비대칭 액편 검증
- SLABx-LH2 대기 농도·LFL 거리의 독립 물리 검증
- 점화·화재·폭발·복사열·IR/F-N 또는 시설 전체 QRA 검증
- 관측값으로 사고 빈도를 역산하거나 센서 기반 빈도를 학습하는 것

따라서 `physical_validation_claim`, `full_chain_validation_claim`,
`accident_release_validation_claim`, `facility_qra_claim`는 모두 `false`로
유지한다. 이 경계가 있어야 PRISM의 조건부 방출→피해 계산이 실제 검증으로
과장되지 않는다.

## 다음 검증 단계

1. 현재 DynamicLH2PoolX 소스와 외부 원자료의 해시를 고정하고 재현 실행한다.
2. PRISM의 설비별 방출 packet과 동일한 방출 조건·시간축으로 source-term 비교를
   수행한다.
3. 동일한 사건에 대해 SLABx-LH2 농도·LFL 관측 비교를 별도로 수행한다.
4. 시설 점화·인구·IR/F-N 결과는 위 구성요소 검증과 분리하여 독립 검토한다.

재현 명령:

```powershell
python scripts/audit_dynamiclh2poolx_evidence.py `
  --source-root "C:/Users/lyul/Desktop/DocuData/SLABx_LH2/.release-work/DynamicLH2PoolX-review" `
  --output results/20261014/dynamiclh2poolx_evidence_audit.json
```
