"""Shared Anthropic client helpers (used by the books/Neufert assistant)."""
import os

_model_cache = None


def get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=api_key)
    except Exception:
        return None


def pick_model(client):
    """Prefer a vision-capable, recent model. ANTHROPIC_MODEL overrides."""
    global _model_cache
    if _model_cache:
        return _model_cache
    pref = os.environ.get("ANTHROPIC_MODEL", "")
    if pref:
        _model_cache = pref
        return pref
    try:
        ids = [m.id for m in client.models.list().data]
        for want in ["claude-opus-4", "claude-sonnet-4", "claude-3-7-sonnet",
                     "claude-3-5-sonnet", "claude-3-5-haiku", "claude-3-haiku"]:
            for mid in ids:
                if want in mid:
                    _model_cache = mid
                    return mid
        if ids:
            _model_cache = ids[0]
            return ids[0]
    except Exception:
        pass
    _model_cache = "claude-3-5-sonnet-20241022"
    return _model_cache
