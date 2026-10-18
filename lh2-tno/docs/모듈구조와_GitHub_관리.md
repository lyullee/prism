# PRISM 구조와 GitHub 관리

2026-10-08, v0.6.0. 정식 이름 **PRISM (Process Risk Integration and Scenario Modeling)**.
공개 저장소는 https://github.com/lyullee/prism 이며 최신 배포 기준은 `main`입니다. 외부 TNO 위험계산 엔진 소스는 이 저장소에 포함되지 않고 별도 backend로 핀 고정합니다.

## 실행 구조

`python prism.py` 또는 설치한 `prism` 명령에서 `standard`(기본)와 `lh2`(선택)를 실행합니다.
실행 진입점은 통합하고 내부 물리 모델과 책임은 분리합니다. 별도의 독립 배포 add-on을 설치하는 방식이 아니라
현재 wheel에 host와 LH2 extension을 함께 담고 runtime에서 선택적으로 import합니다.
외부 기존 엔진이나 설비/SLAB 소스 전체를 이 패키지로 합치지는 않았습니다.

| 코드 | 책임 |
|---|---|
| PRISM host | 모드 선택, 기존 qra.py 실행과 해시 검사 |
| lh2_tno | 시설/포트 계약, 빈도, 센서, 모델 연동/근거/질량 검사 |
| 외부 기존 엔진 | 기본 QRA와 열/폭발 인명 피해, 근거 gate |
| 별도 lh2dt | 설비 PH/유량/재고/명령 시계 |
| SLABx-LH2 / SLABx | 방출·극저온 전이·분산 |
| DynamicLH2PoolX | 지면 LH2 풀/증발 |

## 이름과 호환성

배포 이름 `prism-risk`, 명령 `prism`, import `lh2_tno`입니다.
`lh2-tno` 소스 폴더와 `tno_host` 모듈은 과거 경로·import 호환성을 위해 유지합니다.
`python tno.py`, `tno`, 직접 LH2 명령도 유지합니다. 제품 이름에는 TNO를 사용하지 않으며
방법/문헌/외부 엔진 식별자에는 정확한 출처 이름을 유지합니다.

## 저장소 이전

이전 `tno-lh2`의 모든 로컬 Git 개발 이력을 새 저장소에 보존합니다.
이전 GitHub `tno-lh2` 저장소는 새 업로드·CI 검증 이후 사용자 요청대로 삭제 완료했습니다. 인증된 API의 404와 GitHub 목록에서 확인했습니다.
`tno-qra`는 생성하지 않았습니다. 상세 원격 상태는 로컬 publication.json에 기록합니다.

포함: 코드, 합성 입력, 검사, catalogue와 문서.
제외: 원계측 자료, 책 PDF, 외부 모델 소스 복사본, 원고와 raw 계산 출력.
옛 문서의 로컬 경로와 저장소 URL은 역사 기록이며 현재 사용 안내는 [루트 README](../../README.md)입니다.

## 범위

모드 선택은 새 LH2 시설 전체 QRA 완료를 뜻하지 않습니다.
기존 엔진의 전체 사건수목/기상 IR/F-N과 새 LH2 경로의 완전 결합은 남아 있습니다.
수평·대기압·low-Mach 기체 출구는 이미 계산된 유량 그대로 최종 피해로 연결합니다.
탱크 전단 PH source·액체/2상·수직/팽창 출구·재고 피드백은 추가 구현이 필요합니다.
