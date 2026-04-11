"""OAuth2 client credentials auth for UiPath Automation Cloud.

Implemented in Plan 11-02 per CONTEXT.md D-08..D-11.
Will expose ``UipathAuth(client_id, client_secret, tenant_name, organization, scope)``
plus ``async get_token(http)`` and ``async auth_headers(http)``.
"""
from __future__ import annotations
