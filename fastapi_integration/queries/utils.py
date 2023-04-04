def has_endpoint(obj, endpoint):
    """
    Check if an object has an endpoint attribute.
    """
    return all(getattr(obj, attr_name, None) is not None for attr_name in endpoint.split('.'))