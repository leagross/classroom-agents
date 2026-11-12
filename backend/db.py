"""Optional Postgres persistence for lessons and their messages.

Render's free web service disk is ephemeral (wiped on every deploy/restart),
so true persistence needs an actual database, not a local SQLite file. This
module is a thin wrapper around Render's free Postgres add-on, wired in via
the DATABASE_URL environment variable.

If DATABASE_URL isn't set (e.g. running locally without a Postgres instance),
everything here becomes a no-op and the app falls back to pure in-memory
sessions, exactly as before.
"""

import json
import os

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    # Pin the driver explicitly: SQLAlchemy may otherwise prefer psycopg (v3),
    # which isn't installed — only psycopg2-binary is in requirements.txt.
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

_engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS lessons (
        id TEXT PRIMARY KEY,
        topic TEXT NOT NULL,
        pool_keys TEXT NOT NULL,
        round_count INTEGER NOT NULL DEFAULT 0,
        pool_turn_index INTEGER NOT NULL DEFAULT 0,
        next_jester_round INTEGER NOT NULL,
        user_email TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # Older deployments created the table before these columns existed.
    "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS user_email TEXT",
    "CREATE INDEX IF NOT EXISTS idx_lessons_user_email ON lessons(user_email)",
    "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS plan TEXT",
    "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS activity_index INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS autonomous_turns_used INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS awaiting_user BOOLEAN NOT NULL DEFAULT true",
    """
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
        agent_key TEXT NOT NULL,
        display_name TEXT NOT NULL,
        color TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_messages_lesson_id ON messages(lesson_id)",
    """
    CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        name TEXT,
        picture TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_login_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        user_email TEXT PRIMARY KEY,
        stripe_customer_id TEXT,
        stripe_subscription_id TEXT,
        plan TEXT NOT NULL DEFAULT 'free',
        status TEXT NOT NULL DEFAULT 'none',
        current_period_end TIMESTAMPTZ,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]


def is_enabled() -> bool:
    return _engine is not None


def init_db():
    if not _engine:
        return
    with _engine.begin() as conn:
        for stmt in _SCHEMA_STATEMENTS:
            conn.execute(text(stmt))


def insert_lesson(
    lesson_id: str,
    topic: str,
    pool_keys: str,
    next_jester_round: int,
    user_email: str | None = None,
    plan: dict | None = None,
    awaiting_user: bool = True,
):
    if not _engine:
        return
    with _engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO lessons (id, topic, pool_keys, next_jester_round, user_email, plan, awaiting_user) "
                "VALUES (:id, :topic, :pool_keys, :njr, :user_email, :plan, :awaiting_user)"
            ),
            {
                "id": lesson_id, "topic": topic, "pool_keys": pool_keys,
                "njr": next_jester_round, "user_email": user_email,
                "plan": json.dumps(plan) if plan else None,
                "awaiting_user": awaiting_user,
            },
        )


def update_lesson_state(lesson_id: str, round_count: int, pool_turn_index: int, next_jester_round: int):
    if not _engine:
        return
    with _engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE lessons SET round_count = :rc, pool_turn_index = :pti, "
                "next_jester_round = :njr WHERE id = :id"
            ),
            {"rc": round_count, "pti": pool_turn_index, "njr": next_jester_round, "id": lesson_id},
        )


def update_lesson_plan_state(lesson_id: str, activity_index: int, autonomous_turns_used: int, awaiting_user: bool):
    if not _engine:
        return
    with _engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE lessons SET activity_index = :ai, autonomous_turns_used = :atu, "
                "awaiting_user = :au WHERE id = :id"
            ),
            {"ai": activity_index, "atu": autonomous_turns_used, "au": awaiting_user, "id": lesson_id},
        )


def insert_message(lesson_id: str, agent_key: str, display_name: str, color: str, content: str):
    if not _engine:
        return
    with _engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO messages (lesson_id, agent_key, display_name, color, content) "
                "VALUES (:lesson_id, :agent_key, :display_name, :color, :content)"
            ),
            {
                "lesson_id": lesson_id,
                "agent_key": agent_key,
                "display_name": display_name,
                "color": color,
                "content": content,
            },
        )


def list_lessons_for_user(user_email: str, limit: int = 20):
    if not _engine:
        return []
    with _engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, topic, round_count, created_at
                FROM lessons
                WHERE user_email = :user_email
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"user_email": user_email, "limit": limit},
        ).mappings().all()
        return [dict(r) for r in rows]


def load_lesson(lesson_id: str):
    if not _engine:
        return None
    with _engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT topic, pool_keys, round_count, pool_turn_index, next_jester_round, "
                "plan, activity_index, autonomous_turns_used, awaiting_user "
                "FROM lessons WHERE id = :id"
            ),
            {"id": lesson_id},
        ).mappings().first()
        if not row:
            return None
        lesson = dict(row)
        lesson["plan"] = json.loads(lesson["plan"]) if lesson.get("plan") else None
        return lesson


def upsert_user(email: str, name: str | None, picture: str | None):
    """Record of who has signed in — identity only. Never stores the user's
    Anthropic API key (that stays browser-only, per the app's BYOK policy)."""
    if not _engine:
        return
    with _engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (email, name, picture)
                VALUES (:email, :name, :picture)
                ON CONFLICT (email) DO UPDATE SET
                    name = EXCLUDED.name,
                    picture = EXCLUDED.picture,
                    last_login_at = now()
                """
            ),
            {"email": email, "name": name, "picture": picture},
        )


def get_subscription(user_email: str):
    if not _engine:
        return None
    with _engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT plan, status, current_period_end, stripe_customer_id, stripe_subscription_id "
                "FROM subscriptions WHERE user_email = :email"
            ),
            {"email": user_email},
        ).mappings().first()
        return dict(row) if row else None


def upsert_subscription(
    user_email: str,
    plan: str,
    status: str,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    current_period_end=None,
):
    if not _engine:
        return
    with _engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO subscriptions
                    (user_email, plan, status, stripe_customer_id, stripe_subscription_id, current_period_end)
                VALUES
                    (:email, :plan, :status, :customer_id, :subscription_id, :period_end)
                ON CONFLICT (user_email) DO UPDATE SET
                    plan = EXCLUDED.plan,
                    status = EXCLUDED.status,
                    stripe_customer_id = COALESCE(EXCLUDED.stripe_customer_id, subscriptions.stripe_customer_id),
                    stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                    current_period_end = EXCLUDED.current_period_end,
                    updated_at = now()
                """
            ),
            {
                "email": user_email,
                "plan": plan,
                "status": status,
                "customer_id": stripe_customer_id,
                "subscription_id": stripe_subscription_id,
                "period_end": current_period_end,
            },
        )


def count_lessons_this_month(user_email: str) -> int:
    if not _engine:
        return 0
    with _engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT COUNT(*) AS n FROM lessons
                WHERE user_email = :email
                  AND created_at >= date_trunc('month', now())
                """
            ),
            {"email": user_email},
        ).mappings().first()
        return row["n"] if row else 0


def load_messages(lesson_id: str):
    if not _engine:
        return []
    with _engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT agent_key, display_name, color, content FROM messages "
                "WHERE lesson_id = :id ORDER BY id ASC"
            ),
            {"id": lesson_id},
        ).mappings().all()
        return [dict(r) for r in rows]
