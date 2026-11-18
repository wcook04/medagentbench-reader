"""Helpers, glossary, references and figures for site/build.py. Every number is read from results/*.json."""
import html, json, math, os, re
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = "https://github.com/wcook04/medagentbench-reader"
SITE_URL = "https://wcook04.github.io/medagentbench-reader/"
PDF = "medagentbench-potassium-task.pdf"   # written next to index.html by site/make_pdf.py
BENCH = "https://github.com/stanfordmlgroup/MedAgentBench/blob/99260117137b09f04837a8c18d18a1107efa55ae"


def load(name):
    p = os.path.join(ROOT, "results", name)
    return json.load(open(p)) if os.path.exists(p) else None


R = load("potassium_rule.json")
G = load("grader_controls.json")
A = load("agent_runs.json")
AU = load("audit.json")
BL = load("baselines.json")
EX = load("worked_examples.json")
W = load("whole_task.json")
S = load("standin_conformance.json")
esc = html.escape


def n(x):
    return f"{x:,}"


def pct(a, b, d=0):
    return f"{100 * a / b:.{d}f}%" if b else "–"


def au(name):
    return AU["batches"].get(name)


# ------------------------------------------------------------------ glossary
# Terms follow the sources: "instance", "null agent" and "no-action" from Mantravadi et al.; "grader" and
# "transcript" from Anthropic's guide to agent evaluations; FHIR's own names for its fields.

GLOSS = {
    "instance": ("instance", "One test case: one patient’s record at one time, with the task’s instruction and context. The benchmark releases 30 instances of the potassium task."),
    "derived-instance": ("derived instance", "An instance built in this study from the benchmark’s records: one of the benchmark’s patients with only the potassium results that had been issued by a chosen earlier time, and with every time shifted by the same amount so that the chosen time equals the task’s clock. The instruction and the context are unchanged."),
    "action-required": ("action-required instance", "An instance on which the two orders are required, because the patient’s most recent potassium result is below 3.5 mmol/L. On a no-action instance the most recent result is 3.5 or above and no order is required. The name no-action is taken from Mantravadi and coauthors."),
    "history": ("potassium history", "The potassium results that an instance contains for its patient. It is not the patient’s whole record: no other part of the record is used."),
    "full-chart-baseline": ("all-results baseline", "The first-page baseline with one change: its search requests up to 5,000 results in one page, which is the request the released grader itself sends. It therefore receives every potassium result the patient has."),
    "run": ("run", "One attempt on one instance through the benchmark’s protocol: at most 8 rounds, each of them a GET request, a POST request or FINISH."),
    "transcript": ("transcript", "The complete record of a run: every message the agent sent and every response it received."),
    "grader": ("released grader", "The Python function the benchmark’s authors wrote to score the potassium task, distributed in the file refsol.py. It reads the transcript of a run and returns pass or fail."),
    "relaxed-grader": ("relaxed grader", "The released grader, with its code unchanged, applied to a copy of a run in which two things have been changed: an oral route written as the object that the tool definition declares is rewritten as the plain string, and the final answer is replaced by an empty list, which removes it from scoring. Every other check in the grader still applies. The model’s runs on this page are scored with it, except the runs on tied instances and on instances with an added entered-in-error result, which are scored against the specification’s outcome."),
    "null-agent": ("null agent", "A baseline that sends no request and finishes at once with an empty answer. The name is from Mantravadi and coauthors."),
    "first-page-baseline": ("first-page baseline", "A scripted baseline with no language model. It sends one search under the code K with no sorting and no page size, reads the one page that comes back, takes the result with the most recent effective time on that page, applies the dosing rule, and writes the orders in the form the released grader accepts. It never requests the next page."),
    "page": ("page", "One FHIR Bundle of a paged search: the results that one response to a search contains. On the benchmark’s server a page contains 20 results unless the request sets _count, and the response includes a link to the next page."),
    "default-order": ("default sort order", "The order in which the benchmark’s server lists results when a request does not set _sort: ascending record id. The order of record ids is not the order of effective time."),
    "most-recent-first": ("most recent first", "The one change made in the second condition of this study: when a request does not set _sort, the mock server lists results in reverse chronological order of effective time, the order that a FHIR client requests with _sort=-date. The prompt, the tool definitions and the records are unchanged."),
    "mock-server": ("mock server", "A program written for this study. It stores one patient’s potassium results in memory and responds to searches in the format of the benchmark’s server. It was used for the derived instances, because the benchmark’s server contains only each patient’s complete record."),
    "fhir": ("FHIR", "Fast Healthcare Interoperability Resources, the standard interface of the benchmark’s record server. In FHIR a laboratory result is an Observation, a medication order is a MedicationRequest and an order for a test is a ServiceRequest."),
    "effective-time": ("effective time", "The clinical time of a result, in the FHIR field effectiveDateTime. For a laboratory result it is usually the time the specimen was collected. On this page “most recent” means the latest effective time."),
    "issued-time": ("issued time", "The time at which this version of a result was made available to clinicians, in FHIR’s field issued."),
    "tied": ("tied results", "Two or three potassium results for one patient with the same effective time, which is the most recent in the patient’s history. Instances with tied results whose values differ are reported separately on this page."),
    "loinc": ("LOINC", "A standard coding system for laboratory tests. 2823-3 is the LOINC code for potassium in serum or plasma."),
    "ndc": ("NDC", "National Drug Code, the United States identifier for a medicinal product and pack size. 40032-917-01 is a bottle of 100 potassium chloride extended-release tablets of 20 mEq."),
    "meq": ("mEq", "Milliequivalent, the unit in which potassium doses are written. For potassium, 1 mEq is 1 mmol."),
    "final": ("final", "The FHIR status of a result that is complete. The other statuses include preliminary, amended, corrected and entered-in-error."),
    "tool-definition": ("tool definition", "The description of each permitted request that the benchmark gives the agent: its address, its parameters and their types."),
    "round": ("round", "One message from the agent and the response to it. The benchmark’s harness, the program that passes messages between the agent and the record server, ends a run after 8 rounds."),
    "specification": ("formal specification", "The task’s instruction written in Lean as an exact condition. For any list of results and any clock time, exactly one outcome satisfies it. Where the text of the instruction does not determine the outcome, a choice was written into the specification, and each choice is listed on this page."),
    "reference-implementation": ("reference implementation", "A short Lean program that computes the outcome the specification requires. It is proved in Lean that its output meets the specification for every input."),
    "lean": ("Lean", "A programming language and proof checker. Lean accepts a theorem only when its kernel has checked every step of the proof."),
    "ci": ("95% CI", "A 95% confidence interval from a cluster bootstrap: the patients are resampled at random with replacement 4,000 times, and all of a drawn patient’s instances stay together. It expresses the uncertainty in the rate that comes from which patients are in the data. It does not include the variation between two runs on the same instance."),
}
_NOCAP = {"mEq"}


def g(key, text=None):
    """An inline glossary link. It works as an ordinary link to the glossary; the script adds the hover card."""
    label, _ = GLOSS[key]
    return f'<a class="term" href="#g-{key}" data-term="{key}">{esc(text or label)}</a>'


def glossary_html():
    def shown(label):
        return label if label in _NOCAP else label[0].upper() + label[1:]
    rows = "".join(f'<div class="gl" id="g-{k}"><dt>{esc(shown(GLOSS[k][0]))}</dt><dd>{GLOSS[k][1]}</dd></div>'
                   for k in sorted(GLOSS, key=lambda k: GLOSS[k][0].lower()))
    return f'<dl class="glossary">{rows}</dl>'


# ------------------------------------------------------------------ references (numbered in order of first citation)

_ACC = "[Accessed 18 November 2026]"
REFS = {
    "jiang": 'Jiang Y, Black KC, Geng G, Park D, Zou J, Ng AY, Chen JH. MedAgentBench: a virtual EHR environment to benchmark medical LLM agents. <i>NEJM AI</i> 2025;2(9). <a href="https://doi.org/10.1056/AIdbp2500144">doi:10.1056/AIdbp2500144</a>. Preprint: <a href="https://arxiv.org/abs/2501.14654">arXiv:2501.14654</a>. Code and tasks: <a href="https://github.com/stanfordmlgroup/MedAgentBench">github.com/stanfordmlgroup/MedAgentBench</a>.',
    "mantravadi": 'Mantravadi A, Rajgarhia H, Desikan P, Mukherji A. World feedback for clinical agents: diagnosing RL in FHIR environments. <a href="https://arxiv.org/abs/2607.01470">arXiv:2607.01470</a>, 2026.',
    "bellibatlu": 'Bellibatlu RR, Wang Z, Zhang W. Do agent benchmarks do what they say? An executable-contract audit of tool-using agent environments. <a href="https://arxiv.org/abs/2609.37315">arXiv:2609.37315</a>, 2026.',
    "lee": 'Lee G, Bach E, Yang E, Pollard T, Johnson A, Choi E, Jia Y, Lee JH. FHIR-AgentBench: benchmarking LLM agents for realistic interoperable EHR question answering. <i>Proc Mach Learn Res</i> 2026;297:1297–315. <a href="https://proceedings.mlr.press/v297/lee26a.html">proceedings.mlr.press/v297/lee26a.html</a>.',
    "liu-phys": 'Liu R, Mohiuddin IQ, Schoeffler AJ, Renduchintala K, Nayak A, Vemu PL <i>et al</i>. PhysicianBench: evaluating LLM agents in real-world EHR environments. <a href="https://arxiv.org/abs/2605.02240">arXiv:2605.02240</a>, 2026.',
    "liu-health": 'Liu Q, Zhang S, Qin G, Valanarasu JMJ, Huang X, Argaw P <i>et al</i>. HealthAgentBench: a unified benchmark suite of realistic agentic healthcare environments for challenging frontier AI agents. <a href="https://arxiv.org/abs/2606.31179">arXiv:2606.31179</a>, 2026.',
    "blotske": 'Blotske K, Zhao X, Henry K, Murray B, Gao Y, Smith SE <i>et al</i>. Don’t stop the heart: a performance analysis of large language models and potassium dosing. medRxiv [Preprint] 2026. <a href="https://doi.org/10.64898/2026.06.02.26354762">doi:10.64898/2026.06.02.26354762</a>.',
    "fhir-search": f'HL7. FHIR Release 4: Search. <a href="https://hl7.org/fhir/R4/search.html">hl7.org/fhir/R4/search.html</a> {_ACC}.',
    "hapi": f'HAPI FHIR. JPA Server Starter, <code>AppProperties.java</code>, line 76 (<code>default_page_size = 20</code>), at commit <code>8db6228</code>. <a href="https://github.com/hapifhir/hapi-fhir-jpaserver-starter/blob/8db622874c2d1e3d26fe636978e00d77b75c0d2b/src/main/java/ca/uhn/fhir/jpa/starter/AppProperties.java">github.com/hapifhir/hapi-fhir-jpaserver-starter</a> {_ACC}.',
    "anthropic": f'Anthropic. Demystifying evals for AI agents. 9 January 2026. <a href="https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents">anthropic.com/engineering/demystifying-evals-for-ai-agents</a> {_ACC}.',
    "fhir-obs": f'HL7. FHIR Release 4: Observation, detailed descriptions. <a href="https://hl7.org/fhir/R4/observation-definitions.html">hl7.org/fhir/R4/observation-definitions.html</a> {_ACC}.',
    "fhir-status": f'HL7. FHIR Release 4: value set ObservationStatus. <a href="https://hl7.org/fhir/R4/valueset-observation-status.html">hl7.org/fhir/R4/valueset-observation-status.html</a> {_ACC}.',
    "shi": 'Shi W, Xu R, Zhuang Y, Yu Y, Zhang J, Wu H <i>et al</i>. EHRAgent: code empowers large language models for few-shot complex tabular reasoning on electronic health records. <a href="https://arxiv.org/abs/2401.07128">arXiv:2401.07128</a>, 2024.',
    "lean": 'de Moura L, Ullrich S. The Lean 4 theorem prover and programming language. In: <i>Automated Deduction (CADE 28)</i>. Springer, 2021:625–35. <a href="https://doi.org/10.1007/978-3-030-79876-5_37">doi:10.1007/978-3-030-79876-5_37</a>.',
    "mondl": 'Mondl A, Maisel M, Brock JH. Autoformalization of agent instructions into policy-as-code. <a href="https://arxiv.org/abs/2606.26649">arXiv:2606.26649</a>, 2026.',
    "dailymed": f'Novel Laboratories. Potassium chloride tablet, extended release: prescribing information (revised November 2016). DailyMed, US National Library of Medicine. <a href="https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=eb82527d-88e5-4599-a81a-b3d3144eea19">dailymed.nlm.nih.gov, set id eb82527d</a> {_ACC}.',
    "fhir-dosage": f'HL7. FHIR Release 4: Dosage, detailed descriptions. <a href="https://hl7.org/fhir/R4/dosage-definitions.html">hl7.org/fhir/R4/dosage-definitions.html</a> {_ACC}.',
}
_cited = []


def c(*keys):
    """A numbered citation. References are numbered in the order the page first cites them."""
    out = []
    for k in keys:
        assert k in REFS, k
        if k not in _cited:
            _cited.append(k)
        i = _cited.index(k) + 1
        out.append(f'<a href="#ref-{i}">{i}</a>')
    return '<sup class="cite">' + ",".join(out) + "</sup>"


def references_html():
    missing = [k for k in REFS if k not in _cited]
    if missing:
        print("references not cited on the page, left out of the list:", missing)
    return '<ol class="refs">' + "".join(f'<li id="ref-{i + 1}">{REFS[k]}</li>' for i, k in enumerate(_cited)) + "</ol>"


# ------------------------------------------------------------------ small parts

def thm(name, file="Potassium"):
    line = 1
    for i, l in enumerate(open(os.path.join(ROOT, "lean", file + ".lean")).read().split("\n"), 1):
        if re.match(rf"(theorem|def) {name}\b", l):
            line = i
            break
    return f'<a class="thm" href="{REPO}/blob/main/lean/{file}.lean#L{line}" title="The theorem {name} in the Lean file"><code>{name}</code></a>'


def lean_source():
    src = open(os.path.join(ROOT, "lean", "Potassium.lean")).read()
    a = src.index("/-- One potassium result as the record holds it. -/")
    b = src.index("/-! ## The program -/")
    return esc(src[a:b].rstrip())


def meter(a, b, cls=""):
    """A bar whose length is a/b, with the count and the percentage printed beside it."""
    w = 100 * a / b if b else 0
    return (f'<span class="m {cls}"><span class="m__track" aria-hidden="true"><span class="m__fill" style="width:{w:.1f}%"></span></span>'
            f'<span class="m__n"><b>{n(a)}</b> of {n(b)}</span><span class="m__p">{pct(a, b)}</span></span>')


def yes(ok, a="pass", b="fail"):
    return f'<span class="v v--yes">{a}</span>' if ok else f'<span class="v v--no">{b}</span>'


# ------------------------------------------------------------------ figures

def fig_flow():
    p, o = AU["population"], R["every_report_moment"]["outcomes"]
    rm = p["replace_moments"]
    return f"""<div class="flow" role="img" aria-label="From {p['patients']} patients to {n(p['report_moments'])} derived instances in three groups.">
  <div class="flow__step"><b>{p['patients']}</b><span>patients in the benchmark’s records</span></div>
  <div class="flow__arrow" aria-hidden="true"></div>
  <div class="flow__step"><b>{n(p['potassium_results'])}</b><span>potassium results, each with an effective time and an issued time</span></div>
  <div class="flow__arrow" aria-hidden="true"></div>
  <div class="flow__step"><b>{n(p['report_moments'])}</b><span>derived instances: one for each distinct time at which a patient had a result issued</span></div>
  <p class="flow__by">The {n(p['report_moments'])} derived instances, by the patient’s most recent result ({n(o['notLow'])} + {n(o['replace'])} + {n(o['conflict'])} = {n(p['report_moments'])})</p>
  <div class="flow__out">
    <div class="flow__step flow__step--none"><b>{n(o['notLow'])}</b><span>no-action: the most recent result is 3.5 mmol/L or above</span></div>
    <div class="flow__step flow__step--order"><b>{n(o['replace'])}</b><span>action-required: the most recent result is below 3.5, in {rm['patients']} patients</span></div>
    <div class="flow__step flow__step--open"><b>{n(o['conflict'])}</b><span>tied results with different values at the most recent time</span></div>
  </div>
</div>"""


def fig_cases():
    """The 30 released instances as squares: what is required, and whether the first page holds the most recent result."""
    cb = AU["fixed_programs"]["released_30_cases"]["cases_by_outcome_and_chart"]
    cells = []
    for kind, cls in (("notLow", "cell"), ("conflict", "cell cell--open"), ("replace", "cell cell--order")):
        for grp, off in (("20 results or fewer", False), ("over 20 results, latest on the first page", False), ("over 20 results, latest not on the first page", True)):
            cells += [(kind, cls, off)] * cb.get(f"{kind} | {grp}", 0)
    s, gap, x, y = 22, 6, 0, 8
    parts = ['<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line class="hatch-line" x1="0" y1="0" x2="0" y2="6"/></pattern></defs>']
    prev = None
    for kind, cls, off in cells:
        if prev and kind != prev:
            x += 14
        parts.append(f'<rect class="{cls}" x="{x}" y="{y}" width="{s}" height="{s}" rx="3"/>')
        if off:
            parts.append(f'<circle class="cell-dot" cx="{x + s / 2}" cy="{y + s / 2}" r="3.5"/>')
        x += s + gap
        prev = kind
    off_n = sum(1 for c_ in cells if c_[2])
    return (f'<svg class="cases" viewBox="0 0 {x} {y + s + 8}" role="img" aria-label="The 30 released instances as squares. {off_n} have a dot: the first page of the search does not contain the patient’s most recent result.">{"".join(parts)}</svg>')


def fig_doses():
    """How many of the action-required derived instances get each dose from the task's rule. The label's 20 mEq single-dose line is marked."""
    hist = {int(k): v for k, v in R["every_report_moment"]["dose_histogram_mEq"].items()}
    xs = list(range(10, 150, 10))
    extra = sorted(d for d in hist if d > 140)
    W_, H, left, base, top, step = 760, 300, 46, 232, 34, 42
    scale = (base - top - 14) / max(hist.values())
    pos = {d: left + i * step for i, d in enumerate(xs)}
    gapx = left + len(xs) * step + 34
    for j, d in enumerate(extra):
        pos[d] = gapx + j * step
    last = pos[extra[-1]] if extra else pos[140]
    parts = []
    for gy in (50, 100, 150, 200):
        if gy * scale <= base - top:
            yy = base - gy * scale
            parts.append(f'<line class="grid" x1="{left - 6}" y1="{yy:.1f}" x2="{last + 34}" y2="{yy:.1f}"/><text class="t-num" x="{left - 12}" y="{yy + 4:.1f}" text-anchor="end">{gy}</text>')
    for d, x in pos.items():
        cnt = hist.get(d, 0)
        h = max(cnt * scale, 4 if cnt else 0)
        if cnt:
            parts.append(f'<rect class="{"bar bar--over" if d > 20 else "bar"}" x="{x}" y="{base - h:.1f}" width="30" height="{h:.1f}" rx="2"/>')
            parts.append(f'<text class="t-num" x="{x + 15}" y="{base - h - 6:.1f}" text-anchor="middle">{cnt}</text>')
        parts.append(f'<text class="t-num" x="{x + 15}" y="{base + 18}" text-anchor="middle">{d}</text>')
    parts.append(f'<line class="axis" x1="{left - 6}" y1="{base}" x2="{pos[140] + 34}" y2="{base}"/>')
    if extra:
        bx = gapx - 20
        parts.append(f'<line class="axis" x1="{gapx - 4}" y1="{base}" x2="{last + 34}" y2="{base}"/>')
        parts.append(f'<path class="axis" d="M{bx - 4} {base + 5} l6 -10 M{bx + 4} {base + 5} l6 -10" fill="none"/>')
        parts.append(f'<text class="halo" x="{last + 15}" y="{base - 26}" text-anchor="middle">a result of 0.0</text>')
    parts.append(f'<text x="{left - 6}" y="{base + 42}">Dose required by the task’s rule, mEq</text>')
    parts.append(f'<text x="{left - 6}" y="{top - 16}">Derived instances</text>')
    lx = pos[20] + 36
    parts.append(f'<line class="rule-line" x1="{lx}" y1="{top - 2}" x2="{lx}" y2="{base}"/>')
    over = sum(v for d, v in hist.items() if d > 20)
    parts.append(f'<text class="t-strong halo" x="{lx + 10}" y="{top + 10}">{over} of {sum(hist.values())} instances: more than 20 mEq</text>')
    parts.append(f'<text class="halo" x="{lx + 10}" y="{top + 28}">The product’s label: no more than 20 mEq in a single dose</text>')
    return (f'<svg viewBox="0 0 {W_} {H}" role="img" aria-label="Histogram of the dose the task’s rule requires on each of {sum(hist.values())} action-required derived instances. '
            f'{over} are above 20 mEq.">{"".join(parts)}</svg>')


def fig_chart(ex, w=720, h=226, on_label="in a response the agent received", off_label="never returned to the agent"):
    """One patient's potassium results on one instance: value against effective time. Filled dots were in a response the agent received."""
    rows = ex["chart"]
    t = [datetime.fromisoformat(r["taken"]).timestamp() for r in rows]
    seen = {(x["taken"], x["value"]) for turn in ex["turns"] if turn["action"] == "GET" for x in turn.get("rows", [])}
    lo, hi = min(t), max(t)
    if hi > lo:  # start the time axis on a tick, so the earliest result is inside the labelled range
        d0 = (hi - lo) / 86400
        s0 = next(s for s in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000) if d0 / s <= 6)
        lo = hi - math.ceil(d0 / s0 - 1e-9) * s0 * 86400
    span = (hi - lo) or 1
    vals = [r["value"] for r in rows]
    vlo, vhi = min(min(vals), 3.0) - 0.15, max(max(vals), 4.0) + 0.15
    left, right, top, base = 44, 22, 14, h - 62
    xs = lambda s: left + (s - lo) / span * (w - left - right)  # noqa: E731
    ys = lambda v: base - (v - vlo) / (vhi - vlo) * (base - top)  # noqa: E731
    parts = []
    tick = min(3.0, int(vlo * 2) / 2)
    while tick <= vhi:
        if tick >= vlo:
            parts.append(f'<line class="{"rule-line" if abs(tick - 3.5) < 1e-9 else "grid"}" x1="{left}" y1="{ys(tick):.1f}" x2="{w - right}" y2="{ys(tick):.1f}"/>'
                         f'<text class="t-num" x="{left - 8}" y="{ys(tick) + 4:.1f}" text-anchor="end">{tick:.1f}</text>')
        tick = round(tick + 0.5, 1)
    # time axis: days before the most recent result
    days = span / 86400
    stepd = next(s for s in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000) if days / s <= 6)
    parts.append(f'<line class="axis" x1="{left}" y1="{base + 8}" x2="{w - right}" y2="{base + 8}"/>')
    d = 0
    while d <= days + 1e-9:
        xx = xs(hi - d * 86400)
        parts.append(f'<line class="axis" x1="{xx:.1f}" y1="{base + 8}" x2="{xx:.1f}" y2="{base + 13}"/>'
                     f'<text class="t-num" x="{xx:.1f}" y="{base + 27}" text-anchor="middle">{"0" if d == 0 else f"−{d}"}</text>')
        d += stepd
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["latest"], (rows[i]["taken"], rows[i]["value"]) in seen))

    def label_y(i, text):
        """The line for the label of the most recent result: of the lines just below and just above the
        point, and then further away, the one on which the label covers the fewest other points."""
        px, py = xs(t[i]), ys(rows[i]["value"])
        x1, x0 = px - 14, px - 14 - 6.6 * len(text)
        others = [(xs(t[j]), ys(rows[j]["value"])) for j in range(len(rows)) if j != i]
        covered = lambda y: sum(1 for ox, oy in others if x0 - 6 <= ox <= x1 + 6 and y - 16 <= oy <= y + 9)  # noqa: E731
        steps = ([22, -14] if py < base - 30 else [-14, 22]) + [36, -28, 50, -42]
        lines = [py + s for s in steps if top + 10 <= py + s <= base + 2]
        return min(lines, key=lambda y: (covered(y), lines.index(y)))

    for i in order:
        r = rows[i]
        on = (r["taken"], r["value"]) in seen
        ago = (hi - t[i]) / 86400
        parts.append(f'<circle class="{"dot dot--on" if on else "dot"}" cx="{xs(t[i]):.1f}" cy="{ys(r["value"]):.1f}" r="5"><title>{r["value"]} mmol/L, {ago:.1f} days before the patient’s most recent result, {on_label if on else off_label}</title></circle>')
        if r["latest"]:
            label = f'the patient’s most recent result, {r["value"]} mmol/L'
            parts.append(f'<circle class="dot-ring" cx="{xs(t[i]):.1f}" cy="{ys(r["value"]):.1f}" r="10"/>')
            parts.append(f'<text class="t-strong" x="{xs(t[i]) - 14:.1f}" y="{label_y(i, label):.1f}" text-anchor="end">{label}</text>')
    got = sum(1 for r in rows if (r["taken"], r["value"]) in seen)
    key = (f'<p class="fig-key"><span class="key"><i class="kdot kdot--on"></i>{on_label}</span><span class="key"><i class="kdot"></i>{off_label}</span>'
           '<span class="key"><i class="kdot kdot--ring"></i>the patient’s most recent result</span></p>'
           f'<p class="fig-axis">{len(rows)} potassium results. Vertical axis: mmol/L, with a dashed line at 3.5. Horizontal axis: days before the patient’s most recent result.</p>')
    return (f'<div class="figscroll"><svg viewBox="0 0 {w} {base + 36}" role="img" aria-label="{len(rows)} potassium results over {days:.0f} days. {got} were {on_label}. '
            f'The patient’s most recent result was {"" if any(r["latest"] and (r["taken"], r["value"]) in seen for r in rows) else "not "}among them.">{"".join(parts)}</svg></div>' + key)


MAP_CLASSES = [
    (0, "Pass, with the patient’s most recent result received", "pass, with the patient’s most recent result received"),
    (1, "Pass without the most recent result: the rule applied to an older result gives the same dose", "pass without the patient’s most recent result, because the rule applied to an older result gives the same dose"),
    (2, "No order: searched under K, most recent result not received", "no order; the agent searched under K and did not receive the patient’s most recent result"),
    (3, "A dose computed from an older result", "a dose computed from an older result"),
    (4, "No order: searched only under 2823-3", "no order; the agent searched only under 2823-3"),
    (6, "Required dose, test priority written routine", "required dose, but the test order’s priority is routine"),
    (5, "Most recent result received, a different dose ordered", "the agent received the patient’s most recent result and ordered a different dose"),
]


def fig_map():
    """Every action-required derived instance as one square, for the two search conditions."""
    m = AU["moments_that_require_the_orders"]
    names = ["instances: the patient has 20 results or fewer, so one page contains all of them", "instances: more than 20 results, and the most recent is on the first page",
             "instances: more than 20 results, and the most recent is on a later page"]
    short = {code: s for code, _, s in MAP_CLASSES}
    exs = {}
    for i, e in enumerate(EX["examples"]):
        if e["batch"] in ("replace", "replace_newest"):
            exs[(e["label"], "r" if e["batch"] == "replace" else "n")] = i
    pats = len({c_["p"] for c_ in m["cells"]})
    blocks, first = [], True
    for gi, name in enumerate(names):
        cells = [c_ for c_ in m["cells"] if c_["g"] == gi]
        sq = []
        for c_ in cells:
            er, en = exs.get((c_.get("label"), "r")), exs.get((c_.get("label"), "n"))
            ex_attr = (f' data-ex-r="{er}"' if er is not None else "") + (f' data-ex-n="{en}"' if en is not None else "")
            tip = (f'Patient {c_["p"]} of {pats}, who has {c_["of"]} of these instances. A history of {c_["rows"]} potassium result{"" if c_["rows"] == 1 else "s"}; the rule requires {c_["dose"]} mEq. '
                   f'Default sort order: {short[c_["r"]]}. Most recent first: {short[c_["n"]]}.')
            sq.append(f'<button type="button" class="c r{c_["r"]} n{c_["n"]}{" exr" if er is not None else ""}{" exn" if en is not None else ""}" tabindex="{0 if first else -1}" data-p="{c_["p"]}"{ex_attr} data-t="{esc(tip)}" aria-label="{esc(tip)}"></button>')
            first = False
        blocks.append(f'<div class="map__block"><p class="map__h"><b>{len(cells)}</b> {name}</p><div class="map__cells">{"".join(sq)}</div></div>')
    keys = []
    for code, label, _ in MAP_CLASSES:
        r_ = sum(1 for c_ in m["cells"] if c_["r"] == code)
        n_ = sum(1 for c_ in m["cells"] if c_["n"] == code)
        if r_ or n_:
            keys.append(f'<span class="key{"" if r_ else " zero-r"}{"" if n_ else " zero-n"}"><i class="c k{code}"></i><span class="key__t">{label}</span><b class="cnt cnt-r">{r_}</b><b class="cnt cnt-n">{n_}</b></span>')
    return (f'<div class="map" data-arm="r"><p class="map__lead"><b>All {len(m["cells"])} action-required instances, one square each.</b> The squares are in three groups by the length of the patient’s potassium history and, inside a group, by patient. '
            'The colour of a square is the outcome of the model’s run on that instance with the sort order selected with the Server sort order buttons.</p>'
            '<div class="map__bar"><span class="map__switch-l" id="map-switch-l">Server sort order</span><div class="map__switch" role="group" aria-labelledby="map-switch-l">'
            '<button type="button" data-arm="r" aria-pressed="true">Default (record id)</button><button type="button" data-arm="n" aria-pressed="false">Most recent first</button></div></div>'
            '<div class="map__panel"><p class="map__detail" aria-live="polite">Select a square, or use the Previous and Next buttons, to see one instance here: its patient, the length of the history, and the outcome of the run with each sort order.</p>'
            '<p class="map__nav"><button type="button" data-step="-1">Previous instance</button><button type="button" data-step="1">Next instance</button>'
            '<button type="button" data-step="fail">Next failed run</button></p></div>'
            + "".join(blocks) + f'<div class="map__key">{"".join(keys)}<span class="key"><i class="c k-ex"></i><span class="key__t">one of the six runs shown step by step</span></span></div></div>')


def plain_terms(text):
    """The stored description of a hand-written submission, in the page's terms."""
    for a, b in (("Latest result", "Most recent result"), ("tool schema", "tool definition"), ("lab order", "test order"), ("Lab ordered", "Test ordered"), ("lab priority", "test priority"), ("as the dosing sentence computes", "as the dosing sentence gives")):
        text = text.replace(a, b)
    return text


def controls_table():
    keep = ["reference", "wrong_dose", "no_orders_low", "normal_no_orders", "no_result_no_orders", "route_as_declared", "lab_first", "priority_routine", "unit_lowercase",
            "lab_0859", "lab_other_zone", "future_low", "error_low", "tie_low_first", "tie_low_second", "very_low"]
    by = {c_["id"]: c_ for c_ in G["controls"]}
    rows = []
    for k in keep:
        if k not in by:
            continue
        c_ = by[k]
        inst = c_["instruction"]
        iv = {"meets": '<span class="v v--yes">meets</span>', "does not meet": '<span class="v v--no">does not meet</span>'}.get(inst, '<span class="v v--no">does not meet</span> (the tied results differ, so the specification requires no order)')
        rows.append(f'<tr><td>{esc(plain_terms(c_["submission"]))}</td><td>{iv}</td><td>{yes(c_["grader_pass"], "pass", "fail")}</td></tr>')
    return ('<div class="tablewrap"><table class="tbl"><thead><tr><th>Hand-written submission, on synthetic potassium results</th>'
            '<th>The specification</th><th>The released grader</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")
