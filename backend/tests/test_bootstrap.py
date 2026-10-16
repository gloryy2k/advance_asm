from backend.bootstrap import bootstrap


def test_startup_only_migrates_and_never_downloads(settings):
    bootstrap(settings)
    assert (settings.BBASM_DATA / "bbasm.db").is_file()
    assert not (settings.BBASM_DATA / "audit.jsonl").exists()          # no template download was started here
