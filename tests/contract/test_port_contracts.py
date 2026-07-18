from typing import get_type_hints

from fra.domain.sources import DataEnvelope
from fra.ports.agent_backend import AgentBackend
from fra.ports.documents import DocumentProvider
from fra.ports.market_data import MarketDataProvider


def test_provider_ports_return_only_fra_owned_types() -> None:
    methods = (
        AgentBackend.execute,
        AgentBackend.resume,
        MarketDataProvider.quote,
        MarketDataProvider.history,
        DocumentProvider.search,
        DocumentProvider.fetch,
    )

    for method in methods:
        annotation = str(get_type_hints(method)["return"])
        assert "fra." in annotation
        assert "httpx" not in annotation
        assert "requests" not in annotation
        assert "pandas" not in annotation
        assert "Any" not in annotation


def test_data_envelope_is_the_common_provider_provenance_boundary() -> None:
    assert DataEnvelope.__module__ == "fra.domain.sources"
