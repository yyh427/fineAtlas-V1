"""Model-selected text and navigation requests with compact default feedback."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path

from fineatlas.experiment import FineAtlasExperimentTool
from fineatlas.model_display import simple_feedback


REQUEST_FIELDS = frozenset((
    "session_id", "request_id", "action", "query", "domain",
    "task_dataset_context", "anchor_handles", "target_granularity", "limit",
    "cursor", "max_depth", "node_budget", "edge_budget",
))


def run_requests(config, requests: Path, output: Path, diagnostics: Path | None = None,
                 *, detailed: bool = False) -> dict:
    paths = [requests.resolve(), output.resolve()]
    if diagnostics:
        paths.append(diagnostics.resolve())
    if len(paths) != len(set(paths)):
        raise ValueError("Input, model output and diagnostics must use separate files")
    sessions = {}
    seen = set()
    with ExitStack() as stack:
        source = stack.enter_context(requests.open(encoding="utf-8"))
        public = stack.enter_context(output.open("w", encoding="utf-8"))
        private = (stack.enter_context(diagnostics.open("w", encoding="utf-8"))
                   if diagnostics else None)
        for line in source:
            request = json.loads(line)
            key = (request.get("session_id"), request.get("request_id"))
            if set(request) - REQUEST_FIELDS or not all(key) or key in seen:
                raise ValueError("Invalid, duplicate or forbidden gold/UID fields")
            seen.add(key)
            if key[0] not in sessions:
                sessions[key[0]] = stack.enter_context(FineAtlasExperimentTool(config))
            tool = sessions[key[0]]
            action = request["action"]
            dataset = request.get("task_dataset_context")
            if action == "entries":
                result = tool.entries()
            elif action == "query":
                result = tool.query(request["query"], dataset=dataset,
                                    domain=request.get("domain"),
                                    limit=request.get("limit", 20))
            elif action in ("scope", "expand"):
                options = {k: request[k] for k in (
                    "limit", "cursor", "target_granularity", "max_depth",
                    "node_budget", "edge_budget") if k in request}
                result = tool.scope(request["anchor_handles"], dataset=dataset,
                                    text=request.get("query"), expand=action == "expand",
                                    **options)
            else:
                raise ValueError("Unknown navigation action")
            choices = tool.allowed_choices(result) if action != "entries" else ()
            feedback = tool.candidate_wire(result) if detailed else simple_feedback(result)
            row = {
                "session_id": key[0], "request_id": key[1], "feedback": feedback,
                "allowed_choices": choices, "has_more": result.get("has_more", False),
                "next_cursor": result.get("next_cursor"),
                "retrieval_diagnostics": result.get("retrieval_diagnostics", {}),
            }
            public.write(json.dumps(row, ensure_ascii=False) + "\n")
            if private:
                private.write(json.dumps({"session_id": key[0], "request_id": key[1],
                                          "result": result}, ensure_ascii=False) + "\n")
    return {"requests": len(seen), "sessions": len(sessions),
            "display": "detailed" if detailed else "simple",
            "model_recognition_measured": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-config", required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diagnostics-output", type=Path)
    parser.add_argument("--detailed", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_requests(args.run_config, args.requests, args.output,
                                  args.diagnostics_output, detailed=args.detailed)))


if __name__ == "__main__":
    main()
