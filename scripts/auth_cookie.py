from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COOKIE_PATH = PROJECT_ROOT / ".local" / "ipl_fantasy_cookie.txt"
DEFAULT_LOGIN_URL = "https://fantasy.iplt20.com/"


def load_saved_cookie(cookie_path: Path = DEFAULT_COOKIE_PATH) -> str | None:
    if not cookie_path.exists():
        return None

    cookie = cookie_path.read_text(encoding="utf-8").strip()
    return cookie or None


def save_cookie(cookie: str, cookie_path: Path = DEFAULT_COOKIE_PATH) -> None:
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(cookie.strip(), encoding="utf-8")


def build_cookie_header(cookies: list[dict[str, object]]) -> str:
    relevant_pairs: list[tuple[str, str]] = []
    seen_names: set[str] = set()

    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        domain = str(cookie.get("domain") or "")
        if not name or name in seen_names:
            continue
        if "iplt20.com" not in domain:
            continue
        relevant_pairs.append((name, value))
        seen_names.add(name)

    return "; ".join(f"{name}={value}" for name, value in relevant_pairs)


def capture_cookie_via_browser(
    cookie_path: Path = DEFAULT_COOKIE_PATH,
    login_url: str = DEFAULT_LOGIN_URL,
    headless: bool = False,
) -> str:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Install it with 'pip install playwright'."
        ) from exc

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()
            page.goto(login_url, wait_until="domcontentloaded")

            print("\nA browser window has opened for IPL fantasy login.")
            print("Finish logging in there, then return here and press Enter.")
            input()

            cookie = build_cookie_header(context.cookies())
            browser.close()
    except PlaywrightError as exc:
        raise RuntimeError(
            "Playwright could not launch Chromium. Run 'python -m playwright install chromium' "
            "inside this repo's virtual environment and try again."
        ) from exc

    if not cookie:
        raise RuntimeError(
            "No IPL cookies were captured from the browser session. Make sure you finish logging in before pressing Enter."
        )

    save_cookie(cookie, cookie_path)
    return cookie