import json
import sys

req = json.load(sys.stdin)
action = req.get("action_id")
count = 1 if action == "increment" else 0
json.dump(
    {
        "probe_id": req.get("probe_id"),
        "success": True,
        "observation": {"count": count},
        "state": {"count": count},
        "authorization_ok": True,
    },
    sys.stdout,
)
