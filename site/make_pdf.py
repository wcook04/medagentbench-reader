"""Print the page to site/medagentbench-potassium-task.pdf with Chromium.

  python3 site/make_pdf.py

Needs the Python package `playwright` and its Chromium (`python3 -m playwright install chromium`).
Run `python3 site/build.py` first: the PDF is site/index.html under its print stylesheet (the
`@media print` rules in page.css), on A4, with every collapsed part opened, all six runs shown
and the interactive controls left out. The page is served from a local port for the printing, so
that its fonts and scripts load as they do on the web.
"""
import functools, http.server, pathlib, threading

from playwright.sync_api import sync_playwright

SITE = pathlib.Path(__file__).resolve().parent
OUT = SITE / "medagentbench-potassium-task.pdf"
TITLE = "How MedAgentBench’s potassium task is evaluated"
ADDRESS = "wcook04.github.io/medagentbench-reader"
STRIP = ("font-family: Helvetica, Arial, sans-serif; font-size: 7.5pt; color: #6d6473; width: 100%; "
         "padding: 0 22mm; display: flex; justify-content: space-between;")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(color_scheme="light")
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html", wait_until="networkidle")
            page.evaluate("""async () => {
                document.documentElement.dataset.theme = 'light';
                for (const d of document.querySelectorAll('details')) d.open = true;
                for (const c of document.querySelectorAll('.case[hidden]')) c.hidden = false;
                await document.fonts.ready;
            }""")
            page.emulate_media(media="print", color_scheme="light")
            page.pdf(
                path=str(OUT), format="A4", print_background=True, prefer_css_page_size=True, display_header_footer=True,
                header_template=f'<div style="{STRIP}"><span>{TITLE}</span><span>Will Cook, 18 November 2026</span></div>',
                footer_template=f'<div style="{STRIP}"><span>{ADDRESS}</span><span>page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>',
            )
            browser.close()
    finally:
        server.shutdown()
    print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
