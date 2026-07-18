"""Deterministic claim and citation verification before agent critique is accepted."""

from dataclasses import replace
from datetime import datetime

from fra.domain.errors import RepositoryNotFoundError
from fra.domain.research import (
    Claim,
    ClaimMateriality,
    ClaimStatus,
    ResearchRun,
    VerificationIssue,
    VerificationResult,
    VerificationSeverity,
)
from fra.domain.sources import AuthorityClass
from fra.ports.clock import Clock
from fra.ports.ids import IdGenerator
from fra.ports.repositories import ResearchRepository


class VerificationService:
    """Apply non-negotiable checks that an agent cannot waive with `passed=true`."""

    def __init__(
        self,
        repository: ResearchRepository,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._ids = ids

    def verify(
        self,
        run: ResearchRun,
        claims: tuple[Claim, ...],
        *,
        agent_passed: bool,
        agent_issues: tuple[VerificationIssue, ...],
    ) -> VerificationResult:
        cutoff = _knowledge_cutoff(run, self._clock.now())
        deterministic: list[VerificationIssue] = []
        for claim in claims:
            deterministic.extend(self._verify_claim(run, claim, cutoff))
        if not claims:
            deterministic.append(
                VerificationIssue(
                    "claim_required",
                    "research analysis must produce at least one persisted claim",
                    VerificationSeverity.HIGH,
                )
            )
        issues = (*deterministic, *agent_issues)
        if not agent_passed and not agent_issues:
            issues = (
                *issues,
                VerificationIssue(
                    "agent_rejected",
                    "agent critique rejected the analysis without a structured issue",
                    VerificationSeverity.HIGH,
                ),
            )
        deterministic_passed = not deterministic
        blocking_agent_issue = any(
            issue.severity is VerificationSeverity.HIGH for issue in agent_issues
        )
        passed = deterministic_passed and agent_passed and not blocking_agent_issue
        target_status = ClaimStatus.VERIFIED if passed else ClaimStatus.REJECTED
        for claim in claims:
            self._repository.save_claim(run.id, replace(claim, status=target_status))
        result = VerificationResult(
            self._ids.verification_id(),
            run.id,
            passed,
            deterministic_passed,
            agent_passed,
            tuple(issues),
            self._clock.now(),
        )
        self._repository.save_verification(run.id, result)
        return result

    def _verify_claim(
        self,
        run: ResearchRun,
        claim: Claim,
        cutoff: datetime,
    ) -> tuple[VerificationIssue, ...]:
        issues: list[VerificationIssue] = []
        has_support = bool(claim.evidence_ids or claim.calculation_ids)
        if claim.materiality is not ClaimMateriality.LOW and not has_support:
            issues.append(
                VerificationIssue(
                    "citation_required",
                    "material claim has no evidence or calculation citation",
                    VerificationSeverity.HIGH,
                    claim.id,
                )
            )
        evidence = []
        for evidence_id in claim.evidence_ids:
            try:
                item = self._repository.get_evidence(run.id, evidence_id)
            except RepositoryNotFoundError:
                issues.append(
                    VerificationIssue(
                        "citation_missing",
                        f"claim cites missing evidence {evidence_id}",
                        VerificationSeverity.HIGH,
                        claim.id,
                    )
                )
                continue
            evidence.append(item)
            if item.available_at > cutoff:
                issues.append(
                    VerificationIssue(
                        "look_ahead_evidence",
                        f"evidence {evidence_id} was unavailable at the research cutoff",
                        VerificationSeverity.HIGH,
                        claim.id,
                    )
                )
        for calculation_id in claim.calculation_ids:
            try:
                self._repository.get_calculation(run.id, calculation_id)
            except RepositoryNotFoundError:
                issues.append(
                    VerificationIssue(
                        "citation_missing",
                        f"claim cites missing calculation {calculation_id}",
                        VerificationSeverity.HIGH,
                        claim.id,
                    )
                )
        if (
            claim.materiality is ClaimMateriality.HIGH
            and evidence
            and all(
                item.envelope.descriptor.discovery_only
                or item.envelope.descriptor.authority_class is AuthorityClass.DISCOVERY
                for item in evidence
            )
        ):
            issues.append(
                VerificationIssue(
                    "discovery_only_support",
                    "high-materiality claim is supported only by discovery evidence",
                    VerificationSeverity.HIGH,
                    claim.id,
                )
            )
        return tuple(issues)


def _knowledge_cutoff(run: ResearchRun, default: datetime) -> datetime:
    configured = dict(run.mandate.parameters).get("knowledge_cutoff_at")
    return datetime.fromisoformat(configured) if configured is not None else default
