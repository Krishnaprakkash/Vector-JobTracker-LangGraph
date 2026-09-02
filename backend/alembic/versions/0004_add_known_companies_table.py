"""create known_companies table + seed verified slugs

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SEED = [
    # (slug, ats_source, display_name)
    ("stripe", "greenhouse", "Stripe"),
    ("airbnb", "greenhouse", "Airbnb"),
    ("coinbase", "greenhouse", "Coinbase"),
    ("robinhood", "greenhouse", "Robinhood"),
    ("instacart", "greenhouse", "Instacart"),
    ("asana", "greenhouse", "Asana"),
    ("databricks", "greenhouse", "Databricks"),
    ("gitlab", "greenhouse", "GitLab"),
    ("reddit", "greenhouse", "Reddit"),
    ("roblox", "greenhouse", "Roblox"),
    ("affirm", "greenhouse", "Affirm"),
    ("lyft", "greenhouse", "Lyft"),
    ("pinterest", "greenhouse", "Pinterest"),
    ("twilio", "greenhouse", "Twilio"),
    ("squarespace", "greenhouse", "Squarespace"),
    ("peloton", "greenhouse", "Peloton"),
    ("chime", "greenhouse", "Chime"),
    ("brex", "greenhouse", "Brex"),
    ("gusto", "greenhouse", "Gusto"),
    ("flexport", "greenhouse", "Flexport"),
    ("figma", "greenhouse", "Figma"),
    ("discord", "greenhouse", "Discord"),
    ("webflow", "greenhouse", "Webflow"),
    ("duolingo", "greenhouse", "Duolingo"),
    ("spotify", "lever", "Spotify"),
    ("palantir", "lever", "Palantir"),
    ("openai", "ashby", "OpenAI"),
    ("linear", "ashby", "Linear"),
    ("notion", "ashby", "Notion"),
    ("ramp", "ashby", "Ramp"),
    ("supabase", "ashby", "Supabase"),
    ("posthog", "ashby", "PostHog"),
    ("replit", "ashby", "Replit"),
    ("cohere", "ashby", "Cohere"),
    ("zapier", "ashby", "Zapier"),
    ("render", "ashby", "Render"),
    ("docker", "ashby", "Docker"),
    ("benchling", "ashby", "Benchling"),
    ("workos", "ashby", "WorkOS"),
    ("confluent", "ashby", "Confluent"),
    ("airwallex", "ashby", "Airwallex"),
    ("crusoe", "ashby", "Crusoe"),
]


def upgrade():
    op.create_table(
        "known_companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_slug", sa.String(), nullable=False),
        sa.Column("ats_source", sa.String(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=True),
        sa.UniqueConstraint("company_slug", "ats_source", name="uq_known_company"),
    )

    known_companies = sa.table(
        "known_companies",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("company_slug", sa.String),
        sa.column("ats_source", sa.String),
        sa.column("company_name", sa.String),
    )
    op.bulk_insert(known_companies, [
        {"id": uuid.uuid4(), "company_slug": slug, "ats_source": ats, "company_name": name}
        for slug, ats, name in SEED
    ])


def downgrade():
    op.drop_table("known_companies")