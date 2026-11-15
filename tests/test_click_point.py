"""click_at: a customer clicks a point on the screenshot, for things with no text (swatches, icon buttons)."""
import pytest

from b2a import session

PAGE = """<html><body style="margin:0">
<div id="state">none</div>
<button id="cart" aria-label="Add to cart" style="position:absolute;left:100px;top:100px;width:40px;height:40px"
        onclick="document.getElementById('state').textContent='cart'">&#128722;</button>
<div id="red" title="Red" role="radio" style="position:absolute;left:640px;top:400px;width:40px;height:40px;background:red"
     onclick="document.getElementById('state').textContent='red'"></div>
</body></html>"""


@pytest.fixture(scope="module")
def page():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # no browser installed here
            pytest.skip(f"chromium unavailable: {e}")
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page()
        yield ctx, pg
        b.close()


def _norm(px, py):  # pixel centre of an element -> 0-1000 over the 1280x800 screenshot
    return round(px * 1000 / 1280), round(py * 1000 / 800)


def test_click_icon_button(page):
    ctx, pg = page
    pg.set_content(PAGE)
    pg2, label = session.click_point(ctx, pg, *_norm(120, 120))
    assert pg2.inner_text("#state") == "cart"
    assert label == "🛒" or "cart" in label.lower()


def test_click_swatch_by_title(page):
    ctx, pg = page
    pg.set_content(PAGE)
    pg2, label = session.click_point(ctx, pg, *_norm(660, 420))
    assert pg2.inner_text("#state") == "red"
    assert label == "Red"


def test_out_of_range_is_clamped(page):
    ctx, pg = page
    pg.set_content(PAGE)
    pg2, _ = session.click_point(ctx, pg, -50, 5000)  # bottom-left corner: nothing there, no crash
    assert pg2.inner_text("#state") == "none"
