"""foydalanuvchilar, lavozimlar, rollar, sessiyalar, 2FA

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-24
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE core.permissions (
      code varchar(64) PRIMARY KEY,
      description varchar(300) NOT NULL
    )
    """,
    """
    CREATE TABLE core.roles (
      id serial PRIMARY KEY,
      code varchar(64) NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]{1,63}$'),
      name varchar(200) NOT NULL,
      scope_all boolean NOT NULL,
      is_system boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE core.role_permissions (
      role_id integer NOT NULL REFERENCES core.roles(id) ON DELETE CASCADE,
      permission_code varchar(64) NOT NULL REFERENCES core.permissions(code) ON DELETE CASCADE,
      PRIMARY KEY (role_id, permission_code)
    )
    """,
    """
    CREATE TABLE core.positions (
      id serial PRIMARY KEY,
      code varchar(64) NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]{1,63}$'),
      name varchar(200) NOT NULL,
      role_id integer NOT NULL REFERENCES core.roles(id),
      is_active boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX positions_role_idx ON core.positions (role_id)",
    """
    CREATE TABLE core.position_branches (
      position_id integer NOT NULL REFERENCES core.positions(id) ON DELETE CASCADE,
      branch_id integer NOT NULL CHECK (branch_id > 0),
      PRIMARY KEY (position_id, branch_id)
    )
    """,
    """
    CREATE TABLE core.users (
      id bigserial PRIMARY KEY,
      username varchar(64) NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9._-]{3,64}$'),
      full_name varchar(200) NOT NULL,
      position_id integer NOT NULL REFERENCES core.positions(id),
      password_hash text NOT NULL,
      password_changed_at timestamptz NOT NULL DEFAULT now(),
      must_change_password boolean NOT NULL DEFAULT true,
      is_active boolean NOT NULL DEFAULT true,
      failed_logins integer NOT NULL DEFAULT 0,
      locked_until timestamptz,
      totp_secret_enc bytea,
      totp_enabled boolean NOT NULL DEFAULT false,
      totp_last_step bigint,
      last_login_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX users_position_idx ON core.users (position_id)",
    """
    CREATE TABLE core.password_history (
      id bigserial PRIMARY KEY,
      user_id bigint NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
      password_hash text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX password_history_user_idx ON core.password_history (user_id, created_at DESC)",
    """
    CREATE TABLE core.backup_codes (
      id bigserial PRIMARY KEY,
      user_id bigint NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
      code_hmac bytea NOT NULL,
      used_at timestamptz
    )
    """,
    "CREATE INDEX backup_codes_user_idx ON core.backup_codes (user_id) WHERE used_at IS NULL",
    """
    CREATE TABLE core.sessions (
      id uuid PRIMARY KEY,
      user_id bigint NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
      token_hmac bytea NOT NULL UNIQUE,
      created_at timestamptz NOT NULL,
      last_seen_at timestamptz NOT NULL,
      idle_expires_at timestamptz NOT NULL,
      absolute_expires_at timestamptz NOT NULL,
      revoked_at timestamptz,
      revoke_reason varchar(32),
      ip_enc bytea,
      ua_summary varchar(80) NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX sessions_user_active_idx ON core.sessions (user_id) WHERE revoked_at IS NULL",
    """
    CREATE TABLE core.mfa_challenges (
      token_hmac bytea PRIMARY KEY,
      user_id bigint NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
      kind varchar(8) NOT NULL CHECK (kind IN ('verify', 'enroll')),
      created_at timestamptz NOT NULL,
      expires_at timestamptz NOT NULL,
      attempts integer NOT NULL DEFAULT 0,
      used_at timestamptz,
      pending_secret_enc bytea
    )
    """,
    "CREATE INDEX mfa_challenges_expires_idx ON core.mfa_challenges (expires_at)",
    # ── Huquqlar: foydalanuvchilar o'chirilmaydi, faqat bloklanadi ──
    """
    GRANT SELECT, INSERT, UPDATE, DELETE ON core.permissions, core.roles,
      core.role_permissions, core.positions, core.position_branches TO ugk_app
    """,
    "GRANT SELECT, INSERT, UPDATE ON core.users TO ugk_app",
    "GRANT SELECT, INSERT, DELETE ON core.password_history TO ugk_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON core.backup_codes TO ugk_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON core.sessions, core.mfa_challenges TO ugk_app",
    """
    GRANT USAGE ON SEQUENCE core.roles_id_seq, core.positions_id_seq, core.users_id_seq,
      core.password_history_id_seq, core.backup_codes_id_seq TO ugk_app
    """,
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table in (
        "mfa_challenges", "sessions", "backup_codes", "password_history", "users",
        "position_branches", "positions", "role_permissions", "roles", "permissions",
    ):
        op.execute(f"DROP TABLE core.{table}")
