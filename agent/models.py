DEFAULT_MODEL = "gemini-2.0-flash"


def select_model(phase: str) -> str:
    """
    Select Gemini model based on current task phase.
    Using gemini-2.0-flash for all phases — fast, capable, and free tier friendly.
    """
    return DEFAULT_MODEL
