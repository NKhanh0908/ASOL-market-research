from casual_scout.cli import main


def test_all_collects_sequentially(monkeypatch, tmp_path, capsys):
    calls = []

    def collect(repo, platform, countries, feeds, key, **kwargs):
        calls.append((platform, countries, feeds, kwargs["enrich"]))
        kwargs["on_progress"](f"{platform}: succeeded")
        return "run-" + platform, "succeeded"

    monkeypatch.setattr("casual_scout.collection.platforms.collect_platform", collect)
    assert (
        main(
            [
                "collect",
                "-p",
                "all",
                "--markets",
                "vn,us",
                "--no-enrich",
                "--data-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert calls == [
        ("ios", ["vn", "us"], ["top-free", "top-grossing"], False),
        ("android", ["vn", "us"], ["top-free", "top-grossing"], False),
    ]
    assert "android: succeeded" in capsys.readouterr().out


def test_all_invalid_android_market_does_not_start_ios(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("validation must precede first run")

    monkeypatch.setattr("casual_scout.collection.platforms.collect_platform", forbidden)
    assert main(["collect", "-p", "all", "--markets", "bn", "--data-dir", str(tmp_path)]) == 1
