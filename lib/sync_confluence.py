"""Confluence sync (Skill #1): page trees, whole spaces, images/attachments.

Extracted 1:1 from the original monolithic sync_agent.py."""
import json
import os
import re

from bs4 import BeautifulSoup

from .atlassian_api import strip_html_to_text


def get_children(api, page_id):
    results, start = [], 0
    while True:
        d = api.get(f"/rest/api/content/{page_id}/child/page",
                    params={"limit": 100, "start": start})
        results.extend(d["results"])
        if start + len(d["results"]) >= d.get("size", 0):
            break
        start += len(d["results"])
    return results


def walk_tree(api, page_id, depth, pages):
    for c in get_children(api, page_id):
        pages.append({"id": c["id"], "title": c["title"], "depth": depth})
        walk_tree(api, c["id"], depth + 1, pages)


def _resolve_display_link(api, href):
    """Resolve a Confluence 'display/<space>/<title>' or 'pages/viewpage.action'
    link to a page id via the CQL search API. Returns (page_id, title) or None."""
    if "pageId=" in href:
        pid = href.split("pageId=")[-1].split("&")[0]
        if pid.isdigit():
            return pid, None
    # display/<space>/<title>  or /display/<space>/<title>
    m = re.search(r"/display/([^/]+)/(.+?)(?:#|$)", href)
    if m:
        space, title = m.group(1), m.group(2)
        title = title.replace("+", " ").replace("%5B", "[").replace("%5D", "]")
        try:
            d = api.get("/rest/api/content/search",
                        params={"cql": f'space="{space}" AND title="{title}"',
                                "limit": 1})
            res = d.get("results") or []
            if res:
                return res[0]["id"], res[0].get("title")
        except Exception:
            return None, None
    return None, None


def _extract_links(api, html, url_base):
    """Extract Confluence page links (via contentId/pageId or display/ links)
    and external URLs from a page's storage HTML. Returns
    (list_of_(page_id,title), external_urls)."""
    soup = BeautifulSoup(html, "html.parser")
    conf_links, extern = [], []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        pid, title = _resolve_display_link(api, href)
        if pid:
            conf_links.append((pid, title))
        elif href.startswith("http"):
            extern.append(href)
    # dedupe preserving order
    seen = set()
    uniq = []
    for pid, title in conf_links:
        if pid not in seen:
            seen.add(pid)
            uniq.append((pid, title))
    seen = set()
    extern = [x for x in extern if not (x in seen or seen.add(x))]
    return uniq, extern


def _extract_images(html, url_base):
    """Extract image/attachment URLs (schemas, diagrams) from a page's storage
    HTML. Returns a list of (download_path, filename, alt/name)."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        alt = img.get("alt") or ""
        if not src:
            continue
        # Confluence attachment images usually contain /download/attachments/
        if "/download/attachments/" in src or "images/" in src:
            fname = src.split("/")[-1].split("?")[0] or "image.png"
            out.append({"src": src, "name": fname, "alt": alt})
    return out


def fetch_space_pages(api, space_key):
    """Fetch ALL pages in a Confluence space via the CQL search API
    (paginated). Returns a list of {"id", "title", "depth"}."""
    pages, start = [], 0
    while True:
        try:
            d = api.get("/rest/api/content/search",
                        params={"cql": f'space="{space_key}" AND type=page',
                                "limit": 100, "start": start})
        except Exception as exc:
            print(f"[Confluence] space search failed: {exc.__class__.__name__}")
            break
        results = d.get("results", [])
        for r in results:
            pages.append({"id": r["id"], "title": r.get("title", ""),
                          "depth": 0})
        if start + len(results) >= d.get("size", 0) or not results:
            break
        start += len(results)
    return pages


def sync_confluence(api, page_id, url_base, depth=0, follow_links=False,
                    save_images=False, assets_dir="assets", db_path=None,
                    space_key=None):
    """Walk the Confluence page tree (and optionally follow in-page links to
    other Confluence pages / external pages) and store page text into Chroma.
    When save_images is enabled, downloads image attachments (architecture /
    workflow schemas) into <db_path>/<assets_dir> and records their local path +
    source URL in the page metadata so the dashboard can render them.

    If space_key is provided, ALL pages of that Confluence space are extracted
    (via CQL search) instead of walking a single page tree."""
    if space_key:
        print(f"[Confluence] Extracting ENTIRE space '{space_key}'...")
        pages = fetch_space_pages(api, space_key)
        print(f"[Confluence] Space pages found: {len(pages)}")
    else:
        print(f"[Confluence] Walking page tree from root {page_id}...")
        pages = [{"id": page_id, "title": "Root", "depth": 0}]
        walk_tree(api, page_id, 1, pages)

    # Optional deep crawl: follow in-page Confluence links to other pages.
    if follow_links and depth > 0:
        known = {p["id"] for p in pages}
        frontier = [p for p in pages if p["depth"] < depth]
        while frontier:
            nxt = []
            for p in frontier:
                try:
                    d = api.get(f"/rest/api/content/{p['id']}",
                                params={"expand": "body.storage"})
                except Exception:
                    continue
                html = d.get("body", {}).get("storage", {}).get("value", "")
                conf_links, _ext = _extract_links(api, html, url_base)
                for cid, ctitle in conf_links:
                    if cid not in known:
                        try:
                            cd = api.get(f"/rest/api/content/{cid}",
                                        params={"expand": "body.storage"})
                        except Exception:
                            continue
                        ctitle = cd.get("title", ctitle or f"page-{cid}")
                        known.add(cid)
                        pages.append({"id": cid, "title": ctitle,
                                      "depth": p["depth"] + 1})
                        if p["depth"] + 1 < depth:
                            nxt.append({"id": cid, "title": ctitle,
                                        "depth": p["depth"] + 1})
            frontier = nxt
    print(f"[Confluence] Total pages (after crawl): {len(pages)}")

    # Prepare assets folder for images.
    assets_abs = None
    if save_images and db_path:
        assets_abs = os.path.join(db_path, assets_dir)
        os.makedirs(assets_abs, exist_ok=True)

    docs = []
    for p in pages:
        pid = p["id"]
        d = api.get(f"/rest/api/content/{pid}", params={"expand": "body.storage"})
        title = d.get("title", p["title"])
        html = d.get("body", {}).get("storage", {}).get("value", "")
        text = strip_html_to_text(html)
        full = f"# {title}\n\n{text}" if text else f"# {title}\n\n(no body)"

        meta = {
            "source": "confluence",
            "page_id": pid,
            "title": title,
            "url": f"{url_base}/pages/viewpage.action?pageId={pid}",
        }

        # Download images / attachments (schemas, workflow diagrams).
        if save_images and assets_abs:
            # 1) Inline <img> tags
            images = _extract_images(html, url_base)
            # 2) Attachments from the child/attachment API
            try:
                att_d = api.get(f"/rest/api/content/{pid}/child/attachment",
                                params={"limit": 50})
                for a in att_d.get("results", []):
                    dl = a.get("_links", {}).get("download", "")
                    if not dl:
                        continue
                    title = a.get("title", "attachment")
                    images.append({"src": dl, "name": title, "alt": title})
            except Exception:
                pass
            saved = []
            seen_stems = set()
            for img in images:
                name = img["name"]
                src = img["src"]
                # Skip draw.io / Gliffy XML sources and temp files (they are
                # ASCII diagram sources, not viewable images).
                low_name = name.lower()
                if low_name.endswith((".tmp", ".xml", ".drawio", ".gliffy",
                                      ".json", ".txt", ".md")):
                    continue
                # Normalize: prefer a real image extension for the saved file.
                ext = os.path.splitext(low_name)[1]
                if ext not in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
                               ".bmp"):
                    ext = ".png"
                stem = re.sub(r"[^A-Za-z0-9._-]", "_",
                              os.path.splitext(name)[0])[:100]
                fname = f"{pid}_{stem}{ext}"
                # Deduplicate by stem: keep the first (rendered) image.
                if stem in seen_stems:
                    continue
                local = os.path.join(assets_abs, fname)
                try:
                    data = api.get_bytes(src)
                    # Only keep real image bytes (PNG/JPEG/GIF/SVG/WebP/BMP).
                    head = data[:16]
                    is_img = (head.startswith(b"\x89PNG") or
                              head.startswith(b"\xff\xd8") or
                              head.startswith(b"GIF8") or
                              head.startswith(b"RIFF") or  # webp
                              head.startswith(b"BM") or    # bmp
                              data[:200].lstrip().startswith(b"<svg"))
                    if not is_img:
                        print(f"    [img skip] {fname}: not an image")
                        continue
                    with open(local, "wb") as fh:
                        fh.write(data)
                    seen_stems.add(stem)
                    saved.append({
                        "file": os.path.relpath(local, db_path),
                        "url": src if src.startswith("http") else
                               url_base + src,
                        "alt": img["alt"],
                    })
                except Exception as exc:
                    print(f"    [img skip] {fname}: {exc.__class__.__name__}")
            if saved:
                meta["images"] = json.dumps(saved, ensure_ascii=False)
                meta["has_images"] = "1"
                # Append image references to the document text for traceability.
                full += "\n\nImages/attachments:"
                for s in saved:
                    full += f"\n  - {s.get('alt') or s.get('file')} " \
                            f"({s.get('file')})"

        docs.append({
            "id": f"confluence_{pid}",
            "text": full,
            "metadata": meta,
        })
        print(f"  [OK] {pid} | {title} ({len(text)} chars)")
    return docs
