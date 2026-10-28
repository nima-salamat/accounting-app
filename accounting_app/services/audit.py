"""Central helper for append-only business audit events."""
import json

from accounting_app.database.models import AuditEvent


def record_audit(user, action, resource, target_id=None, details=None, remote_addr=None):
    """Record actor, action, resource, target and bounded details inside the caller's transaction."""
    actor = getattr(user, "username", None) or "system"
    user_id = getattr(user, "id", None)
    safe_details = details if isinstance(details, dict) else {}
    encoded = json.dumps(safe_details, ensure_ascii=False, sort_keys=True, default=str)
    if len(encoded) > 8000:
        encoded = json.dumps({"truncated": True, "preview": encoded[:7900]}, ensure_ascii=False)
    return AuditEvent.create(
        user=user_id,
        actor_name=str(actor)[:256],
        action=str(action)[:48],
        resource=str(resource)[:64],
        target_id=str(target_id)[:64] if target_id is not None else None,
        details=encoded,
        remote_addr=str(remote_addr)[:128] if remote_addr else None,
    )
