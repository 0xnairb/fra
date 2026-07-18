from pathlib import Path

from fra.application.doctor_service import DoctorService


def test_doctor_checks_only_runtime_and_configuration_at_wp0() -> None:
    probed: list[Path | None] = []

    def probe(path: Path | None) -> str:
        probed.append(path)
        return "built-in defaults"

    report = DoctorService(
        configuration_probe=probe,
        python_version=lambda: (3, 12, 1),
    ).check(None)

    assert report.ok is True
    assert [check.name for check in report.checks] == ["Python runtime", "Configuration"]
    assert probed == [None]


def test_doctor_reports_an_unsupported_runtime_without_skipping_config() -> None:
    report = DoctorService(
        configuration_probe=lambda _: "built-in defaults",
        python_version=lambda: (3, 11, 9),
    ).check(None)

    assert report.ok is False
    assert report.checks[0].ok is False
    assert report.checks[1].ok is True
