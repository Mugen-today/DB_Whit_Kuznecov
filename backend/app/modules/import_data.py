"""Legacy unvalidated import is intentionally unavailable."""

def execute(*args, **kwargs):
    if not args and "store" not in kwargs:
        raise NotImplementedError("Use strict record API")
    raise ValueError("Legacy GPKG import disabled: submit complete records to POST /v1/records; no default medical values are generated")
