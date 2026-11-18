"""Scripted submissions against Stanford's released task 9 grader, on synthetic potassium rows.

The grader file is distributed by Stanford through a Box link in the benchmark README and is not
copied into this repository. Pass its path. Its `task9` function runs unmodified; only its record
request is replaced by a function returning the synthetic rows.

Usage: python3 study/grader_controls.py --grader /path/to/refsol.py --out results/grader_controls.json
"""
import argparse, hashlib, io, json, types, contextlib, copy

BASE = "http://localhost:8080/fhir/"
MRN = "SYNTHETIC"
CLOCK = "2023-11-13T10:15:00+00:00"


def load(path):
    src = open(path).read()
    sha = hashlib.sha256(src.encode()).hexdigest()
    mod = types.ModuleType("refsol")
    mod.__dict__["send_get_request"] = lambda url, **k: {"data": json.dumps({"entry": mod.ROWS})}
    exec(compile(src.replace("from .utils import *", ""), "refsol", "exec"), mod.__dict__)
    return mod, sha


class Msg:
    def __init__(self, role, content):
        self.role, self.content = role, content


class Run:
    def __init__(self, posts, final):
        self.history = []
        for url, payload in posts:
            self.history.append(Msg("agent", f"POST {url}\n{json.dumps(payload)}"))
            self.history.append(Msg("user", "POST request accepted and executed successfully. Please call FINISH if you have got answers for all the questions and finished all the requested tasks"))
        self.result = final


def row(time, value, status="final", unit="mmol/L"):
    return {"resource": {"resourceType": "Observation", "status": status, "effectiveDateTime": time,
                         "valueQuantity": {"value": value, "unit": unit}}}


def med(dose, route="oral", unit="mEq"):
    return (BASE + "MedicationRequest", {
        "resourceType": "MedicationRequest",
        "medicationCodeableConcept": {"coding": [{"system": "http://hl7.org/fhir/sid/ndc", "code": "40032-917-01"}]},
        "authoredOn": CLOCK,
        "dosageInstruction": [{"route": route, "doseAndRate": [{"doseQuantity": {"value": dose, "unit": unit}}]}],
        "status": "active", "intent": "order", "subject": {"reference": f"Patient/{MRN}"}})


def lab(when="2023-11-14T08:00:00+00:00", priority="stat"):
    return (BASE + "ServiceRequest", {
        "resourceType": "ServiceRequest",
        "code": {"coding": [{"system": "http://loinc.org", "code": "2823-3"}]},
        "authoredOn": CLOCK, "status": "active", "intent": "order", "priority": priority,
        "subject": {"reference": f"Patient/{MRN}"}, "occurrenceDateTime": when})


LOW = [row("2023-11-13T08:00:00+00:00", 3.1)]
CONTROLS = [
    # id, what is submitted, rows, posts, final answer, what the instruction requires of this submission
    ("reference", "Low result 3.1. Orders 40 mEq oral and a potassium level at 08:00 next day.", LOW, [med(40), lab()], "[3.1]", "meets"),
    ("route_as_declared", "Same orders; route written as the object the tool schema declares, {\"text\": \"oral\"}.", LOW, [med(40, route={"text": "oral"}), lab()], "[3.1]", "meets"),
    ("lab_first", "Same two orders, lab order sent before the medication order.", LOW, [lab(), med(40)], "[3.1]", "meets"),
    ("priority_routine", "Same orders; lab priority \"routine\".", LOW, [med(40), lab(priority="routine")], "[3.1]", "meets"),
    ("unit_lowercase", "Same orders; dose unit written \"meq\".", LOW, [med(40, unit="meq"), lab()], "[3.1]", "meets"),
    ("lab_0859", "Lab ordered for 08:59:59 next day.", LOW, [med(40), lab("2023-11-14T08:59:59+00:00")], "[3.1]", "does not meet"),
    ("lab_other_zone", "Lab ordered for 08:00 next day at UTC−8, which is 16:00 on the task's clock.", LOW, [med(40), lab("2023-11-14T08:00:00-08:00")], "[3.1]", "does not meet"),
    ("wrong_dose", "Orders 20 mEq where the rule gives 40.", LOW, [med(20), lab()], "[3.1]", "does not meet"),
    ("no_orders_low", "Low result; no orders; empty answer.", LOW, [], "[]", "does not meet"),
    ("no_result_no_orders", "No potassium result in the record; no orders; empty answer.", [], [], "[]", "meets"),
    ("normal_no_orders", "Latest result 4.0; no orders; empty answer.", [row("2023-11-13T08:00:00+00:00", 4.0)], [], "[]", "meets"),
    ("tie_low_first", "Two results at the same time, 3.3 then 3.6 in server order; orders 20 mEq.",
     [row("2023-11-13T08:00:00+00:00", 3.3), row("2023-11-13T08:00:00+00:00", 3.6)], [med(20), lab()], "[3.3]", "undetermined"),
    ("tie_low_second", "The same two results in the other order, 3.6 then 3.3; the same orders.",
     [row("2023-11-13T08:00:00+00:00", 3.6), row("2023-11-13T08:00:00+00:00", 3.3)], [med(20), lab()], "[3.3]", "undetermined"),
    ("future_low", "Latest result before the clock is 4.0. A result of 3.0 is dated one hour after the clock. No orders.",
     [row("2023-11-13T08:00:00+00:00", 4.0), row("2023-11-13T11:15:00+00:00", 3.0)], [], "[]", "meets"),
    ("error_low", "Latest result is 3.0 with status entered-in-error; the one before is 4.0. No orders.",
     [row("2023-11-13T07:00:00+00:00", 4.0), row("2023-11-13T08:00:00+00:00", 3.0, status="entered-in-error")], [], "[]", "meets"),
    ("very_low", "Latest result 1.0. Orders 250 mEq oral, as the dosing sentence computes.", [row("2023-11-13T08:00:00+00:00", 1.0)], [med(250), lab()], "[1.0]", "meets"),
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--grader", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    mod, sha = load(a.grader)
    out = []
    for cid, text, rows, posts, final, instruction in CONTROLS:
        mod.ROWS = copy.deepcopy(rows)
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                verdict = mod.task9({"id": "task9_control", "eval_MRN": MRN}, Run(posts, final), BASE) is True
            except Exception as e:  # the grader raised
                verdict = False
        out.append({"id": cid, "submission": text, "instruction": instruction, "grader_pass": verdict})
        print(f"{cid:22} instruction: {instruction:14} grader: {'pass' if verdict else 'fail'}")
    json.dump({"grader_sha256": sha, "rows": "synthetic", "controls": out}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
