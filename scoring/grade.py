"""
Grade Policy
"""


def calculate_grade(
    score: int
) -> str:


    if score >= 90:
        return "S"

    elif score >= 70:
        return "A"

    elif score >= 50:
        return "B"

    elif score >= 30:
        return "C"

    else:
        return "D"