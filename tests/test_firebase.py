import responses

from maxxair_fan import config, firebase


@responses.activate
def test_fb_get_success(monkeypatch):
    monkeypatch.setattr(config, "FIREBASE_URL", "https://test.firebaseio.com")
    monkeypatch.setattr(config, "FIREBASE_SECRET", "secret123")
    firebase.reset_backoff_state()

    responses.add(
        responses.GET,
        "https://test.firebaseio.com/fans/fan1.json",
        json={"targetTemp": 72, "direction": "in"},
        match=[responses.matchers.query_param_matcher({"auth": "secret123"})],
    )

    data = firebase.fb_get("fans/fan1")
    assert data == {"targetTemp": 72, "direction": "in"}


@responses.activate
def test_fb_get_failure(monkeypatch):
    monkeypatch.setattr(config, "FIREBASE_URL", "https://test.firebaseio.com")
    monkeypatch.setattr(config, "FIREBASE_SECRET", "")
    firebase.reset_backoff_state()

    responses.add(
        responses.GET,
        "https://test.firebaseio.com/fans/fan1.json",
        status=401,
    )

    assert firebase.fb_get("fans/fan1") is None


@responses.activate
def test_fb_patch_success(monkeypatch):
    monkeypatch.setattr(config, "FIREBASE_URL", "https://test.firebaseio.com")
    monkeypatch.setattr(config, "FIREBASE_SECRET", "secret123")
    firebase.reset_backoff_state()

    responses.add(
        responses.PATCH,
        "https://test.firebaseio.com/fans/fan1.json",
        status=200,
        match=[
            responses.matchers.query_param_matcher({"auth": "secret123"}),
            responses.matchers.header_matcher({"Content-Type": "application/json"}),
        ],
    )

    payload = {"currentTemp": 75.0, "lastUpdate": "2026-01-01T00:00:00+00:00"}
    assert firebase.fb_patch("fans/fan1", payload) is True


@responses.activate
def test_fb_patch_failure(monkeypatch):
    monkeypatch.setattr(config, "FIREBASE_URL", "https://test.firebaseio.com")
    monkeypatch.setattr(config, "FIREBASE_SECRET", "")
    firebase.reset_backoff_state()

    responses.add(
        responses.PATCH,
        "https://test.firebaseio.com/fans/fan1.json",
        status=500,
    )

    assert firebase.fb_patch("fans/fan1", {"currentTemp": 75.0}) is False


def test_fb_get_no_url(monkeypatch):
    monkeypatch.setattr(config, "FIREBASE_URL", "")
    firebase.reset_backoff_state()
    assert firebase.fb_get("fans/fan1") is None


def test_fb_patch_no_url(monkeypatch):
    monkeypatch.setattr(config, "FIREBASE_URL", "")
    firebase.reset_backoff_state()
    assert firebase.fb_patch("fans/fan1", {"currentTemp": 75.0}) is False


@responses.activate
def test_fb_get_backoff_increases_with_failures(monkeypatch, mocker):
    monkeypatch.setattr(config, "FIREBASE_URL", "https://test.firebaseio.com")
    monkeypatch.setattr(config, "FIREBASE_SECRET", "")
    firebase.reset_backoff_state()
    sleep = mocker.patch("maxxair_fan.firebase.time.sleep")
    url = "https://test.firebaseio.com/fans/fan1.json"

    responses.add(responses.GET, url, status=500)
    responses.add(responses.GET, url, status=500)
    responses.add(responses.GET, url, json={"targetTemp": 72.0})

    assert firebase.fb_get("fans/fan1") is None
    sleep.assert_not_called()

    assert firebase.fb_get("fans/fan1") is None
    sleep.assert_called_once_with(2)

    assert firebase.fb_get("fans/fan1") == {"targetTemp": 72.0}
    assert sleep.call_args_list[-1] == mocker.call(4)
