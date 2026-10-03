import mirage


def test_import_mirage() -> None:
    assert isinstance(mirage.__version__, str)
    assert mirage.__version__
