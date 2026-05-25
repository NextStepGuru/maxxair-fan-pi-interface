import pytest


@pytest.fixture
def mock_subprocess_run(mocker):
    return mocker.patch("maxxair_fan.fan.subprocess.run", return_value=mocker.Mock(returncode=0))
