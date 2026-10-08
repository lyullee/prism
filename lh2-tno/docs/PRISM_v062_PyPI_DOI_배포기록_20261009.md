# PRISM 0.6.2 — PyPI·DOI 배포 기록

2026-10-09에 PRISM 0.6.2의 검증된 소스와 배포 파일을 GitHub Release, PyPI, Zenodo에 공개했다. 이 문서는 공개 후 영수증을 고정한다.

## 공개 주소

| 대상 | 주소 또는 식별자 |
|---|---|
| GitHub Release | https://github.com/lyullee/prism/releases/tag/v0.6.2 |
| Git commit | `783b8860c709fd0b7d944b0fe5e9b19d5cd95e15` |
| PyPI | https://pypi.org/project/prism-risk/0.6.2/ |
| PyPI workflow | https://github.com/lyullee/prism/actions/runs/37833213191 |
| Zenodo record | https://zenodo.org/records/23246944 |
| 버전 DOI | https://doi.org/10.5281/zenodo.23246944 |
| 전체 버전 DOI | https://doi.org/10.5281/zenodo.23241358 |

버전 DOI는 PRISM 0.6.2의 소프트웨어 기록이다. 전체 버전 DOI는 Zenodo의 모든 버전을 대표하며 최신 버전으로 연결된다. 둘 다 IJHE 논문 DOI나 시설 안전 인증을 의미하지 않는다.

## 공개 파일과 해시

Zenodo에는 Git tag `v0.6.2`에서 만든 소스 ZIP과 PyPI 배포 파일을 함께 보관했다. Zenodo에 표시된 MD5는 다음과 같으며, 업로드 전에 만든 로컬 파일과 대조했다.

| 파일 | Zenodo MD5 |
|---|---|
| `PRISM-0.6.2-source.zip` | `c5457e8d0810f8372450ff2276311674` |
| `prism_risk-0.6.2-py3-none-any.whl` | `e82c83fd12174fcf3e1eb696bf1b7091` |
| `prism_risk-0.6.2.tar.gz` | `69a9578ed57ea3ab074228a341f91a6c` |

PyPI 공개 JSON에서 확인한 CI 배포 파일 SHA-256은 다음과 같다.

| 파일 | PyPI SHA-256 |
|---|---|
| `prism_risk-0.6.2-py3-none-any.whl` | `8f176d1e61c6df375992e0305597709465ad38e21e1bd39775372ad2b49c8e1c` |
| `prism_risk-0.6.2.tar.gz` | `1b970f70e810250c2c41f4c06b8e407d266edcd03470de55558776e0c22f53f1` |

PyPI 파일은 GitHub Actions가 태그를 checkout하여 다시 빌드한 산출물이다. 따라서 로컬에서 별도로 만든 wheel의 바이트 해시와 다를 수 있으며, 논문 재현에는 PyPI JSON의 해시를 사용한다.

## 검증

- 패키지 루트에서 portable test **263개 통과**
- `compileall` 통과
- `CURRENT_STATUS.json`, `DEVELOPMENT_GOAL.json`, `.zenodo.json` JSON 파싱 통과
- `python -m build --sdist --wheel` 통과
- `twine check --strict` 통과
- GitHub Actions build와 trusted PyPI publish job 성공
- PyPI 공개 인덱스에서 `0.6.2`와 wheel/sdist 두 파일 확인
- Zenodo record에서 공개 상태, 버전 `0.6.2`, MIT 라이선스, 세 파일, DOI resolver 확인

## 사용

```powershell
python -m pip install prism-risk==0.6.2
prism --describe-modes
```

외부 설비 provider와 원계측 자료는 배포 파일에 포함하지 않았다. provider 사고 방출 packet이 없으면 PRISM은 해당 사건을 `UNCOMPUTED`로 남기며 시설 전체 연간 IR/F-N을 0으로 대체하지 않는다. 최신 provider 감사는 JSON 556개를 검사했고 정상·스크리닝 유량 24개와 사고 방출 후보 0개를 분리했다. 따라서 0.6.2의 DOI/PyPI 공개는 소프트웨어 재현성 확보를 뜻하며, 전체 시설 QRA 완료·독립 물리 검증·1 Hz 신규 물리 계산 완료를 뜻하지 않는다.
