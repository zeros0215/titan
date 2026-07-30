from report.report_generator import ReportGenerator
from validation.validation_result import ValidationResult


class ConsoleReporter:
    """Outputs a precomputed validation report to the console."""

    def __init__(self, generator: ReportGenerator | None = None) -> None:
        self.generator = generator or ReportGenerator()

    def report(self, validation: ValidationResult) -> None:
        print(self.generator.generate_markdown(validation), end="")
