"""Markdown profile and append-only portfolio repositories."""

from datetime import datetime
from pathlib import Path
from typing import Any

from fra.adapters.storage.serialization import decode, encode
from fra.adapters.storage.workspace import Workspace
from fra.domain.errors import (
    RepositoryConflictError,
    RepositoryCorruptError,
    RepositoryNotFoundError,
)
from fra.domain.ids import PortfolioId, ProfileId
from fra.domain.portfolio import InvestorProfile, Portfolio


class MarkdownProfileRepository:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def save(self, profile: InvestorProfile) -> None:
        path = self._workspace.path(f"profiles/{self._workspace.safe_segment(profile.id)}.md")
        with self._workspace.lock(f"profile-{profile.id}"):
            if path.exists():
                raise RepositoryConflictError(f"profile {profile.id} is immutable")
            body = (
                f"# Investor Profile {profile.id}\n\n"
                f"- Investment objective: {profile.investment_objective}\n"
                f"- Horizon: {profile.horizon_years} years\n"
                f"- Risk tolerance: {profile.risk_tolerance.value}\n"
                f"- Risk capacity: {profile.risk_capacity.value}\n"
                f"- Maximum loss: {profile.maximum_loss}\n"
                f"- Liquidity need: {profile.liquidity_need}\n"
                f"- Tax jurisdiction: {profile.tax_jurisdiction}\n"
            )
            self._workspace.writer.write_text(
                path,
                self._workspace.codec.render(
                    _metadata(
                        "fra.investor_profile", str(profile.id), profile.confirmed_at, profile
                    ),
                    body,
                ),
            )

    def get(self, profile_id: ProfileId) -> InvestorProfile:
        path = self._workspace.path(f"profiles/{self._workspace.safe_segment(profile_id)}.md")
        if not path.is_file():
            raise RepositoryNotFoundError(f"profile {profile_id} does not exist")
        return _read(path, "fra.investor_profile", InvestorProfile)

    def list(self) -> tuple[InvestorProfile, ...]:
        return tuple(
            self.get(ProfileId(path.stem))
            for path in sorted(self._workspace.path("profiles").glob("*.md"))
        )


class MarkdownPortfolioRepository:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def save(self, portfolio: Portfolio) -> None:
        portfolio_id = self._workspace.safe_segment(portfolio.id)
        path = self._workspace.path(f"portfolios/{portfolio_id}/v{portfolio.version:03d}.md")
        with self._workspace.lock(f"portfolio-{portfolio_id}"):
            if path.exists():
                raise RepositoryConflictError(
                    f"portfolio {portfolio.id} version {portfolio.version} is immutable"
                )
            if (
                portfolio.version > 1
                and not self._workspace.path(
                    f"portfolios/{portfolio_id}/v{portfolio.version - 1:03d}.md"
                ).is_file()
            ):
                raise RepositoryConflictError("portfolio versions must be contiguous")
            rows = "\n".join(
                f"| {item.instrument_id} | {item.symbol} | {item.weight} | "
                f"{item.currency.code} | {portfolio.as_of.date()} |"
                for item in portfolio.positions
            )
            body = (
                f"# {portfolio.kind.value.title()} Portfolio {portfolio.id}\n\n"
                "| Instrument ID | Symbol | Weight | Currency | As of |\n"
                "| --- | --- | ---: | --- | --- |\n"
                f"{rows}\n"
            )
            metadata = _metadata("fra.portfolio", str(portfolio.id), portfolio.as_of, portfolio)
            metadata["version"] = portfolio.version
            metadata["kind"] = portfolio.kind.value
            self._workspace.writer.write_text(path, self._workspace.codec.render(metadata, body))

    def get(self, portfolio_id: PortfolioId, version: int | None = None) -> Portfolio:
        root = self._workspace.path(f"portfolios/{self._workspace.safe_segment(portfolio_id)}")
        paths = sorted(root.glob("v[0-9][0-9][0-9].md")) if root.is_dir() else []
        if version is None:
            if not paths:
                raise RepositoryNotFoundError(f"portfolio {portfolio_id} does not exist")
            path = paths[-1]
        else:
            path = root / f"v{version:03d}.md"
            if not path.is_file():
                raise RepositoryNotFoundError(
                    f"portfolio {portfolio_id} version {version} does not exist"
                )
        return _read(path, "fra.portfolio", Portfolio)

    def list(self) -> tuple[Portfolio, ...]:
        root = self._workspace.path("portfolios")
        if not root.is_dir():
            return ()
        return tuple(
            self.get(PortfolioId(path.name)) for path in sorted(root.iterdir()) if path.is_dir()
        )


def _metadata(schema: str, item_id: str, timestamp: datetime, item: object) -> dict[str, Any]:
    rendered = timestamp.isoformat().replace("+00:00", "Z")
    return {
        "schema": schema,
        "schema_version": 1,
        "id": item_id,
        "created_at": rendered,
        "updated_at": rendered,
        "payload": encode(item),
    }


def _read[T](path: Path, schema: str, expected: type[T]) -> T:
    try:
        metadata, _body = WorkspaceCodec(path).parse(schema)
        value = decode(metadata["payload"])
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise RepositoryCorruptError(f"could not reconstruct {path.name}: {error}") from error
    if not isinstance(value, expected):
        raise RepositoryCorruptError(f"{path.name} does not contain {expected.__name__}")
    return value


class WorkspaceCodec:
    """Keep the shared codec invocation small for both repository classes."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def parse(self, schema: str) -> tuple[dict[str, Any], str]:
        from fra.adapters.storage.markdown_codec import MarkdownCodec

        return MarkdownCodec().parse(self._path.read_text(encoding="utf-8"), expected_schema=schema)
