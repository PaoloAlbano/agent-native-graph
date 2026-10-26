import sys

import pytest

from agent_native_graph.interfaces.cli import RESEARCH_COMMANDS, main


@pytest.mark.parametrize("command", sorted(RESEARCH_COMMANDS))
def test_research_command_help_uses_packaged_module(command: str, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["agent-native-graph", command, "--help"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 0
    assert "usage:" in capsys.readouterr().out
