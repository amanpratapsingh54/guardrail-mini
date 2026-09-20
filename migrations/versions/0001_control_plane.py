"""Create tenant, project, policy, key, and model metadata tables.

Revision ID: 0001_control_plane
Revises:
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_control_plane"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = sa.Uuid(as_uuid=True)
    op.create_table(
        "tenants",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "projects",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("tenant_id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"], unique=False)
    op.create_table(
        "api_keys",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("project_id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_project_id", "api_keys", ["project_id"], unique=False)
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"], unique=False)
    op.create_table(
        "policy_metadata",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("policy_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("review_threshold", sa.Float(), nullable=True),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", name="uq_policy_metadata_policy_id"),
    )
    op.create_table(
        "policy_configurations",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("project_id", uuid_type, nullable=False),
        sa.Column("policy_id", sa.String(length=100), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("review_threshold", sa.Float(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["policy_metadata.policy_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "policy_id", name="uq_project_policy_configuration"),
    )
    op.create_index(
        "ix_policy_configurations_policy_id", "policy_configurations", ["policy_id"], unique=False
    )
    op.create_table(
        "model_versions",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("framework", sa.String(length=100), nullable=False),
        sa.Column("artifact_uri", sa.String(length=1000), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "version", name="uq_model_version"),
    )


def downgrade() -> None:
    op.drop_table("model_versions")
    op.drop_index("ix_policy_configurations_policy_id", table_name="policy_configurations")
    op.drop_table("policy_configurations")
    op.drop_table("policy_metadata")
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_project_id", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("ix_projects_tenant_id", table_name="projects")
    op.drop_table("projects")
    op.drop_table("tenants")
