"""Build site/index.html from the results files. Every number on the page is read from results/*.json.

Usage: python3 site/build.py
"""
import json, os, re
from datetime import datetime
from parts import *  # noqa: F401,F403
from parts import R, A, AU, BL, EX, W, S, HERE, ROOT, REPO, BENCH, au, n, pct, esc, g, c, thm, meter, yes

REL, NEW = au("replace"), au("replace_newest")
CP = au("control_pilot")
PAIR = AU["paired"]
POP = AU["population"]
EV = R["every_report_moment"]
N = REL["runs"]
FP = BL["first_page_baseline_on_action_required_instances"]
B30, BD = BL["released_30"], BL["derived"]
GC = AU["grader_comparison"]
ALL = AU["all_runs"]
GRADER_SHA = A["grader_sha256"]
NO_ACTION = EV["outcomes"]["notLow"]
TIED = EV["outcomes"]["conflict"]
FP_FAIL = N - FP["pass"]
MODEL = "DeepSeek V4.1 Flash"

WORDS = ["none", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def word(k, cap=False):
    w = WORDS[k] if 0 <= k < len(WORDS) else str(k)
    return w.capitalize() if cap else w


def ci(pair):
    lo, hi = pair
    return f"{100 * lo:.0f} to {100 * hi:.0f}%"


def count(b, *starts):
    return sum(v for k, v in b["by_outcome"].items() if any(k.startswith(s) for s in starts))


NO_RECENT_30 = count(CP, "matched (no order); no reply held")


# ------------------------------------------------------------------ the first screen: abstract, key points, one table





def background():
    return f"""
<section id="background">
  <h2>Background</h2>
  <p>MedAgentBench has 300 test cases written by physicians, which its authors call tasks, in 10 categories of 30, with the de-identified records of 100 patients and a {g("fhir")} record server that the agent searches before it submits orders.{c("jiang")} Here, as in Mantravadi and coauthors, a category is called a task type and each of its 30 test cases an instance.{c("mantravadi")} The potassium task is task type 9 of the original release, which is the version studied here. Later benchmarks for agents on FHIR records include FHIR-AgentBench, whose authors compare methods of retrieving records, PhysicianBench and HealthAgentBench.{c("lee", "liu-phys", "liu-health")}</p>
  <p>Two groups of authors have audited how MedAgentBench scores a run. Mantravadi and coauthors report that a {g("null-agent")}, which sends no request and finishes with an empty answer, passes 41.7% of the 600 tasks in the benchmark’s second version. They report that four task types in that version have 70 to 97% of their instances on the no-action branch, where no order is required, and that the graders for three task types, among them task type 9 of the original release, require formats that the task context does not state, including a route written as a bare string. They built a corrected benchmark, in which they document those formats and limit the share of no-action instances.{c("mantravadi")} They do not discuss the paging of search results in their paper, and they do not say how the instances of this task type in the corrected benchmark were built. Their paper contains no link to code or data for the corrected benchmark, and none was found in a search on 18 November 2026, so the corrected benchmark could not be examined in this study. Bellibatlu and coauthors report that no write request the agent sends in the benchmark changes a stored record, and that the graders for its action tasks score the payload the agent sent.{c("bellibatlu")}</p>
  <p>In this study one task type is traced from its instruction to its grading code. Neither group of authors reports the result that this study adds: on the 30 released instances, the released grader gives the same score to a script that retrieves the patient’s most recent result and to a script that reads only the first page of a search. Instances on which the two scripts receive different scores can be derived from the benchmark’s existing records.</p>
</section>"""


def task():
    over20 = B30["charts_over_20_results"]
    return f"""
<section id="task">
  <h2>What is the agent asked to do?</h2>
  <p>In each instance the agent receives an instruction and a context. They are the same on all 30 instances apart from the patient identifier.</p>
  <div class="taskcard wide">
    <p class="lbl">Instruction</p>
    <blockquote>Check patient <span class="ph">[identifier]</span>’s most recent potassium level. If low, then order replacement potassium according to dosing instructions. Also pair this order with a morning serum potassium level to be completed the next day at 8am.</blockquote>
    <p class="lbl">Context, sentence by sentence</p>
    <table class="ctx">
      <tr><td><q>It’s <span class="nobr">2023-11-13T10:15:00+00:00</span> now.</q></td><td>The current time that the task states, called the task’s clock on this page. It is the same on every instance.</td></tr>
      <tr><td><q>The code for potassium is “K”.</q></td><td>The code under which the record server stores potassium results.</td></tr>
      <tr><td><q>The NDC for replacement potassium is <span class="nobr">40032-917-01</span>.</q></td><td>The product to order. An {g("ndc")} identifies a product and pack size.</td></tr>
      <tr><td><q>Dosing instructions: for every 0.1 mEq/L (or mmol/L) below threshold, order 10 mEq potassium oral repletion) to reach a goal of 3.5 serum level.</q></td><td>The dosing rule. The threshold is 3.5&nbsp;mmol/L.</td></tr>
      <tr><td><q>The LOINC code for serum potassium level is 2823-3.</q></td><td>The {g("loinc")} code to write on the order for the repeat test. The stored results do not have this code, so the server returns no results to a search under it.</td></tr>
    </table>
    <p class="src"><a class="ext" href="{BENCH}/data/medagentbench/test_data_v2.json">The task file at the benchmark commit used here</a></p>
  </div>
  <p>The task is one rule: read the patient’s most recent result; if it is below 3.5, submit a medication order and a test order; otherwise submit none. On the one released instance that requires the orders, the patient’s most recent result is 3.1&nbsp;mmol/L, which is 0.4 below 3.5, so the dose is 4 × 10 = 40&nbsp;{g("meq")}. The two orders are 40&nbsp;mEq of the product with that NDC by mouth, and a potassium test at 08:00 on 14 November.</p>
  <p>The agent works in {g("round", "rounds")}, and the benchmark’s harness ends a run after 8 rounds. The harness is the program that passes messages between the agent and the record server. In each round the agent sends one message and receives one response. The message is a GET request, which is a search of the record server; a POST request, whose payload is an order; or FINISH with a list of answers.{c("jiang")} Two orders and FINISH use three rounds, which leaves at most five for searches. POST requests are not sent to the record server. The harness parses the payload as JSON, returns a response saying that the request was accepted, and writes the message to the run’s transcript, the record of every message and response in the run, which the grader later reads. No order therefore changes a stored record.{c("jiang", "bellibatlu")} On this page, “the agent submitted an order” means that it sent a POST request that was accepted in this way, and “the benchmark’s protocol” means these rules for rounds and messages.</p>
  <h3 id="search">What a search returns</h3>
  <p>The {g("tool-definition")} for the laboratory search contains three parameters: the code, the patient and a date. It does not state the order of the results or how many a response contains. The released server, whose capability statement gives its software as HAPI FHIR Server 7.6.0, returns each page of a search as one FHIR Bundle of 20 results, in ascending order of record id, with a link to the next page. A record id is the identifier of one stored result. Each result also has an {g("effective-time")}, the clinical time in its FHIR field <code>effectiveDateTime</code>, which is usually the time the specimen was collected. Record ids are not assigned in the order of effective time. The first page therefore does not necessarily contain the 20 most recent results.</p>
  <p>The patient’s most recent result can always be retrieved with one request, because a client can set the order of the results with FHIR’s <code>_sort</code> parameter or the page size with <code>_count</code>.{c("fhir-search")} The agent can also request the next page by following its link; within the benchmark’s 8 rounds, the agent can receive at most 100 results in this way. The tool definition states neither parameter nor the link to the next page, which appears only in the server’s response. A page size of 20 is the default in the HAPI FHIR JPA server starter project.{c("hapi")} Of the 30 patients in the released instances, {over20} have more than 20 potassium results.</p>
</section>"""


def grading():
    rows = [
        ("How many orders", "Exactly two accepted POST requests, the medication order first.", "Two orders: the instruction. That the medication order comes first: not stated."),
        ("Medication order: product", "The NDC system and the code 40032-917-01 in the first entry of the order’s list of codings.", "Task context."),
        ("Medication order: dose", "A value within 0.1&nbsp;mEq of the rule’s dose, which is 10&nbsp;mEq for each 0.1&nbsp;mmol/L below 3.5. The unit written exactly <code>mEq</code>.", "Task context."),
        ("Medication order: route", "<code>route.lower().strip() == 'oral'</code>, which only a string can satisfy.", "The tool definition declares <code>route</code> as an object with a <code>text</code> field."),
        ("Test order", "The LOINC system and the code 2823-3 in the first entry of the list of codings, priority <code>stat</code>, and a time that contains the text <code>2023-11-14T08:</code>.", "The instruction (the time) and the task context (the code). The tool definition states <code>stat</code> as the priority to use."),
        ("Both orders", 'Status <code>active</code>, intent <code>order</code>, and the subject exactly <code>{"reference": "Patient/[identifier]"}</code>. The time written must contain <code>2023-11-13T10:15</code> on the medication order and equal <code>2023-11-13T10:15:00+00:00</code> on the test order.', "Tool definitions (status and intent) and task context (the clock). The <code>Patient/</code> prefix is not stated: the tool definition states that the reference is the patient’s FHIR ID."),
        ("Final answer", "An empty list, or a list whose only element is the potassium value (<code>-1</code> if the patient has no result).", "The prompt states the form <code>FINISH([answer1, answer2, ...])</code>. The task contains no question, and what the list should contain is not stated."),
    ]
    body = "".join(f"<tr><th scope='row'>{a}</th><td>{b}</td><td>{c_}</td></tr>" for a, b, c_ in rows)
    return f"""
<section id="grading">
  <h2>How is a run graded?</h2>
  <p>The {g("grader", "released grader")} is a Python function of about 60 lines. It first sends its own search to the record server, requesting up to 5,000 of the patient’s potassium results in one page, and takes the one with the most recent effective time (the first one listed, if several share that time). It then reads the {g("transcript")} of the {g("run")}, which is the record of every message the agent sent and every response it received.</p>
  <ul>
    <li>If the result the grader took is 3.5 or above, or the patient has no result, the run passes when no message from the agent contains the text <code>POST</code> and the final answer is an empty list or a list whose only element is the potassium value (<code>-1</code> if the patient has no result).</li>
    <li>If that result is below 3.5, the run passes when the agent sent exactly two accepted POST requests and each payload has the fields in the table below.</li>
  </ul>
  <p>The grader therefore scores what the agent submitted. None of its checks uses the agent’s searches or the responses to them, so a run can pass when no response to the agent contained the result that the grader itself used.</p>
  <div class="tablewrap wide"><table class="tbl tbl--compare tbl--thirds"><caption>What the released grader requires of a run when the two orders are required</caption><thead><tr><td></td><th>What the released grader requires</th><th>Where the text given to the agent states it</th></tr></thead><tbody>{body}</tbody></table></div>
  <p>No text that the agent receives states four of these requirements, and this page calls them undocumented requirements. The grader requires the route as a plain string, and the tool definition declares it as an object; Mantravadi and coauthors reported this.{c("mantravadi")} The grader requires a final answer in one form, an empty list or the potassium value, and no text the agent receives states that form. The grader also requires the medication order first and the <code>Patient/</code> prefix in the subject. The authors of Anthropic’s guide to agent evaluations recommend that everything a grader checks be clear from the task description.{c("anthropic")}</p>
  <p>The grader contains no test of whether an order is clinically appropriate. The doses the task’s rule requires are compared with the product’s label under <a href="#dose">What does a pass mean clinically?</a></p>
  <details><summary>What the released grader accepts on hand-written submissions</summary>
  <p>The grader was run on hand-written submissions for synthetic potassium histories. It passes a repeat test ordered for 08:59 the next day, and one ordered for 08:00 in another time zone. It counts a result dated after the task’s clock, or a result marked entered-in-error, and takes it as the most recent result when it has the latest effective time. When two results share the most recent effective time it uses whichever the server lists first.</p>
  {controls_table()}</details>
</section>"""


def released():
    off = OFF30
    rc = R["benchmark_clock"]["released_cases"]
    assert rc["conflict_cases_where_every_tied_value_is_at_or_above_3.5"] == rc["outcomes"]["conflict"] == 1
    return f"""
<section id="released">
  <h2>Why does a script that reads only the first page pass all 30 released instances?</h2>
  <p>Each released instance is one patient’s record at the time on the task’s clock. On 29 of the 30 the released grader requires no order, and on 1 it requires the two orders, with a dose of 40&nbsp;mEq.</p>
  <figure class="wide">{fig_cases()}
    <div class="fig-key"><span class="key"><i class="sw"></i>28 instances: the most recent result is 3.5 or above</span><span class="key"><i class="sw sw--open"></i>1 instance: two results share the most recent time, both are 3.5 or above, and the grader uses the first listed</span><span class="key"><i class="sw sw--order"></i>1 instance: the two orders are required</span><span class="key"><i class="sw sw--dot"></i>{off} instances with a dot: the patient’s most recent result is not on the first page</span></div>
  </figure>
  <p>For {off} of the 30 patients the most recent result is not on the first page of the search. On none of those {off} does the grader require an order, and the most recent result on the first page is also 3.5 or above. A script that reads only the first page therefore submits what the grader requires on all 30.</p>
  <p>Three scripted baselines, which are fixed programs with no language model, were run to test whether, on any released instance, the released grader gives different scores to a script that reads one page and a script that reads every result.</p>
  <ul>
    <li>The {g("null-agent")} sends no request and finishes with an empty answer. It passes on every instance on which no order is required.</li>
    <li>The {g("first-page-baseline")} sends one search under the code K, reads the one page that comes back, applies the dosing rule to the most recent result on that page, and writes its orders in the form the released grader accepts.</li>
    <li>The {g("full-chart-baseline", "all-results baseline")} is the first-page baseline with one change: its search requests up to 5,000 results in one page, which is the request the grader itself sends, so it receives every potassium result the patient has. It applies the same dosing rule, and only the results it receives differ.</li>
  </ul>
  <p>All three were run through the benchmark’s protocol against a local copy of the released server, and the released grader scored their transcripts.</p>
  <div class="tablewrap wide"><table class="tbl tbl--fit"><thead><tr><td></td><th class="num">Instances passed, of 30</th><th class="num">Runs in which the script received the patient’s most recent result, of 30</th></tr></thead><tbody>
    <tr><th scope="row">Null agent</th><td class="num"><b>{B30["null_agent"]["pass"]}</b></td><td class="num">0</td></tr>
    <tr><th scope="row">First-page baseline</th><td class="num"><b>{B30["first_page_baseline"]["pass"]}</b></td><td class="num">{B30["first_page_holds_most_recent_result"]}</td></tr>
    <tr><th scope="row">All-results baseline</th><td class="num"><b>{B30["full_chart_baseline"]["pass"]}</b></td><td class="num">30</td></tr>
  </tbody></table></div>
  <p>On the released instances the released grader gives the same score to the all-results baseline, which always receives the patient’s most recent result, and to the first-page baseline, which does not receive it on {off} of the 30. The two scores would differ only on an instance where the dosing rule gives different orders for the patient’s most recent result and for the most recent result on the first page. The released instances contain no such instance.</p>
</section>"""


def derived():
    rm = POP["replace_moments"]
    nu = POP["results_with_no_unit"]
    av = R["availability"]
    return f"""
<section id="derived">
  <h2>How were further instances derived?</h2>
  <p>More instances can be built from the benchmark’s records than the 30 that its authors released. For any earlier time, the results that a patient had by that time form a record on which the same task could have been set. A {g("derived-instance")} is one such record: one of the benchmark’s patients, with only the potassium results that had been made available by a chosen earlier time.</p>
  <p>A FHIR Observation contains two times for a result.{c("fhir-obs")} The {g("effective-time")}, in the field <code>effectiveDateTime</code>, is the clinical time of the result, which for a laboratory test is usually the time the specimen was collected. The {g("issued-time")}, in the field <code>issued</code>, is the time at which this version of the result was made available. A derived instance contains the results issued at or before the chosen time. Among those, the most recent result is the one with the latest effective time, as in the released grader.</p>
  <p>The task’s text and the grader both contain the fixed date 13 November 2023. So that both can be used without edits, every time in a derived instance is shifted by the same amount, so that the chosen time equals the task’s clock and every interval between results is unchanged. The instruction, the context, the prompt, the tool definitions and the grader are the released ones.</p>
  <p>The records of the benchmark’s 100 patients contain {n(POP["potassium_results"])} potassium results, with {n(POP["report_moments"])} distinct combinations of patient and issued time. Each combination is one derived instance, so each patient has one instance for each distinct time at which one of their results was issued.</p>
  <div class="wide">{fig_flow()}</div>
  <p>The outcome required on each derived instance is computed by a {g("reference-implementation")} of the task’s instruction, written and verified in Lean and described under <a href="#spec">What is specified, and what is proved?</a> By its output, the {n(POP["report_moments"])} instances fall into three groups.</p>
  <ul>
    <li><b>{n(NO_ACTION)} no-action instances.</b> The most recent result is 3.5 or above, and no order is required.</li>
    <li><b>{N} {g("action-required", "action-required instances")}</b>, in {rm["patients"]} patients. The most recent result is below 3.5, and the two orders are required. These are the instances used in the sections that follow.</li>
    <li><b>{TIED} tied instances.</b> Two or three results share the most recent effective time and have different values. The instruction does not state what to do when tied results differ. The specification requires no order on these, and they are reported separately, under <a href="#spec">What is specified, and what is proved?</a></li>
  </ul>
  <p>On the {N} action-required and the {n(NO_ACTION)} no-action instances the released grader requires the same outcome as the reference implementation.</p>
  <p>The derived instances have five properties that limit what can be concluded from them.</p>
  <ul>
    <li><b>They are reconstructions.</b> The released data contains one version of each result, and all {n(POP["potassium_results"])} have the status {g("final")}. A history rebuilt at an earlier time therefore cannot contain a preliminary value that was later revised.</li>
    <li><b>They are selected.</b> The {N} were kept because the orders are required. They are not a sample from which to estimate how often the orders are required, and they are not {N} separate episodes of low potassium: a low result stays the most recent while results with earlier effective times are issued after it, and each of those issued times is a further instance. The {N} contain {rm["distinct_patient_and_sample_time_pairs"]} distinct combinations of patient and most recent effective time. Each instance is run on its own, and the agent receives no information about orders on earlier instances.</li>
    <li><b>They come from few patients.</b> The {N} come from {rm["patients"]} patients, each of whom has between {rm["moments_per_patient"]["min"]} and {rm["moments_per_patient"]["max"]} instances (median {rm["moments_per_patient"]["median"]:.0f}). Five patients have {rm["moments_from_the_5_patients_with_most"]} of the {N}.</li>
    <li><b>They contain only issued results.</b> For {av["moments_when_a_more_recent_specimen_was_still_unreported"]} of the {n(av["result_issue_moments"])} results, at the time the result was issued another specimen, with a later effective time, had already been collected and not yet reported. The derived instance set at that issued time does not contain the later result.</li>
    <li><b>Six results have no unit.</b> Their values, {nu["lowest_value"]} to {nu["highest_value"]}, are read as mmol/L like the other {n(POP["potassium_results"] - nu["n"])}. One of them is recorded as 0.0 and is discussed under <a href="#dose">What does a pass mean clinically?</a></li>
  </ul>
</section>"""


def results():
    def cnt(b, *starts):
        return count(b, *starts)
    k_pass, k_same = ("matched; a reply held",), ("matched; no reply held the latest result (an older",)
    k_none = ("latest result never returned; the newest result it received was not low", "latest result never returned; no order")
    k_old, k_code, k_prio, k_diff = ("latest result never returned; dosed",), ("never searched",), ("required dose ordered",), ("latest result returned; ordered a different dose",)
    out_rows = [
        ("Pass. The agent received the patient’s most recent result", k_pass, "ok"),
        ("Pass without the patient’s most recent result. The most recent result the agent received gives the same dose", k_same, "ok"),
        ("No order. The agent searched under K and did not receive the patient’s most recent result", k_none, ""),
        ("A dose computed from the most recent result on the first page, which was not the patient’s most recent", k_old, ""),
        ("No order. The agent searched only under 2823-3 and received no results", k_code, ""),
        ("The required dose, with the test order’s priority written <code>routine</code>", k_prio, ""),
        ("The agent received the patient’s most recent result and ordered a different dose", k_diff, ""),
    ]
    out_html = "".join(f'<tr class="{cls}"><th scope="row">{label}</th><td class="num">{n(cnt(REL, *keys))}</td><td class="num">{n(cnt(NEW, *keys))}</td></tr>' for label, keys, cls in out_rows)
    assert sum(cnt(REL, *k) for _, k, _ in out_rows) == N and sum(cnt(NEW, *k) for _, k, _ in out_rows) == N
    assert cnt(REL, *k_none) + cnt(REL, *k_old) + cnt(REL, *k_code) == RETR_FAIL
    groups = [("20 results or fewer", G_SHORT, "20 results or fewer, so one page contains all of them"),
              ("over 20 results, latest on the first page", G_ON, "More than 20 results, and the most recent is on the first page"),
              ("over 20 results, latest not on the first page", G_OFF, "More than 20 results, and the most recent is on a later page")]
    chart_html = "".join(
        f'<tr><th scope="row">{label}</th><td class="num">{BY[kb]["instances"]}</td><td class="num">{BY[kb]["pass"]}</td>'
        f'<td class="num"><b>{REL["by_chart"][k]["matched"]}</b></td><td class="num"><b>{NEW["by_chart"][k]["matched"]}</b></td></tr>' for k, kb, label in groups)
    late = "over 20 results, latest not on the first page"
    p = PAIR["released_search_vs_newest_first"]
    lo, hi = p["interval_95_resampling_patients"]
    rs = REL["by_search"]
    only_r, only_n = rs["searched_only_by_2823-3"]["runs"], NEW["by_search"]["searched_only_by_2823-3"]["runs"]
    k_new = NEW["by_search"]["searched_K_and_read_the_first_page_only"]
    nl = au("notLow")
    nl_no_recent = count(nl, "matched (no order); no reply held")
    nl_loinc = nl["by_search"]["searched_only_by_2823-3"]["runs"]
    rep = PAIR["released_search_run_twice"]
    same = rep["both_matched"] + rep["neither_matched"]
    tr = AU["released_cases_same_requests"]
    fw = AU["fields_the_model_wrote"]
    prio = GC["required_dose_but_relaxed_fail"].get("the test order's priority is not stat", 0)
    assert prio == sum(GC["required_dose_but_relaxed_fail"].values())
    nf = ALL["runs_that_did_not_finish"]["by_status"]
    assert sum(nf.values()) == ALL["final_answer"].get("did not finish", 0) == nf.get("provider_failure:no_content", 0) + nf.get("invalid_action", 0)
    assert not set(ALL["runs_that_did_not_finish"]["by_batch"]) & set(MAIN_BATCHES) and not set(ALL["runs_that_did_not_finish"]["by_batch"]) & {"conflictHard_table", "conflictHard_contract"}
    mp = lambda x: f"{100 * x:.0f}%"  # noqa: E731
    return f"""
<section id="results">
  <h2>Does a language model also stop at the first page?</h2>
  <p>{MODEL} was run through the benchmark’s protocol by this study’s own runner, a program that applies the same rules as the benchmark’s harness, with the benchmark’s prompt, tool definitions, task text and limit of 8 rounds unchanged, at low reasoning effort and temperature 0. It was run once on each of the 30 released instances, against a local copy of the released server. It was then run once on each of the {N} action-required derived instances under each of two conditions, described below, against the mock server.</p>

  <h3 id="scoring">How the model’s runs are scored</h3>
  <p>Under the released grader no run of the model passes, whatever orders the agent submitted. The runs fail on two of the grader’s undocumented requirements. Firstly, every run that finished ended with a list of sentences as its final answer, where the grader requires an empty list or the bare potassium value. The model was run {n(ALL["runs"])} times in this study, counting every condition (the conditions are listed under <a href="#made">How this was made</a>). Of these runs, {n(ALL["final_answer"]["a list holding one or more sentences"])} ended this way. The other {sum(nf.values())}, all in conditions listed only under <a href="#all-runs">Every run of the model</a>, ended without a final answer: in {nf.get("provider_failure:no_content", 0)} the model provider returned no content, and in {nf.get("invalid_action", 0)} the model sent a message that is not one of the three permitted actions. The benchmark’s authors report answers written as full sentences as a common error of the models they tested.{c("jiang")} Secondly, in the four conditions run on action-required instances, described below, the model submitted {n(fw["medication_orders"])} medication orders. It wrote the route as the object that the tool definition declares, for example <code>{{"text": "oral"}}</code>, in {n(fw["route_written_as_an_object"])} of them, and left the route out of the other {fw.get("route_absent", 0)}.</p>
  <p>To score the model’s orders apart from those two formats, the model’s runs are scored by a {g("relaxed-grader")}. It is the released grader, with its code unchanged, applied to a copy of the run in which the route and the final answer have been changed. An oral route written as the declared object is rewritten as the string <code>oral</code>, which keeps the route the agent wrote and changes only its form. The final answer is replaced by an empty list, which removes the final answer from the scoring, so that a wrong statement in it is not counted. Every other check in the grader still applies: the product, the dose, the two times, the priority, and the two other undocumented requirements (the medication order first and the <code>Patient/</code> prefix), on which no run of the model failed.</p>
  <p>The scripted baselines write the route as a string and finish with an empty list, so the two changes do not alter their transcripts. The relaxed grader and the released grader give the baselines the same scores, and the model’s scores under the relaxed grader can be compared with them.</p>

  <h3>On the 30 released instances</h3>
  <p>The model passed all 30. In {NO_RECENT_30} of the 30 runs the agent did not receive the patient’s most recent result. In {CP["by_search"]["searched_K_and_read_the_first_page_only"]["runs"]} of the 30 the agent sent a search under K and requested only the first page, as the first-page baseline does.</p>

  <h3>On the {N} action-required derived instances</h3>
  <ul>
    <li><b>{g("default-order", "Default sort order")}.</b> The mock server returns pages as the released server does: 20 results per page, in ascending order of record id.</li>
    <li><b>{g("most-recent-first", "Most recent first")}.</b> One change to the mock server: when a request does not set <code>_sort</code>, the server lists results in reverse chronological order of effective time, the order that a FHIR client requests with <code>_sort=-date</code>. The prompt is unchanged and does not state the change.</li>
  </ul>
  <div class="tablewrap wide"><table class="tbl tbl--main"><caption>Instances passed, of the {N} that require the orders. The model is scored by the relaxed grader and the baselines by the released grader.</caption>
    <thead><tr><td></td><th>Per instance</th><th class="num">95% CI</th><th class="num">Patient-level mean, {FP["patients"]} patients</th></tr></thead><tbody>
    <tr><th scope="row">{MODEL}, default sort order</th><td>{meter(REL["matched"], N)}</td><td class="num">{ci(REL["interval_95_resampling_patients"])}</td><td class="num">{mp(REL["by_patient"]["mean_of_patient_shares"])}</td></tr>
    <tr><th scope="row">{MODEL}, most recent first</th><td>{meter(NEW["matched"], N)}</td><td class="num">{ci(NEW["interval_95_resampling_patients"])}</td><td class="num">{mp(NEW["by_patient"]["mean_of_patient_shares"])}</td></tr>
    <tr class="ref"><th scope="row">First-page baseline, for comparison</th><td>{meter(FP["pass"], N, "m--quiet")}</td><td class="num">{ci(FP["interval_95_resampling_patients"])}</td><td class="num">{mp(FP["mean_of_patient_pass_rates"])}</td></tr>
    <tr class="ref"><th scope="row">All-results baseline, for comparison</th><td>{meter(ALLRES, N, "m--quiet")}</td><td class="num muted">–</td><td class="num">100%</td></tr>
  </tbody></table></div>
  <p>With the default sort order the model passes fewer instances than the first-page baseline, {REL["matched"]} against {FP["pass"]}. The baseline cannot fail in three ways in which some of the model’s runs failed. In {cnt(REL, *k_code)} runs the agent searched only under 2823-3, the code for ordering the repeat test. In {cnt(REL, *k_prio)} it wrote the test order’s priority as <code>routine</code>. In {cnt(REL, *k_diff)} it ordered a different dose after it had received the patient’s most recent result.</p>
  <p>The two conditions were run on the same {N} instances, so each instance has a pair of outcomes.</p>
  <div class="tablewrap"><table class="tbl tbl--pair"><caption>Paired outcomes on the {N} instances</caption>
    <thead><tr><td></td><th class="num">Passed with the most recent first</th><th class="num">Failed with the most recent first</th></tr></thead><tbody>
    <tr><th scope="row">Passed with the default sort order</th><td class="num">{p["both_matched"]}</td><td class="num">{p["only_first_matched"]}</td></tr>
    <tr><th scope="row">Failed with the default sort order</th><td class="num">{p["only_second_matched"]}</td><td class="num">{p["neither_matched"]}</td></tr>
  </tbody></table></div>
  <p>The per-instance pass rate was {100 * p["difference_in_share"]:.0f} percentage points higher with the most recent first than with the default sort order (95% CI {100 * lo:.0f} to {100 * hi:.0f}).</p>
  <p>The per-instance rate and the patient-level mean in the table are computed differently. The per-instance rate is the share of the {N} runs that pass. In it, a patient with many instances counts more, and those patients have long histories. The patient-level mean is the average of the {FP["patients"]} patients’ own pass rates: {mp(p["first_mean_of_patient_shares"])} with the default sort order and {mp(p["second_mean_of_patient_shares"])} with the most recent first, a difference of {100 * p["mean_of_patient_differences"]:.0f} percentage points.</p>

  <figure class="wide">{fig_map()}
    <figcaption>With the default sort order, {BY[G_OFF]["instances"] - REL["by_chart"][late]["matched"]} of the {N - REL["matched"]} failed runs are in the third group, where the patient’s most recent result is on a later page. With the most recent results first, {NEW["by_chart"][late]["matched"]} of the {BY[G_OFF]["instances"]} instances in the third group pass, and {N - NEW["matched"]} runs fail: {BY[G_SHORT]["instances"] - NEW["by_chart"]["20 results or fewer"]["matched"]}, {BY[G_ON]["instances"] - NEW["by_chart"]["over 20 results, latest on the first page"]["matched"]} and {BY[G_OFF]["instances"] - NEW["by_chart"][late]["matched"]} in the three groups. When a square is selected, the same patient’s other squares are marked. A square with a dot is one of the <a href="#transcripts">six runs</a> shown step by step. A different outcome under the two conditions on a single instance is not evidence that the sort order caused it, because repeated runs on one instance can differ.</figcaption></figure>

  <h3 id="errors">Error analysis</h3>
  <p>Each run is assigned to exactly one row of the table. “The agent received the patient’s most recent result” means that at least one server response to the agent contained a result with the most recent effective time in the patient’s history. The agent can receive that result and not use it.</p>
  <div class="tablewrap wide"><table class="tbl tbl--fit"><thead><tr><td></td><th class="num">Default sort order</th><th class="num">Most recent first</th></tr></thead><tbody>{out_html}
    <tr class="sum"><th scope="row">All runs</th><td class="num">{N}</td><td class="num">{N}</td></tr></tbody></table></div>
  <p>In {RETR_FAIL} of the model’s {N - REL["matched"]} failed runs with the default sort order, the agent did not receive the patient’s most recent result. These {RETR_FAIL} runs are of two kinds. In {cnt(REL, *k_none) + cnt(REL, *k_old)} runs the agent searched under K and the responses it received did not contain that result; in {cnt(REL, *k_none)} of these runs the agent submitted no order and in {cnt(REL, *k_old)} a dose computed from an older result. In {cnt(REL, *k_code)} runs the agent searched only under 2823-3.</p>
  <p><b>Stopping at the first page.</b> With the default sort order the agent sent a search under K and requested only the first page in {rs["searched_K_and_read_the_first_page_only"]["runs"]} of the {N} runs. It followed the link to the next page in {rs.get("searched_K_and_followed_the_next_page_link", {"runs": 0})["runs"]}, and it never set <code>_sort</code>. With the most recent first, in all {k_new["runs"]} runs in which the agent searched under K, the agent received the patient’s most recent result on the first page. Of those runs, {k_new["matched"]} passed, and in the other {k_new["runs"] - k_new["matched"]} the agent wrote the test order’s priority as <code>routine</code>.</p>
  <p><b>Searching under the wrong code.</b> The agent searched under the wrong code with both sort orders, and this failure does not depend on paging. The task context contains two codes: K, under which the record server stores potassium results, and 2823-3, the LOINC code to write on the order for the repeat test. The tool definition describes the search’s <code>code</code> parameter as “the observation identifier (base name)”. With the default sort order the agent searched under 2823-3 in {REL["searched_by_both_codes"] + only_r} of the {N} runs. The server returns an empty page and no error to that search. In {REL["searched_by_both_codes"]} runs the agent then searched under K. In the other {only_r} the agent stopped and reported that the patient had no potassium result. With the most recent first the agent stopped after that search in {only_n} runs. Only {p["both_searched_only_by_2823-3"]} instances are among both the {only_r} and the {only_n}, so these stops do not appear to be tied to particular instances.</p>

  <h3>Results by length of history</h3>
  <div class="tablewrap wide"><table class="tbl"><caption>Instances passed, by the length of the patient’s potassium history. The released grader scored the first-page baseline, and the relaxed grader scored the model.</caption><thead><tr><th>The patient’s potassium history on the instance</th><th class="num">Instances</th><th class="num">First-page baseline</th><th class="num">Model, default sort order</th><th class="num">Model, most recent first</th></tr></thead><tbody>{chart_html}</tbody></table></div>
  <p>The three rows are defined by where the patient’s most recent result falls under the default sort order. Where it was on a later page, the model passed {REL["by_chart"][late]["matched"]} of {BY[G_OFF]["instances"]} with the default sort order, the same number as the first-page baseline. In {count(REL, "matched; no reply held")} of those runs the dosing rule applied to the most recent result on the first page gives the same dose, and in {rs.get("searched_K_and_followed_the_next_page_link", {"matched": 0})["matched"]} the agent followed the link to the next page.</p>

  <h3>No-action instances</h3>
  <p>The model was also run, with the default sort order, on a random sample of {nl["runs"]} of the {n(NO_ACTION)} no-action instances. It passed {nl["matched"]}. In {nl_no_recent} of those {nl["matched"]} runs the agent did not receive the patient’s most recent result, and in {nl_loinc} of the {nl_no_recent} the agent had searched only under 2823-3 and received no result at all. On the other {nl["runs"] - nl["matched"]} instances the agent submitted a dose computed from an older low result. The most-recent-first condition was not run on no-action instances.</p>

  <h3>Variation between runs</h3>
  <p>The {N} instances were put in one fixed random sequence, and the run with the default sort order was repeated on the first {rep["moments_in_both"]} with identical settings. To the same request, the mock server’s response in a second run differs only in three values that the mock server generates for each response: the response’s id, its <code>lastUpdated</code> time, and the token in the link to the next page. The model passed {rep["first_matched"]} the first time and {rep["second_matched"]} the second. The pass or fail result was the same both times on {same} instances and different on {rep["moments_in_both"] - same}. On the 30 released instances, the model was run twice on the released server; it passed 30 of 30 both times, and the agent sent the same requests in the same order on {tr["control_pilot vs control_repeat"]["same_requests_in_the_same_order"]} of 30. The confidence intervals above do not include this variation.</p>
</section>"""


# ------------------------------------------------------------------ six transcripts

TABS = ["Most recent result on page 2", "Same instance, most recent first", "Dose from an older result", "Searched only under 2823-3", "A history of 12 results", "A no-action instance"]


def days_before(iso_text, ref):
    sec = (datetime.fromisoformat(ref) - datetime.fromisoformat(iso_text)).total_seconds()
    if abs(sec) < 1:
        return "at the same time as"
    if sec < 5400:
        return f"{sec / 60:.0f} minutes earlier than"
    if sec < 2 * 86400:
        return f"{sec / 3600:.0f} hours earlier than"
    return f"{sec / 86400:.0f} days earlier than"


def post_line(turn):
    p = turn.get("payload") or {}
    try:
        if p.get("resourceType") == "MedicationRequest":
            di = p["dosageInstruction"][0]
            dq = di["doseAndRate"][0]["doseQuantity"]
            code = p["medicationCodeableConcept"]["coding"][0]["code"]
            return f'A medication order for the product with NDC {esc(str(code))}: <b>{dq["value"]} {esc(str(dq.get("unit")))}</b>, route written as <code>{esc(json.dumps(di.get("route")))}</code>.'
        if p.get("resourceType") == "ServiceRequest":
            return (f'An order for a test with LOINC code {esc(str(p["code"]["coding"][0]["code"]))} at <b>{esc(str(p.get("occurrenceDateTime")))}</b>'
                    + (f', priority {esc(str(p["priority"]))}.' if p.get("priority") else ", with no priority field."))
    except (KeyError, IndexError, TypeError):
        pass
    return "A POST request."


def exact_messages(ex):
    out = []
    for t in ex["turns"]:
        if t["action"] == "GET":
            out.append(t["request"])
        elif t["action"] == "POST":
            out.append("POST " + str(t.get("url")) + "\n" + json.dumps(t.get("payload"), indent=1))
        else:
            out.append(t.get("text", ""))
    return "\n\n".join(out)


def case(ex, i):
    rows = ex["chart"]
    latest = next(r for r in rows if r["latest"])
    need = ex["required"]
    if need["outcome"] == "replace":
        req = (f'The patient’s most recent result is {latest["value"]} mmol/L, which is below 3.5. Two orders are required: {need["dose_mEq"]} mEq of the named product by mouth, '
               f'and a potassium test at 08:00 on 14 November.')
    else:
        req = f'The patient’s most recent result is {latest["value"]} mmol/L, which is not below 3.5. No order is required.'
    steps = []
    for t in ex["turns"]:
        if t["action"] == "GET":
            short = t["request"].replace("GET ", "", 1).split("/fhir/")[-1]
            got = t["returned"]
            if got == 0:
                back = "The server returned no results."
            else:
                newest = max(t["rows"], key=lambda r: r["taken"])
                has = any(r["taken"] == latest["taken"] and r["value"] == latest["value"] for r in t["rows"])
                more_ = " and a link to the next page" if t["next_page_link"] else ""
                back = (f'The server returned {got} of the {len(rows)} results{more_}. '
                        + ("The patient’s most recent result was among them." if has else
                           f'The most recent of the {got} was {newest["value"]} mmol/L, taken {days_before(newest["taken"], latest["taken"])} the patient’s most recent result, which was not among them.'))
            steps.append(f'<li><span class="step__who">The agent searched</span><code class="req">GET {esc(short)}</code><span class="step__back">{back}</span></li>')
        elif t["action"] == "POST":
            steps.append(f'<li><span class="step__who">The agent submitted an order</span><span class="step__back">{post_line(t)}</span></li>')
        elif t["action"] == "FINISH":
            raw = t["text"].strip()
            try:
                inner = json.loads(raw[raw.index("(") + 1: raw.rindex(")")])
                text = " ".join(str(x) for x in inner) if isinstance(inner, list) else str(inner)
            except ValueError:
                text = re.sub(r'^FINISH\(\["?|"?\]\)$', "", raw)
            steps.append(f'<li><span class="step__who">The agent finished with a list containing this text</span><q class="said">{esc(text)}</q></li>')
    ok = ex["relaxed_pass"]
    placed = any(t["action"] == "POST" for t in ex["turns"])
    bad = ex["stanford_checks_failed"]
    if need["outcome"] == "replace":
        why = ("Both orders, with the required dose and every required field." if ok else
               "No order was submitted." if not placed else "The dose is not the required dose." if "dose value" in bad else "A required field is missing.")
    else:
        why = "No order was required and none was submitted." if ok else "An order was submitted where none was required."
    gr = []
    if "route is the plain string oral" in bad:
        gr.append("the route is the declared object, and the grader requires a plain string")
    if "dose value" in bad:
        gr.append("the dose is not the required dose")
    if "test priority is stat" in bad:
        gr.append("the test order’s priority is not <code>stat</code>")
    if need["outcome"] == "replace" and not placed:
        gr.append("the two orders are missing")
    gr.append("the final answer is a list of sentences, and the grader requires an empty list or the potassium value")
    seen_rows = [r for t in ex["turns"] if t["action"] == "GET" for r in t.get("rows", [])]
    ns = max(seen_rows, key=lambda r: r["taken"]) if seen_rows else None
    first_n = next((t["returned"] for t in ex["turns"] if t["action"] == "GET" and t["returned"]), 0)
    placed_dose = next((t["payload"]["dosageInstruction"][0]["doseAndRate"][0]["doseQuantity"]["value"] for t in ex["turns"]
                        if t["action"] == "POST" and (t.get("payload") or {}).get("resourceType") == "MedicationRequest"), None)
    nsv = ns["value"] if ns else ""
    notes = {
        0: f"The first page contained {first_n} of the {len(rows)} results, in order of record id. The most recent of those {first_n} was {nsv} mmol/L, which is not below 3.5, and the agent submitted no order. The patient’s most recent result was on the second page, which the agent did not request.",
        1: "The potassium history and the prompt are the same as in run 1. The mock server listed the most recent results first, the patient’s most recent result was first on the page, and the agent wrote the two required orders.",
        2: f"The most recent result on the first page was {nsv} mmol/L, and the agent ordered {placed_dose} mEq, which is the rule applied to that value. The patient’s most recent result, {latest['value']} mmol/L, was on the second page, and the rule applied to it gives {need['dose_mEq']} mEq.",
        3: "The task context gives 2823-3 as the LOINC code for the repeat test. The record server stores potassium results under the code K. The search under 2823-3 returned an empty page, and the agent reported that the patient had no potassium result.",
        4: f"The server returned all {len(rows)} results on one page, and the agent’s medication order has the dose that the rule gives for the most recent of them.",
        5: (f"The agent read the first page, where the most recent result was {nsv} mmol/L, and submitted no order, which is what the grader requires. The patient’s most recent result was on a later page"
            + (f", and it is also {latest['value']} mmol/L." if latest["value"] == nsv else f": {latest['value']} mmol/L.")),
    }
    return f"""
<div class="case" role="tabpanel" id="case-{i}" aria-labelledby="casetab-{i}"{'' if i == 0 else ' hidden'}>
  <h3 class="case__title">Run {i + 1}. {esc(TABS[i])}</h3>
  <p class="case__req"><span class="lbl">Required by the task’s rule</span> {req}</p>
  <figure class="case__fig">{fig_chart(ex)}</figure>
  <ol class="steps">{''.join(steps)}</ol>
  <dl class="scores">
    <div><dt>Relaxed grader</dt><dd>{yes(ok)} {why}</dd></div>
    <div><dt>Released grader</dt><dd>{yes(ex["released_pass"])} {("It fails because " + "; ".join(gr) + ".") if not ex["released_pass"] else ""}</dd></div>
    <div><dt>What happened</dt><dd>{notes[i]}</dd></div>
    <div><dt>Why this run is shown</dt><dd>It is {esc(shown_because(ex["chosen_because"]))}.</dd></div>
  </dl>
  <details class="msgs"><summary>The agent’s messages, exactly as sent</summary><pre><code>{esc(exact_messages(ex))}</code></pre></details>
</div>"""


def transcripts():
    exs = EX["examples"]
    tabs = "".join(f'<button type="button" role="tab" id="casetab-{i}" aria-controls="case-{i}" aria-selected="{"true" if i == 0 else "false"}">{i + 1}. {esc(TABS[i])}</button>' for i in range(len(exs)))
    return f"""
<section id="transcripts">
  <h2>Six runs, step by step</h2>
  <p>The six runs below are runs of the model from the study. Each was selected by a fixed rule, given with the run, that uses only recorded properties of the run and its instance. The rules were written to find one example of each of six outcomes, so the six runs are illustrations and are not a random sample. Each panel contains what the task’s rule requires, the patient’s results, what each server response contained, the orders the agent submitted, and the two graders’ verdicts. The agent’s own messages are given exactly as sent. The server’s responses are summarised, because each contains the full FHIR resource of every result.</p>
  <p>The potassium values are from the benchmark’s released, de-identified records. The patient identifiers in the messages are the ones the mock server used for the derived instances, and are not the benchmark’s identifiers. Times are shown as days before the patient’s most recent result.</p>
  <div class="cases-ui wide">
    {"".join(f'<span class="anchor" id="transcript-{i + 1}"></span>' for i in range(len(exs)))}
    <div class="casetabs" role="tablist" aria-label="Six runs">{tabs}</div>
    {''.join(case(e, i) for i, e in enumerate(exs))}
  </div>
</section>"""


# ------------------------------------------------------------------ model-written programs

def programs():
    PS = W["primary_summary"]
    bl, se, s8 = PS["blind"]["relaxed"], PS["seen_raised_caps"]["relaxed"], PS["seen_limit_8_rounds"]["relaxed"]
    same = W["first_page_baseline_comparison"]["blind_programs_identical"]
    beh_b, beh_s = W["summary"]["blind"]["programs_by_search_behaviour"], W["summary"]["seen"]["programs_by_search_behaviour"]
    caps = W["scoring"]["caps_without_round_limit"]
    Pg = W["programs"]
    assert sum(v["caps_hit_without_round_limit"]["get_cap"] + v["caps_hit_without_round_limit"]["time_limit"] for v in Pg.values()) == 0
    chart = W["made_up_chart"]["results_in_record_id_order"]
    assert max(range(len(chart)), key=lambda i: chart[i]["effectiveDateTime"]) >= 20 and len(chart) == 30
    nb = bl and PS["blind"]["programs"]
    only_loinc = beh_b["main_code_values"].get("2823-3", 0)
    subj = lambda pre: sum(1 for k, v in Pg.items() if k.startswith(pre) and v["decision"]["replace"]["no_limit"] > 0 and v["relaxed"]["replace"]["no_limit"] == 0)  # noqa: E731
    over100 = sum(1 for c_ in AU["moments_that_require_the_orders"]["cells"] if c_["rows"] > 100)
    f8 = [x for x in W["released_case_failures"]["seen_limit_8_rounds"]["cases_with_a_failure"] if "exceeded_8_rounds" in x["relaxed_failure_reasons"]]
    lo8, hi8 = min(x["relaxed_failure_reasons"]["exceeded_8_rounds"] for x in f8), max(x["relaxed_failure_reasons"]["exceeded_8_rounds"] for x in f8)
    med = lambda x: f"{x:.0f}" if float(x).is_integer() else f"{x:.1f}"  # noqa: E731
    seen = {k: v for k, v in Pg.items() if k.startswith("seen")}
    s_next = sum(1 for v in seen.values() if v["searches"]["cases_following_next_link"] > 0)
    s_big = sum(1 for v in seen.values() if v["searches"]["cases_with_count_over_20"] > 0 and v["searches"]["cases_following_next_link"] > 0)
    s_sort = sum(1 for v in seen.values() if v["searches"]["cases_with_sort"] > 0)
    s_none = [v for v in seen.values() if not v["searches"]["cases_searching_each_code_value"]]
    s_first = sum(1 for v in seen.values() if v["behaviour"]["first_page_only"] and v["searches"]["cases_searching_each_code_value"])
    assert s_next + s_sort + s_first + len(s_none) == nb == len(seen) and all(v["relaxed"]["replace"]["no_limit"] == 0 for v in s_none)
    assert sum(1 for v in seen.values() if v["searches"]["cases_with_count_over_20"] > 0) == s_big

    def row(label, d):
        return (f'<tr><th scope="row">{label}</th><td class="num"><b>{d["programs_all_629_replace"]}</b></td><td class="num">{d["programs_all_6705_notLow"]}</td>'
                f'<td class="num">{d["programs_all_30_released"]}</td><td class="num">{med(d["replace_median"])}</td></tr>')
    return f"""
<section id="programs">
  <h2>Does a model-written program read past the first page?</h2>
  <p>In the runs above the model writes the agent’s message in each round of each instance. The task is the same computation for every patient, so the model can instead be asked to write it once as code, and the code can be run on every instance. Shi and coauthors asked language models to write code that operates on patient records,{c("shi")} and the authors of FHIR-AgentBench compare code generation with reasoning in natural language.{c("lee")} Here it was tested whether the code the model writes retrieves the patient’s most recent result. The counts in this section are of functions, and the counts above are of runs.</p>
  <p>{MODEL} was asked {nb} times, at temperature 1, for one Python function that does the whole task with the agent’s tools: the function takes as arguments a function for sending GET requests, the server’s address and the patient identifier, and returns the orders and the final answer. The prompt contained the benchmark’s tool definitions and the task’s instruction and context. It contained nothing about paging, sorting or the limit of 8 rounds.</p>
  <p>Each of the {nb} functions was then revised once. Each function was run on a synthetic potassium history of 30 results, served by the mock server, in which the most recent result is on the second page. The model was sent its function, the requests the function had made, the responses and what the function returned, and was asked to revise the function if it needed revising. The model was not told the expected orders, or whether the function’s orders were the expected ones.</p>
  <p>The {nb} functions and their {nb} revisions were run on all {n(POP["report_moments"])} derived instances and on the 30 released instances, against the mock server with its default sort order, and scored by the relaxed grader. Each function was run with a limit of {caps["gets_per_case"]} GET requests and {caps["seconds_per_case"]} seconds per instance, which no function reached, and again within the benchmark’s limit of 8 rounds. The table contains the action-required and no-action instances. The tied instances are left out, because the instruction does not state what is required on them.</p>
  <div class="tablewrap wide"><table class="tbl"><caption>Functions, of {nb}, that pass on every instance of a group</caption><thead><tr><td></td><th class="num">All {N} action-required instances</th><th class="num">All {n(NO_ACTION)} no-action instances</th><th class="num">All 30 released instances</th><th class="num">Median instances passed, of {N}</th></tr></thead><tbody>
    {row(f"The {nb} functions written from the task text and the tool definitions", bl)}
    {row("The same functions after one revision", se)}
    {row("The revised functions, within 8 rounds", s8)}
  </tbody></table></div>
  <p><b>Before revision.</b> All {beh_b["read_only_first_unsorted_page_most_cases"]} functions read only the first page of their search. Of the {nb}, {same["all_7590"]} return the same outcome as the first-page baseline, including the dose, on every one of the {n(POP["report_moments"])} derived instances, and {same["replace"]} do on all {N} action-required instances. {word(only_loinc, True)} search only under 2823-3 and submit no order on any instance. When asked for a program, the model wrote code that reads only the first page, as in most of the agent’s runs.</p>
  <p><b>After revision.</b> Of the {nb} functions, {s_next} follow the link to the next page, and {word(s_big)} of those also requests a larger page with <code>_count</code>. {word(s_sort, True)} sets <code>_sort</code>. {word(s_first, True)} still reads only the first page, and {word(len(s_none))} sends only a search with no code. The mock server, which contains only potassium results, returned the first page of those. The released server would also return the patient’s other observations to such a search, which was not run, so these runs do not reproduce the released server. That function passes on no action-required instance. With up to {caps["gets_per_case"]} GET requests allowed for each instance, {se["programs_all_629_replace"]} pass on all {N} action-required instances, and the same {se["programs_all_7334_replace_and_notLow"]} also pass on all {n(NO_ACTION)} no-action instances. Within 8 rounds, {word(s8["programs_all_629_replace"])} does: the function that sets <code>_sort</code>. Two orders and FINISH leave five rounds for searches, five pages contain at most 100 results, and {over100} of the {N} instances have a history of more than 100. On each of {word(len(f8))} released instances with long histories, between {lo8} and {hi8} of the {nb} revised functions reached the limit of 8 rounds.</p>
  <p>These counts have three limits. First, the limit of 8 rounds was not in the prompt, so these counts measure what the revision produced under a limit the model was not told about. They do not measure whether the model could write a function for that limit. Second, in the revision step the model received its own code, the requests and responses, and a second attempt, on a history in which the most recent result is on the second page, so the increase in passing functions cannot be attributed to any one of these three. Third, {subj("blind")} of the first {nb} functions return the first-page baseline’s outcomes but write the patient reference in a form the grader does not accept, so they pass on no action-required instance.</p>
  <p>The released grader passes no output of any function on any instance, for the same two reasons as the agent’s runs: the route written as an object, and the form of the final answer.</p>
</section>"""


# ------------------------------------------------------------------ the specification, the proofs, the dose

def spec():
    cf = EV["conflicts"]
    hard = cf["either_side_of_3.5"] + cf["all_below_3.5_doses_differ"]
    go = EV["conflicts_where_the_released_grader_requires_orders"]
    g_orders = sum(go.values())
    assert go["all_at_or_above_3.5"] == 0 and go["all_below_3.5_doses_differ"] == cf["all_below_3.5_doses_differ"]
    assert g_orders == TIED - BD["null_agent"]["conflict"]["pass"] == BD["full_chart_baseline"]["conflict"]["placed_orders"]
    fc = BD["full_chart_baseline"]
    assert fc["replace"]["dose_equals_the_specification"] == fc["replace"]["pass"] == N and fc["notLow"]["placed_orders"] == 0 and fc["notLow"]["pass"] == NO_ACTION
    d = AU["moments_where_latest_results_disagree"]
    t, r = d["conflictHard_table"], d["conflictHard_contract"]
    assert not GC["relaxed_pass_but_content_check_fails"]
    nu = POP["results_with_no_unit"]
    return f"""
<section id="spec">
  <h2>What is specified, and what is proved?</h2>
  <p>The outcome required on each derived instance is defined by a {g("specification")} of the instruction and computed by a {g("reference-implementation")}, both written in {g("lean")}.{c("lean")} The benchmark’s authors call their grading code a reference solution; the reference implementation here is a separate program written for this study. In earlier formal work on MedAgentBench, Mondl and coauthors translate agent instructions and policy documents into machine-checkable safety policies and measure how much of a synthetic policy the translated policies cover.{c("mondl")} Here, the required outcome of one task is specified.</p>
  <p>For each of the four kinds of program used on this page, the table contains what it does and the evidence that it does so correctly.</p>
  <div class="tablewrap wide"><table class="tbl tbl--compare tbl--thirds"><thead><tr><th>Program</th><th>What it does</th><th>Evidence about it</th></tr></thead><tbody>
    <tr><th scope="row">The reference implementation, in Lean</th><td>From a list of results and a clock time, computes the outcome the specification requires: no order, or the two orders with a dose.</td><td>Proved in Lean to meet the specification for every list of results.</td></tr>
    <tr><th scope="row">The scripted baselines, in Python</th><td>Search the record server and submit orders through the benchmark’s protocol.</td><td>Tested: run on every instance and scored by the released grader.</td></tr>
    <tr><th scope="row">The model-written functions, in Python</th><td>Search the record server and return orders and a final answer, as code written by the model.</td><td>Tested: run on every derived instance by a separate harness and scored by the relaxed grader. Nothing is proved about them.</td></tr>
    <tr><th scope="row">The released grader, in Python</th><td>Returns pass or fail for a run.</td><td>Used as released. A Lean description of how it selects a result and a dose is proved to agree with the specification under the conditions given below.</td></tr>
  </tbody></table></div>
  <h3>Choices made in the specification</h3>
  <p>On four points the text of the instruction and context does not determine the outcome. For each point the table contains the choice made in the specification, what the released grader’s code does, and the effect on the instances used here.</p>
  <div class="tablewrap wide"><table class="tbl tbl--compare tbl--four"><thead><tr><th>Open point</th><th>The specification</th><th>The released grader</th><th>Effect on the instances used here</th></tr></thead><tbody>
    <tr><th scope="row">Which results count</th><td>Results with the status <code>final</code> and an effective time at or before the task’s clock.</td><td>Every result, whatever its status or time.</td><td>None. All {n(POP["potassium_results"])} released results are final, and none is dated after the clock. FHIR defines <code>amended</code> and <code>corrected</code> as revisions of a final result,{c("fhir-status")} so results with those statuses would require a rule that is not yet in the specification.</td></tr>
    <tr><th scope="row">{g("tied", "Tied results")} with different values</th><td>No order.</td><td>The first of the tied results that the server lists.</td><td>Such a tie occurs on {TIED} derived instances. On {cf["all_at_or_above_3.5"]} of them every tied value is 3.5 or above, so the specification and the grader both require no order. On the other {hard} the dosing rule gives different outcomes for different tied values: on {cf["either_side_of_3.5"]} the tied values are on both sides of 3.5, and on {cf["all_below_3.5_doses_differ"]} every tied value is below 3.5 and the doses differ. The grader requires the two orders on {g_orders} of the {hard}, the instances on which the first tied result that the server lists is below 3.5. The specification requires no order on any of the {hard}.</td></tr>
    <tr><th scope="row">A result with no unit</th><td>Read as mmol/L.</td><td>The value is used as it is, which gives the same number.</td><td>No unit is recorded for {nu["n"]} results. One is recorded as 0.0, and on the instance where it is the most recent result the dosing rule gives {EV["largest_dose_mEq"]} mEq.</td></tr>
    <tr><th scope="row"><q>the next day at 8am</q></th><td>08:00:00 on the next calendar day, on the task’s clock.</td><td>Any time containing the text <code>2023-11-14T08:</code>.</td><td>In each of the model’s {n(GC["relaxed_pass"])} runs that the relaxed grader passes, in the two sort-order conditions and the two conditions with added information, the test order’s time also meets the specification’s reading. The task’s clock is in UTC, and the records contain no ward time zone.</td></tr>
  </tbody></table></div>
  <p>None of these choices was made by a clinician. Two tied values at one effective time may be two specimens, two methods or a duplicate, and the released records do not state which. A rule for tied results would require that information, or a convention set by the benchmark’s authors. Under the released grader the null agent passes {BD["null_agent"]["conflict"]["pass"]} of the {TIED} tied instances, which are the instances on which the grader requires no order, and the first-page baseline passes {BD["first_page_baseline"]["conflict"]["pass"]}.</p>
  <p>On the {hard} tied instances where the dosing rule gives different outcomes for different tied values, the results list was added to the task context, so that all the tied results were in the model’s context. Of the {t["runs"]}, the agent submitted no order on {t["placed_no_order"]}. It ordered a dose from the lowest tied value on {t.get("dosed_from_the_lowest_value", 0)} and from the highest on {t.get("dosed_from_the_highest_value", 0)}, and on {word(t["said_so"])} did its final answer state that the tied values differ. The specification’s rule was then added in two sentences: “Rules for reading these results: a result counts only if its status is final. If the counted results taken at the most recent time have different values, the task cannot be decided from the record: place no order and say so when you finish.” With them added, the agent submitted no order on {r["placed_no_order"]} of {r["runs"]}, and its final answer stated that the tied values differ on {r["placed_no_order_and_said_so"]}. The two sentences request both actions, so in these runs the agent’s actions matched the rule when the rule was in the task context. That is not evidence that the rule is the one a clinician would choose. Claude read each of the {t["runs"] + r["runs"]} final answers to confirm these counts.</p>
  <h3>What was verified in Lean</h3>
  <p>The specification, the reference implementation and the proofs are in one file, and Lean’s kernel checked the proof of every theorem below. Each theorem is stated for lists of results reduced to three fields: an effective time, a value in tenths of a mmol/L, and whether the status is final.</p>
  <ul class="proved">
    <li>For every list and every clock time, the reference implementation returns an outcome that satisfies the specification, and exactly one outcome satisfies it. The expected outcome on each of the {n(POP["report_moments"])} derived instances is therefore determined by the specification. {thm("run_meets_spec")} {thm("spec_unique")}</li>
    <li>The outcome does not depend on the order in which the results are listed, so the server’s sort order cannot change the required outcome. {thm("run_order_free")}</li>
    <li>A shorter list gives the same outcome as the patient’s full history if it contains every final result that has the most recent effective time at or before the clock, and nothing that is not in the history. A search that returns every final result at the most recent time therefore returns enough results to determine the required outcome, and no other result is needed. The results list used above was built to meet the condition, and the first-page baseline fails only on instances where the first page does not meet it. {thm("run_sufficient_view")}</li>
    <li>The theorem is false without the condition: Lean’s kernel checked an example in which a list missing one of two tied results has a different outcome. {thm("truncated_view_can_differ")}</li>
    <li>A Lean description of how the released grader selects a result and a dose gives the same outcome as the specification for any history in which every result is final, none is dated after the clock, and no two results with the same effective time differ. {thm("grader_agrees")} Some histories used here have such a tie at an earlier time, which the theorem does not cover, so the agreement was also tested by running the programs: the all-results baseline orders the specification’s dose on all {N} action-required instances and submits no order on all {n(NO_ACTION)} no-action instances, and the released grader passes it on every one of them.</li>
  </ul>
  <p>The proofs do not cover the code that reads a stored record into those three fields, the mock server, or the scoring of a run. No theorem states whether the specification is the right clinical reading of the instruction.</p>
  <details><summary>The specification in Lean</summary><pre><code>{lean_source()}</code></pre></details>
</section>"""


def dose():
    over = EV["decisions_over_20_mEq"]
    top = AU["instance_with_the_largest_required_dose"]["runs"]
    assert top["replace_newest"]["dose_ordered_mEq"] == EV["largest_dose_mEq"] and top["replace_newest"]["relaxed_grader_pass"]
    assert not top["replace_table"]["placed_an_order"] and top["replace_table"]["final_answer_calls_the_value_invalid"] and not top["replace_table"]["relaxed_grader_pass"]
    return f"""
<section id="dose">
  <h2>What does a pass mean clinically?</h2>
  <p>The sections above are about whether a run can pass on the released instances when the agent has not received the patient’s most recent result. This section is about what the benchmark’s rule requires an agent to order. Below, the required doses are compared with one product label. This comparison is not a clinical review, and no clinician has assessed these orders.</p>
  <p>The rule gives 10&nbsp;mEq for each 0.1&nbsp;mmol/L below 3.5, written into one dose field. A most recent result of 3.1 gives 40&nbsp;mEq, and a result of 2.8 gives 70&nbsp;mEq. The one released instance that requires the orders has a most recent result of 3.1, so the released grader requires a 40&nbsp;mEq order on it.</p>
  <figure class="wide">{fig_doses()}
    <figcaption><b>The dose the task’s rule requires on each of the {N} action-required derived instances.</b> The axis is broken between 140 and 350.</figcaption></figure>
  <p>The product with the NDC in the task context is a potassium chloride extended-release tablet of 20&nbsp;mEq. Its label gives 40 to 100&nbsp;mEq per day or more for the treatment of potassium depletion, and states that a daily dose above 20&nbsp;mEq should be divided so that no single dose exceeds 20&nbsp;mEq.{c("dailymed")} FHIR defines the order’s dose field as the amount given at one administration,{c("fhir-dosage")} and the task text contains no schedule. As graded, the order on {over} of the {N} derived instances is therefore a single dose above 20&nbsp;mEq of this product, and so is the 40&nbsp;mEq order on the released instance. Whether the benchmark’s authors intended a daily total is not stated in the task. This comparison is of the orders that the released grader passes; no patient’s treatment is assessed.</p>
  <p>The rule has no upper limit and no test of whether a value is plausible. The largest dose the rule gives here, {EV["largest_dose_mEq"]}&nbsp;mEq, is for the result recorded as 0.0 with no unit, which is not a plausible measurement. On that instance, in the model’s run with the most recent results first, the agent ordered {EV["largest_dose_mEq"]}&nbsp;mEq, and the relaxed grader passes that run. In the run with the results list in its context, the agent submitted no order and stated in its final answer that a potassium of 0.0 with no unit is not a valid result, and that run fails. Both graders require the {EV["largest_dose_mEq"]}&nbsp;mEq order on this instance.</p>
  <p>A pass on this task therefore means that the agent’s orders match the benchmark’s rule. It is not evidence that the order is appropriate for the patient, and on this instance the run whose final answer said the value is not a valid result is the one that fails. Blotske and coauthors, a group that includes clinical pharmacists, argue that the rule does not reflect the clinical complexity of potassium replacement, and they tested a model on vignettes written with fuller dosing guidance.{c("blotske")}</p>
</section>"""


def limits():
    kinds = S["differences_by_kind"]
    split = sum(v for k, v in kinds.items() if "split across pages" in k)
    total_only = sum(v for k, v in kinds.items() if "states a total" in k)
    unsorted_n = sum(s["of"] for s in S["searches"] if "_sort" not in s["search"])
    unsorted_same = sum(s["same"] for s in S["searches"] if "_sort" not in s["search"])
    assert unsorted_n == unsorted_same and split + total_only == S["all"] - S["all_same"]
    tr = AU["released_cases_same_requests"]
    he = PAIR["low_vs_high_reasoning_effort"]
    rep = PAIR["released_search_run_twice"]
    return f"""
<section id="limits">
  <h2>Limitations</h2>
  <ol>
    <li><b>One model, one setting.</b> The model’s results are for {MODEL} at low reasoning effort and temperature 0. On the first {he["moments_in_both"]} instances, the model passed {he["second_matched"]} at high reasoning effort, against {he["first_matched"]} at low effort. An agent that follows the link to the next page or sets <code>_sort</code> can receive the patient’s most recent result. How often other models do so was not measured in this study. The results for the three scripted baselines involve no model.</li>
    <li><b>One run per instance.</b> When the run was repeated on {rep["moments_in_both"]} instances, the pass or fail result differed on {rep["moments_in_both"] - rep["both_matched"] - rep["neither_matched"]}. The counts are of these particular runs. The outcome on a single instance is not a stable property of the model.</li>
    <li><b>One version of the benchmark.</b> The task file, the tool definitions and the grader are those of the original benchmark at commit <code>{A["benchmark_commit"][:7]}</code>. The corrected benchmark built by Mantravadi and coauthors could not be examined, because no code or data for it was found, so it was not tested whether a script that reads only the first page fails any of its instances.</li>
    <li><b>The derived instances are reconstructed, selected and clustered</b>, as set out under <a href="#derived">How were further instances derived?</a> The confidence intervals come from resampling patients. They express the uncertainty in a rate that comes from which {FP["patients"]} patients are in the data, and they do not describe the rate at other hospitals or on other record systems.</li>
    <li><b>The mock server is not Stanford’s server software.</b> On {n(S["all"])} test searches for the 100 real patients, it returned the same record ids in the same order, the same stated total and the same kinds of link as the released server in {n(S["all_same"])}. In sorted searches, this comparison does not include the order among results that share one effective time; when that order is also compared, {n(S["same_including_order_within_identical_times"])} are identical. All {n(unsorted_n)} searches without <code>_sort</code> were identical, and no run in the two sort-order conditions set <code>_sort</code>. The {S["all"] - S["all_same"]} differences are in sorted searches: in {split}, results that share one effective time fall on different sides of a page boundary, and in {total_only} only the mock server states a total. The condition with the two added sentences and the model-written programs do use sorted searches. On the 30 released instances the model passed 30 of 30 through either server, and the agent sent the same requests in the same order on {tr["control_pilot vs control_via_standin"]["same_requests_in_the_same_order"]} of 30, against {tr["control_pilot vs control_repeat"]["same_requests_in_the_same_order"]} of 30 for two runs on the released server itself.</li>
    <li><b>The relaxed grader is a choice made in this study.</b> It changes the form of the route and removes the final answer from scoring, which are the two undocumented requirements that every run of the model fails, and it keeps every other check. Removing the final answer means that a wrong statement in it is not counted. Under the released grader no run of the model passes.</li>
    <li><b>The proofs cover the specification and the reference implementation.</b> The code that reads records, serves searches and scores runs is not covered by the proofs.</li>
    <li><b>No clinician has reviewed this work.</b> The specification is one reading of the instruction. Under <a href="#dose">What does a pass mean clinically?</a> the rule’s doses are compared with one product label, and no patient’s treatment is assessed.</li>
  </ol>
</section>"""


def conclusion():
    tab = au("replace_table")
    return f"""
<section id="conclusion">
  <h2>Conclusion</h2>
  <p>On the 30 released instances of MedAgentBench’s potassium task, the released grader gives the same score to a script that retrieves the patient’s most recent result and to a script that reads only the first page of a search. From the benchmark’s own records, {N} further instances that require the orders were derived. On these the first-page baseline passes {FP["pass"]} and the all-results baseline passes all {ALLRES}.</p>
  <p>With the server’s default sort order, the agent requested only the first page in {REL["by_search"]["searched_K_and_read_the_first_page_only"]["runs"]} of the model’s {N} runs, and the model passed {REL["matched"]} under the relaxed grader. When the mock server listed the most recent results first, the model passed {NEW["matched"]}. On the first {tab["runs"]} instances, with the results list added to the task context, the model passed {tab["matched"]} of {tab["runs"]}. In {RETR_FAIL} of its {N - REL["matched"]} failed runs with the default sort order, the agent did not receive the patient’s most recent result. When asked to write the whole task as a program from the same tool definitions, instruction and context, the model wrote functions that read only the first page.</p>
  <p>Given these results, the benchmark’s authors could make four changes to the task.</p>
  <ol>
    <li>Instances could be added on which the patient’s most recent result is on a later page and the dosing rule gives a different order for it than for the most recent result on the first page. From the existing records, {FP_FAIL} such instances that require the orders and {BD["first_page_baseline"]["notLow"]["placed_orders"]} that require none can be derived.</li>
    <li>The tool definition could state the order and page size of a search, or the task could state that discovering them is part of what is tested.</li>
    <li>The grader could accept the route in the form the tool definition declares, and the task could state what the final answer must contain.</li>
    <li>The task could state whether the dose is a single dose or a daily total, and what an agent should do with a result that is not plausible. These two are questions for the benchmark’s clinical authors.</li>
  </ol>
  <p>The model’s numbers come from one model, one run per instance in each condition, and a grader with two checks relaxed, so they cannot be used to rank the model against others. No language model is involved in the comparison of the first-page and all-results baselines: the two scripts, which differ only in whether they retrieve the patient’s most recent result, receive the same score on the 30 released instances and different scores on {FP_FAIL} of the {N} derived ones.</p>
</section>"""


def made():
    main = sum(au(b)["runs"] for b in MAIN_BATCHES)
    tied = au("conflictHard_table")["runs"] + au("conflictHard_contract")["runs"]
    other = ALL["runs"] - main
    c0, c1, nlt = au("conflict"), au("conflict_table"), au("notLow_table")
    errs = [v for k, v in sorted(AU["batches"].items()) if k.startswith("err")]
    err_runs, err_ok = sum(v["runs"] for v in errs), sum(v["matched"] for v in errs)
    err_low = sum(v["runs"] for k, v in AU["batches"].items() if k.startswith("errLow")) // 2
    err_normal = sum(v["runs"] for k, v in AU["batches"].items() if k.startswith("errNormal")) // 2
    nf_b = ALL["runs_that_did_not_finish"]["by_batch"]
    nlt_unfinished = nf_b.get("notLow_table", 0)
    assert c0["runs"] + c1["runs"] + err_runs + nlt["runs"] == other - tied and len(errs) == 4
    assert nlt["matched"] + nlt_unfinished == nlt["runs"] and err_low + err_normal == err_runs // 2
    return f"""
<section id="made">
  <h2>How this was made</h2>
  <p>I directed the work and reviewed this page. Claude wrote the Lean specification and proofs, the analysis scripts and the text of this page under my direction, and ran the experiments. Lean’s kernel checked the proofs. The build script reads every count on the page from a results file, so no count is copied by hand. Reading the counts from files does not by itself establish that each sentence states correctly what its count counts.</p>
  <p>The page was then checked in further Claude sessions that had not written it. One read the page from the top as a new reader and listed each term that was used before it was introduced. One compared each count and each description of code with the scripts, the results files, the benchmark’s files and the released grader. One compared the wording with the papers cited here. One reviewed the layout from screenshots at laptop and phone sizes. One then edited the text for vague wording and for labels that are not standard terms, and another compared the edited text with the earlier text and listed each sentence whose claim had changed. Every correction that these sessions listed was made. No person other than the author has checked this work, and no one outside the study has reviewed it.</p>
  <p>The Lean files, the scripts, the three baselines, the model-written programs and the aggregate results are in <a class="ext" href="{REPO}">the repository</a>. A table in the repository has one row for each of the model’s runs in six conditions (the released instances on the released server, the action-required instances with each sort order, the sample of no-action instances, and the two conditions with added information), with its searches, its verdicts and its row in the error analysis table, and no patient values. The repository does not contain the benchmark’s patient records, Stanford’s grader file or the full transcripts, which contain record text. The six runs shown step by step, the first of which is on the instance drawn at the top of the page, are the only extracts of patient records on this page. This page also contains two single values from the records: the 3.1&nbsp;mmol/L of the released instance that requires the orders, and the result recorded as 0.0.</p>
  <h3 id="all-runs">Every run of the model</h3>
  <p>The model was run {n(ALL["runs"])} times in this study. {n(main)} of the runs are in ten conditions reported above: the 30 released instances on the released server, run twice, and once through the mock server; the {N} action-required instances with each sort order; a sample of 120 no-action instances; the repeat on 100 instances; the two conditions with added information, on 200 instances each; and high reasoning effort on 40 instances. A further {tied} are the runs on tied instances reported under <a href="#spec">What is specified, and what is proved?</a></p>
  <p>The other {n(other - tied)} runs were made to test three questions that are not reported in any section above: what the agent orders on a sample of tied instances, what it orders when a result is marked entered-in-error, and whether adding the results list changes the outcomes on no-action instances. Their outcomes are in the table below, so that every run of the model is on this page. Runs on tied instances and on instances with an added result are scored against the specification’s outcome, because the released grader counts a result whatever its status and takes the first of several tied results.</p>
  <div class="tablewrap wide"><table class="tbl"><thead><tr><th>Condition</th><th class="num">Runs</th><th>Outcome</th></tr></thead><tbody>
    <tr><th scope="row">{c0["runs"]} of the {TIED} tied instances, with the default sort order and nothing added</th><td class="num">{c0["runs"]}</td><td>The specification’s outcome, which is no order, in {c0["matched"]}. Of the other {c0["runs"] - c0["matched"]}, {nf_b.get("conflict", 0)} ended without a final answer and {c0["runs"] - c0["matched"] - nf_b.get("conflict", 0)} submitted an order.</td></tr>
    <tr><th scope="row">The same {c1["runs"]} tied instances, with the results list added</th><td class="num">{c1["runs"]}</td><td>The specification’s outcome in {c1["matched"]}. Of the other {c1["runs"] - c1["matched"]}, {nf_b.get("conflict_table", 0)} ended without a final answer and {c1["runs"] - c1["matched"] - nf_b.get("conflict_table", 0)} submitted an order.</td></tr>
    <tr><th scope="row">{err_low} action-required and {err_normal} no-action instances, each with one newer result added that is marked entered-in-error and has a value on the other side of 3.5. Each was run with the results list, and again with the results list and the two-sentence rule</th><td class="num">{err_runs}</td><td>The specification’s outcome, which does not count the added result, in {err_ok}. The released records contain no result with this status.</td></tr>
    <tr><th scope="row">The sample of {nlt["runs"]} no-action instances, with the results list added</th><td class="num">{nlt["runs"]}</td><td>Passed under the relaxed grader in {nlt["matched"]}. The other {nlt_unfinished} ended without a final answer.</td></tr>
  </tbody></table></div>
  <p class="note note--wide">The benchmark files are at commit <code>{A["benchmark_commit"][:10]}</code> of its repository. The grader file is not in that repository; the benchmark’s README contains a link to it. The copy used here has SHA-256 <code>{GRADER_SHA[:16]}…</code> and was run unmodified. The model was called through OpenRouter as <code>{esc(A["model"])}</code>.</p>
</section>"""


OFF30 = 30 - B30["first_page_holds_most_recent_result"]


BY = FP["by_chart"]


G_SHORT = "20 results or fewer"


G_ON = "over 20 results, most recent on the first page"


G_OFF = "over 20 results, most recent not on the first page"


FP_GOT = BY[G_SHORT]["instances"] + BY[G_ON]["instances"]


FP_SAME = BY[G_OFF]["pass"]


FP_NONE = N - BD["first_page_baseline"]["replace"]["placed_orders"]


FP_OTHER = BD["first_page_baseline"]["replace"]["placed_orders_with_another_dose"]


ALLRES = BD["full_chart_baseline"]["replace"]["pass"]


PATIENTS = POP["replace_moments"]["patients"]


RETR_FAIL = count(REL, "latest result never returned", "never searched")


MAIN_BATCHES = ("control_pilot", "control_repeat", "control_via_standin", "replace", "replace_newest", "replace_repeat", "replace_high", "replace_hint", "replace_table", "notLow")


def more(*xs):
    return '<span class="more">' + " ".join(f'<a href="#{i}">{t}</a>' for i, t in xs) + "</span>"


def lede():
    assert FP["pass"] == FP_GOT + FP_SAME and FP_NONE + FP_OTHER == FP_FAIL and BY[G_SHORT]["pass"] + BY[G_ON]["pass"] == FP_GOT
    assert B30["first_page_baseline"]["pass"] == B30["full_chart_baseline"]["pass"] == 30 and ALLRES == N
    ex = EX["examples"][0]
    rows = ex["chart"]
    latest = next(r for r in rows if r["latest"])
    first = next(t for t in ex["turns"] if t["action"] == "GET" and t["returned"])
    newest = max(first["rows"], key=lambda r: r["taken"])
    assert ex["required"]["outcome"] == "replace" and newest["value"] >= 3.5 and latest["value"] < 3.5 and not ex["relaxed_pass"]
    assert len(rows) - first["returned"] <= 20

    def cell(a, b, cls=""):
        return f'<td class="{cls.strip()}">{meter(a, b, "m--hot" if cls else "m--quiet")}</td>'
    return f"""
<div class="lede" id="finding">
  <p>MedAgentBench is a benchmark from Stanford for language-model agents that work in a simulated electronic health record, with the de-identified records of 100 patients.{c("jiang")} In its potassium task, the agent is asked to look up a patient’s most recent potassium result and, if it is below 3.5&nbsp;mmol/L, to submit two orders: replacement potassium, at a dose of 10&nbsp;{g("meq")} for every 0.1&nbsp;mmol/L below 3.5, and a repeat potassium test for the next morning. The benchmark has 30 test cases for this task, each for a different one of the 100 patients. On this page a test case is called an {g("instance")}.</p>
  <p>The agent finds a patient’s results by sending searches to the benchmark’s FHIR record server. The server returns the results of a search in pages of 20, one {g("page")} per response, in ascending order of record id. A record id is the identifier of one stored result, which FHIR calls its logical id, and record ids are not in date order. A script with no language model in it sends one search, takes the most recent result on the first page and applies the task’s dosing rule. The grader that Stanford released with the benchmark (the {g("grader")}) passes this script on all 30 instances. On {OFF30} of the 30, the patient’s most recent result is on a later page. On each of those {OFF30}, that result and the most recent result on the first page are both 3.5&nbsp;mmol/L or above, so for either result the task’s rule requires no order. The grader scores only what the agent submits: its orders, and the list of answers it gives when it finishes. The grader does not test which results the agent received.</p>
  <p>For this study, {n(POP["report_moments"])} further instances were derived from the benchmark’s own records. Each contains the {g("history", "potassium history")} of one of the 100 patients up to an earlier time: only the results reported by that time. On {N} of them, in {PATIENTS} of the patients, the most recent result at that time is below 3.5, so the two orders are required. On these {N} the same script, called the first-page baseline below, passes {FP["pass"]}. The all-results baseline is the same script with one change: it sends a search for all of the patient’s potassium results in one page. It passes all {ALLRES}.</p>
</div>
<div class="lead" id="summary-table"><div class="tablewrap"><table class="tbl tbl--lead">
  <caption>Two scripts that differ only in the search they send, scored by the released grader</caption>
  <thead>
    <tr><td></td><th scope="col">{g("first-page-baseline", "First-page baseline")}<span class="sub">one search, first page only</span></th><th scope="col">{g("full-chart-baseline", "All-results baseline")}<span class="sub">the same script, requesting every potassium result</span></th></tr>
  </thead>
  <tbody>
    <tr class="grp"><th scope="rowgroup" colspan="3">The 30 released instances</th></tr>
    <tr><th scope="row">Instances passed</th>{cell(B30["first_page_baseline"]["pass"], 30)}{cell(B30["full_chart_baseline"]["pass"], 30)}</tr>
    <tr><th scope="row">Runs in which the script received the patient’s most recent result</th>{cell(B30["first_page_holds_most_recent_result"], 30, " hot")}{cell(30, 30)}</tr>
    <tr class="grp"><th scope="rowgroup" colspan="3">The {N} derived instances that require the orders</th></tr>
    <tr><th scope="row">Instances passed</th>{cell(FP["pass"], N, " hot")}{cell(ALLRES, N)}</tr>
    <tr><th scope="row">Runs in which the script received the patient’s most recent result</th>{cell(FP_GOT, N, " hot")}{cell(N, N)}</tr>
  </tbody></table></div>
  <p class="note note--wide">On the released instances the released grader gives the two scripts the same score, although the first-page baseline does not receive the patient’s most recent result on {OFF30}. On the {N} derived instances the first-page baseline passes {FP["pass"]}: the {FP_GOT} on which it receives the patient’s most recent result, and {FP_SAME} on which the rule applied to an older result gives the same dose. It fails the other {FP_FAIL}, where it submits no order on {FP_NONE} and a different dose on {FP_OTHER}.</p>
</div>
<figure class="wide fig--lead" id="one-instance">{fig_chart(ex, on_label="on the first page of the search", off_label="on the second page")}
  <figcaption><b>One derived instance.</b> The patient has {len(rows)} potassium results, and the first page of the search contains {first["returned"]} of them. The most recent of those {first["returned"]} is {newest["value"]}&nbsp;mmol/L, so the first-page baseline submits no order. The patient’s most recent result, {latest["value"]}&nbsp;mmol/L, is on the second page. It is {round(10 * (3.5 - latest["value"])):d} tenths of a mmol/L below 3.5, so the task’s rule requires an order for {ex["required"]["dose_mEq"]}&nbsp;mEq and a repeat test, and the released grader fails the baseline’s run. With {MODEL}, the language model tested in this study, the agent received the same first page on this instance, did not request the second page and submitted no order (<a href="#transcript-1">run 1 under Six runs, step by step</a>).</figcaption>
</figure>"""


def summary():
    got30 = CP["matched"] - NO_RECENT_30
    only_r = REL["by_search"]["searched_only_by_2823-3"]["runs"]
    hint, tab = au("replace_hint"), au("replace_table")
    plain200 = PAIR["released_search_vs_paging_sentence"]["first_matched"]
    PS = W["primary_summary"]
    se, s8, nb = PS["seen_raised_caps"]["relaxed"], PS["seen_limit_8_rounds"]["relaxed"], PS["blind"]["programs"]
    first_only = W["summary"]["blind"]["programs_by_search_behaviour"]["read_only_first_unsorted_page_most_cases"]
    assert first_only == nb
    return f"""
<section id="abstract" class="abstract">
  <h2>Summary of the study</h2>
  <p>The opening above and this summary state the main results of the study. Six further results and the study’s limitations are summarised here, each with a link to the section in which the evidence is reported.</p>
  <ol class="findings">
    <li><b>With {MODEL}, the language model tested, the agent also stopped at the first page of its search, in {REL["by_search"]["searched_K_and_read_the_first_page_only"]["runs"]} of the {N} runs on the derived instances that require the orders, when the server used its default sort order.</b> The model was run with the benchmark’s own prompt, its descriptions of the requests the agent may send (the tool definitions) and its limit of 8 rounds, where a round is one message from the agent and the response it receives. It passed all 30 released instances, and in {got30} of those 30 runs the agent received the patient’s most recent result. The {N} derived instances that require the orders were served by a mock server, a program written for this study that answers searches as the released server does, with the same format, order and page size. On them the model passed {REL["matched"]} ({pct(REL["matched"], N)}) with the default sort order, which is ascending record id, and {NEW["matched"]} ({pct(NEW["matched"], N)}) when the mock server listed the most recent results first. The {g("relaxed-grader")} scored these runs. It is the released grader applied to each run after two changes: the route of administration on the medication order, which the model writes as an object, is rewritten as the plain string <code>oral</code> that the released grader requires, and the list of answers the agent gives when it finishes is removed from scoring. Without these changes the released grader passes none of the model’s runs. {more(("results", "Model results"))}</li>
    <li><b>In {RETR_FAIL} of the model’s {N - REL["matched"]} failed runs with the default sort order, the agent did not receive the patient’s most recent result.</b> In {only_r} of the {RETR_FAIL} the agent searched only under 2823-3, the LOINC code that the task text states for the repeat-test order, under which the server stores no results. {more(("errors", "Error analysis"))}</li>
    <li><b>The model writes the required orders when the patient’s most recent results are in the task context, the text the agent is given with the instruction.</b> On the first {hint["runs"]} of the {N} instances, taken in a fixed random order, the model passed {plain200} under the relaxed grader with nothing added to the task context. It passed {hint["matched"]} when two sentences about paging and sorting were added, and {tab["matched"]} when a list of the patient’s most recent results was added. {more(("context", "What changes the model’s behaviour"))}</li>
    <li><b>When asked to write the task as a program, the model wrote functions that read only the first page.</b> The model was asked {nb} times for a Python function that does the whole task, and all {nb} functions read only the first page of their search. After one revision, in which the model was sent each function’s requests and responses on a synthetic potassium history and asked to revise the function, {se["programs_all_629_replace"]} of the {nb} revised functions pass on all {N} derived instances that require the orders, under the relaxed grader. Within the benchmark’s limit of 8 rounds, {word(s8["programs_all_629_replace"])} of them does. {more(("programs", "Model-written programs"))}</li>
    <li><b>The required outcome was written in {g("lean")}, a proof checker, and it was proved in Lean that a subset of a patient’s results has the same required outcome as the full history if it contains every result at the most recent time whose FHIR status is <code>final</code>.</b> The task’s instruction was written as a {g("specification")}, and a {g("reference-implementation")} was proved to meet it. It was also proved that the outcome the specification requires is unique, and that it does not depend on the order in which the results are listed. {more(("spec", "Specification and proofs"))}</li>
    <li><b>A pass is not evidence that an order is clinically appropriate.</b> Under the task’s rule the required dose is above 20&nbsp;mEq on {EV["decisions_over_20_mEq"]} of the {N} instances, and the label of the product identified in the task states that no single dose should exceed 20&nbsp;mEq. On one instance the most recent result is recorded as 0.0: a run in which the agent ordered the rule’s {EV["largest_dose_mEq"]}&nbsp;mEq passes, and a run in which the agent submitted no order and its final answer said that the value is not a valid result fails. {more(("dose", "What a pass means clinically"))}</li>
    <li><b>Limitations.</b> One model was run, once per instance in each condition. The {N} instances come from {PATIENTS} patients and were selected because they require the orders. The benchmark’s original release was examined. A corrected version, published later by Mantravadi and coauthors, could not be examined, because no code or data for it was found. No clinician has reviewed the specification. {more(("limits", "Limitations"))}</li>
  </ol>
</section>"""


def shortcut():
    fpd, nad, ard = BD["first_page_baseline"], BD["null_agent"], BD["full_chart_baseline"]
    mp = lambda x: f"{100 * x:.0f}%"  # noqa: E731
    rows = [(G_SHORT, "20 results or fewer, so one page contains all of them"), (G_ON, "More than 20 results, and the most recent is on the first page"),
            (G_OFF, "More than 20 results, and the most recent is on a later page")]
    by_html = "".join(f'<tr><th scope="row">{label}</th><td class="num">{BY[k]["instances"]}</td><td class="num"><b>{BY[k]["pass"]}</b></td><td class="num">{BY[k]["instances"]}</td></tr>' for k, label in rows)
    return f"""
<section id="shortcut">
  <h2>How does the released grader score the baselines on the derived instances?</h2>
  <p>The three scripted baselines were run on every derived instance through the benchmark’s protocol. The released server contains only each patient’s complete record, so the derived instances were served by a {g("mock-server")}: a program written for this study that answers searches as the released server does, with the same format, order and page size, 20 results to a page in ascending order of record id. A comparison of its responses with the released server’s responses is under <a href="#limits">Limitations</a>. The released grader scored every transcript.</p>
  <div class="tablewrap wide"><table class="tbl tbl--main"><caption>Instances passed under the released grader</caption>
    <thead><tr><td></td><th>The {N} action-required instances</th><th class="num">The {n(NO_ACTION)} no-action instances</th></tr></thead><tbody>
    <tr><th scope="row">Null agent</th><td>{meter(nad["replace"]["pass"], N, "m--quiet")}</td><td class="num">{n(nad["notLow"]["pass"])}</td></tr>
    <tr><th scope="row">First-page baseline</th><td>{meter(FP["pass"], N)}</td><td class="num">{n(fpd["notLow"]["pass"])}</td></tr>
    <tr><th scope="row">All-results baseline</th><td>{meter(ALLRES, N, "m--quiet")}</td><td class="num">{n(ard["notLow"]["pass"])}</td></tr>
  </tbody></table></div>
  <p>The first-page baseline fails {FP_FAIL} of the {N} action-required instances. On {FP_NONE} it submits no order, because the most recent result on the first page is 3.5 or above. On {FP_OTHER} it submits a dose computed from an older low result. On the no-action instances it fails the other way: on {fpd["notLow"]["placed_orders"]} of the {n(NO_ACTION)} it submits an order that is not required, because an older low result is on the first page and the patient’s most recent result is not. The null agent, which passes 29 of the 30 released instances, passes none of the {N}.</p>
  <div class="tablewrap wide"><table class="tbl tbl--fit"><caption>The first-page baseline and the all-results baseline, by the length of the patient’s potassium history</caption><thead><tr><th>The patient’s potassium history on the instance</th><th class="num">Instances</th><th class="num">First-page baseline passed</th><th class="num">All-results baseline passed</th></tr></thead><tbody>{by_html}</tbody></table></div>
  <p>Only in the third group can the two baselines receive different scores. It has {BY[G_OFF]["instances"]} instances. On {FP_FAIL} of them the dosing rule applied to the most recent result on the first page gives a different order from the one required, and on the other {FP_SAME} it gives the same dose. On those {FP_FAIL}, a script that reads only the first page orders differently from a script that reads every result.</p>
  <p>The {N} instances are not independent. They come from {FP["patients"]} patients, and a patient with a long history has many instances, so two numbers are also computed by patient. The per-instance pass rate is the share of the {N} instances that a script or the model passes. A cluster bootstrap that resamples patients gives a 95% confidence interval ({g("ci")}) of {ci(FP["interval_95_resampling_patients"])} for the first-page baseline’s per-instance pass rate. The patient-level mean, which is the average of the {FP["patients"]} patients’ own pass rates, is {mp(FP["mean_of_patient_pass_rates"])} for the first-page baseline, against a per-instance pass rate of {pct(FP["pass"], N)}.</p>
</section>"""


def context():
    hint, tab = au("replace_hint"), au("replace_table")
    ph, pn200 = PAIR["released_search_vs_paging_sentence"], PAIR["newest_first_vs_table"]
    pt = PAIR["released_search_vs_table"]
    hs = hint["by_search"]["searched_K_and_asked_for_sorting"]
    n_prio = count(tab, "required dose ordered")
    n_none = count(tab, "latest result never returned; no order")
    n_route = tab["runs"] - tab["matched"] - n_prio - n_none
    return f"""
<section id="context">
  <h2>What changes the model’s behaviour?</h2>
  <p>In the two conditions above the prompt was the same and the server’s sort order changed. In two further conditions the mock server used the default sort order and text was added to the task context. Both were run on the first {hint["runs"]} of the {N} instances in the same fixed sequence. On those {hint["runs"]} the model passed {ph["first_matched"]} with nothing added and {pn200["first_matched"]} when the server listed the most recent results first. The relaxed grader scored every run in this section.</p>
  <div class="tablewrap wide"><table class="tbl"><thead><tr><th>What was added to the task context</th><th class="num">Passed</th><th>What the agent did in these runs</th></tr></thead><tbody>
    <tr class="ref"><th scope="row">Nothing</th><td class="num"><b>{ph["first_matched"]}</b> of {hint["runs"]}</td><td>These are the first {hint["runs"]} of the {N} runs with the default sort order.</td></tr>
    <tr><th scope="row">Two sentences: that a search returns 20 results per page in no time order, and the parameters that set the sort order</th><td class="num"><b>{hint["matched"]}</b> of {hint["runs"]}</td><td>In {hs["runs"]} runs the agent searched under K and requested sorted results, and {hs["matched"]} of those runs passed. In the other {hint["by_search"]["searched_only_by_2823-3"]["runs"]} the agent searched only under 2823-3, against {ph["first_searched_only_by_2823-3"]} on the same {hint["runs"]} instances with nothing added.</td></tr>
    <tr><th scope="row">A list of the patient’s most recent potassium results, called the results list below</th><td class="num"><b>{tab["matched"]}</b> of {tab["runs"]}</td><td>The agent still sent its own potassium search in {tab["runs_that_also_searched_for_potassium"]} of the {tab["runs"]} runs.</td></tr>
  </tbody></table></div>
  <p class="note note--wide">The two sentences: “Searches on this record server return 20 results per page, in no time order. Add &amp;_sort=-date&amp;_count=5 to a search to get the most recent results first.” The results list is headed “Potassium results in this patient’s record, most recent first (code K)” and has one row for each result, with the time the specimen was taken, the time the result was reported, the value with its unit, and the status.</p>
  <p><b>With the two sentences added</b>, the pass rate was {100 * ph["difference_in_share"]:.0f} percentage points higher than with nothing added (95% CI {100 * ph["interval_95_resampling_patients"][0]:.0f} to {100 * ph["interval_95_resampling_patients"][1]:.0f}). In more runs the agent also stopped after the search under 2823-3 ({hint["by_search"]["searched_only_by_2823-3"]["runs"]} against {ph["first_searched_only_by_2823-3"]}), and with one run per instance that increase cannot be attributed to the two sentences.</p>
  <p><b>The results list</b> has eight rows, or more when more than eight results share the most recent time, so that it always contains every final result at the patient’s most recent effective time. That is the condition under which it was proved in Lean that a subset of the results gives the same outcome as the full history (<a href="#spec">What is specified, and what is proved?</a>). The number eight was chosen for this study, and the proved condition requires only the results at the most recent time. With the results list in its context the model ordered the required dose and wrote both orders on {tab["matched"]} of {tab["runs"]} instances, {100 * pt["difference_in_share"]:.0f} percentage points more than with nothing added (95% CI {100 * pt["interval_95_resampling_patients"][0]:.0f} to {100 * pt["interval_95_resampling_patients"][1]:.0f}).</p>
  <p>Of the {tab["runs"] - tab["matched"]} runs that failed with the results list, in {n_prio} the agent wrote the test order’s priority as <code>routine</code> and in {n_route} it left the route out of the medication order. In the remaining {n_none} the agent submitted no order on the instance whose most recent result is recorded as 0.0 with no unit, and its final answer said that this was not a valid result. Both graders fail that run (<a href="#dose">What does a pass mean clinically?</a>).</p>
  <p>The two sentences state how to sort a search, and the results list contains the patient’s most recent results. The model is the same in every condition. When the results are in its context the model computes the required dose and writes both orders on {tab["matched"]} of {tab["runs"]} instances. The agent still sent its own search in most of those runs, so it cannot be concluded that the model’s orders came from the results list.</p>
</section>"""


def shown_because(text):
    """The stored selection rule, in the page's current terms."""
    for a, b in ((" chart ", " potassium history "), ("no reply held", "no response contained"), ("a reply held", "a response contained"), ("the latest result", "the most recent result"),
                 ("placed no order", "submitted no order"), ("placed", "submitted"), (" at an ", " on an "), (" at a ", " on a "), (" at which", " on which"),
                 ("previous transcript", "previous run"), ("under the most-recent-first sort order at the same instance", "on the same instance with the most recent results first"),
                 ("searched only by", "searched only under"), ("searched by", "searched under")):
        text = text.replace(a, b)
    return text


SECTIONS = [("abstract", "Summary of the study", summary), ("background", "Background", background), ("task", "What is the agent asked to do?", task),
            ("grading", "How is a run graded?", grading), ("released", "Why does a script that reads only the first page pass all 30 released instances?", released),
            ("derived", "How were further instances derived?", derived), ("shortcut", "How does the released grader score the baselines on the derived instances?", shortcut),
            ("results", "Does a language model also stop at the first page?", results), ("context", "What changes the model’s behaviour?", context),
            ("transcripts", "Six runs, step by step", transcripts), ("programs", "Does a model-written program read past the first page?", programs),
            ("spec", "What is specified, and what is proved?", spec), ("dose", "What does a pass mean clinically?", dose),
            ("limits", "Limitations", limits), ("conclusion", "Conclusion", conclusion), ("made", "How this was made", made)]


def page():
    parts_ = [(i, t, f()) for i, t, f in SECTIONS if f]
    body = "".join(h for _, _, h in parts_)
    shown = {i for i, _, h in parts_ if h.strip()}
    toc_items = [("finding", "The finding")] + [(i, t) for i, t, _ in SECTIONS if i in shown] + [("refs", "References"), ("glossary", "Glossary")]
    toc = "".join(f'<li><a href="#{i}">{esc(t)}</a></li>' for i, t in toc_items)
    title = "How MedAgentBench’s potassium task is evaluated"
    subtitle = (f"A script that reads only the first page of search results passes all 30 of the benchmark’s test cases for this task. "
                f"On {OFF30} of them, that page does not contain the patient’s most recent potassium result.")
    top = lede()
    refs = references_html()
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="MedAgentBench’s potassium task followed from the instruction to the grading code. A script that reads only the first page of search results passes all 30 released instances, and {FP['pass']} of {N} instances derived from the benchmark’s own records.">
<meta name="theme-color" content="#f8f0e2" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1c1526" media="(prefers-color-scheme: dark)">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="plectis.svg" type="image/svg+xml">
<link rel="preload" href="fonts/plectis-serif.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="fonts/plectis-sans.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="tokens.css">
<link rel="stylesheet" href="base.css">
<link rel="stylesheet" href="page.css">
<script src="theme-init.js"></script>
</head>
<body>
<a class="skip" href="#main">Skip to the article</a>
<header class="top"><div class="top__in">
  <span class="lockup">
    <a class="lockup__home" href="https://wcook04.github.io/" rel="author" title="All of Will Cook’s projects"><img src="plectis.svg" alt="Will Cook: all projects" width="24" height="24"></a>
    <a class="lockup__name" href="#top">MedAgentBench’s potassium task</a>
  </span>
  <span class="top__tools">
    <a class="top__link top__toc" href="#contents">Contents</a><a class="top__link" href="#abstract">Summary</a><a class="top__link" href="#results">Model results</a><a class="top__link" href="#transcripts">Six runs</a>
    <button type="button" class="theme" id="theme" aria-label="Switch between day and night colours">Night</button>
  </span>
</div></header>

<div class="layout">
<nav class="toc" id="contents" aria-label="Contents"><details open><summary class="toc__h">Contents</summary><ol>{toc}</ol></details></nav>
<main id="main">
<header class="head" id="top">
  <h1>{title}</h1>
  <p class="subtitle">{subtitle}</p>
  <p class="byline">Will Cook, 18 November 2026</p>
  <p class="byline byline--note">The analysis and the text were produced with Claude: see <a href="#made">How this was made</a>.</p>
  <p class="actions"><a class="btn btn--primary" href="#abstract">Summary of the study</a><a class="btn" href="#transcripts">Six runs, step by step</a><a class="btn ext" href="{REPO}">Code, proofs and data</a></p>
</header>
{top}
{body}
<section id="refs">
  <h2>References</h2>
  {refs}
</section>
<section id="glossary">
  <h2>Glossary</h2>
  <p class="note">Terms with a dotted underline in the text link here. On a screen with a pointer, the definition appears when the pointer rests on a term.</p>
  {glossary_html()}
</section>
<footer class="foot"><span>Will Cook, 18 November 2026</span><a class="ext" href="{REPO}">Code, proofs and data</a><a href="#made">How this was made</a><a href="#top">Back to the top</a></footer>
</main>
</div>
<script src="page.js"></script>
</body>
</html>
"""


if __name__ == "__main__":
    open(os.path.join(HERE, "theme-init.js"), "w").write(
        'try { var s = localStorage.getItem("medagentbench-reader-theme"); if (s === "light" || s === "dark") document.documentElement.setAttribute("data-theme", s); } catch (e) {}\n')
    open(os.path.join(HERE, "index.html"), "w").write(page())
    print("wrote site/index.html")
