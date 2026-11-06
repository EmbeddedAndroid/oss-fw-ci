import json

from ossci import run, site


def test_site_index(tmp_path):
    from test_run import new_doc
    doc = new_doc(tmp_path)
    run.main(["skip", str(doc), "no LAVA_TOKEN"])
    s = tmp_path / "site"
    idx = site.add(str(s), [str(doc)])
    assert idx["runs"][0]["id"] == "123-1" and (s / "results" / "123-1.json").exists()
    assert (s / "index.html").exists() and (s / "app.js").exists()
    assert json.load(open(s / "index.json"))["runs"][0]["targets"][0]["state"] == "skipped"
