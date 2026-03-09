from database.models import PermissionEnum, User


def has_permission(user: User, resource: str, action: PermissionEnum) -> bool:
    if user.is_superuser:
        return True

    if not user.role:
        return False

    for rp in user.role.permissions:
        if (
            rp.permission.resource == resource and
            rp.permission.action == action
        ):
            return True

    return False
