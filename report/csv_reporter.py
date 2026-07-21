from report.reporter import Reporter


class CsvReporter(Reporter):

    def report(
        self,
        ranking
    ) -> None:

        ...