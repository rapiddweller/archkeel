from app.service import run


def test_run() -> None:
    assert run() == 1
