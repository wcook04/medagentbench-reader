# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_02.py after one look at the server's responses on a made-up chart, seed 1002, temperature 1.0. Unedited.
import json
from urllib.parse import urlencode
from decimal import Decimal, ROUND_CEILING

def run_task(get, api_base, mrn):
    base = api_base.rstrip("/")

    # Fetch all pages of potassium observations for this patient.
    observations = []
    url = f"{base}/Observation?{urlencode({'patient': mrn, 'code': 'K'})}"
    seen_urls = set()
    while url and url not in seen_urls:
        seen_urls.add(url)
        try:
            response_text = get(url)
        except Exception:
            break
        try:
            bundle = json.loads(response_text)
        except Exception:
            break
        if not isinstance(bundle, dict):
            break
        for entry in bundle.get("entry", []) or []:
            resource = entry.get("resource", entry) if isinstance(entry, dict) else {}
            if isinstance(resource, dict):
                observations.append(resource)
        # Follow pagination "next" link if present.
        next_url = None
        for link in bundle.get("link", []) or []:
            if isinstance(link, dict) and link.get("relation") == "next":
                next_url = link.get("url")
                break
        url = next_url

    most_recent_value = None
    most_recent_datetime = ""

    for resource in observations:
        if resource.get("resourceType") not in (None, "Observation"):
            continue

        value = None
        if isinstance(resource.get("valueQuantity"), dict):
            value = resource["valueQuantity"].get("value")
        if value is None and "valueString" in resource:
            try:
                value = float(resource["valueString"])
            except Exception:
                pass
        if value is None:
            continue

        dt = (
            resource.get("effectiveDateTime")
            or resource.get("issued")
            or resource.get("effectiveInstant")
            or ""
        )
        if not dt and isinstance(resource.get("effectivePeriod"), dict):
            dt = resource["effectivePeriod"].get("start", "")

        if most_recent_value is None or dt > most_recent_datetime:
            most_recent_value = value
            most_recent_datetime = dt

    posts = []
    answers = []

    if most_recent_value is None:
        answers.append(f"No potassium level found for patient {mrn}.")
        return posts, answers

    try:
        level = Decimal(str(most_recent_value))
    except Exception:
        answers.append(f"Most recent potassium level could not be interpreted: {most_recent_value}.")
        return posts, answers

    threshold = Decimal("3.5")

    if level < threshold:
        deficit = threshold - level
        increments = (deficit / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
        dose_mEq = int(increments) * 10

        authored_on = "2023-11-13T10:15:00+00:00"
        next_day_8am = "2023-11-14T08:00:00+00:00"

        medication_request = {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/sid/ndc",
                        "code": "40032-917-01",
                        "display": "Potassium replacement"
                    }
                ],
                "text": "Potassium oral repletion"
            },
            "authoredOn": authored_on,
            "dosageInstruction": [
                {
                    "route": {"text": "oral"},
                    "doseAndRate": [
                        {
                            "doseQuantity": {
                                "value": dose_mEq,
                                "unit": "mEq"
                            }
                        }
                    ]
                }
            ],
            "status": "active",
            "intent": "order",
            "subject": {"reference": f"Patient/{mrn}"}
        }

        service_request = {
            "resourceType": "ServiceRequest",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "2823-3",
                        "display": "Potassium [Moles/volume] in Serum or Plasma"
                    }
                ]
            },
            "authoredOn": authored_on,
            "status": "active",
            "intent": "order",
            "priority": "stat",
            "subject": {"reference": f"Patient/{mrn}"},
            "occurrenceDateTime": next_day_8am
        }

        posts.append((f"{base}/MedicationRequest", medication_request))
        posts.append((f"{base}/ServiceRequest", service_request))

        answers.append(
            f"Most recent potassium level is {most_recent_value} mEq/L, which is low. "
            f"Ordered {dose_mEq} mEq oral potassium replacement and a morning serum potassium level "
            f"for {next_day_8am}."
        )
    else:
        answers.append(
            f"Most recent potassium level is {most_recent_value} mEq/L, which is not low. "
            f"No replacement potassium was ordered."
        )

    return posts, answers
