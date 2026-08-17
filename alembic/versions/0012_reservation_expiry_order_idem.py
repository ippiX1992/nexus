"""Reservation 'expired' status + storefront order idempotency key (0012).

Two small, additive changes that support routing the storefront checkout
through the Inventory Engine:

* Widen the reservation status check to allow 'expired', so the expiry
  sweeper can distinguish an automatically-expired hold from a manual release.
* Add an optional idempotency key to storefront orders (unique per tenant,
  NULLs allowed) so a double-clicked / retried checkout creates one order and
  reserves stock once.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_inventory_reservation_status", "inventory_reservations", type_="check")
    op.create_check_constraint(
        "ck_inventory_reservation_status",
        "inventory_reservations",
        "status IN ('held','released','committed','expired')",
    )
    op.add_column("storefront_orders", sa.Column("idempotency_key", sa.String(200), nullable=True))
    op.create_index(
        "uq_storefront_order_idempotency_key",
        "storefront_orders",
        ["tenant_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_storefront_order_idempotency_key", table_name="storefront_orders")
    op.drop_column("storefront_orders", "idempotency_key")
    op.drop_constraint("ck_inventory_reservation_status", "inventory_reservations", type_="check")
    op.create_check_constraint(
        "ck_inventory_reservation_status",
        "inventory_reservations",
        "status IN ('held','released','committed')",
    )
