from __future__ import annotations

import httpx
import pytest
import respx

from app.pipeline.discovery import MAX_CHARS, MAX_PAGE_BYTES, discover
from app.pipeline.errors import PipelineError

HOME = "https://example.com"


@respx.mock
def test_reachable_site_returns_non_empty_text():
    respx.get(HOME).mock(
        return_value=httpx.Response(
            200, html="<html><body><h1>Acme</h1><p>We build robots.</p></body></html>"
        )
    )
    text = discover(HOME)
    assert "Acme" in text
    assert "robots" in text


@respx.mock
def test_script_and_nav_are_stripped():
    html = (
        "<html><body>"
        "<nav>Home About Contact</nav>"
        "<script>var x = 1;</script>"
        "<p>Real content here.</p>"
        "</body></html>"
    )
    respx.get(HOME).mock(return_value=httpx.Response(200, html=html))
    text = discover(HOME)
    assert "Real content here." in text
    assert "var x" not in text
    assert "Contact" not in text


@respx.mock
def test_unreachable_site_raises_pipeline_error():
    respx.get(HOME).mock(return_value=httpx.Response(404))
    with pytest.raises(PipelineError):
        discover(HOME)


@respx.mock
def test_connection_error_raises_pipeline_error():
    respx.get(HOME).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(PipelineError):
        discover(HOME)


@respx.mock
def test_follows_same_domain_links():
    home = "https://example.com/"  # explicit root path so it only matches "/"
    home_html = (
        '<html><body><p>Home page.</p>'
        '<a href="/about">About</a>'
        '<a href="https://other.com/x">External</a>'
        "</body></html>"
    )
    respx.get(home).mock(return_value=httpx.Response(200, html=home_html))
    about = respx.get("https://example.com/about").mock(
        return_value=httpx.Response(200, html="<p>About us content.</p>")
    )
    external = respx.get("https://other.com/x").mock(
        return_value=httpx.Response(200, html="<p>should not fetch</p>")
    )
    text = discover(home)
    assert "Home page." in text
    assert "About us content." in text
    assert about.called
    assert not external.called  # only same-domain links are followed


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata (link-local)
        "http://[::1]:5432/",
    ],
)
def test_ssrf_private_and_metadata_hosts_are_blocked(url):
    # The guard raises before any request is sent, so no respx mock is needed.
    with pytest.raises(PipelineError):
        discover(url)


@respx.mock
def test_caps_text_length():
    big = "word " * 10_000  # ~50k chars
    respx.get(HOME).mock(
        return_value=httpx.Response(200, html=f"<html><body><p>{big}</p></body></html>")
    )
    text = discover(HOME)
    assert len(text) == MAX_CHARS


@respx.mock
def test_harvests_page_metadata():
    html = (
        "<html><head>"
        "<title>Beyond Technologies</title>"
        '<meta name="description" content="Defense systems and drones.">'
        '<meta property="og:description" content="FPV kamikaze drones and UGVs.">'
        "</head><body><p>Home.</p></body></html>"
    )
    respx.get(HOME).mock(return_value=httpx.Response(200, html=html))
    text = discover(HOME)
    assert "Beyond Technologies" in text
    assert "Defense systems and drones." in text
    assert "FPV kamikaze drones and UGVs." in text


# A thin SPA homepage: one visible word, one script bundle carrying the content.
_SPA_HOME = (
    "<html><head><title>Beyond Technologies</title></head><body>"
    "<div id='root'>Beyond Technologies</div>"
    '<script type="module" src="/assets/index-DJ8r56aJ.js"></script>'
    "</body></html>"
)

# Bundle strings: two prose backtick literals (one English, one Turkish) plus
# junk that MUST be filtered (a URL, an asset path, minified code).
_SPA_BUNDLE = (
    "const a=`Beyond Technologies designs and manufactures the BAZNA FPV "
    "kamikaze drone and the Tayron UGV for modern defense operations.`;"
    "const b=`Beyond Teknoloji, savunma sanayii icin kamikaze insansiz hava "
    "araclari ve yer araclari uretmektedir ve Liftron sistemini sunar.`;"
    'const u="https://cdn.example.com/assets/index-DJ8r56aJ.js";'
    'const p="/assets/vendor-1a2b3c.css";'
    "function r(){return a+b;};var x=1,y=2,z=3;o={q:1,w:2,e:3,r:4,t:5};"
)


@respx.mock
def test_spa_fallback_extracts_bundle_prose():
    # Explicit root path so the home route only matches "/", not the bundle URL.
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, html=_SPA_HOME)
    )
    bundle = respx.get("https://example.com/assets/index-DJ8r56aJ.js").mock(
        return_value=httpx.Response(
            200, text=_SPA_BUNDLE, headers={"content-type": "application/javascript"}
        )
    )
    text = discover(HOME)

    # Product names and prose (both languages) survive extraction.
    assert "BAZNA" in text
    assert "Tayron UGV" in text
    assert "insansiz hava araclari" in text  # Turkish prose kept, not ASCII-filtered
    # Junk is filtered out.
    assert "cdn.example.com" not in text
    assert "/assets/vendor" not in text
    assert "function r()" not in text
    # The bundle fetch went through the shared (SSRF-guarded) client.
    assert bundle.called


@respx.mock
def test_localized_bundle_content_survives_truncation():
    # A bundle whose framework runtime (ASCII English prose) is emitted *before*
    # the site's own Turkish content, larger than MAX_CHARS combined. The
    # localized content must still land in the capped output.
    noise = "".join(
        f"const n{i}=`This React router framework noise string number {i} is "
        f"plain English and appears early in the bundle source order here.`;"
        for i in range(400)
    )
    turkish = (
        "const c=`Beyond Teknoloji savunma sanayii icin BAZNA kamikaze "
        "insansiz hava araci ve otonom sistemler gelistirir sirketimiz.`;"
    ).replace("icin", "için").replace("gelistirir", "geliştirir")
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, html=_SPA_HOME)
    )
    respx.get("https://example.com/assets/index-DJ8r56aJ.js").mock(
        return_value=httpx.Response(200, text=noise + turkish)
    )
    text = discover(HOME)
    assert len(text) == MAX_CHARS
    assert "BAZNA" in text  # localized content prioritised over framework noise


@respx.mock
def test_non_spa_does_not_fetch_bundles():
    # Plenty of server-rendered text -> the SPA fallback must not trigger.
    body = "<p>" + ("This company builds industrial robots. " * 40) + "</p>"
    html = (
        "<html><body>" + body + '<script src="/assets/app.js"></script></body></html>'
    )
    respx.get(HOME).mock(return_value=httpx.Response(200, html=html))
    bundle = respx.get("https://example.com/assets/app.js").mock(
        return_value=httpx.Response(200, text="ignored")
    )
    text = discover(HOME)
    assert "industrial robots" in text
    assert not bundle.called


# A page whose visible copy is pure marketing prose, but whose JSON-LD states
# the facts plainly — the shape SEO tooling emits on most commercial sites.
_JSONLD_HOME = """<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Organization",
 "name": "Globex Robotics",
 "legalName": "Globex Robotics A.S.",
 "description": "We build autonomous warehouse robots.",
 "brand": {"@type": "Brand", "name": "PalletMover"},
 "sameAs": ["https://www.linkedin.com/company/globex"],
 "address": {"@type": "PostalAddress", "addressLocality": "Berlin",
             "addressCountry": "DE"}}
</script>
</head><body><p>Imagine a world that just works. We dare to dream.</p></body></html>"""


@respx.mock
def test_jsonld_facts_are_extracted():
    respx.get(HOME).mock(return_value=httpx.Response(200, html=_JSONLD_HOME))
    text = discover(HOME)
    assert "Globex Robotics" in text
    assert "Globex Robotics A.S." in text  # legalName, an alias-worthy form
    assert "We build autonomous warehouse robots." in text
    assert "PalletMover" in text  # nested brand node
    assert "linkedin.com/company/globex" in text  # sameAs, as text (never fetched)
    assert "Berlin" in text  # nested address feeds `locations`
    # The visible copy is still harvested; JSON-LD is a second read, not a swap.
    assert "We dare to dream." in text


@respx.mock
def test_jsonld_survives_truncation():
    # JSON-LD leads the combined text, so it is still there after the cut even
    # when the page carries far more visible copy than MAX_CHARS.
    big = "word " * 10_000  # ~50k chars
    html = _JSONLD_HOME.replace("We dare to dream.", big)
    respx.get(HOME).mock(return_value=httpx.Response(200, html=html))
    text = discover(HOME)
    assert len(text) == MAX_CHARS
    assert "Globex Robotics" in text


@respx.mock
def test_jsonld_handles_graph_arrays_and_malformed_blocks():
    html = (
        "<html><head>"
        # Malformed block first: it must not cost us the good one after it.
        '<script type="application/ld+json">{"name": broken,,}</script>'
        '<script type="application/ld+json">'
        '{"@graph": [{"@type": "WebSite", "name": "globex.com"},'
        ' {"@type": "Organization", "name": "Globex Robotics",'
        '  "description": "Warehouse automation."}]}'
        "</script>"
        # A top-level array is equally legal schema.org.
        '<script type="application/ld+json">'
        '[{"@type": "Product", "name": "ArmBot"}]'
        "</script>"
        "</head><body><p>Home.</p></body></html>"
    )
    respx.get(HOME).mock(return_value=httpx.Response(200, html=html))
    text = discover(HOME)
    assert "Globex Robotics" in text
    assert "Warehouse automation." in text
    assert "ArmBot" in text


@respx.mock
def test_page_without_jsonld_is_unchanged():
    # Existing fixtures carry no JSON-LD: the extra pass must be a no-op, not a
    # stray separator or empty segment.
    html = "<html><body><p>Real content here.</p></body></html>"
    respx.get(HOME).mock(return_value=httpx.Response(200, html=html))
    assert discover(HOME) == "Real content here."


@respx.mock
def test_non_html_link_is_skipped():
    # A linked PDF's bytes must never reach BeautifulSoup/_clean_text, where the
    # resulting mojibake would eat the MAX_CHARS budget real page copy needed.
    home = "https://example.com/"
    home_html = (
        "<html><body><p>Home page.</p>"
        '<a href="/brochure.pdf">Brochure</a>'
        '<a href="/about">About</a>'
        "</body></html>"
    )
    respx.get(home).mock(return_value=httpx.Response(200, html=home_html))
    pdf = respx.get("https://example.com/brochure.pdf").mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF-1.4 \xff\xfe binary garbage endobj",
            headers={"content-type": "application/pdf"},
        )
    )
    respx.get("https://example.com/about").mock(
        return_value=httpx.Response(200, html="<p>About us content.</p>")
    )
    text = discover(home)
    assert "About us content." in text
    assert pdf.called  # we only learn the type by asking...
    assert "PDF-1.4" not in text  # ...but its bytes are dropped, not parsed
    assert "endobj" not in text


@respx.mock
def test_link_without_content_type_is_still_parsed():
    # Fail open on a missing/empty Content-Type, matching net_guard's stance and
    # keeping header-less fixtures working.
    home = "https://example.com/"
    home_html = '<html><body><p>Home.</p><a href="/about">About</a></body></html>'
    respx.get(home).mock(return_value=httpx.Response(200, html=home_html))
    respx.get("https://example.com/about").mock(
        return_value=httpx.Response(
            200, content=b"<p>About us content.</p>", headers={"content-type": ""}
        )
    )
    assert "About us content." in discover(home)


@respx.mock
def test_oversized_page_is_skipped():
    home = "https://example.com/"
    home_html = '<html><body><p>Home.</p><a href="/huge">Huge</a></body></html>'
    respx.get(home).mock(return_value=httpx.Response(200, html=home_html))
    respx.get("https://example.com/huge").mock(
        return_value=httpx.Response(
            200,
            html="<p>Enormous page.</p>",
            headers={"content-length": str(MAX_PAGE_BYTES + 1)},
        )
    )
    assert "Enormous page." not in discover(home)


@respx.mock
def test_non_html_homepage_raises_pipeline_error():
    respx.get(HOME).mock(
        return_value=httpx.Response(
            200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"}
        )
    )
    with pytest.raises(PipelineError):
        discover(HOME)


@respx.mock
def test_prefers_content_ful_turkish_links():
    home = "https://example.com/"
    home_html = (
        "<html><body><p>Home.</p>"
        '<a href="/login">Login</a>'
        '<a href="/urunler">Ürünler</a>'
        '<a href="/contact">Contact</a>'
        "</body></html>"
    )
    respx.get(home).mock(return_value=httpx.Response(200, html=home_html))
    urunler = respx.get("https://example.com/urunler").mock(
        return_value=httpx.Response(200, html="<p>Product catalogue.</p>")
    )
    respx.get("https://example.com/login").mock(
        return_value=httpx.Response(200, html="<p>Login form.</p>")
    )
    respx.get("https://example.com/contact").mock(
        return_value=httpx.Response(200, html="<p>Contact page.</p>")
    )
    text = discover(home)
    assert "Product catalogue." in text
    assert urunler.called  # the content-ful Turkish path was crawled
