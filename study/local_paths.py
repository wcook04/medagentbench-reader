"""Where this machine keeps what the repository does not hold.

Set these environment variables, or write study/local.json (not committed) with the same names in lower case:

  MEDAGENTBENCH_REPO     a checkout of github.com/stanfordmlgroup/MedAgentBench at the commit named in run_task9.py
  MEDAGENTBENCH_GRADER   the task grader file that the benchmark's README links to (refsol.py)
  KEY_LOADER_PATH        optional: a directory whose system.lib.openrouter_free_runtime loads OPENROUTER_API_KEY
"""
import json, os

_HERE = os.path.dirname(os.path.abspath(__file__))


def local(name):
    """Returns the configured value, or None when it is not set."""
    v = os.environ.get(name.upper())
    if v:
        return v
    p = os.path.join(_HERE, "local.json")
    return (json.load(open(p)) if os.path.exists(p) else {}).get(name)
