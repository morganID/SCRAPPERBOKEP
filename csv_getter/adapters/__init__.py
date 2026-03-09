"""Base classes for adapters."""


class BaseAdapter:
    DOMAINS = []
    CONTAINER_SELECTOR = ""
    TITLE_SELECTOR = ""
    LINK_SELECTOR = ""
    THUMBNAIL_SELECTOR = ""
    DURATION_SELECTOR = ""
    VIEWS_SELECTOR = ""


class AdapterRegistry:
    _adapters = {}

    @classmethod
    def register(cls, adapter_cls):
        for domain in getattr(adapter_cls, "DOMAINS", []):
            cls._adapters[domain] = adapter_cls
        return adapter_cls

    @classmethod
    def get(cls, domain):
        return cls._adapters.get(domain)