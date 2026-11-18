"""Role-tag heuristics for Level 0 (spec 5.2). Tags are labels layered over directory-based components."""
from __future__ import annotations

NAME_ROLES = {
    "frontend": {"frontend", "front", "ui", "web", "client", "static", "templates", "public", "webapp"},
    "api": {"api", "routes", "routers", "views", "endpoints", "handlers", "controllers", "rest", "graphql"},
    "backend": {"backend", "server", "app", "core", "services", "service", "engine"},
    "auth": {"auth", "authentication", "login", "security", "oauth", "permissions", "accounts"},
    "db": {"db", "database", "models", "migrations", "orm", "repositories", "repository", "schemas", "alembic", "storage"},
    "infra": {"infra", "infrastructure", "deploy", "deployment", "terraform", "docker", "k8s", "kubernetes", "helm", "ci", ".github", "ops"},
    "tests": {"tests", "test", "testing"},
    "docs": {"docs", "doc", "documentation"},
    "cli": {"cli", "scripts", "bin", "commands"},
    "shared": {"utils", "util", "common", "shared", "helpers", "lib", "libs"},
}
DEP_ROLES = {
    "api": {"fastapi", "flask", "django", "starlette", "aiohttp", "tornado", "sanic", "rest_framework", "graphene", "strawberry"},
    "db": {"sqlalchemy", "psycopg2", "psycopg", "pymongo", "redis", "peewee", "asyncpg", "mysql", "sqlite3", "alembic", "tortoise", "motor"},
    "auth": {"jwt", "jose", "passlib", "authlib", "oauthlib", "bcrypt"},
    "cli": {"click", "typer", "argparse", "fire"},
    "frontend": {"streamlit", "dash", "jinja2", "gradio"},
}
INFRA_CONTEXT = ("dockerfile", "docker-compose", ".tf", ".tfvars", "k8s", "helm")


def detect_roles(dir_name: str, external_imports: set[str], file_paths: list[str]) -> list[str]:
    roles: list[str] = []
    n = dir_name.lower().lstrip(".") if dir_name.startswith(".") and dir_name != ".github" else dir_name.lower()
    for role, names in NAME_ROLES.items():
        if n in names:
            roles.append(role)
    for role, deps in DEP_ROLES.items():
        if external_imports & deps and role not in roles:
            roles.append(role)
    low = [p.lower().rsplit("/", 1)[-1] for p in file_paths]
    if any(x.startswith(INFRA_CONTEXT) or x.endswith(INFRA_CONTEXT) for x in low) and "infra" not in roles:
        roles.append("infra")
    return roles[:3]
