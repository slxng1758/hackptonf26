"""Description mode: a product with no website still gets a page the customer agents can browse.

The owner (or the director's briefer) gives a name, description, price and what changed. We render a plain store page
with a details page and an "Add to cart" button, served by this API, so session.browse() works unchanged:

    POST /api/products   {name, description, price?, changes?, features?, image_url?}   -> {id, url}
    GET  /api/products/{id}/          the product page
    GET  /api/products/{id}/details   full description + what's new
    GET  /api/products/{id}/cart      "added to cart" (clicking the buy button is the purchase signal)

Only what the owner wrote goes on the page: no invented reviews, ratings, or claims.
"""
from __future__ import annotations

import html
import json
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
PRODUCTS = ROOT / "runs" / "products"
BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:4620")


class Product(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=5, max_length=8000)
    price: str = Field("", max_length=60, description="as the owner writes it, e.g. '$24' or '$4.50 a cup'")
    changes: str = Field("", max_length=2000, description="what's new vs the previous version")
    features: list[str] = Field(default_factory=list, max_length=12)
    image_url: str = Field("", max_length=500)
    business: str = Field("", max_length=120)


def from_brief(brief: dict) -> Product:
    """Accept the director's product brief ({name, summary, price, key_features, changes_vs_previous}) as well."""
    price = brief.get("price")
    return Product(name=brief.get("name") or "Product", description=brief.get("summary") or brief.get("description") or "",
                   price=f"${price:g}" if isinstance(price, (int, float)) else str(price or ""),
                   changes=brief.get("changes_vs_previous") or brief.get("changes") or "",
                   features=list(brief.get("key_features") or brief.get("features") or [])[:12])


def create(p: Product, base_url: str = BASE_URL) -> dict:
    pid = re.sub(r"[^a-z0-9]+", "-", p.name.lower()).strip("-")[:30] + "-" + uuid.uuid4().hex[:6]
    d = PRODUCTS / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "product.json").write_text(p.model_dump_json(indent=2))
    return {"id": pid, "url": f"{base_url}/api/products/{pid}/"}


def load(pid: str) -> Product:
    f = PRODUCTS / Path(pid).name / "product.json"
    if not f.exists():
        raise FileNotFoundError(pid)
    return Product(**json.loads(f.read_text()))


# ---------------------------------------------------------------- HTML

CSS = """*{box-sizing:border-box}body{margin:0;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1d1d1f;background:#fafafa}
header{background:#fff;border-bottom:1px solid #e5e5e5;padding:14px 32px;display:flex;justify-content:space-between;align-items:center}
header a{color:#1d1d1f;text-decoration:none;margin-left:20px;font-size:15px}.brand{font-weight:700;font-size:18px;margin:0}
main{max-width:980px;margin:32px auto;padding:0 24px}table{width:100%;border-collapse:collapse;background:#fff;margin:16px 0}th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #e5e5e5}.hero{display:grid;grid-template-columns:1fr 1fr;gap:40px;background:#fff;border-radius:16px;padding:32px}
.img{background:#f0f0f3;border-radius:12px;min-height:280px;display:flex;align-items:center;justify-content:center;color:#888;font-size:14px;overflow:hidden}
.img img{width:100%;height:100%;object-fit:cover}h1{font-size:30px;margin:0 0 8px}.price{font-size:24px;font-weight:600;margin:12px 0 20px}
.btn{display:inline-block;background:#0071e3;color:#fff;padding:14px 28px;border-radius:999px;text-decoration:none;font-size:16px;border:0}
.new{background:#fff7e0;border:1px solid #f0d58a;border-radius:10px;padding:12px 14px;margin:16px 0;font-size:15px}
section{background:#fff;border-radius:16px;padding:28px 32px;margin-top:24px}ul{padding-left:20px;line-height:1.7}p{line-height:1.6}
footer{color:#888;font-size:12px;text-align:center;padding:40px}"""


def _e(s: str) -> str:
    return html.escape(s or "")


def _paras(s: str) -> str:
    return "".join(f"<p>{_e(x.strip())}</p>" for x in re.split(r"\n\s*\n|\n", s or "") if x.strip())


def _page(p: Product, pid: str, body: str, title: str) -> str:
    base = f"/api/products/{pid}"
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{_e(title)}</title><style>{CSS}</style></head><body>"
            f"<header><p class='brand'>{_e(p.business or p.name)}</p><nav><a href='{base}/'>Shop</a><a href='{base}/details'>Details</a>"
            f"<a href='{base}/cart'>Cart</a></nav></header><main>{body}</main>"
            f"<footer>{_e(p.business or p.name)}</footer></body></html>")


def _summary(p: Product) -> str:
    first = re.split(r"(?<=[.!?])\s+", p.description.strip(), maxsplit=2)
    return " ".join(first[:2])


def render_index(p: Product, pid: str) -> str:
    img = f"<img src='{_e(p.image_url)}' alt='{_e(p.name)}'>" if p.image_url else _e(p.name)
    new = f"<div class='new'><b>New:</b> {_e(p.changes)}</div>" if p.changes else ""
    feats = "".join(f"<li>{_e(f)}</li>" for f in p.features)
    body = (f"<div class='hero'><div class='img'>{img}</div><div><h1>{_e(p.name)}</h1><p>{_e(_summary(p))}</p>{new}"
            + (f"<div class='price'>{_e(p.price)}</div>" if p.price else "<div class='price'></div>")
            + f"<a class='btn' href='/api/products/{pid}/cart?add=1'>Add to cart</a>"
            f"<p><a href='/api/products/{pid}/details'>See full details</a></p></div></div>"
            + (f"<section><h2>Features</h2><ul>{feats}</ul></section>" if feats else ""))
    return _page(p, pid, body, p.name)


def render_details(p: Product, pid: str) -> str:
    body = (f"<section><h1>{_e(p.name)}</h1>{_paras(p.description)}"
            + (f"<h2>What's new</h2>{_paras(p.changes)}" if p.changes else "")
            + (f"<h2>Price</h2><p>{_e(p.price)}</p>" if p.price else "")
            + f"<p><a class='btn' href='/api/products/{pid}/cart?add=1'>Add to cart</a></p></section>")
    return _page(p, pid, body, f"{p.name}: details")


def _line(p: Product) -> str:
    price = _e(p.price) if p.price else "see price on the details page"
    return (f"<table><tr><th>Item</th><th>Qty</th><th>Price</th></tr><tr><td>{_e(p.name)}</td><td>1</td><td>{price}</td></tr>"
            f"<tr><td colspan='2'><b>Total</b></td><td><b>{price}</b></td></tr></table>")


def render_cart(p: Product, pid: str, has_item: bool = True) -> str:
    """A working cart (the customer's choice is kept in a cookie), so simulated customers can finish a purchase instead of
    hitting a dead end that they then blame on the business."""
    base = f"/api/products/{pid}"
    if not has_item:
        body = f"<section><h1>Your cart is empty</h1><p><a class='btn' href='{base}/details'>See the product</a></p></section>"
    else:
        body = (f"<section><h1>Your cart</h1>{_line(p)}"
                f"<p><a class='btn' href='{base}/checkout'>Checkout</a> <a href='{base}/'>Continue shopping</a></p></section>")
    return _page(p, pid, body, "Cart")


def render_checkout(p: Product, pid: str) -> str:
    base = f"/api/products/{pid}"
    body = (f"<section><h1>Checkout</h1>{_line(p)}<p>This is a test store: placing the order takes no payment and no personal details.</p>"
            f"<p><a class='btn' href='{base}/order'>Place order</a> <a href='{base}/cart'>Back to cart</a></p></section>")
    return _page(p, pid, body, "Checkout")


def render_order(p: Product, pid: str) -> str:
    body = (f"<section><h1>Order placed</h1><p>Thank you! Your order for {_e(p.name)}{f' ({_e(p.price)})' if p.price else ''} is confirmed.</p>"
            f"<p><a href='/api/products/{pid}/'>Back to the shop</a></p></section>")
    return _page(p, pid, body, "Order placed")


# ---------------------------------------------------------------- API

router = APIRouter(prefix="/api/products")


@router.post("")
def create_product(p: Product):
    return create(p)


def _get(pid: str) -> Product:
    try:
        return load(pid)
    except FileNotFoundError:
        raise HTTPException(404, "no such product")


@router.get("/{pid}/", response_class=HTMLResponse)
def index(pid: str):
    return render_index(_get(pid), pid)


@router.get("/{pid}/details", response_class=HTMLResponse)
def details(pid: str):
    return render_details(_get(pid), pid)


@router.get("/{pid}/cart", response_class=HTMLResponse)
def cart(pid: str, request: Request, add: int = 0):
    p = _get(pid)
    has = bool(add) or request.cookies.get(f"cart_{pid}") == "1"
    r = HTMLResponse(render_cart(p, pid, has))
    if add:
        r.set_cookie(f"cart_{pid}", "1", path=f"/api/products/{pid}")
    return r


@router.get("/{pid}/checkout", response_class=HTMLResponse)
def checkout(pid: str):
    return render_checkout(_get(pid), pid)


@router.get("/{pid}/order", response_class=HTMLResponse)
def order(pid: str):
    return render_order(_get(pid), pid)
