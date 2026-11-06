"""ossci-run/1 (schema/run.schema.json, docs/results-schema.md)."""
import datetime
import json
import os

import jsonschema

SCHEMA = json.load(open(os.path.join(os.path.dirname(__file__), "schema", "run.schema.json")))
_V = jsonschema.Draft202012Validator(SCHEMA)


def errors(doc):
    return ["%s: %s" % ("/".join(str(p) for p in e.absolute_path) or "(root)", e.message)
            for e in sorted(_V.iter_errors(doc), key=lambda e: list(e.absolute_path))]


def check(doc):
    errs = errors(doc)
    if errs:
        raise ValueError("invalid run document:\n  " + "\n  ".join(errs))
    return doc


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
