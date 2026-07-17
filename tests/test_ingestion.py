from src.ingestion import slugify, tokenize_commodities


def test_slugify() -> None:
    assert slugify("Greenbushes – Lithium") == "greenbushes-lithium"


def test_tokenize_commodities() -> None:
    assert tokenize_commodities("Li-Ta-Sn") == {"Li", "Ta", "Sn"}
    assert tokenize_commodities(None) == set()
