from app.main import main


if __name__ == "__main__":
    print("Running TITAN pipeline...")

    main([
        "select",
        "--date", "2026-07-06",
        "--top-n", "5",
    ])

    main([
        "validate",
        "--selection-date", "2026-07-06",
        "--evaluation-date", "2026-07-10",
        "--holding-days", "4",
        "--success-return", "0.03",
        "--trade-time", "10:00",
        "--sell-time", "14:00",
        "--market-trend-filter",
    ])

    main([
        "export",
        "--format", "csv",
        "--package",
        "--output", "output/exports/validation_package",
    ])

    print("Pipeline completed.")
