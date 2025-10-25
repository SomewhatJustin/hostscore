from bs4 import BeautifulSoup

from backend.api.extract import _extract_photos, extract_listing


def test_extract_photos_older_layout_labels():
    html = """
        <div>
            <button aria-label="Queen Bed">
                <div role="img">
                    <picture>
                        <source srcset="https://example.com/photo-lg.jpg?im_w=960 1x">
                        <img alt="Listing image 1" src="https://example.com/photo.jpg?im_w=720">
                    </picture>
                </div>
            </button>
            <button>
                <div role="img" aria-label="Exterior night" style="background-image: url('https://example.com/exterior.jpg?im_w=1024');"></div>
            </button>
        </div>
    """

    soup = BeautifulSoup(html, "html.parser")
    photos = _extract_photos(soup)

    assert [photo.url for photo in photos] == [
        "https://example.com/photo-lg.jpg?im_w=960",
        "https://example.com/exterior.jpg?im_w=1024",
    ]
    assert photos[0].alt == "Queen Bed"
    assert photos[1].alt == "Exterior night"


def test_extract_listing_flags_legacy_gallery():
    html = """
        <html>
            <body>
                <main>
                    <h1 data-testid="title">Sample listing</h1>
                    <div data-section-id="DESCRIPTION_DEFAULT">
                        <p>Simple description.</p>
                    </div>
                    <button aria-label="Listing image 1">
                        <img src="https://example.com/a.jpg?im_w=720" alt="Listing image 1" />
                    </button>
                </main>
            </body>
        </html>
    """

    listing = extract_listing(html, "https://example.test/listing")

    assert listing.uses_legacy_gallery is True
