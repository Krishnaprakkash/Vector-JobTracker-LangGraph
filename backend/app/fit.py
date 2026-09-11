def fit_label(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 60:
        return "Reasonable"
    if score >= 30:
        return "Moderate"
    return "Aspirational"