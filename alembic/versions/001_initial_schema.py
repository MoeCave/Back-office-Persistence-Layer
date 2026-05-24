"""Initial schema creation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── fighter ────────────────────────────────────────────────────────────────
    op.create_table(
        "fighter",
        sa.Column("fighter_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("birth_date", sa.DateTime(), nullable=True),
        sa.Column("gender", sa.String(length=10), nullable=True),
        sa.Column("belt_level", sa.String(length=50), nullable=True),
        sa.Column("club_name", sa.String(length=150), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("fighter_id"),
    )

    # ── medical_record ─────────────────────────────────────────────────────────
    op.create_table(
        "medical_record",
        sa.Column("medical_record_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("blood_type", sa.String(length=10), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("doctor_name", sa.String(length=200), nullable=True),
        sa.Column("fighter_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["fighter_id"], ["fighter.fighter_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("medical_record_id"),
        sa.UniqueConstraint("fighter_id"),
    )

    # ── tournament ─────────────────────────────────────────────────────────────
    op.create_table(
        "tournament",
        sa.Column("tournament_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("start_date", sa.DateTime(), nullable=True),
        sa.Column("end_date", sa.DateTime(), nullable=True),
        sa.Column("max_fighters", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("tournament_id"),
    )

    # ── tatami ─────────────────────────────────────────────────────────────────
    op.create_table(
        "tatami",
        sa.Column("tatami_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("mat_number", sa.Integer(), nullable=True),
        sa.Column("area_size", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("tournament_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.tournament_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tatami_id"),
    )

    # ── category ───────────────────────────────────────────────────────────────
    op.create_table(
        "category",
        sa.Column("category_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("belt_level", sa.String(length=50), nullable=True),
        sa.Column("weight_min_kg", sa.Float(), nullable=True),
        sa.Column("weight_max_kg", sa.Float(), nullable=True),
        sa.Column("gender", sa.String(length=10), nullable=True),
        sa.PrimaryKeyConstraint("category_id"),
    )

    # ── fighter_category_registration ──────────────────────────────────────────
    op.create_table(
        "fighter_category_registration",
        sa.Column("fighter_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("tournament_id", sa.Integer(), nullable=False),
        sa.Column("weight_in_weight_kg", sa.Float(), nullable=True),
        sa.Column("registration_date", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("is_approved", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["category.category_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fighter_id"], ["fighter.fighter_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.tournament_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("fighter_id", "category_id", "tournament_id"),
    )

    # ── match ──────────────────────────────────────────────────────────────────
    op.create_table(
        "match",
        sa.Column("match_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheduled_time", sa.DateTime(), nullable=True),
        sa.Column("round_number", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("win_method", sa.String(length=100), nullable=True),
        sa.Column("tournament_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("blue_fighter_id", sa.Integer(), nullable=True),
        sa.Column("red_fighter_id", sa.Integer(), nullable=True),
        sa.Column("winner_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["blue_fighter_id"], ["fighter.fighter_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["category_id"], ["category.category_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["red_fighter_id"], ["fighter.fighter_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.tournament_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["winner_id"], ["fighter.fighter_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("match_id"),
    )


def downgrade() -> None:
    op.drop_table("match")
    op.drop_table("fighter_category_registration")
    op.drop_table("category")
    op.drop_table("tatami")
    op.drop_table("tournament")
    op.drop_table("medical_record")
    op.drop_table("fighter")
