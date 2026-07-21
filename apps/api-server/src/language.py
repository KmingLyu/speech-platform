def output_script_for(language: str | None) -> str:
    """Map a requested Chinese locale to the transcript's output script."""
    normalized = (language or "").lower().replace("_", "-")
    if normalized in {"zh-tw", "zh-hant-tw"}:
        return "traditional"
    if normalized in {"zh-cn", "zh-hans-cn"}:
        return "simplified"
    return "original"
