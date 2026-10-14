"""Helpers for keeping explicit non-release component exclusions out of ledgers."""
from __future__ import annotations

from collections.abc import Iterable, Mapping


def expected_component_ids_for_release(
    component_ids: Iterable[object],
    *,
    excluded_model_components: Mapping[object, object] | Iterable[object] = (),
    additional_component_ids: Iterable[object] = (),
) -> tuple[str, ...]:
    """Return components that must have an accidental-release ledger row.

    A manifest can contain an interface or boundary component that is explicitly
    excluded from the frequency plan.  Such a component remains visible in the
    scope/exclusion ledger, but it must not be passed as an *expected release*
    component: doing so turns a documented exclusion into a misleading
    ``missing expected component`` error.  Extension components are appended in
    declaration order and are de-duplicated without inventing any event.
    """

    if isinstance(excluded_model_components, Mapping):
        excluded = {str(key) for key in excluded_model_components}
    else:
        excluded = {str(value) for value in excluded_model_components}

    output: list[str] = []
    seen: set[str] = set()
    for value in (*component_ids, *additional_component_ids):
        component_id = str(value).strip()
        if not component_id or component_id in excluded or component_id in seen:
            continue
        seen.add(component_id)
        output.append(component_id)
    return tuple(output)
