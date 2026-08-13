def normalize_python_code(code: str) -> str:
    """Keep formatting stable for generated snippets in Day-1."""
    return code.strip() + "\n"
