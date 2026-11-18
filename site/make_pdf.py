"""Typeset the page as a paper: site/medagentbench-potassium-task.pdf.

  python3 site/make_pdf.py [--keep BUILD_DIR]

Run `python3 site/build.py` first. Needs Pandoc, Tectonic and the Python package `playwright` with its
Chromium (`python3 -m playwright install chromium`).

The PDF is set by LaTeX, the same way as a paper: Pandoc writes the LaTeX and Tectonic typesets it, on A4
at 11pt with numbered sections, a structured abstract, numbered references and a glossary. Its text is
the page's text. The steps:

  1. Chromium opens site/index.html and saves each figure as an image.
  2. The article is rewritten in the browser into plain HTML: figures become those images, bars become
     their numbers, interactive controls are removed, and every table is given the column widths it has
     on the page.
  3. Pandoc turns that HTML into LaTeX with site/paper_preamble.tex, and Tectonic sets the PDF.

Two things on the web page are left out of the PDF: the interactive controls of the map of 629 runs, and
the agent's messages exactly as sent under each of the six runs (the steps of each run are kept).
"""
import argparse, functools, http.server, pathlib, re, shutil, subprocess, tempfile, threading

from playwright.sync_api import sync_playwright

SITE = pathlib.Path(__file__).resolve().parent
OUT = SITE / "medagentbench-potassium-task.pdf"
PREAMBLE = SITE / "paper_preamble.tex"
WEB = "https://wcook04.github.io/medagentbench-reader/"
REPO = "https://github.com/wcook04/medagentbench-reader"

# Before the figures are saved: open every collapsed part, show all six runs, white ground, no controls.
PREPARE = """() => {
  document.documentElement.dataset.theme = 'light';
  for (const d of document.querySelectorAll('details')) d.open = true;
  for (const c of document.querySelectorAll('.case[hidden]')) c.hidden = false;
  const style = document.createElement('style');
  style.textContent = `
    :root { --ground: #ffffff !important; --surface: #ffffff !important; }
    body, figure, .flow, .case, .lead { background: #ffffff !important; }
    .top, .toc, .casetabs, .map__lead, .map__bar, .map__panel, .term-tip, figure figcaption { display: none !important; }
    .layout { display: block !important; }
    .case { border: 0 !important; padding: 0 !important; }
  `;
  document.head.appendChild(style);
  const main = document.querySelector('main');
  // Column widths of every table as the page lays them out, kept for the paper.
  for (const t of main.querySelectorAll('table')) {
    let best = null;
    for (const r of t.rows) {
      const plain = [...r.cells].every(c => c.colSpan === 1);
      if (plain && (!best || r.cells.length > best.cells.length)) best = r;
    }
    if (!best) continue;
    const w = [...best.cells].map(c => c.getBoundingClientRect().width);
    const total = w.reduce((a, b) => a + b, 0);
    t.dataset.cols = w.map(x => (100 * x / total).toFixed(1)).join(',');
  }
  let k = 0;
  for (const el of main.querySelectorAll('figure, .flow')) el.dataset.fig = String(++k);
  return k;
}"""

# After the figures are saved: rewrite the article into plain HTML that Pandoc reads as a paper.
REWRITE = """() => {
  const main = document.querySelector('main');
  const q = (s, r = main) => [...r.querySelectorAll(s)];
  const text = s => document.createTextNode(s);
  const abstract = document.querySelector('#paper-abstract').innerHTML;
  const subtitle = main.querySelector('.subtitle').textContent.trim();
  const title = main.querySelector('h1').textContent.trim();

  for (const el of q('[data-fig]')) {
    const cap = el.querySelector('figcaption');
    const lead = el.querySelector('.map__lead');
    let caption = cap ? cap.innerHTML : '';
    caption = caption.replace('When a square is selected, the same patient’s other squares are marked. ', '');
    if (lead) {
      caption = 'All 629 action-required instances, one square each, in three groups by the length of the patient’s '
        + 'potassium history and, inside a group, by patient. The colour of a square is the outcome of the model’s run '
        + 'on that instance with the default sort order. ' + caption;
    }
    // A figure with a caption becomes a numbered figure. One without is set as a plain image.
    const fig = document.createElement(caption ? 'figure' : 'p');
    fig.innerHTML = '<img src="fig-' + el.dataset.fig + '.png" width="100%">' + (caption ? '<figcaption>' + caption + '</figcaption>' : '');
    el.replaceWith(fig);
  }

  q('.head, .actions, .foot, .casetabs, .print-only, .skip, template, .map__bar, .map__panel').forEach(e => e.remove());

  for (const d of q('details.msgs')) {
    const p = document.createElement('p');
    p.innerHTML = '<i>The agent’s messages, exactly as sent, are on the web version.</i>';
    d.replaceWith(p);
  }
  for (const d of q('details')) {
    const wrap = document.createElement('div');
    const s = d.querySelector('summary');
    if (s) { const p = document.createElement('p'); p.innerHTML = '<b>' + s.textContent.trim() + '</b>'; wrap.appendChild(p); s.remove(); }
    while (d.firstChild) wrap.appendChild(d.firstChild);
    d.replaceWith(wrap);
  }

  for (const m of q('.m')) {
    const n = m.querySelector('.m__n'), p = m.querySelector('.m__p');
    const pt = p ? p.textContent.trim() : '';
    m.replaceWith(text((n ? n.textContent.trim() : '') + (pt && pt !== '–' ? ' (' + pt + ')' : '')));
  }
  for (const a of q('a.term')) a.replaceWith(...a.childNodes);
  for (const m of q('.more')) {
    const a = m.matches('a') ? m : m.querySelector('a');
    const s = document.createElement('span');
    const label = m.textContent.replace(/^[^A-Za-z]+/, '').trim();
    s.innerHTML = a ? ' See <a href="' + a.getAttribute('href') + '">' + label + '</a>.' : ' See ' + label + '.';
    m.replaceWith(s);
  }
  for (const s of q('th .sub')) s.textContent = ' (' + s.textContent.trim() + ')';
  // The verdicts of a run: "Relaxed grader: fail. No order was submitted."
  for (const dl of q('dl.scores')) {
    for (const v of dl.querySelectorAll('dd .v')) { const b = document.createElement('i'); b.textContent = v.textContent.trim() + '.'; v.replaceWith(b); }
  }
  for (const d of q('dl > div')) d.replaceWith(...d.childNodes);

  for (const li of q('ol.steps > li')) {
    const who = li.querySelector('.step__who');
    if (who) { const b = document.createElement('b'); b.textContent = who.textContent.trim() + '. '; who.replaceWith(b); }
    for (const c of li.querySelectorAll('code')) c.after(text(' '));
    for (const s of li.querySelectorAll('.step__back, .said')) s.before(text(' '));
  }
  // A label directly above a table with no caption becomes that table's caption, so that the two stay on one page.
  for (const l of q('p.lbl')) {
    const t = l.nextElementSibling;
    if (t && t.matches('table') && !t.querySelector('caption')) {
      const cap = document.createElement('caption'); cap.textContent = l.textContent.trim();
      t.prepend(cap); l.remove();
    }
  }
  for (const l of q('p.lbl')) l.innerHTML = '<b>' + l.textContent.trim() + '</b>';
  for (const l of q('span.lbl')) { const b = document.createElement('b'); b.textContent = l.textContent.trim() + '. '; l.replaceWith(b); }

  for (const t of q('table')) {
    const cols = (t.dataset.cols || '').split(',').filter(Boolean);
    if (!cols.length) continue;
    const g = document.createElement('colgroup');
    g.innerHTML = cols.map(c => '<col width="' + c + '%" style="width: ' + c + '%">').join('');
    const old = t.querySelector('colgroup'); if (old) old.remove();
    const cap = t.querySelector('caption');
    if (cap) cap.after(g); else t.prepend(g);
  }

  // Straight double quotes in running text. LaTeX would set both of a pair as closing quotes, so a JSON
  // object is set as code and any other quoted word gets an opening and a closing quote.
  {
    const walk = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
    const nodes = [];
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (n.nodeValue.includes('"') && !n.parentElement.closest('code, pre, svg, script, style')) nodes.push(n);
    }
    for (const n of nodes) {
      const span = document.createElement('span');
      for (const piece of n.nodeValue.split(/(\\{"[^{}]*\\})/)) {
        if (/^\\{"[^{}]*\\}$/.test(piece)) { const c = document.createElement('code'); c.textContent = piece; span.appendChild(c); }
        else span.appendChild(text(piece.replace(/"([^"]*)"/g, '“$1”')));
      }
      n.replaceWith(...span.childNodes);
    }
  }

  // A line under a table that is only a link to the table's source: "Source: the task file ...".
  for (const p of q('p.src')) {
    const a = p.querySelector('a');
    if (!a || p.textContent.trim() !== a.textContent.trim()) continue;
    const t = a.textContent.trim();
    a.textContent = t[0].toLowerCase() + t.slice(1);
    a.before(text('Source: ')); a.after(text('.'));
  }
  // A row that names a group of rows is set in bold.
  for (const th of q('tr.grp > th')) th.innerHTML = '<b>' + th.innerHTML + '</b>';

  // The web text says "this page". In the PDF that would mean one sheet, so it becomes "this document".
  // The section on how the work was made also names the web page itself, and that is kept as "the web page".
  const reword = (root, pairs) => {
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      let s = n.nodeValue;
      for (const [a, b] of pairs) s = s.split(a).join(b);
      if (s !== n.nodeValue) n.nodeValue = s;
    }
  };
  const firstCaption = (main.querySelector('figure > figcaption') || {}).textContent || '';
  reword(main, [['On this page', 'In this document'], ['on this page', 'in this document'],
                ['This page', 'This document'], ['this page', 'this document']]);
  const made = main.querySelector('#made');
  if (made) reword(made, [['every count on the page', 'every count in the text'],
                          ['The page was then checked', 'The web page was then checked'],
                          ['One read the page from the top', 'One read the web page from the top'],
                          ['drawn at the top of the page', 'drawn in Figure 1']]);
  const madeText = made ? made.textContent.replace(/\\s+/g, ' ') : '';
  const leftover = (main.textContent.replace(/\\s+/g, ' ').match(/.{0,40}\\b[Tt]his page\\b.{0,20}/g) || [])
    .concat(madeText.match(/.{0,40}(?<!web|first|one|a|later|second) page\\b(?! size).{0,20}/g) || []);

  // The glossary's note is about hovering on the web page.
  q('#glossary > p.note').forEach(e => e.remove());
  // Long addresses in the references may break after a slash, a hyphen or an underscore.
  for (const a of q('ol.refs a')) {
    if (/[\\/]/.test(a.textContent)) a.textContent = a.textContent.replace(/([\\/\\-_])/g, '$1\\u200b');
  }

  // Section ids move onto their headings, so that links inside the PDF land on them.
  for (const sec of q('section[id]')) {
    const h = sec.querySelector('h2');
    if (h) { h.id = sec.id; sec.removeAttribute('id'); if (['refs', 'glossary'].includes(h.id)) h.className = 'unnumbered'; }
  }
  for (const li of q('ol.refs > li[id]')) { li.insertAdjacentHTML('afterbegin', '<span id="' + li.id + '"></span>'); li.removeAttribute('id'); }
  const lede = main.querySelector('.lede');
  if (lede) { const h = document.createElement('h2'); h.textContent = 'The finding'; h.id = lede.id || 'finding'; lede.removeAttribute('id'); lede.before(h); }

  return { title, subtitle, abstract, body: main.innerHTML, leftover, firstCaption };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def keep_short_tables_whole(tex):
    """A table whose rows hold under 1,000 characters of LaTeX (about 17 printed lines at most) is not split
    across two pages. In a longtable, a row that ends with `\\\\*` cannot be followed by a page break."""
    def one(m):
        head, sep, body = m.group(0).partition("\\endlastfoot")
        if not sep or len(body) >= 1000:
            return m.group(0)
        rows = re.split(r"(\\\\[ \t]*\n)", body)
        ends = [k for k, part in enumerate(rows) if re.fullmatch(r"\\\\[ \t]*\n", part)]
        for k in ends[:-1]:
            rows[k] = "\\\\*\n"
        return head + sep + "".join(rows)
    return re.sub(r"\\begin\{longtable\}.*?\\end\{longtable\}", one, tex, flags=re.S)


def keep_labels_with_their_text(tex):
    """A paragraph that is only a bold label ("Instruction") is not the last line of a page."""
    return re.sub(r"(?m)^(\\textbf\{[^{}\n]{1,80}\})\n\n", r"\1\\par\\nopagebreak\n\n", tex)


def run(cmd, **kw):
    done = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if done.returncode:
        raise SystemExit(f"{cmd[0]} failed:\n{done.stdout[-3000:]}\n{done.stderr[-3000:]}")
    return done.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", help="write the intermediate files to this folder and keep them")
    a = ap.parse_args()
    build = pathlib.Path(a.keep) if a.keep else pathlib.Path(tempfile.mkdtemp(prefix="medagentbench-paper-"))
    build.mkdir(parents=True, exist_ok=True)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            # 780px wide: the article is then about as wide as the printed column, so the text inside the figures
            # comes out near 8pt and the tables are measured at the proportions they will be set in.
            page = browser.new_page(color_scheme="light", device_scale_factor=3, viewport={"width": 780, "height": 900})
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html", wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            figures = page.evaluate(PREPARE)
            for k in range(1, figures + 1):
                page.locator(f'[data-fig="{k}"]').screenshot(path=str(build / f"fig-{k}.png"))
            parts = page.evaluate(REWRITE)
            browser.close()
    finally:
        server.shutdown()

    if parts["leftover"]:
        raise SystemExit("the PDF text still names the web page as 'this page' or 'the page':\n  " + "\n  ".join(parts["leftover"]))
    if not parts["firstCaption"].startswith("One derived instance"):
        raise SystemExit("Figure 1 is no longer the chart of one derived instance, and the text refers to it as Figure 1: "
                         + parts["firstCaption"][:80])

    (build / "abstract.html").write_text(parts["abstract"], encoding="utf-8")
    abstract_md = run(["pandoc", "-f", "html", "-t", "markdown", str(build / "abstract.html")])
    note = (f'<p><i>This is the PDF edition of the web page at <a href="{WEB}">{WEB.removeprefix("https://").rstrip("/")}</a>, '
            f'which has the interactive figures. Code, proofs and data: <a href="{REPO}">{REPO.removeprefix("https://")}</a>. '
            'The analysis and the text were produced with Claude: see <a href="#made">How this was made</a>.</i></p>')
    (build / "paper.html").write_text(note + parts["body"], encoding="utf-8")
    meta = ["---", f'title: "{parts["title"]}"', f'subtitle: "{parts["subtitle"]}"', 'author: "Will Cook"', 'date: "18 November 2026"',
            "lang: en-GB", "abstract: |"] + ["  " + line for line in abstract_md.splitlines()] + ["---", ""]
    (build / "meta.yaml").write_text("\n".join(meta), encoding="utf-8")

    run(["pandoc", str(build / "paper.html"), "--from", "html", "--to", "latex", "--standalone", "--number-sections",
         "--shift-heading-level-by=-1", "--metadata-file", str(build / "meta.yaml"), "-H", str(PREAMBLE),
         "-V", "papersize=a4", "-V", "fontsize=11pt", "-V", "geometry:margin=25mm", "-V", "colorlinks=true",
         "-V", "linkcolor=black", "-V", "urlcolor=[HTML]{7A3E00}", "-V", "monofont=Menlo", "-V", "monofontoptions=Scale=0.8",
         "--resource-path", str(build), "--output", str(build / "paper.tex")])
    tex = build / "paper.tex"
    tex.write_text(keep_labels_with_their_text(keep_short_tables_whole(tex.read_text(encoding="utf-8"))), encoding="utf-8")
    run(["tectonic", str(tex), "--outdir", str(build)], cwd=str(build))
    shutil.copyfile(build / "paper.pdf", OUT)
    print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.2f} MB", "| intermediate files in", build)


if __name__ == "__main__":
    main()
