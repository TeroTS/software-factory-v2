from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import tests_support


@pytest.mark.parametrize("running", [True, False])
def test_runner_harness_uses_container_mounts_and_container_signals(tmp_path, monkeypatch, running):
    process = Mock()
    process.poll.return_value = None if running else 130
    process.wait.return_value = 130
    commands = SimpleNamespace(run=Mock(), Popen=Mock(return_value=process), DEVNULL=-3)
    monkeypatch.setattr(tests_support, "subprocess", commands)
    monkeypatch.setattr(
        tests_support,
        "os",
        SimpleNamespace(environ={"FACTORY_RUNNER_IMAGE": "runner:test"}, stat=lambda _: SimpleNamespace(st_gid=988)),
    )
    config = tmp_path / "operator.toml"
    with tests_support.runner_container(config, Mock()) as (actual, name):
        assert actual is process
        create = commands.run.call_args_list[0].args[0]
        assert create[:2] == ["docker", "create"]
        assert create[-3:] == ["runner:test", "--config", str(config)]
        assert create[create.index("--group-add") + 1] == "988"
        assert f"type=bind,src={tmp_path},dst={tmp_path}" in create
        assert "type=bind,src=/home/factory/artifacts,dst=/home/factory/artifacts" in create
        credentials = tmp_path / "home/.config/software-factory"
        assert f"type=bind,src={credentials},dst={credentials},readonly" in create
        assert "--pull=never" in create
        assert commands.Popen.call_args.args[0] == ["docker", "start", "--attach", name]
    calls = [call.args[0] for call in commands.run.call_args_list]
    assert (["docker", "kill", "--signal", "TERM", name] in calls) is running
    assert calls[-1] == ["docker", "rm", "--force", name]
    process.send_signal.assert_not_called()
    process.wait.assert_called_once_with(timeout=120)
