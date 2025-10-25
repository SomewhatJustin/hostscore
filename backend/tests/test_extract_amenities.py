from bs4 import BeautifulSoup

from backend.api.extract import _extract_amenities


def test_extract_amenities_from_modal_markup():
    html = """
        <div role="dialog">
            <section>
                <h1>What this place offers</h1>
                <section>
                    <h2>Bathroom</h2>
                    <ul role="list">
                        <li><div><div id="bathroom-item" class="label">Hair dryer</div></div></li>
                        <li><div><div id="bathroom-item-2" class="label">Shampoo</div></div></li>
                    </ul>
                </section>
                <section>
                    <h2>Services</h2>
                    <ul role="list">
                        <li><div><div>Self check-in</div></div></li>
                        <li><div><div>Lockbox</div></div></li>
                    </ul>
                </section>
            </section>
        </div>
    """

    soup = BeautifulSoup("<main></main>", "html.parser")
    dialog = BeautifulSoup(html, "html.parser")

    amenities = _extract_amenities(soup, dialog)

    assert amenities == ["Hair dryer", "Shampoo", "Self check-in", "Lockbox"]
