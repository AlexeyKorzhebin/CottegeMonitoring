"""Authentication for REST and MCP."""

from cottage_monitoring.auth.context import ApiKeyContext
from cottage_monitoring.auth.deps import get_api_key_context, require_scope

__all__ = ["ApiKeyContext", "get_api_key_context", "require_scope"]
