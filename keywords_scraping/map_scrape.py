import re
from keywords_scraping.json_parser import _extract_dealers_from_json
from bs4 import BeautifulSoup, NavigableString, Tag
from playwright.async_api import async_playwright
from keywords_scraping.contact_regex import _block_to_dealer, extract_phones, extract_emails, _walk_up_to_card, BLOCK_TAGS, clean
from keywords_scraping.html_parser import parse_dealers_from_html, extract_from_initial_html, extract_popup_data, _parse_google_mymaps_panel
from keywords_scraping.contact_regex import _block_to_dealer



# ─────────────────────────────────────────────────────────────────────────────
# MAP INTERACTION
# ─────────────────────────────────────────────────────────────────────────────

# async def _try_map_and_search(url: str, queries: list[str]) -> list[dict]:
#     dealers = []
#     intercepted_data = []

#     async with async_playwright() as p:
#         browser = await p.chromium.launch(headless=False)
#         context = await browser.new_context()
#         page = await context.new_page()

#         async def handle_response(response):
#             url_lower = response.url.lower()
#             if any(kw in url_lower for kw in [
#                 'dealer', 'location', 'store', 'branch', 'marker', 'pin', 'map', 'poi'
#             ]):
#                 try:
#                     ct = response.headers.get('content-type', '')
#                     if 'json' in ct:
#                         body = await response.json()
#                         intercepted_data.append({'url': response.url, 'data': body})
#                 except:
#                     pass

#         page.on('response', handle_response)
#         await page.goto(url, wait_until='networkidle', timeout=30000)
#         await page.wait_for_timeout(3000)

#         # Strategy 1: Network intercept
#         if intercepted_data:
#             for item in intercepted_data:
#                 parsed = _extract_dealers_from_json(item['data'])
#                 if parsed:
#                     dealers.extend(parsed)
#             if dealers:
#                 print(f"[NETWORK] Got {len(dealers)} dealers from XHR intercept")
#                 await browser.close()
#                 return dealers

#         # Strategy 2: Find the right frame (iframe vs main page)
#         MARKER_SELECTORS = [
#             'img[src*="maps.gstatic.com/mapfiles"]',
#             'img[src*="marker"]',
#             'img[src*="pin"]',
#             'area[title]',
#             'gmp-advanced-marker',
#             '.gm-style [role="button"]:not([aria-label*="zoom"]):not([aria-label*="Street"]):not([aria-label*="Map"]):not([aria-label*="Satellite"])',
#             '.leaflet-marker-icon',
#             '.leaflet-div-icon',
#             '.mapboxgl-marker',
#             '.maplibregl-marker',
#             '[class*="marker"]:not([class*="markercluster-"])',
#             '[class*="Marker"]:not([class*="MarkerCluster"])',
#             '.marker-cluster',
#             '[class*="cluster"]',
#         ]

#         # ── Step 1: Find which frame has markers, WITHOUT zooming yet ──
#         map_frame = None
#         map_selector = None
#         map_markers = []

#         frames = [page] + list(page.frames)

#         for frame in frames:
#             await _zoom_map_in(
#                         marker_frame=frame ,
#                         page=page ,
#                         steps=10
#                         )
#             for selector in MARKER_SELECTORS:
#                 try:
#                     markers = await frame.query_selector_all(selector)

#                     if not markers:
#                         continue

#                     print(f"[DOM] Selector '{selector}' -> {len(markers)} elements (frame: {frame.url[:80]})")

#                     # ─────────────────────────────
#                     # Zoom BEFORE extraction
#                     # ─────────────────────────────
                    
#                     # allow map rerender
#                     await page.wait_for_timeout(3000)

#                     # ─────────────────────────────
#                     # REDISCOVER markers AFTER zoom
#                     # ─────────────────────────────

#                     # markers = await frame.query_selector_all(selector)

#                     # print(
#                     #     f"[DOM] After zoom -> "
#                     #     f"{len(markers)} markers"
#                     # )

#                     # ── KEY FIX: pass the frame itself so clicks happen inside it ──
#                     frame_dealers = await _click_markers_and_extract(
#                         marker_frame=frame,
#                         page=page,
#                         markers=markers,
#                     )
#                     dealers.extend(frame_dealers)

#                     if frame_dealers:
#                         break  # good selector found, stop trying others
#                 except Exception as e:
#                     continue

#             if dealers:
#                 break  # good frame found, stop trying others

#         # Strategy 3: Canvas grid scan fallback
#         if not dealers:
#             dealers.extend(await _canvas_click_scan(page))

#         await browser.close()

#     return dealers
 
async def _try_map_and_search(url: str, queries: list[str]) -> list[dict]:
    dealers = []
    intercepted_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        async def handle_response(response):
            url_lower = response.url.lower()
            if any(kw in url_lower for kw in [
                'dealer', 'location', 'store', 'branch', 'marker', 'pin', 'map', 'poi'
            ]):
                try:
                    ct = response.headers.get('content-type', '')
                    if 'json' in ct:
                        body = await response.json()
                        intercepted_data.append({'url': response.url, 'data': body})
                except:
                    pass

        page.on('response', handle_response)
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(3000)

        # Strategy 1: Network intercept
        if intercepted_data:
            for item in intercepted_data:
                parsed = _extract_dealers_from_json(item['data'])
                if parsed:
                    dealers.extend(parsed)
            if dealers:
                print(f"[NETWORK] Got {len(dealers)} dealers from XHR intercept")
                await browser.close()
                return dealers

        MARKER_SELECTORS = [
            'img[src*="maps.gstatic.com/mapfiles"]',
            'img[src*="marker"]',
            'img[src*="pin"]',
            'area[title]',
            'gmp-advanced-marker',
            '.gm-style [role="button"]:not([aria-label*="zoom"]):not([aria-label*="Street"]):not([aria-label*="Map"]):not([aria-label*="Satellite"])',
            '.leaflet-marker-icon',
            '.leaflet-div-icon',
            '.mapboxgl-marker',
            '.maplibregl-marker',
            '[class*="marker"]:not([class*="markercluster-"])',
            '[class*="Marker"]:not([class*="MarkerCluster"])',
            '.marker-cluster',
            '[class*="cluster"]',
        ]

        # ── Step 1: Find which frame has markers, WITHOUT zooming yet ──
        map_frame = None
        map_selector = None
        map_markers = []

        frames = [page] + list(page.frames)
        for frame in frames:
            for selector in MARKER_SELECTORS:
                try:
                    markers = await frame.query_selector_all(selector)
                    if markers:
                        print(f"[DOM] Selector '{selector}' -> {len(markers)} elements (frame: {frame.url[:80]})")
                        map_frame = frame
                        map_selector = selector
                        map_markers = markers
                        break
                except Exception:
                    continue
            if map_frame:
                break

        if not map_frame:
            print("[MAP] No markers found in any frame — trying canvas scan")
            dealers.extend(await _canvas_click_scan(page))
            await browser.close()
            return dealers

        # ── Step 2: Zoom ONCE on the frame that has markers ──
        await _zoom_map_in(marker_frame=map_frame, page=page, steps=10)
        await page.wait_for_timeout(3000)

        # ── Step 3: Re-query markers after zoom (positions may have changed) ──
        fresh_markers = await map_frame.query_selector_all(map_selector)
        print(f"[DOM] After zoom -> {len(fresh_markers)} markers")

        # ── Step 4: Extract ──
        frame_dealers = await _click_markers_and_extract(
            marker_frame=map_frame,
            page=page,
            markers=fresh_markers,
        )
        dealers.extend(frame_dealers)

        # Strategy 3: Canvas grid scan fallback
        if not dealers:
            dealers.extend(await _canvas_click_scan(page))

        await browser.close()

    return dealers
 
# async def _click_markers_and_extract(
#     marker_frame,
#     page,
#     markers,
# ) -> list[dict]:

#     results = []
#     seen_positions = set()
#     clicked_positions = set()

#     POPUP_SELECTORS = [

#         # Google Maps
#         '.gm-style-iw',
#         '.gm-style-iw-c',
#         '.gm-style-iw-d',

#         # Google My Maps / sidebars
#         '[class*="qqvbed"]',
#         '[jsname="WOdXFb"]',

#         # Generic map wrappers
#         '[class*="goog-container"]',

#         # Generic popup systems
#         '[class*="InfoWindow"]',
#         '[class*="infowindow"]',
#         '[class*="popup"]',
#         '[class*="Popup"]',

#         # Leaflet / Mapbox
#         '.leaflet-popup-content',
#         '.mapboxgl-popup-content',

#         # Sidebar / panels
#         '[class*="sidebar"]',
#         '[class*="Sidebar"]',
#         '[class*="panel"]',
#         '[class*="detail"]',

#         # ARIA
#         '[role="dialog"]',
#         '[role="tooltip"]',
#     ]

#     async def close_popup():

#         for close_sel in [
#             '[aria-label="Close"]',
#             '.gm-ui-hover-effect',
#             'button[jsaction*="close"]',
#             '[data-dismiss]',
#         ]:

#             try:
#                 btn = await marker_frame.query_selector(close_sel)

#                 if btn:
#                     await btn.evaluate("el => el.click()")
#                     await page.wait_for_timeout(500)
#                     return

#             except Exception:
#                 continue

#     async def wait_for_map_ready(selector: str):
#         """Wait for markers to re-appear after navigation back."""
#         for _ in range(10):
#             els = await marker_frame.query_selector_all(selector)
#             if els:
#                 return els
#             await page.wait_for_timeout(500)
#         return []

#     original_url = page.url

#     # snapshot markers
#     marker_snapshots = []

#     for marker in markers[:100]:

#         try:
#             box = await marker.bounding_box()

#             if not box or box['width'] < 4 or box['height'] < 4:
#                 continue

#             cell = (
#                 round(box['x'] / 5),
#                 round(box['y'] / 5),
#             )

#             if cell in seen_positions:
#                 continue

#             seen_positions.add(cell)

#             marker_snapshots.append((marker, box))

#         except Exception:
#             continue

#     print(f"[CLICK] {len(marker_snapshots)} unique markers")

#     # ── Track which marker selector found these (for re-query after nav) ──
#     # Passed in from outside — store as closure variable
#     active_selector = None  # set below on first successful find

#     for i, (handle, box) in enumerate(marker_snapshots):

#         try:
#             print(f"[CLICK] Marker {i+1}/{len(marker_snapshots)} at ({box['x']:.0f}, {box['y']:.0f})")

#             # ── Refresh handle for i > 0, but skip already-clicked positions ──
#             current_handle = handle
#             current_box = box

#             if i > 0:
#                 fresh = await _resolve_handle_by_position(
#                     marker_frame, box, clicked_positions, tolerance=80
#                 )
#                 if fresh:
#                     current_handle, current_box = fresh
#                     print(f"  → Refreshed handle at ({current_box['x']:.0f}, {current_box['y']:.0f})")
#                 else:
#                     print(f"  → Could not refresh handle, using stored")

#             # ── Mark this position as clicked before doing anything ──
#             clicked_cell = (round(current_box['x'] / 5), round(current_box['y'] / 5))
#             clicked_positions.add(clicked_cell)

#             clicked = False

#             # strategy 1
#             try:
#                 await current_handle.evaluate("el => el.click()")
#                 clicked = True

#             except Exception:
#                 pass

#             # strategy 2
#             if not clicked:

#                 try:
#                     await marker_frame.evaluate(
#                         """
#                         ([x, y]) => {

#                             const el =
#                                 document.elementFromPoint(x, y);

#                             if (el)
#                                 el.click();
#                         }
#                         """,
#                         [box['x'], box['y']]
#                     )

#                     clicked = True

#                 except Exception as e:
#                     print(f"  → Click failed: {e}")
#                     continue

#             await page.wait_for_timeout(2000)

#             # ─────────────────────────────
#             # Find BEST popup/sidebar
#             # ─────────────────────────────

#             popup, popup_source, debug = (
#                 await _find_best_popup_candidate(
#                     marker_frame,
#                     page,
#                     POPUP_SELECTORS,
#                 )
#             )

#             if not popup:
#                 print("  → No popup found")
#                 continue

#             print(
#                 f"  → Best popup "
#                 f"(score={debug['score']}, "
#                 f"area={debug['area']:.0f})"
#             )

#             html = await popup.inner_html()
#             text = await popup.inner_text()

#             print(f"  → Preview:\n{text[:800]}")

#             # ─────────────────────────────
#             # Strategy A
#             # Google structured sidebar
#             # ─────────────────────────────

#             structured = (
#                 _parse_google_sidebar_structured(html)
#             )

#             if structured:

#                 print(
#                     f"  → Structured sidebar: "
#                     f"{structured.get('name')} | "
#                     f"{structured.get('phone')}"
#                 )

#                 results.append(structured)

#                 await close_popup()

#                 continue

#             # ─────────────────────────────
#             # Strategy B
#             # MyMaps parser
#             # ─────────────────────────────

#             mymaps_result = (
#                 _parse_google_mymaps_panel(html)
#             )

#             if mymaps_result:

#                 print(
#                     f"  → MyMaps: "
#                     f"{mymaps_result.get('name')}"
#                 )

#                 results.append(mymaps_result)

#                 await close_popup()

#                 continue

#             # ─────────────────────────────
#             # Strategy C
#             # Generic HTML parser
#             # ─────────────────────────────

#             parsed = parse_dealers_from_html(html)

#             if parsed:

#                 print(
#                     f"  → HTML parser: "
#                     f"{len(parsed)} dealers"
#                 )

#                 results.extend(parsed)

#                 await close_popup()

#                 continue

#             # ─────────────────────────────
#             # Strategy D
#             # Follow detail links
#             # ─────────────────────────────
            
#             hrefs = []

            
#             try:
#                 links = await popup.query_selector_all('a[href]')

#                 for link in links:
#                     href = await link.get_attribute('href')
#                     if href:
#                         hrefs.append(href)
#             except Exception:
#                     pass

#             detail_found = False

#             for href in hrefs:

#                 if href.startswith('tel:'):
#                     phone = re.sub(r'\D', '', href.replace('tel:', ''))

#                     if phone:
#                         results.append({
#                             'name':    text.split('\n')[0].strip(),
#                             'address': '\n'.join(text.split('\n')[1:]).strip(),
#                             'phone':   [phone],
#                             'email':   [],
#                             'source':  'tel_link',
#                         })
#                         detail_found = True
#                     continue

#                 if href.startswith('mailto:') or href.strip() in ('#', original_url):
#                     continue

#                 # # Skip anchors that just point back to the map page
#                 # if href.strip() in ('#', original_url):
#                 #     continue

#                 print(f"  → Following detail link: {href[:80]}")

#                 try:
#                     # ── Navigate to the detail page ──
#                     # Use page.goto instead of link.click() — more reliable,
#                     # handles both full URLs and relative paths correctly,
#                     # and avoids the popup element becoming stale mid-click.
#                     target_url = href if href.startswith('http') else page.url.split('#')[0] + href
                    
#                     await page.goto(target_url, wait_until='networkidle', timeout=15000)
#                     await page.wait_for_timeout(1500)

#                     detail_html = await page.content()
#                     detail_parsed = parse_dealers_from_html(detail_html)

#                     if detail_parsed:
#                         print(f"  → Got {len(detail_parsed)} from detail page")
#                         results.extend(detail_parsed)
#                         detail_found = True
#                     else:
#                         # Try extracting from page text directly
#                         detail_text = await page.evaluate("() => document.body.innerText")
#                         phones = extract_phones(detail_text)
#                         emails = extract_emails(detail_text)
#                         if phones:
#                             results.append({
#                                 'name':    text.split('\n')[0].strip(),
#                                 'address': '\n'.join(text.split('\n')[1:]).strip(),
#                                 'phone':   phones,
#                                 'email':   emails,
#                                 'source':  'detail_page_raw',
#                             })
#                             detail_found = True

#                     # ── Return to map page ──
#                     print(f"  → Returning to map: {original_url}")
#                     await page.goto(original_url, wait_until='networkidle', timeout=15000)
#                     await page.wait_for_timeout(2000)

#                     # # ── CRITICAL: Re-acquire fresh marker handles ──
#                     # # All handles in marker_snapshots are now stale.
#                     # # Re-query and rebuild remaining snapshots from position i+1 onward.
#                     # fresh_markers_found = False
#                     # for marker_sel in [
#                     #     'img[src*="maps.gstatic.com/mapfiles"]',
#                     #     'img[src*="marker"]',
#                     #     '.leaflet-marker-icon',
#                     #     '.mapboxgl-marker',
#                     #     '[class*="marker"]',
#                     # ]:
#                     #     try:
#                     #         fresh = await marker_frame.query_selector_all(marker_sel)
#                     #         if fresh:
#                     #             # Rebuild remaining snapshots for markers i+1 onward
#                     #             # Match by stored bounding box position
#                     #             fresh_snapshots = []
#                     #             fresh_seen = set()
#                     #             for m in fresh:
#                     #                 try:
#                     #                     b = await m.bounding_box()
#                     #                     if not b or b['width'] < 4:
#                     #                         continue
#                     #                     c = (round(b['x'] / 5), round(b['y'] / 5))
#                     #                     if c in fresh_seen:
#                     #                         continue
#                     #                     fresh_seen.add(c)
#                     #                     fresh_snapshots.append((m, b))
#                     #                 except Exception:
#                     #                     continue

#                     #             # Replace remaining entries in marker_snapshots
#                     #             if fresh_snapshots:
#                     #                 # Map old positions to new handles by proximity
#                     #                 remaining_boxes = [b for _, b in marker_snapshots[i+1:]]
#                     #                 for j, old_box in enumerate(remaining_boxes):
#                     #                     best_handle = None
#                     #                     best_dist = float('inf')
#                     #                     for new_handle, new_box in fresh_snapshots:
#                     #                         dist = abs(new_box['x'] - old_box['x']) + abs(new_box['y'] - old_box['y'])
#                     #                         if dist < best_dist:
#                     #                             best_dist = dist
#                     #                             best_handle = new_handle
#                     #                     if best_handle and best_dist < 20:
#                     #                         marker_snapshots[i+1+j] = (best_handle, remaining_boxes[j])

#                     #                 fresh_markers_found = True
#                     #                 print(f"  → Re-acquired {len(fresh_snapshots)} fresh marker handles")
#                     #                 break
#                     #     except Exception:
#                     #         continue

#                     # if not fresh_markers_found:
#                     #     print("  → Could not re-acquire markers after navigation — stopping")
#                     #     break  # can't reliably continue clicking remaining markers

#                     # break  # only follow one detail link per popup

#                     # ── Update marker_snapshots[i+1:] with fresh handles ──
#                     # Do this inline here so the outer for-loop picks up fresh handles
#                     await _refresh_marker_snapshots(
#                         marker_frame, page, marker_snapshots, start_index=i + 1, clicked_positions=clicked_positions,tolerance=40
#                     )

#                 except Exception as e:
#                     print(f"  → Detail page error: {e}")
#                     # Try to get back to the map regardless
#                     try:
#                         await page.goto(original_url, wait_until='networkidle', timeout=10000)
#                         await page.wait_for_timeout(1500)
#                         await _refresh_marker_snapshots(
#                         marker_frame, page, marker_snapshots, start_index=i + 1, clicked_positions=clicked_positions, tolerance=40
#                     )
#                     except Exception:
#                         pass
                    
#                 break

#             # ─────────────────────────────
#             # Strategy E
#             # Raw fallback
#             # ─────────────────────────────

#             if not detail_found:
            
#                 raw = {
#                     'name': text.split('\n')[0].strip(),
#                     'address': '\n'.join(
#                         text.split('\n')[1:]
#                     ).strip(),
#                     'phone': extract_phones(text),
#                     'email': extract_emails(text),
#                     'source': 'map_popup_raw',
#                 }

#                 print(f"  → Raw: {raw['name']} | {raw['phone']}")

#                 results.append(raw)

#             await close_popup()

#         except Exception as e:
#             print(f"[CLICK] Error on marker {i+1}: {e}")
#             continue

#     return deduplicate_dealers(results)
 
async def _click_markers_and_extract(
    marker_frame,
    page,
    markers,
) -> list[dict]:

    """
    Stable marker click extractor.

    KEY DESIGN CHANGES:
    -------------------
    1. NEVER navigates main map page
    2. Opens detail pages in NEW TAB
    3. No marker remapping needed
    4. Waits for popup content changes
    5. Handles reused popup containers
    6. Prevents duplicate marker clicks
    """

    import re
    from urllib.parse import urljoin

    results = []

    # ---------------------------------------------------------
    # Dedup clicked markers
    # ---------------------------------------------------------

    clicked_cells = set()

    # ---------------------------------------------------------
    # Popup selectors
    # ---------------------------------------------------------

    POPUP_SELECTORS = [

        # Google
        '.gm-style-iw',
        '.gm-style-iw-c',
        '.gm-style-iw-d',

        # Google My Maps
        '[class*="qqvbed"]',
        '[jsname="WOdXFb"]',

        # Generic popup
        '[class*="InfoWindow"]',
        '[class*="infowindow"]',
        '[class*="popup"]',
        '[class*="Popup"]',

        # Leaflet / Mapbox
        '.leaflet-popup-content',
        '.mapboxgl-popup-content',

        # Sidebar/panel
        '[class*="sidebar"]',
        '[class*="Sidebar"]',
        '[class*="panel"]',
        '[class*="detail"]',

        # ARIA
        '[role="dialog"]',
        '[role="tooltip"]',
    ]

    # ---------------------------------------------------------
    # Close popup helper
    # ---------------------------------------------------------

    async def close_popup():

        CLOSE_SELECTORS = [

            '[aria-label="Close"]',
            '.gm-ui-hover-effect',
            'button[jsaction*="close"]',
            '[data-dismiss]',
            '[class*="close"]',
            '[class*="Close"]',
        ]

        for sel in CLOSE_SELECTORS:

            try:
                btn = await marker_frame.query_selector(sel)

                if not btn:
                    continue

                if not await btn.is_visible():
                    continue

                await btn.click(force=True, timeout=2000)

                await page.wait_for_timeout(700)

                return

            except Exception:
                continue

        # ESC fallback
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
        except Exception:
            pass

    # ---------------------------------------------------------
    # Snapshot unique markers
    # ---------------------------------------------------------

    marker_snapshots = []

    seen_positions = set()

    for marker in markers[:100]:

        try:
            box = await marker.bounding_box()

            if not box:
                continue

            if box["width"] < 4 or box["height"] < 4:
                continue

            cell = (
                round(box["x"] / 10),
                round(box["y"] / 10),
            )

            if cell in seen_positions:
                continue

            seen_positions.add(cell)

            marker_snapshots.append(
                {
                    "handle": marker,
                    "box": box,
                    "cell": cell,
                }
            )

        except Exception:
            continue

    print(f"[CLICK] {len(marker_snapshots)} unique markers")

    # ---------------------------------------------------------
    # Popup state tracker
    # ---------------------------------------------------------

    last_popup_signature = None

    # ---------------------------------------------------------
    # MAIN LOOP
    # ---------------------------------------------------------

    for idx, item in enumerate(marker_snapshots):

        handle = item["handle"]
        box = item["box"]
        cell = item["cell"]

        if cell in clicked_cells:
            continue

        clicked_cells.add(cell)

        print(
            f"[CLICK] Marker "
            f"{idx+1}/{len(marker_snapshots)} "
            f"at ({box['x']:.0f}, {box['y']:.0f})"
        )

        try:

            # -------------------------------------------------
            # Bring marker into view
            # -------------------------------------------------

            try:
                await handle.scroll_into_view_if_needed()
            except Exception:
                pass

            # -------------------------------------------------
            # Click marker
            # -------------------------------------------------

            clicked = False

            # Strategy 1
            try:

                await handle.click(
                    force=True,
                    timeout=3000,
                )

                clicked = True

            except Exception:
                pass

            # Strategy 2
            if not clicked:

                try:

                    await handle.evaluate(
                        "el => el.click()"
                    )

                    clicked = True

                except Exception:
                    pass

            # Strategy 3
            if not clicked:

                try:

                    await marker_frame.evaluate(
                        """
                        ([x, y]) => {

                            const el =
                                document.elementFromPoint(x, y);

                            if (el)
                                el.click();
                        }
                        """,
                        [
                            box["x"],
                            box["y"],
                        ]
                    )

                    clicked = True

                except Exception as e:

                    print(f"  → Click failed: {e}")

                    continue

            # -------------------------------------------------
            # Wait popup stabilize
            # -------------------------------------------------

            popup = None
            popup_text = None
            popup_html = None

            for _ in range(12):

                try:

                    popup_candidate = None
                    best_area = 0

                    for sel in POPUP_SELECTORS:

                        try:

                            found = await marker_frame.query_selector_all(sel)

                            for p in found:

                                try:

                                    if not await p.is_visible():
                                        continue

                                    b = await p.bounding_box()

                                    if not b:
                                        continue

                                    area = b["width"] * b["height"]

                                    if area > best_area:
                                        best_area = area
                                        popup_candidate = p

                                except Exception:
                                    continue

                        except Exception:
                            continue

                    if popup_candidate:

                        text = (
                            await popup_candidate.inner_text()
                        ).strip()

                        if not text:
                            await page.wait_for_timeout(500)
                            continue

                        signature = (
                            text[:300].strip()
                        )

                        # popup changed
                        if signature != last_popup_signature:

                            popup = popup_candidate
                            popup_text = text
                            popup_html = await popup.inner_html()

                            last_popup_signature = signature

                            break

                    await page.wait_for_timeout(500)

                except Exception:
                    await page.wait_for_timeout(500)

            if not popup:

                print("  → No popup found")

                continue

            print(f"  → Popup preview:\n{popup_text[:500]}")

            # -------------------------------------------------
            # Strategy A
            # Structured sidebar parser
            # -------------------------------------------------

            structured = (
                _parse_google_sidebar_structured(
                    popup_html
                )
            )

            if structured:

                print(
                    f"  → Structured: "
                    f"{structured.get('name')}"
                )

                results.append(structured)

                await close_popup()

                continue

            # -------------------------------------------------
            # Strategy B
            # MyMaps parser
            # -------------------------------------------------

            mymaps_result = (
                _parse_google_mymaps_panel(
                    popup_html
                )
            )

            if mymaps_result:

                print(
                    f"  → MyMaps: "
                    f"{mymaps_result.get('name')}"
                )

                results.append(mymaps_result)

                await close_popup()

                continue

            # -------------------------------------------------
            # Strategy C
            # Generic HTML parser
            # -------------------------------------------------

            parsed = parse_dealers_from_html(
                popup_html
            )

            if parsed:

                print(
                    f"  → HTML parser: "
                    f"{len(parsed)} dealers"
                )

                results.extend(parsed)

                await close_popup()

                continue

            # -------------------------------------------------
            # Strategy D
            # Follow detail links in NEW TAB
            # -------------------------------------------------

            detail_found = False

            try:

                links = await popup.query_selector_all(
                    'a[href]'
                )

            except Exception:
                links = []

            hrefs = []

            for link in links:

                try:

                    href = await link.get_attribute(
                        'href'
                    )

                    if href:
                        hrefs.append(href)

                except Exception:
                    continue

            for href in hrefs:

                href = href.strip()

                # ---------------------------------------------
                # tel:
                # ---------------------------------------------

                if href.startswith("tel:"):

                    phone = re.sub(
                        r"\D",
                        "",
                        href.replace("tel:", "")
                    )

                    if phone:

                        results.append({

                            "name":
                                popup_text.split("\n")[0].strip(),

                            "address":
                                "\n".join(
                                    popup_text.split("\n")[1:]
                                ).strip(),

                            "phone":
                                [phone],

                            "email":
                                [],

                            "source":
                                "tel_link",
                        })

                        detail_found = True

                    continue

                # ---------------------------------------------
                # skip mailto
                # ---------------------------------------------

                if href.startswith("mailto:"):
                    continue

                # ---------------------------------------------
                # Build full URL
                # ---------------------------------------------

                full_url = urljoin(page.url, href)

                print(
                    f"  → Opening detail tab: "
                    f"{full_url[:100]}"
                )

                try:

                    detail_page = (
                        await page.context.new_page()
                    )

                    await detail_page.goto(
                        full_url,
                        wait_until="networkidle",
                        timeout=20000,
                    )

                    await detail_page.wait_for_timeout(2000)

                    detail_html = await detail_page.content()

                    detail_parsed = (
                        parse_dealers_from_html(
                            detail_html
                        )
                    )

                    if detail_parsed:

                        print(
                            f"  → Detail page: "
                            f"{len(detail_parsed)} dealers"
                        )

                        results.extend(detail_parsed)

                        detail_found = True

                    else:

                        detail_text = await detail_page.evaluate(
                            "() => document.body.innerText"
                        )

                        phones = extract_phones(detail_text)

                        emails = extract_emails(detail_text)

                        if phones or emails:

                            results.append({

                                "name":
                                    popup_text.split("\n")[0].strip(),

                                "address":
                                    "\n".join(
                                        popup_text.split("\n")[1:]
                                    ).strip(),

                                "phone":
                                    phones,

                                "email":
                                    emails,

                                "source":
                                    "detail_page_raw",
                            })

                            detail_found = True

                    await detail_page.close()

                    break

                except Exception as e:

                    print(
                        f"  → Detail tab error: {e}"
                    )

                    try:
                        await detail_page.close()
                    except Exception:
                        pass

                    continue

            # -------------------------------------------------
            # Strategy E
            # Raw fallback
            # -------------------------------------------------

            if not detail_found:

                raw = {

                    "name":
                        popup_text.split("\n")[0].strip(),

                    "address":
                        "\n".join(
                            popup_text.split("\n")[1:]
                        ).strip(),

                    "phone":
                        extract_phones(popup_text),

                    "email":
                        extract_emails(popup_text),

                    "source":
                        "map_popup_raw",
                }

                print(
                    f"  → Raw fallback: "
                    f"{raw['name']}"
                )

                results.append(raw)

            # -------------------------------------------------
            # Close popup
            # -------------------------------------------------

            await close_popup()

        except Exception as e:

            print(
                f"[CLICK] Error on marker "
                f"{idx+1}: {e}"
            )

            try:
                await close_popup()
            except Exception:
                pass

            continue

    return deduplicate_dealers(results)

# async def _resolve_handle_by_position(
#     frame,
#     box: dict,
#     clicked_positions: set,   # ← skip handles near already-clicked spots
#     tolerance: int = 80,
# ):
#     MARKER_SELECTORS = [
#         'img[src*="maps.gstatic.com/mapfiles"]',
#         'img[src*="marker"]',
#         'img[src*="pin"]',
#         '.leaflet-marker-icon',
#         '.mapboxgl-marker',
#         'gmp-advanced-marker',
#         '[class*="marker"]:not([class*="cluster"])',
#     ]

#     best_handle = None
#     best_dist = float('inf')
#     best_box = None

#     for sel in MARKER_SELECTORS:
#         try:
#             candidates = await frame.query_selector_all(sel)
#             for c in candidates:
#                 try:
#                     b = await c.bounding_box()
#                     if not b or b['width'] < 4:
#                         continue

#                     # ── Skip already-clicked positions ──
#                     cell = (round(b['x'] / 5), round(b['y'] / 5))
#                     if cell in clicked_positions:
#                         continue

#                     dist = abs(b['x'] - box['x']) + abs(b['y'] - box['y'])
#                     if dist < best_dist:
#                         best_dist = dist
#                         best_handle = c
#                         best_box = b
#                 except Exception:
#                     continue
#         except Exception:
#             continue

#     if best_handle:
#         print(f"  → Resolved handle dist={best_dist:.0f}px")
#         return best_handle, best_box   # ← return box too so caller can update current_box

#     return None

# async def _refresh_marker_snapshots(
#     frame,
#     page,
#     marker_snapshots: list,
#     start_index: int,
#     clicked_positions: set,   # ← new param
#     tolerance: int = 40,
# ):
#     if start_index >= len(marker_snapshots):
#         return

#     MARKER_SELECTORS = [
#         'img[src*="maps.gstatic.com/mapfiles"]',
#         'img[src*="marker"]',
#         'img[src*="pin"]',
#         '.leaflet-marker-icon',
#         '.mapboxgl-marker',
#         'gmp-advanced-marker',
#         '[class*="marker"]:not([class*="cluster"])',
#     ]

#     # Wait for markers to re-appear
#     fresh_markers = []
#     for attempt in range(8):
#         for sel in MARKER_SELECTORS:
#             try:
#                 candidates = await frame.query_selector_all(sel)
#                 if not candidates:
#                     continue
#                 seen = set()
#                 for c in candidates:
#                     try:
#                         b = await c.bounding_box()
#                         if not b or b['width'] < 4 or b['height'] < 4:
#                             continue
#                         cell = (round(b['x'] / 10), round(b['y'] / 10))
#                         if cell in seen:
#                             continue
#                         seen.add(cell)
#                         fresh_markers.append((c, b))
#                     except Exception:
#                         continue
#                 if fresh_markers:
#                     break
#             except Exception:
#                 continue
#         if fresh_markers:
#             break
#         await page.wait_for_timeout(500)

#     if not fresh_markers:
#         print(f"  → Refresh: no markers found")
#         return

#     # ── Only keep markers NOT in clicked_positions ──
#     unclicked_fresh = [
#         (h, b) for h, b in fresh_markers
#         if (round(b['x'] / 5), round(b['y'] / 5)) not in clicked_positions
#     ]

#     print(f"  → {len(fresh_markers)} fresh markers, {len(unclicked_fresh)} unclicked")

#     # Assign unclicked fresh markers to remaining snapshot slots in order
#     remaining_count = len(marker_snapshots) - start_index
#     refreshed = 0
#     for j, (new_handle, new_box) in enumerate(unclicked_fresh):
#         idx = start_index + j
#         if idx >= len(marker_snapshots):
#             break
#         marker_snapshots[idx] = (new_handle, new_box)
#         refreshed += 1

#     print(f"  → Refreshed {refreshed}/{remaining_count} handles")
 
async def _zoom_map_in(
    marker_frame,
    page,
    steps=5,
):

    """
    Robust map zoom helper.

    Strategy order:
    1. Click real zoom-in buttons
    2. Hover map + CTRL + wheel zoom
    3. Drag map slightly to activate focus then wheel zoom
    """

    print("\n[ZOOM] Starting map zoom...")

    # =========================================================
    # Zoom button selectors
    # =========================================================

    ZOOM_SELECTORS = [

        # Google Maps
        'button[aria-label="Zoom in"]',
        '[aria-label="Zoom in"]',
        'button[title="Zoom in"]',
        '[title="Zoom in"]',

        # Google newer controls
        '.gm-control-active[aria-label="Zoom in"]',

        # Leaflet
        '.leaflet-control-zoom-in',

        # Mapbox
        '.mapboxgl-ctrl-zoom-in',

        # Generic
        '[class*="zoom"][class*="in"]',
        '[id*="zoom"][id*="in"]',
    ]

    # =========================================================
    # Map container selectors
    # =========================================================

    MAP_SELECTORS = [

        # Google maps
        '.gm-style',
        '[role="application"]',

        # Leaflet
        '.leaflet-container',

        # Mapbox
        '.mapboxgl-canvas-container',
        '.mapboxgl-map',

        # Generic
        'canvas',
        'iframe',
        '[class*="map"]',
    ]

    zoomed = False

    # =========================================================
    # STRATEGY 1
    # Real zoom button click
    # =========================================================

    for step in range(steps):

        print(f"[ZOOM] Button step {step + 1}")

        clicked = False

        for sel in ZOOM_SELECTORS:

            for context_name, context in [
                ("frame", marker_frame),
                ("page", page),
            ]:

                try:

                    buttons = await context.query_selector_all(sel)

                    if not buttons:
                        continue

                    for btn in buttons:

                        try:

                            if not await btn.is_visible():
                                continue

                            box = await btn.bounding_box()

                            if not box:
                                continue

                            print(
                                f"  → Clicking zoom button "
                                f"'{sel}' "
                                f"({context_name})"
                            )

                            # Scroll into view
                            await btn.scroll_into_view_if_needed()

                            # Real click
                            await btn.click(
                                force=True,
                                timeout=3000,
                            )

                            await page.wait_for_timeout(1200)

                            clicked = True
                            zoomed = True

                            break

                        except Exception as e:
                            print(f"    button click failed: {e}")
                            continue

                    if clicked:
                        break

                except Exception:
                    continue

            if clicked:
                break

    # =========================================================
    # STRATEGY 2
    # CTRL + mouse wheel zoom
    # =========================================================

    if not zoomed:

        print("[ZOOM] CTRL + wheel fallback")

        try:

            hovered = False

            for sel in MAP_SELECTORS:

                for context_name, context in [
                    ("frame", marker_frame),
                    ("page", page),
                ]:

                    try:

                        map_el = await context.query_selector(sel)

                        if not map_el:
                            continue

                        if not await map_el.is_visible():
                            continue

                        box = await map_el.bounding_box()

                        if not box:
                            continue

                        center_x = box["x"] + (box["width"] / 2)
                        center_y = box["y"] + (box["height"] / 2)

                        print(
                            f"  → Hovering map "
                            f"'{sel}' "
                            f"({context_name})"
                        )

                        # Move mouse to map center
                        await page.mouse.move(center_x, center_y)

                        hovered = True

                        break

                    except Exception:
                        continue

                if hovered:
                    break

            # CTRL + wheel zoom
            if hovered:

                await page.keyboard.down("Control")

                for i in range(steps):

                    print(f"  → CTRL wheel zoom {i+1}")

                    await page.mouse.wheel(0, -2500)

                    await page.wait_for_timeout(1000)

                await page.keyboard.up("Control")

                zoomed = True

        except Exception as e:

            print(f"[ZOOM] CTRL wheel failed: {e}")

    # =========================================================
    # STRATEGY 3
    # Drag map slightly then wheel zoom
    # =========================================================

    if not zoomed:

        print("[ZOOM] Drag activation fallback")

        try:

            map_el = None

            for sel in MAP_SELECTORS:

                try:

                    map_el = await marker_frame.query_selector(sel)

                    if map_el:
                        break

                except Exception:
                    continue

            if map_el:

                box = await map_el.bounding_box()

                if box:

                    center_x = box["x"] + (box["width"] / 2)
                    center_y = box["y"] + (box["height"] / 2)

                    # Small drag
                    await page.mouse.move(center_x, center_y)

                    await page.mouse.down()

                    await page.mouse.move(
                        center_x + 40,
                        center_y + 40,
                        steps=10,
                    )

                    await page.mouse.up()

                    await page.wait_for_timeout(1000)

                    # Wheel zoom
                    for i in range(steps):

                        print(f"  → Drag-wheel zoom {i+1}")

                        await page.mouse.wheel(0, -2500)

                        await page.wait_for_timeout(1000)

                    zoomed = True

        except Exception as e:

            print(f"[ZOOM] Drag fallback failed: {e}")

    # =========================================================
    # Final settle
    # =========================================================

    await page.wait_for_timeout(2500)

    print(f"[ZOOM] Finished | success={zoomed}\n")
 
async def _canvas_click_scan(page) -> list[dict]:
    """Last resort for canvas/WebGL maps — grid click scan."""
    results = []

    map_selectors = [
        '.gm-style', '#map', '[id*="map"]', '[class*="map"]',
        'canvas', '.mapboxgl-canvas', '.maplibregl-canvas'
    ]

    map_el = None
    for sel in map_selectors:
        map_el = await page.query_selector(sel)
        if map_el:
            break

    if not map_el:
        return results

    box = await map_el.bounding_box()
    if not box:
        return results

    print(f"[CANVAS] Scanning map at {box} with grid clicks")

    cols, rows = 6, 4
    for row in range(rows):
        for col in range(cols):
            x = box['x'] + (box['width'] / (cols + 1)) * (col + 1)
            y = box['y'] + (box['height'] / (rows + 1)) * (row + 1)

            await page.mouse.click(x, y)
            await page.wait_for_timeout(800)

            popup = await page.query_selector('.gm-style-iw, [class*="popup"], [role="dialog"]')
            if not popup:
                continue

            html = await popup.inner_html()
            text = await popup.inner_text()
            print(f"  → Canvas popup: {text[:80].strip()}")

            # ── Try MyMaps parser first, then generic parser ──
            mymaps_result = _parse_google_mymaps_panel(html)
            if mymaps_result:
                results.append(mymaps_result)
            else:
                parsed = parse_dealers_from_html(html)
                if parsed:
                    results.extend(parsed)
                elif extract_phones(text) or text.strip():
                    results.append({
                        'name':    text.split('\n')[0].strip(),
                        'address': '\n'.join(text.split('\n')[1:]).strip(),
                        'phone':   extract_phones(text),
                        'email':   extract_emails(text),
                        'source':  'canvas_raw',
                    })

            # ── Close using page (no marker_frame here) ──
            for close_sel in ['[aria-label="Close"]', '.gm-ui-hover-effect', 'button[jsaction*="close"]']:
                try:
                    btn = await page.query_selector(close_sel)
                    if btn:
                        await btn.evaluate("el => el.click()")
                        await page.wait_for_timeout(300)
                        break
                except:
                    continue

    return results

async def _debug_dump_frame_elements(frame, page):
    """
    Call this once to identify what elements appear after clicking a marker.
    Prints all visible elements with text content > 10 chars.
    """
    elements = await frame.evaluate("""() => {
        const results = [];
        document.querySelectorAll('*').forEach(el => {
            const text = el.innerText?.trim();
            const rect = el.getBoundingClientRect();
            if (
                text && text.length > 10 && text.length < 300 &&
                rect.width > 0 && rect.height > 0 &&
                !['SCRIPT','STYLE','HTML','BODY'].includes(el.tagName)
            ) {
                results.push({
                    tag: el.tagName,
                    id: el.id,
                    classes: el.className,
                    jsname: el.getAttribute('jsname') || '',
                    text: text.substring(0, 80)
                });
            }
        });
        return results.slice(0, 40);
    }""")
    
    print("\n[DEBUG FRAME ELEMENTS AFTER CLICK]")
    for el in elements:
        print(f"  <{el['tag']}> id='{el['id']}' class='{el['classes'][:50]}' jsname='{el['jsname']}' → {el['text'][:60]}")


async def _find_best_popup_candidate(
    marker_frame,
    page,
    popup_selectors,
):

    """
    Finds the BEST popup/sidebar container after marker click.

    Strategy:
    - search ALL selectors
    - search BOTH frame and page
    - collect ALL visible candidates
    - score semantically
    - prefer smallest meaningful container

    Returns:
        (best_element, best_context, debug_info)
    """

    SEMANTIC_LABELS = [
        'dealer',
        'dealer name',
        'showroom',
        'address',
        'phone',
        'mobile',
        'contact',
        'email',
        'branch',
        'location',
    ]

    best_el = None
    best_context = None
    best_score = -1
    best_area = float('inf')

    seen_texts = set()

    for sel in popup_selectors:

        for context, label in [
            (marker_frame, 'frame'),
            (page, 'page'),
        ]:

            try:
                elements = await context.query_selector_all(sel)

            except Exception:
                continue

            for el in elements:

                try:
                    if not await el.is_visible():
                        continue

                    text = (await el.inner_text()).strip()

                    if len(text) < 10:
                        continue

                    normalized = re.sub(r'\s+', ' ', text.lower())

                    # deduplicate repeated containers
                    if normalized in seen_texts:
                        continue

                    seen_texts.add(normalized)

                    phones = extract_phones(text)
                    emails = extract_emails(text)

                    semantic_hits = sum(
                        1
                        for word in SEMANTIC_LABELS
                        if word.lower() in normalized
                    )

                    box = await el.bounding_box()

                    if not box:
                        continue

                    area = box['width'] * box['height']

                    # ignore microscopic elements
                    if area < 100:
                        continue

                    score = 0

                    # semantic signals
                    score += len(phones) * 30
                    score += len(emails) * 30
                    score += semantic_hits * 10

                    # richer content
                    if len(text) > 100:
                        score += 10

                    if len(text) > 300:
                        score += 10

                    # structured sidebar hints
                    if 'dealer name' in normalized:
                        score += 20

                    if 'phone' in normalized:
                        score += 20

                    if 'address' in normalized:
                        score += 20

                    # penalize giant wrappers
                    if area > 700000:
                        score -= 40

                    # penalize tiny field rows
                    if area < 3000:
                        score -= 20

                    better = False

                    # primary: higher score
                    if score > best_score:
                        better = True

                    # tie-breaker:
                    # prefer smaller meaningful container
                    elif score == best_score and area < best_area:
                        better = True

                    if better:

                        best_el = el
                        best_context = context
                        best_score = score
                        best_area = area

                        print(
                            f"  → Candidate "
                            f"selector='{sel}' "
                            f"context={label} "
                            f"score={score} "
                            f"area={area:.0f}"
                        )

                except Exception:
                    continue

    return best_el, best_context, {
        'score': best_score,
        'area': best_area,
    }


def _parse_google_sidebar_structured(html: str) -> dict | None:

    """
    Parse structured Google My Maps sidebar panels.

    Example:

        Dealer Name -> Syakar Trading
        Address     -> Kathmandu
        Phone No.   -> 01-xxxxxxx

    Strategy:
    1. Extract label/value pairs
    2. Build a temporary semantic HTML block
    3. Reuse _block_to_dealer() for consistency
    """

    soup = BeautifulSoup(html, 'lxml')

    rows = soup.select('[class*="qqvbed-p83tee"]')

    if not rows:
        return None

    data = {}

    # =========================================================
    # Extract label/value pairs
    # =========================================================

    for row in rows:

        try:

            children = row.find_all(recursive=False)

            if len(children) < 2:
                continue

            label = clean(
                children[0].get_text(" ", strip=True)
            ).lower()

            value = clean(
                children[1].get_text(" ", strip=True)
            )

            if not label or not value:
                continue

            data[label] = value

        except Exception:
            continue

    if not data:
        return None

    # =========================================================
    # Convert structured rows into semantic HTML
    # so _block_to_dealer() can parse it naturally
    # =========================================================

    semantic_html = '<div class="dealer-card">'

    for label, value in data.items():

        semantic_html += f"""
            <div class="dealer-field">
                <span class="label">{label}</span>
                <span class="value">{value}</span>
            </div>
        """

    semantic_html += '</div>'

    semantic_soup = BeautifulSoup(
        semantic_html,
        'lxml'
    )

    card = semantic_soup.select_one('.dealer-card')

    if not card:
        return None

    dealer = _block_to_dealer(card)

    # =========================================================
    # Extra semantic enrichment
    # because Google labels are predictable
    # =========================================================

    for key, value in data.items():

        k = key.lower()

        # ─────────────────────────────
        # Name
        # ─────────────────────────────

        if (
            not dealer.get('name')
            and any(x in k for x in [
                'dealer',
                'showroom',
                'branch',
                'name',
            ])
        ):
            dealer['name'] = value

        # ─────────────────────────────
        # Address
        # ─────────────────────────────

        elif (
            not dealer.get('address')
            and any(x in k for x in [
                'address',
                'location',
                'city',
            ])
        ):
            dealer['address'] = value

        # ─────────────────────────────
        # Phone
        # ─────────────────────────────

        elif any(x in k for x in [
            'phone',
            'mobile',
            'contact',
            'tel',
        ]):

            phones = extract_phones(value)

            if phones:
                dealer.setdefault('phone', [])

                for p in phones:
                    if p not in dealer['phone']:
                        dealer['phone'].append(p)

        # ─────────────────────────────
        # Email
        # ─────────────────────────────

        elif 'email' in k:

            emails = extract_emails(value)

            if emails:
                dealer.setdefault('email', [])

                for e in emails:
                    if e not in dealer['email']:
                        dealer['email'].append(e)

    # =========================================================
    # Global fallback scan
    # =========================================================

    joined = ' '.join(data.values())

    if not dealer.get('phone'):
        dealer['phone'] = extract_phones(joined)

    if not dealer.get('email'):
        dealer['email'] = extract_emails(joined)

    # =========================================================
    # Normalize
    # =========================================================

    dealer['source'] = 'google_sidebar_structured'

    dealer.setdefault('name', '')
    dealer.setdefault('address', '')
    dealer.setdefault('phone', [])
    dealer.setdefault('email', [])

    # =========================================================
    # Validation
    # =========================================================

    if not any([
        dealer['name'],
        dealer['address'],
        dealer['phone'],
        dealer['email'],
    ]):
        return None

    return dealer


# async def _click_markers_and_extract(marker_frame, page, markers) -> list[dict]:
#     results = []
#     seen_positions = set()

#     POPUP_SELECTORS = [
#         '.gm-style-iw',
#         '.gm-style-iw-c',
#         '.gm-style-iw-d',

#         '.qqvbed-p83tee',
#         '[class*="qqvbed-p83tee"]',
#         '[class*="qqvbed"]',
#         '[jsname="WOdXFb"]',
#         '[class*="goog-container"]',
#         '.qqvbed-nUpftc',
        
#         '[class*="InfoWindow"]',
#         '[class*="infowindow"]',
#         '[class*="popup"]',
#         '[class*="Popup"]',
#         '.leaflet-popup-content',
#         '.mapboxgl-popup-content',
#         '[class*="sidebar"]',
#         '[class*="Sidebar"]',
#         '[class*="panel"]',
#         '[class*="detail"]',
#         '[role="dialog"]',
#         '[role="tooltip"]',
#     ]

#     async def close_popup():
#         for close_sel in [
#             '[aria-label="Close"]',
#             '.gm-ui-hover-effect',
#             'button[jsaction*="close"]',
#             '[data-dismiss]',
#         ]:
#             try:
#                 btn = await marker_frame.query_selector(close_sel)
#                 if btn:
#                     await btn.evaluate("el => el.click()")
#                     await page.wait_for_timeout(500)
#                     return
#             except:
#                 continue

#     original_url = page.url

#     # ── Snapshot BOTH the handle AND its bounding box ──
#     # Handle = use for direct JS click (most reliable)
#     # Box    = fallback if handle becomes stale after navigation
#     marker_snapshots = []  # list of (handle, box)
#     for marker in markers[:100]:
#         try:
#             box = await marker.bounding_box()
#             if not box or box['width'] < 4 or box['height'] < 4:
#                 continue
#             cell = (round(box['x'] / 5), round(box['y'] / 5))
#             if cell in seen_positions:
#                 continue
#             seen_positions.add(cell)
#             marker_snapshots.append((marker, box))
#         except:
#             continue

#     print(f"[CLICK] {len(marker_snapshots)} unique markers to process")

#     for i, (handle, box) in enumerate(marker_snapshots):
#         try:
#             print(f"[CLICK] Marker {i+1}/{len(marker_snapshots)} at ({box['x']:.0f}, {box['y']:.0f})")

#             # ── Click strategy: handle first, elementFromPoint as fallback ──
#             clicked = False

#             # Strategy 1: direct JS click on the stored handle (works even off-screen)
#             try:
#                 await handle.evaluate("el => el.click()")
#                 clicked = True
#             except Exception:
#                 pass  # handle is stale (post-navigation) — fall through

#             # Strategy 2: re-find the element by its stored coordinates
#             # NOTE: elementFromPoint in a frame uses the frame's OWN coordinate space,
#             # NOT the page viewport. The bounding_box() from a frame element IS already
#             # in the frame's coordinate space, so this is correct.
#             if not clicked:
#                 try:
#                     await marker_frame.evaluate(
#                         """([x, y]) => {
#                             const el = document.elementFromPoint(x, y);
#                             if (el) el.click();
#                         }""",
#                         [box['x'], box['y']]
#                     )
#                     clicked = True
#                 except Exception as e:
#                     print(f"  → Both click strategies failed: {e}")
#                     continue

#             await page.wait_for_timeout(2000)

#             # ── Find popup ──
#             popup = None
#             popup_source = None

#             for sel in POPUP_SELECTORS:
#                 for context, label in [(marker_frame, 'frame'), (page, 'page')]:
#                     try:
#                         elements = await context.query_selector_all(sel)
#                         if el and await el.is_visible():
#                             txt = (await el.inner_text()).strip()
#                             if len(txt) > 3:
#                                 popup = el
#                                 popup_source = context
#                                 print(f"  → Popup via '{sel}' in {label}")
#                                 break
#                     except:
#                         continue
#                 if popup:
#                     break

#             if not popup:
#                 print(f"  → No popup — scanning full frame HTML")
#                 try:
#                     frame_html = await marker_frame.content()
#                     parsed = parse_dealers_from_html(frame_html)
#                     if parsed:
#                         print(f"  → Extracted {len(parsed)} from full frame")
#                         results.extend(parsed)
#                 except:
#                     pass
#                 continue

#             html = await popup.inner_html()
#             text = await popup.inner_text()
#             print(f"  → Text preview: {text[:800].strip()}")

#             # ── Strategy A: Google My Maps structured panel ──
#             mymaps_result = _parse_google_mymaps_panel(html)
#             if mymaps_result:
#                 print(f"  → MyMaps: {mymaps_result['name']} | {mymaps_result['phone']}")
#                 results.append(mymaps_result)
#                 await close_popup()
#                 continue

#             # ── Strategy B: standard HTML parser ──
#             parsed = parse_dealers_from_html(html)
#             if parsed:
#                 print(f"  → HTML parser: {len(parsed)} dealer(s)")
#                 results.extend(parsed)
#                 await close_popup()
#                 continue

#             # ── Strategy C: follow detail link ──
#             links = await popup.query_selector_all('a[href]')
#             detail_found = False

#             for link in links:
#                 href = await link.get_attribute('href')
#                 if not href:
#                     continue

#                 if href.startswith('tel:'):
#                     phone = re.sub(r'\D', '', href.replace('tel:', ''))
#                     if phone:
#                         results.append({
#                             'name':    text.split('\n')[0].strip(),
#                             'address': '\n'.join(text.split('\n')[1:]).strip(),
#                             'phone':   [phone],
#                             'email':   [],
#                             'source':  'tel_link',
#                         })
#                     detail_found = True
#                     continue

#                 if href.startswith('mailto:'):
#                     continue

#                 try:
#                     print(f"  → Following detail link: {href[:60]}")
#                     await link.evaluate("el => el.click()")
#                     await page.wait_for_timeout(2500)

#                     if page.url != original_url:
#                         # Full navigation
#                         detail_html = await page.content()
#                         detail_parsed = parse_dealers_from_html(detail_html)
#                         if detail_parsed:
#                             print(f"  → Got {len(detail_parsed)} from detail page")
#                             results.extend(detail_parsed)
#                             detail_found = True
#                         await page.go_back()
#                         await page.wait_for_load_state('networkidle')
#                         await page.wait_for_timeout(1500)
#                         break
#                     else:
#                         # Hash routing (Subaru #/dealer/125)
#                         new_html = await page.content()
#                         new_parsed = parse_dealers_from_html(new_html)
#                         if new_parsed:
#                             results.extend(new_parsed)
#                             detail_found = True
#                         await page.evaluate(f"window.location.href = '{original_url}'")
#                         await page.wait_for_timeout(1500)
#                         break

#                 except Exception as e:
#                     print(f"  → Link error: {e}")
#                     continue

#             # ── Strategy D: raw fallback ──
#             if not detail_found:
#                 raw = {
#                     'name':    text.split('\n')[0].strip(),
#                     'address': '\n'.join(text.split('\n')[1:]).strip(),
#                     'phone':   extract_phones(text),
#                     'email':   extract_emails(text),
#                     'source':  'map_popup_raw',
#                 }
#                 print(f"  → Raw: {raw['name']} | phones: {raw['phone']}")
#                 results.append(raw)

#             await close_popup()

#         except Exception as e:
#             print(f"[CLICK] Error on marker {i+1}: {e}")
#             continue

#     return results
 
def is_placeholder(text: str) -> bool:
    t = text.strip().lower()
    return t in [
        "",
        "select",
        "select province",
        "select district",
        "select city",
        "choose",
        "all",
        "all provinces",
        "all districts",
        "all cities"
    ]
 
async def get_selected_option(select):
    return await select.evaluate("""
        el => {
            const opt = el.options[el.selectedIndex];
            return opt ? opt.innerText.trim().toLowerCase() : "";
        }
    """)

async def is_select_meaningful(page, select):
    options = await select.query_selector_all("option")

    texts = [
        (await opt.inner_text()).strip().lower()
        for opt in options
    ]

    # if only placeholders → useless
    if all(is_placeholder(t) for t in texts):
        return False

    # if only "all + same values" → useless
    if any("all" in t for t in texts) and len(texts) <= 2:
        return False

    return True


async def discover_map_entities(page, state):

    frames = [page] + list(page.frames)

    selectors = [
        'gmp-advanced-marker',
        '.leaflet-marker-icon',
        '.mapboxgl-marker',
        '.gm-style [role="button"]',
    ]

    for frame in frames:

        for selector in selectors:

            try:
                markers = await frame.query_selector_all(selector)

                if not markers:
                    continue

                # logger.info(
                #     f'[MAP] {selector} -> {len(markers)} markers'
                # )

                print(
                    f'[MAP] {selector} -> {len(markers)} markers'
                )

                await collect_marker_data(
                    page,
                    frame,
                    markers,
                    state,
                )

            except Exception as e:
                # logger.debug(f'[MAP] selector error: {e}')
                print(f'[MAP] selector error: {e}')

async def collect_marker_data(page, frame, markers, state):

    seen_positions = set()

    marker_snapshots = []

    for marker in markers[:100]:

        try:
            box = await marker.bounding_box()

            if not box:
                continue

            cell = (
                round(box['x'] / 5),
                round(box['y'] / 5),
            )

            if cell in seen_positions:
                continue

            seen_positions.add(cell)

            marker_snapshots.append((marker, box))

        except:
            continue

    for handle, box in marker_snapshots:

        try:
            try:
                await handle.evaluate('el => el.click()')
            except:
                await frame.evaluate(
                    '''([x, y]) => {
                        const el = document.elementFromPoint(x, y);
                        if (el) el.click();
                    }''',
                    [box['x'], box['y']]
                )

            popup = await wait_for_popup(page, frame)

            if not popup:
                continue

            await extract_popup_data(popup, state)

        except Exception as e:
            # logger.debug(f'[MAP] marker click failed: {e}')
            print(f'[MAP] marker click failed: {e}')

async def wait_for_popup(page, frame, timeout=5000):

    selectors = [
        '.gm-style-iw',
        '.leaflet-popup-content',
        '.mapboxgl-popup-content',
        '[role="dialog"]',
        '[class*="popup"]',
    ]

    for sel in selectors:

        for ctx in [frame, page]:

            try:
                popup = await ctx.wait_for_selector(
                    sel,
                    timeout=timeout,
                    state='visible',
                )

                if popup:
                    return popup

            except:
                continue

    return None

def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")



def normalize_phone_list(phone_field) -> list[str]:
    """
    Converts:
        "+977-9801234567"
        ["9801234567", "01-4412345"]
        "9801234567 / 9811111111"

    into normalized unique list.
    """

    if not phone_field:
        return []

    if not isinstance(phone_field, list):
        phone_field = [phone_field]

    numbers = []

    for item in phone_field:
        if not item:
            continue

        # split multiple numbers in same string
        parts = re.split(r"[,|;/\n]", str(item))

        for part in parts:
            digits = normalize_phone(part)

            if len(digits) < 7:
                continue

            numbers.append(digits)

    return sorted(set(numbers))


def completeness_score(dealer: dict) -> int:
    """
    Higher score = better dealer record.
    """

    score = 0

    # important fields
    if dealer.get("name"):
        score += 3

    if dealer.get("address"):
        score += 3

    if dealer.get("phone"):
        score += 5

    if dealer.get("email"):
        score += 2

    # bonus for multiple phones/emails
    score += len(dealer.get("phone", []))
    score += len(dealer.get("email", []))

    return score


def merge_dealers(old: dict, new: dict) -> dict:
    """
    Merge two dealer records intelligently.
    Keeps richer data from both.
    """

    merged = {
        "name": old.get("name") or new.get("name") or "",

        "address": (
            old.get("address")
            if len(old.get("address", "")) >= len(new.get("address", ""))
            else new.get("address", "")
        ),

        "phone": sorted(set(
            normalize_phone_list(old.get("phone")) +
            normalize_phone_list(new.get("phone"))
        )),

        "email": sorted(set(
            old.get("email", []) +
            new.get("email", [])
        )),

        "source": old.get("source") or new.get("source", "")
    }

    return merged


def deduplicate_dealers(dealers: list[dict]) -> list[dict]:
    """
    Deduplicate dealers using normalized phone numbers.

    Strategy:
        1. Normalize phones
        2. Create stable phone key
        3. Keep richest version
        4. Merge partial records
    """

    final = {}

    for d in dealers:

        # normalize phones
        normalized_phones = normalize_phone_list(
            d.get("phone")
        )

        # cannot deduplicate without phone
        if not normalized_phones:
            continue

        # stable hashable key
        phone_key = tuple(normalized_phones)

        # first occurrence
        if phone_key not in final:
            final[phone_key] = {
                **d,
                "phone": normalized_phones
            }
            continue

        existing = final[phone_key]

        # merge both
        merged = merge_dealers(existing, d)

        # keep better merged result
        existing_score = completeness_score(existing)
        merged_score = completeness_score(merged)

        if merged_score >= existing_score:
            final[phone_key] = merged

    return list(final.values())
 