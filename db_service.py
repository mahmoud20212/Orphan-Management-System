"""Backwards-compatible shim for database service.

Existing imports like rom db_service import DBService will continue to work.
New code should import directly from 
epositories.db_repository.
"""
from repositories.db_repository import DBService

__all__ = ["DBService"]
