import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: smoke tests requiring live docker-compose environment")


def pytest_collection_modifyitems(config, items):
    """Skip smoke tests unless --run-smoke is passed."""
    if config.getoption("--run-smoke", default=False):
        return
    skip_smoke = pytest.mark.skip(reason="need --run-smoke option to run")
    for item in items:
        if "smoke" in item.keywords:
            item.add_marker(skip_smoke)


def pytest_addoption(parser):
    parser.addoption(
        "--run-smoke",
        action="store_true",
        default=False,
        help="run smoke tests against live docker-compose",
    )