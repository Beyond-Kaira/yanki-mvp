"""HTML extraction shared by crawl link discovery and page analysis."""

from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.site_audit.models import ParsedPage


def extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [
        urljoin(base_url, str(anchor["href"]))
        for anchor in soup.find_all("a", href=True)
    ]


def parse_page(html: str, current_url: str) -> ParsedPage:
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(" ", strip=True) if isinstance(title_tag, Tag) else ""

    meta_description_tag = soup.find("meta", attrs={"name": "description"})
    meta_description_value = (
        meta_description_tag.get("content")
        if isinstance(meta_description_tag, Tag)
        else None
    )
    meta_description = (
        str(meta_description_value).strip() if meta_description_value else None
    )

    html_tag = soup.find("html")
    html_lang_value = html_tag.get("lang") if isinstance(html_tag, Tag) else None
    html_lang = str(html_lang_value).strip() if html_lang_value else None

    images_missing_alt = sum(
        1 for image in soup.find_all("img") if not str(image.get("alt") or "").strip()
    )
    empty_anchors = sum(
        1
        for anchor in soup.find_all("a", href=True)
        if not anchor.get_text(" ", strip=True) and anchor.find("img") is None
    )

    hreflangs: list[dict[str, str | None]] = []
    for link in soup.find_all("link", rel="alternate"):
        hreflang = link.get("hreflang")
        if hreflang:
            href = link.get("href")
            hreflangs.append(
                {
                    "lang": str(hreflang).strip().lower(),
                    "href": urljoin(current_url, str(href)) if href else None,
                }
            )

    raw_schemas: list[str] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw_schema = script.get_text(strip=True)
        if raw_schema:
            raw_schemas.append(raw_schema)

    return ParsedPage(
        title=title,
        h1_count=len(soup.find_all("h1")),
        meta_description=meta_description,
        html_lang=html_lang,
        images_missing_alt=images_missing_alt,
        empty_anchors=empty_anchors,
        hreflangs=hreflangs,
        raw_schemas=raw_schemas,
    )
