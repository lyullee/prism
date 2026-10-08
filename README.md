# TNO-LH2

Generic liquid-hydrogen facility risk-assessment integration. The Python
package is in [`lh2-tno`](lh2-tno/README.md).

This repository contains the LH2 integration package, documented frequency
catalogue, synthetic examples, tests, and development records. It is an
add-on to the existing TNO consequence/QRA engine and separately maintained
LH2 process and dispersion models. Provider source code, TNO books, raw
facility measurements, and manuscript working files are not included.

## Local checks

```sh
python -m pip install -e "./lh2-tno[test]"
cd lh2-tno
python -m pytest -q
```

External physics runs require explicit local provider paths, source hashes,
and dependency versions. The normal unit suite uses synthetic inputs and
does not require those provider packages.

Version 0.3.0 demonstrates one matching tank-hole event's automatically
generated frequency connected to the diagnostic source-to-harm chain. It
does not certify complete facility QRA, field accident frequencies, or
fresh physics calculations at 1 Hz. See
[`CURRENT_STATUS.json`](lh2-tno/CURRENT_STATUS.json) and
the [IJHE research protocol](lh2-tno/docs/IJHE_연구프로토콜.md).
