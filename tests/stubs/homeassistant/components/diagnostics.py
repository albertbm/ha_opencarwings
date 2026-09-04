def async_redact_data(data, to_redact):
    """Minimal async_redact_data stub."""
    if not isinstance(data, dict):
        return data
    out = {}
    for k, v in data.items():
        if k in to_redact:
            out[k] = "**REDACTED**"
        elif isinstance(v, dict):
            out[k] = async_redact_data(v, to_redact)
        elif isinstance(v, list):
            out[k] = [async_redact_data(i, to_redact) for i in v]
        else:
            out[k] = v
    return out
