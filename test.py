from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

from camoufox.sync_api import Camoufox
from playwright.sync_api import (
    Page,
    BrowserContext,
    Locator,
    TimeoutError as PlaywrightTimeoutError,
)

BASE_URL = "https://divulgacione14congreso.registraduria.gov.co/departamento/01"
DOWNLOAD_DIR = Path("downloads_e14")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

CORPORATION_TEXT = "CONSULTAS"

# =========================
# XPaths
# =========================

XPATH_CORP_INPUT = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/div/div[1]/app-custom-select/div/div[1]/input"
XPATH_CORP_LIST = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/div/div[1]/app-custom-select/div/div[2]/ul"

XPATH_MUNIC_INPUT = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/div/div[2]/app-custom-select/div/div[1]/input"
XPATH_MUNIC_LIST = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/div/div[2]/app-custom-select/div/div[2]/ul"

XPATH_ZONE_INPUT = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/div/div[3]/app-custom-select/div/div[1]/input"
XPATH_ZONE_LIST = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/div/div[3]/app-custom-select/div/div[2]/ul"

XPATH_POST_INPUT = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/div/div[4]/app-custom-select/div/div[1]/input"
XPATH_POST_LIST = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/div/div[4]/app-custom-select/div/div[2]/ul"

# Ajusta si tu botón real de buscar es otro
XPATH_SEARCH_BUTTON = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/div/div[5]/app-custom-button/div/button"

RESULTS_CONTAINER_XPATH = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/div[2]/div[2]"
PAGINATOR_CONTAINER_XPATH = "//div[contains(@class,'container')][.//div[contains(@class,'page')]]"
RESULT_PDF_BUTTONS_XPATH = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/div[2]/div[2]/div/div[2]/div/span/img"

# Modal de descarga completada
XPATH_DOWNLOAD_OK_BUTTON = "/html/body/app-root/div/div/div/div[2]/app-department/div[2]/div/app-consult/app-custom-modal[1]/div/div[2]/div/app-custom-button/div/button"

DEFAULT_TIMEOUT_MS = 30_000
NAVIGATION_TIMEOUT_MS = 90_000


# =========================
# Helpers básicos
# =========================

def xpath(page: Page, value: str) -> Locator:
    return page.locator(f"xpath={value}")


def wait_small(seconds: float = 0.6):
    time.sleep(seconds)


def slugify(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[^\w\s\-]+", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "_", text)
    return text[:180] or "empty"


def safe_filename(*parts: str, suffix: str = ".pdf") -> str:
    joined = "__".join(slugify(p) for p in parts if p and p.strip())
    return f"{joined}{suffix}"


def boot_page(page: Page):
    page.set_default_timeout(DEFAULT_TIMEOUT_MS)
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

    page.goto(BASE_URL, wait_until="commit", timeout=NAVIGATION_TIMEOUT_MS)
    xpath(page, XPATH_CORP_INPUT).wait_for(state="visible", timeout=NAVIGATION_TIMEOUT_MS)
    time.sleep(3)


def close_any_open_dropdown(page: Page):
    try:
        page.keyboard.press("Escape")
        wait_small(0.2)
    except Exception:
        pass


def clear_and_type(locator: Locator, value: str):
    locator.click()
    locator.press("Control+a")
    locator.press("Backspace")
    locator.type(value, delay=30)


# =========================
# Limpieza de textos
# =========================

def normalize_spaces(text: str) -> str:
    return " ".join(text.split()).strip()


def clean_generic_option_text(raw: str) -> str:
    raw = normalize_spaces(raw)
    raw = re.sub(r"\s*\(\d+%\)\s*$", "", raw)
    return raw.strip()


def extract_name_after_dash_before_paren(raw: str) -> str:
    """
    Ejemplo:
    '004 — ABEJORRAL (100%)' -> 'ABEJORRAL'
    '073 - CAMPAMENTO (100%)' -> 'CAMPAMENTO'
    """
    raw = normalize_spaces(raw)
    m = re.search(r"^\s*\d+\s*[—-]\s*(.*?)\s*(?:\(\d+%\))?\s*$", raw)
    if m:
        return m.group(1).strip()
    return clean_generic_option_text(raw)


# =========================
# Dropdowns
# =========================

def wait_dropdown_options(page: Page, list_xpath: str, min_items: int = 1, timeout_ms: int = 30_000):
    page.wait_for_function(
        """
        ([xp, minItems]) => {
            const result = document.evaluate(
                xp,
                document,
                null,
                XPathResult.FIRST_ORDERED_NODE_TYPE,
                null
            );
            const ul = result.singleNodeValue;
            if (!ul) return false;
            const items = ul.querySelectorAll("li, p");
            return items.length >= minItems;
        }
        """,
        arg=[list_xpath, min_items],
        timeout=timeout_ms,
    )


def get_options_texts(
    page: Page,
    input_xpath: str,
    list_xpath: str,
    mode: str = "generic",
) -> list[str]:
    """
    mode:
      - generic: texto limpio normal
      - after_dash: toma lo que va después de — y antes de (
    """
    close_any_open_dropdown(page)

    input_loc = xpath(page, input_xpath)
    input_loc.wait_for(state="visible")
    input_loc.click()
    wait_small(0.5)

    wait_dropdown_options(page, list_xpath, min_items=1, timeout_ms=30_000)

    list_loc = xpath(page, list_xpath)
    list_loc.wait_for(state="visible", timeout=30_000)

    items = list_loc.locator("li, p")
    result: list[str] = []

    count = items.count()
    for i in range(count):
        txt = items.nth(i).inner_text().strip()
        if not txt:
            continue

        if mode == "after_dash":
            cleaned = extract_name_after_dash_before_paren(txt)
        else:
            cleaned = clean_generic_option_text(txt)

        if cleaned:
            result.append(cleaned)

    close_any_open_dropdown(page)
    return list(dict.fromkeys(result))


def select_option_from_dropdown(
    page: Page,
    input_xpath: str,
    list_xpath: str,
    option_text: str,
):
    close_any_open_dropdown(page)

    input_loc = xpath(page, input_xpath)
    input_loc.wait_for(state="visible", timeout=30_000)
    input_loc.click()
    wait_small(0.3)

    clear_and_type(input_loc, option_text)
    wait_dropdown_options(page, list_xpath, min_items=1, timeout_ms=30_000)

    list_loc = xpath(page, list_xpath)
    list_loc.wait_for(state="visible", timeout=30_000)

    option = list_loc.get_by_text(option_text, exact=False)
    if option.count() == 0:
        raise RuntimeError(f"No encontré la opción '{option_text}' en el dropdown.")

    option.first.click()
    wait_small(0.8)


def get_dropdown_snapshot(page: Page, input_xpath: str, list_xpath: str) -> list[str]:
    try:
        return get_options_texts(page, input_xpath, list_xpath, mode="generic")
    except Exception:
        return []


def select_municipality(page: Page, municipality_name: str):
    old_zone_snapshot = get_dropdown_snapshot(page, XPATH_ZONE_INPUT, XPATH_ZONE_LIST)

    select_option_from_dropdown(page, XPATH_MUNIC_INPUT, XPATH_MUNIC_LIST, municipality_name)

    page.wait_for_function(
        """
        ([xp, oldItems]) => {
            const result = document.evaluate(
                xp,
                document,
                null,
                XPathResult.FIRST_ORDERED_NODE_TYPE,
                null
            );
            const ul = result.singleNodeValue;
            if (!ul) return false;
            const items = [...ul.querySelectorAll("li, p")].map(x => x.textContent.trim()).filter(Boolean);
            return items.length > 0 && JSON.stringify(items) !== JSON.stringify(oldItems);
        }
        """,
        arg=[XPATH_ZONE_LIST, old_zone_snapshot],
        timeout=30_000,
    )
    wait_small(0.8)


def select_zone(page: Page, zone_name: str):
    old_post_snapshot = get_dropdown_snapshot(page, XPATH_POST_INPUT, XPATH_POST_LIST)

    select_option_from_dropdown(page, XPATH_ZONE_INPUT, XPATH_ZONE_LIST, zone_name)

    page.wait_for_function(
        """
        ([xp, oldItems]) => {
            const result = document.evaluate(
                xp,
                document,
                null,
                XPathResult.FIRST_ORDERED_NODE_TYPE,
                null
            );
            const ul = result.singleNodeValue;
            if (!ul) return false;
            const items = [...ul.querySelectorAll("li, p")].map(x => x.textContent.trim()).filter(Boolean);
            return items.length > 0 && JSON.stringify(items) !== JSON.stringify(oldItems);
        }
        """,
        arg=[XPATH_POST_LIST, old_post_snapshot],
        timeout=30_000,
    )
    wait_small(0.8)


def select_post(page: Page, post_name: str):
    select_option_from_dropdown(page, XPATH_POST_INPUT, XPATH_POST_LIST, post_name)
    wait_small(0.5)


def set_corporation(page: Page):
    select_option_from_dropdown(page, XPATH_CORP_INPUT, XPATH_CORP_LIST, CORPORATION_TEXT)
    wait_small(1.0)


# =========================
# Resultados / búsqueda
# =========================

def click_search(page: Page):
    button = xpath(page, XPATH_SEARCH_BUTTON)
    button.wait_for(state="visible", timeout=30_000)
    button.click()
    wait_small(1.0)


def wait_results_loaded(page: Page):
    container = xpath(page, RESULTS_CONTAINER_XPATH)
    container.wait_for(state="visible", timeout=30_000)

    page.wait_for_function(
        """
        (xp) => {
            const result = document.evaluate(
                xp,
                document,
                null,
                XPathResult.FIRST_ORDERED_NODE_TYPE,
                null
            );
            const node = result.singleNodeValue;
            if (!node) return false;
            return node.querySelectorAll("img").length > 0 || node.textContent.trim().length > 0;
        }
        """,
        arg=RESULTS_CONTAINER_XPATH,
        timeout=30_000,
    )
    wait_small(1.0)


def get_paginator_labels(page: Page) -> list[str]:
    paginator = xpath(page, PAGINATOR_CONTAINER_XPATH)
    if paginator.count() == 0:
        return ["01"]

    pages = paginator.locator(".page")
    result: list[str] = []

    count = pages.count()
    for i in range(count):
        txt = pages.nth(i).inner_text().strip()
        if txt:
            result.append(txt)

    return result or ["01"]


def click_paginator_page(page: Page, label: str):
    paginator = xpath(page, PAGINATOR_CONTAINER_XPATH)
    if paginator.count() == 0:
        return

    target = paginator.locator(".page", has_text=label)
    if target.count() == 0:
        raise RuntimeError(f"No encontré la página '{label}' en el paginador.")

    old_html = xpath(page, RESULTS_CONTAINER_XPATH).inner_html()

    target.first.click()

    page.wait_for_function(
        """
        ([xp, oldHtml]) => {
            const result = document.evaluate(
                xp,
                document,
                null,
                XPathResult.FIRST_ORDERED_NODE_TYPE,
                null
            );
            const node = result.singleNodeValue;
            if (!node) return false;
            return node.innerHTML !== oldHtml;
        }
        """,
        arg=[RESULTS_CONTAINER_XPATH, old_html],
        timeout=30_000,
    )
    wait_small(1.0)


def get_pdf_buttons(page: Page) -> Locator:
    return xpath(page, RESULT_PDF_BUTTONS_XPATH)


# =========================
# Modal descarga ok
# =========================

def close_download_modal_if_present(page: Page):
    try:
        btn = xpath(page, XPATH_DOWNLOAD_OK_BUTTON)
        if btn.count() > 0 and btn.first.is_visible(timeout=1500):
            btn.first.click()
            wait_small(0.8)
            return
    except Exception:
        pass

    # fallback: escape por si el modal sigue abierto
    try:
        page.keyboard.press("Escape")
        wait_small(0.3)
    except Exception:
        pass


# =========================
# Descargas
# =========================

def save_pdf_from_result(
    page: Page,
    context: BrowserContext,
    result_index: int,
    municipality: str,
    zone: str,
    post: str,
    page_label: str,
):
    buttons = get_pdf_buttons(page)
    total = buttons.count()

    if result_index >= total:
        return

    button = buttons.nth(result_index)

    file_name = safe_filename(
        municipality,
        zone,
        post,
        f"page_{page_label}",
        f"item_{result_index + 1:02d}",
    )
    target_path = DOWNLOAD_DIR / file_name

    downloaded = False

    # Intento 1: descarga directa
    try:
        with page.expect_download(timeout=7000) as download_info:
            button.click()
        download = download_info.value
        download.save_as(str(target_path))
        downloaded = True
        print(f"[OK] Descarga directa: {target_path}")
    except Exception:
        pass

    # Intento 2: popup / nueva pestaña
    if not downloaded:
        try:
            with context.expect_page(timeout=7000) as page_info:
                button.click()
            pdf_page = page_info.value
            pdf_page.wait_for_load_state("load", timeout=15_000)

            pdf_url = pdf_page.url
            if pdf_url and pdf_url.startswith("http"):
                response = context.request.get(pdf_url, timeout=20_000)
                if response.ok:
                    target_path.write_bytes(response.body())
                    downloaded = True
                    print(f"[OK] PDF desde popup: {target_path}")
                else:
                    print(f"[WARN] Popup abierto pero response no OK: {pdf_url}")
            else:
                print(f"[WARN] Popup sin URL usable: {pdf_url}")

            try:
                pdf_page.close()
            except Exception:
                pass

        except Exception as e:
            print(f"[WARN] No pude descargar item {result_index + 1}: {e}")

    # Cerrar el modal/aviso si aparece
    close_download_modal_if_present(page)
    wait_small(0.5)


def process_current_results(
    page: Page,
    context: BrowserContext,
    municipality: str,
    zone: str,
    post: str,
):
    wait_results_loaded(page)

    paginator_labels = get_paginator_labels(page)

    for page_label in paginator_labels:
        print(f"      [PAGINA] {page_label}")
        click_paginator_page(page, page_label)

        buttons = get_pdf_buttons(page)
        count = buttons.count()
        print(f"        [ITEMS] {count}")

        for idx in range(count):
            save_pdf_from_result(
                page=page,
                context=context,
                result_index=idx,
                municipality=municipality,
                zone=zone,
                post=post,
                page_label=page_label,
            )


# =========================
# Flujo principal
# =========================

def run():
    with Camoufox(
        headless=False,
        humanize=True,
        geoip=True,
    ) as browser:
        context = browser.new_context(
            accept_downloads=True,
        )
        page = context.new_page()

        boot_page(page)

        # 1) Seleccionar corporación
        set_corporation(page)

        # 2) Leer municipios: solo nombre después de dash y antes del paréntesis
        municipalities = get_options_texts(
            page,
            XPATH_MUNIC_INPUT,
            XPATH_MUNIC_LIST,
            mode="after_dash",
        )
        print(f"[INFO] Municipios detectados: {len(municipalities)}")

        for municipality in municipalities:
            print(f"[MUNICIPIO] {municipality}")

            try:
                select_municipality(page, municipality)

                # 3) Leer zonas
                zones = get_options_texts(
                    page,
                    XPATH_ZONE_INPUT,
                    XPATH_ZONE_LIST,
                    mode="generic",
                )
                print(f"  [INFO] Zonas detectadas: {len(zones)}")

                for zone in zones:
                    print(f"  [ZONA] {zone}")

                    try:
                        select_zone(page, zone)

                        # 4) Leer puestos: solo nombre después de dash y antes del paréntesis
                        posts = get_options_texts(
                            page,
                            XPATH_POST_INPUT,
                            XPATH_POST_LIST,
                            mode="after_dash",
                        )
                        print(f"    [INFO] Puestos detectados: {len(posts)}")

                        for post in posts:
                            print(f"    [PUESTO] {post}")

                            try:
                                select_post(page, post)
                                click_search(page)
                                process_current_results(
                                    page=page,
                                    context=context,
                                    municipality=municipality,
                                    zone=zone,
                                    post=post,
                                )
                            except Exception as e:
                                print(f"    [ERROR] puesto '{post}': {e}")

                    except Exception as e:
                        print(f"  [ERROR] zona '{zone}': {e}")

            except Exception as e:
                print(f"[ERROR] municipio '{municipality}': {e}")

        context.close()


if __name__ == "__main__":
    run()