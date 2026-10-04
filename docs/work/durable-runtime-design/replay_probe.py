"""Independent toy reducers test event/checkpoint contract feasibility, not production replay."""
import copy
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def empty():
    return {"position": 0, "state": {}, "events": {}, "dedupe": {}, "versions": {}}


def make_event(event_id, record, version, payload):
    item = {"id": event_id, "key": event_id, "record": record, "version": version, "payload": payload}
    item["digest"] = digest(item)
    return item


def incremental(batches, initial=None):
    result = copy.deepcopy(initial or empty())
    for sequence, events in batches:
        if sequence != result["position"] + 1:
            raise ValueError("gap")
        stage = copy.deepcopy(result)
        for event in events:
            if event["digest"] != digest({k: v for k, v in event.items() if k != "digest"}):
                raise ValueError("digest")
            reservation = f'{event["record"]}:{event["version"]}'
            keys = (("events", event["id"]), ("dedupe", event["key"]), ("versions", reservation))
            if any(key in stage[table] and stage[table][key] != event["digest"] for table, key in keys):
                raise ValueError("conflict")
            if event["id"] in stage["events"]:
                continue
            prior = stage["state"].get(event["record"])
            if event["version"] != (prior[0] if prior else 0) + 1:
                raise ValueError("version")
            stage["state"][event["record"]] = [event["version"], event["payload"]]
            for table, key in keys:
                stage[table][key] = event["digest"]
        stage["position"] = sequence
        result = stage
    return result


def reference(batches):
    # Independent aggregate formulation: no incremental reducer/state calls.
    envelopes = []
    for ordinal, (sequence, batch) in enumerate(batches, start=1):
        if sequence != ordinal:
            raise ValueError("gap")
        envelopes.extend(batch)
    result = empty()
    for table, field in (("events", "id"), ("dedupe", "key")):
        for item in envelopes:
            key = item[field]
            if key in result[table] and result[table][key] != item["digest"]:
                raise ValueError("conflict")
            result[table][key] = item["digest"]
    records = sorted({item["record"] for item in envelopes})
    for record in records:
        versions = {}
        for item in [e for e in envelopes if e["record"] == record]:
            bare = {k: v for k, v in item.items() if k != "digest"}
            if digest(bare) != item["digest"]:
                raise ValueError("digest")
            version = item["version"]
            if version in versions and versions[version] != item:
                raise ValueError("conflict")
            versions[version] = item
        if sorted(versions) != list(range(1, len(versions) + 1)):
            raise ValueError("version")
        for version, item in versions.items():
            result["versions"][f"{record}:{version}"] = item["digest"]
        last = versions[max(versions)]
        result["state"][record] = [last["version"], last["payload"]]
    result["position"] = len(batches)
    return result


first = [make_event("start", "execution", 1, {"status": "running"}),
         make_event("attach", "directory", 1, {"solver": "s", "parent": "execution"}),
         make_event("hypothesis", "solver", 1, {"candidate": True}),
         make_event("overlay", "overlay", 1, {"frontier": ["solver"]})]
second = [make_event("revise", "overlay", 2, {"frontier": [], "reopenable": ["solver"]})]
batches = [(1, first), (2, second)]
assert incremental(batches) == reference(batches)
checkpoint = json.loads(json.dumps(incremental(batches[:1])))
assert incremental(batches[1:], checkpoint) == reference(batches)
bad = make_event("different", "overlay", 1, {"frontier": []})
for reducer in (incremental, reference):
    try:
        reducer([(1, first + [bad])])
    except ValueError as exc:
        assert str(exc) == "conflict"
    else:
        raise AssertionError("equal-version conflict accepted")
before = copy.deepcopy(checkpoint)
try:
    incremental([(2, second + [bad])], checkpoint)
except ValueError:
    pass
else:
    raise AssertionError("bad tail accepted")
assert checkpoint == before
print(json.dumps({"genesis_agreement": True, "checkpoint_tail_agreement": True,
                  "equal_version_conflict": "both rejected", "failed_batch_no_effect": True,
                  "limits": "Toy records/shared JSON hash only. Not production canonical codec, authorization, complete type family or CI proof."}, indent=2))
