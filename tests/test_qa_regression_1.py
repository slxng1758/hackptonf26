"""Regressions found by /qa on 2026-11-14 (report: .gstack/qa-reports/, local only).

ISSUE-001  Customers clicked a greyed-out configurator option (Apple's storage before color) over and over: 0 of 7 bought.
ISSUE-002  "Order placed before noon ships today" on a real site counted as a placed order.
ISSUE-003  The generated store's main "Add to cart" button led to an empty cart.
ISSUE-004  A description made only of punctuation crashed POST /api/sims with a 500.
ISSUE-005  A bad body to /evals or /social crashed with a 500 instead of a 422.
ISSUE-006  On a real site, adding to cart then saying "maybe later" scored below saying "maybe later" without the cart.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from b2a import outcome, product_page, session

CONFIGURATOR = """<fieldset><label><input type=radio name=color value=lavender> Lavender</label></fieldset>
<fieldset><label><input type=radio name=cap value=256 disabled> 256GB</label></fieldset>"""


# Regression: ISSUE-001 (greyed-out option explained to the customer). Found by /qa on 2026-11-14
def test_disabled_option_is_detected():
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content(CONFIGURATOR)
        assert session.is_disabled(pg, "256GB") is True
        assert session.is_disabled(pg, "Lavender") is False
        b.close()


# Regression: ISSUE-002 (order text only counts on our own store). Found by /qa on 2026-11-14
def test_order_confirmed_only_where_ordering_is_possible():
    real_site = "Order placed before noon ships today. Your order is confirmed within 24 hours."
    assert outcome.order_confirmed(real_site, can_order=False) is False
    assert outcome.order_confirmed("Thank you for your order!", can_order=True) is True


# Regression: ISSUE-003 (store add-to-cart button adds). Found by /qa on 2026-11-14
def test_store_add_to_cart_button_adds_the_item():
    html = product_page.render_index(product_page.Product(name="Mug", description="A plain mug for coffee.", price="$12"), "mug-1")
    assert "/api/products/mug-1/cart?add=1" in html


# Regression: ISSUE-004 (punctuation-only description gets a name). Found by /qa on 2026-11-14
def test_name_from_punctuation_only_description():
    import server
    assert server._name_from("##########") == "Your product"


# Regression: ISSUE-005 (bad bodies are a 422, not a 500). Found by /qa on 2026-11-14
@pytest.mark.parametrize("route,body", [("evals", {}), ("social", {"x": 1})])
def test_bad_eval_and_social_bodies_are_422(route, body):
    import server
    r = TestClient(server.app).post(f"/api/sims/nope/{route}", json=body)
    assert r.status_code == 422


# Regression: ISSUE-006 (cart then maybe is not worse than maybe). Found by /qa on 2026-11-14
def test_cart_then_maybe_scores_at_least_maybe():
    carted = outcome.decide({"decision": "maybe later"}, [{"cart": True}], can_order=False)
    plain = outcome.decide({"decision": "maybe later"}, [], can_order=False)
    assert outcome.SCORE[carted] >= outcome.SCORE[plain]


# Regression: ISSUE-014 (live server 404'd the demo listing when runs/amazon/pages existed but was empty). Found by /qa on 2026-11-15
def test_product_page_served_from_committed_demo_listing():
    import server
    c = TestClient(server.app)
    assert c.get("/api/product/B09LHS6RGF.html").status_code == 200
    assert c.get("/api/product/B09LHS6RGF-cart.html").status_code == 200
    assert c.get("/api/product/..%2Fserver.py").status_code == 404
    assert c.get("/api/product/nope.html").status_code == 404
