"""Declarative production-cell template; the external launcher owns capture."""
from __future__ import annotations


def _execute_declared_cell(cell, factory, root_constructor, operation):
    authority = factory(host_bootstrap_capability=cell["host_bootstrap_capability"], host_bootstrap_material_verifier=cell["host_bootstrap_material_verifier"], server_time=cell["server_time"])
    service = root_constructor(verified_production_host_authority=authority)
    result = service.sync_event(operation=operation, content=cell["content"], operation_id=cell["operation_identity"], authenticated_host_ingress=cell["authenticated_host_ingress"])
    return result


CAPTURE_ENTRYPOINT = "_execute_declared_cell"
