import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Mock heavy ML modules before they are imported
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_heavy_modules():
    """Mock heavy ML modules (text_embedder, captioner) to avoid model loading during tests."""
    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = [0.0] * 384  # Dummy embedding
    
    mock_captioner = MagicMock()
    mock_captioner.caption.return_value = "Test caption"
    
    with patch.dict("sys.modules", {
        "sentence_transformers": MagicMock(),
        "app.infrastructure.ml.text_embedder": MagicMock(text_embedder=mock_embedder),
        "app.infrastructure.ml.captioner": MagicMock(captioner=mock_captioner, CAPTIONING_PROMPT="Test"),
    }):
        yield


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