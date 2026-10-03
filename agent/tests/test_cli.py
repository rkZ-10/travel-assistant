import pytest

from travel_agent import cli


@pytest.mark.parametrize("argv", [
    ["ask", "HYD to MAA", "-v", "--model", "haiku", "--budget", "0.2"],
    ["ask", "-v", "HYD to MAA"],
    ["chat", "-v"],
])
def test_options_after_subcommand(monkeypatch, argv):
    seen = {}

    async def fake(args):
        seen.update(vars(args))
        return 0

    monkeypatch.setattr(cli, "_ask", fake)
    monkeypatch.setattr(cli, "_chat", fake)
    assert cli.main(argv) == 0
    assert seen["verbose"] is True
