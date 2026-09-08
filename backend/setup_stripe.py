"""Set up Stripe products/prices for ArenaHub SaaS plans (idempotent)."""
import os
import sys
import stripe
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"

CATALOG = [
    {
        "emergent_product_id": "arenahub_starter",
        "name": "ArenaHub Starter — Gestão de Torneios",
        "tax_code": "txcd_10103001",  # SaaS
        "prices": [
            {"lookup_key": "starter_monthly", "amount": 4900, "currency": "brl", "interval": "month"},
            {"lookup_key": "starter_yearly", "amount": 49000, "currency": "brl", "interval": "year"},
        ],
    },
]

def get_or_create_product(entry):
    for p in stripe.Product.list(active=True).auto_paging_iter():
        if p.to_dict().get("metadata", {}).get("emergent_product_id") == entry["emergent_product_id"]:
            return p
    return stripe.Product.create(
        name=entry["name"], tax_code=entry.get("tax_code"),
        metadata={"managed_by": "emergent", "emergent_product_id": entry["emergent_product_id"]},
    )

def ensure_price(product, p):
    existing = stripe.Price.list(lookup_keys=[p["lookup_key"]], active=True, limit=1).data
    if existing and (existing[0].unit_amount != p["amount"] or existing[0].currency != p["currency"]):
        stripe.Price.modify(existing[0].id, active=False)
        existing = []
    if not existing:
        kwargs = dict(
            product=product.id, unit_amount=p["amount"], currency=p["currency"],
            lookup_key=p["lookup_key"], transfer_lookup_key=True,
        )
        if p.get("interval"):
            kwargs["recurring"] = {"interval": p["interval"]}
        price = stripe.Price.create(**kwargs)
        print(f"  Created price {p['lookup_key']}: {price.id}")
    else:
        print(f"  Existing price {p['lookup_key']}: {existing[0].id}")

def main():
    for entry in CATALOG:
        product = get_or_create_product(entry)
        print(f"Product: {product.name} ({product.id})")
        for p in entry["prices"]:
            ensure_price(product, p)
    print("\nDone.")

if __name__ == "__main__":
    main()
