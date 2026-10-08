# PRISM 0.6.0 — PyPI·DOI 배포 완료 기록

2026-10-08. 사용자가 PRISM의 PyPI·DOI 발행과 MIT 라이선스를 선택한 요청에 따라 발행했다.

## 바로 확인할 주소

| 항목 | 주소 / 값 |
|---|---|
| 제품 이름 | PRISM — Process Risk Integration and Scenario Modeling |
| Python 배포명 | `prism-risk` |
| 버전 | `0.6.0` |
| 라이선스 | MIT, Copyright (c) 2026 Ugwiyeon Lee |
| 저자 / 소속 | Lee, Ugwiyeon / Korea Gas Safety Corporation |
| PyPI | https://pypi.org/project/prism-risk/0.6.0/ |
| 버전 DOI | https://doi.org/10.5281/zenodo.23241359 |
| 전체 버전 DOI | https://doi.org/10.5281/zenodo.23241358 |
| Zenodo | https://zenodo.org/records/23241359 |
| GitHub | https://github.com/lyullee/prism — 비공개 유지 |
| GitHub Release | https://github.com/lyullee/prism/releases/tag/v0.6.0 — 연구용 prerelease 표시 |
| 고정 release commit | `49abcd36b5314a45a3013f559a68bc53a6f6c090` |
| 고정 release tag | `v0.6.0` |
| PyPI 배포 workflow | https://github.com/lyullee/prism/actions/runs/37795878407 — success |

DOI는 예약만 한 상태가 아니다. 공개 record API에서 발행 기록을 읽었고 DOI resolver가 위 Zenodo 공개 기록으로 이동하는 것을 확인했다. PyPI도 pending publisher 등록만 한 상태가 아니다. GitHub OIDC 배포가 성공했고 공개 인덱스에서 설치했다.

## 아주 쉽게 구분하면

- **GitHub**: 개발 중인 코드와 변경 이력을 보관하는 곳. 현재 비공개이므로 계정 권한이 필요하다.
- **PyPI**: `pip install`로 Python 프로그램을 설치하는 곳. 공개되어 있다.
- **Zenodo DOI**: 논문에서 정확히 어떤 프로그램 버전을 사용했는지 인용하는 영구 주소. 공개 소스·문서·예제도 여기에서 받을 수 있다.
- 이 DOI는 **소프트웨어 DOI**다. IJHE 논문의 게재나 저널 DOI 발급을 뜻하지 않는다.

## 설치와 시작

Python 3.12 이상으로 새 가상환경에서 실행한다.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install prism-risk==0.6.0
.venv\Scripts\prism.exe --describe-modes
.venv\Scripts\prism.exe --mode lh2 --help
```

외부 모델 없이 시설 구성 검증과 문헌 빈도 생성이 가능하다. 실제 방출·확산·화재/폭발 계산에는 README에서 설명한 외부 provider와 실행 환경이 필요하다.

예제와 전체 안내가 필요하면 Zenodo의 `PRISM-0.6.0-source.zip`을 내려받아 압축을 푼다. 압축을 푼 루트에서:

```powershell
.venv\Scripts\prism.exe --mode lh2 lh2-tno/examples/storage_terminal.json
.venv\Scripts\prism.exe --mode lh2 lh2-tno/examples/lh2_frequency_facility.json --frequency-plan lh2-tno/examples/lh2_frequency_plan.json --output events.json
```

빈도 예제는 합성 시설의 16개 사건을 만든다. `total_facility_annual_risk=null`은 전체 시설의 모든 사건별 피해를 합산하지 않았다는 뜻이다.

## 배포한 파일과 동일성 확인

Zenodo와 GitHub Release에 다음 세 파일을 보관했다. wheel·sdist는 GitHub Actions가 빌드하여 **실제 PyPI에 발행한 파일**을 다시 내려받아 사용했다. 로컬 사전 빌드 파일과 혼동하지 않는다.

| 파일 | bytes | SHA-256 |
|---|---:|---|
| `PRISM-0.6.0-source.zip` | 229028 | `ecf832df1cf18548a7ae922cd5cb53ed651b06169ce0503de84d93c9ce3ffda0` |
| `prism_risk-0.6.0-py3-none-any.whl` | 62239 | `16dafdee8397ef9417d79973e589afbc061e546a18eca9170f32d346bb3f3d68` |
| `prism_risk-0.6.0.tar.gz` | 123562 | `98b9d9a0368fa5896136c53625f64f357ad0a0ee345a793f675c52bc76a5a542` |

Zenodo 공개 파일도 다시 내려받아 SHA-256과 Zenodo MD5를 대조했다. 모든 파일이 지정한 배포 파일과 일치했다. 전체 소스 ZIP의 Git tree는 `a8ebf3209e006fb59aad211bace5a4e00c570b98`이며 release commit과 같은 tree다.

소스 ZIP과 sdist의 `CURRENT_STATUS.json`은 **빌드 시점** 기록이므로 DOI 예약·배포 준비 상태가 남아 있다. 이 문서와 main의 현재 상태 파일은 **발행 후** 기록이다. 발행된 0.6.0 파일이나 태그를 덮어쓰지 않았다.

## 확인한 검사

- 로컬 사전 배포 검사: 154개 portable 단위·계약·보존·모드 검사 통과.
- 사전 빌드한 sdist 압축을 풀어 설치·재빌드·154개 검사 통과. 예제 경로가 누락되지 않도록 테스트 fixture를 배포 포함 examples로 연결했다.
- GitHub release workflow: 고정 태그 버전 대조, 154개 검사, sdist/wheel 빌드, `twine check --strict`, PyPI trusted publishing 성공.
- PyPI 공개 인덱스의 0.6.0을 새 Windows 가상환경에 설치하고 `prism --describe-modes` 및 빈도 예제 명령 실행 성공.
- PyPI JSON의 두 배포 파일 SHA-256 및 Zenodo 세 파일의 동일성 대조 성공.
- Zenodo 공개 기록의 제목·버전·저자·소속·MIT 라이선스 및 DOI resolver 확인 성공.
- 이 배포 작업에서 외부 물리 엔진을 새로 재실행하지 않았다. 과거 물리 계산 근거는 별도 개발 기록을 참조한다.

## 인용

특정 재현 실험에는 버전 DOI를 사용한다.

> Lee, U. (2026). PRISM: Process Risk Integration and Scenario Modeling (v0.6.0) (Version 0.6.0) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.23241359

`CITATION.cff`와 `.zenodo.json`에도 저자·라이선스·버전 인용 정보를 보관했다. 전체 버전을 대표하는 인용에는 `10.5281/zenodo.23241358`을 사용할 수 있다.

## 다음 버전을 배포할 때

1. 코드 변경·검증과 README/현재 상태를 정리하고 새 버전을 지정한다. 공개 0.6.0은 다시 업로드할 수 없다.
2. 새 버전의 DOI가 필요하면 **기존 Zenodo 기록의 New version**을 사용하여 예약한다. 새 독립 기록을 매번 만들지 않는다.
3. 새 버전 DOI·날짜·버전을 인용 파일과 pyproject에 반영한다.
4. 검토한 commit에 `v버전` 태그를 만들고 GitHub main과 태그를 업로드한다.
5. `Publish PRISM to PyPI` workflow를 수동 실행한다. `release_ref`에는 검토한 고정 태그를 넣는다. GitHub `pypi` 환경과 PyPI publisher의 repository/workflow/environment 이름을 유지한다.
6. 공개 PyPI에서 설치·실행·해시를 확인한다. 실제 PyPI 파일과 소스 보관본을 Zenodo 새 버전에 올리고 검토 후 발행한다.
7. DOI resolver와 파일 동일성을 확인하고 발행 후 기록을 main 및 코드 옆 보관 폴더에 남긴다.

## 연구 범위와 상세 증빙

PRISM 자체에 MIT를 적용하며 외부 엔진·책·원자료의 권리는 바꾸지 않았다. 외부 모델 소스, 실측 원자료, 로컬 원고와 자격 증명은 새 공개 배포에 포함하지 않았다. 전체 시설 LH2 연간 IR/F-N, 독립 현장 검증, 매초 신규 물리 계산과 완전한 설비 재고·에너지 피드백은 후속 개발 항목이다.

로컬 상세 증빙: `results/20261008/prism_publication_v060/`의 `publication_complete.json`, `pypi_download_verification.json`, `github_release.json`, `release_verification.json`, `sdist_tests.xml`, `pypi_published.jpg`, `zenodo_published.jpg`. 이 results 기록은 Git에서 제외하여 개발 PC와 코드 옆 보관본에 유지한다.
