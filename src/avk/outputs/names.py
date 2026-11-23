"""Names for projection output files."""


def file_name(product: str, scenario: str, kind: str) -> str:
    """Return the base name. The sink adds the file extension."""
    return f"{product}_{scenario}_{kind}"
