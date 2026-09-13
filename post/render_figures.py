"""Render each [data-fig] element of figures.html to its own PNG.

Captured at element level rather than through a fixed viewport, so a figure is sized by its own
content and nothing needs cropping by hand.
"""
import argparse
import pathlib

HERE = pathlib.Path(__file__).parent
SOURCE = HERE / "figures.html"
OUT = HERE / "figures"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=2,
                    help="device pixel ratio; 2 keeps the text crisp when the platform scales it down")
    ap.add_argument("--only", help="render just this one figure")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    OUT.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1760, "height": 1200},
                                device_scale_factor=args.scale)
        page.goto(SOURCE.resolve().as_uri())
        # Webfonts land after load, and a figure captured before they do renders in a fallback
        # face, which is obvious the moment two figures sit next to each other in an article.
        page.wait_for_function("document.fonts.status === 'loaded'", timeout=30_000)

        names = page.eval_on_selector_all("[data-fig]", "els => els.map(e => e.dataset.fig)")
        for name in names:
            if args.only and name != args.only:
                continue
            element = page.query_selector(f'[data-fig="{name}"]')
            box = element.bounding_box()
            element.screenshot(path=str(OUT / f"{name}.png"))
            print(f"  {name}.png  {int(box['width'])}x{int(box['height'])} css px "
                  f"({int(box['width']) * args.scale}px wide)")
        browser.close()
    print(f"\n{len(names)} figures in {OUT}")


if __name__ == "__main__":
    main()
