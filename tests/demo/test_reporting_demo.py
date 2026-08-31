import pytest


def test_demo_pass():
    """Intentional PASS for reporting demonstration."""
    assert True


def test_demo_second_pass():
    """Second intentional PASS for reporting demonstration."""
    assert 2 + 2 == 4


def test_demo_failure():
    """Intentional FAIL for reporting demonstration."""
    assert False, "Demo failure: simulated application validation failure"


def test_demo_another_failure():
    """Second intentional FAIL for reporting demonstration."""
    expected = "SUCCESS"
    actual = "FAILED"

    assert actual == expected, (
        f"Demo failure: expected '{expected}', got '{actual}'"
    )


@pytest.mark.skip(reason="Demo SKIP: feature not available in current environment")
def test_demo_skip():
    """Intentional SKIP for reporting demonstration."""
    assert True


@pytest.mark.skip(reason="Demo SKIP: environment dependency not configured")
def test_demo_environment_skip():
    """Second intentional SKIP for reporting demonstration."""
    assert True