from textkit.pipeline import Pipeline


def test_run():
    assert Pipeline().run("running") == ["runn"]
