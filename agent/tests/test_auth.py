from travel_agent import auth


def test_login_detection_from_files_and_env(tmp_path):
    assert not auth.claude_login_present({}, home=tmp_path, platform="win32")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ".credentials.json").write_text("{}")
    assert auth.claude_login_present({}, home=tmp_path, platform="win32")
    assert auth.claude_login_present({"CLAUDE_CODE_OAUTH_TOKEN": "t"}, home=tmp_path / "x", platform="linux")
    other = tmp_path / "cfg"
    other.mkdir()
    assert not auth.claude_login_present({"CLAUDE_CONFIG_DIR": str(other)}, home=tmp_path, platform="linux")


def test_precedence():
    key = "sk-ant-api03-" + "y" * 30
    assert auth.detect({}, key, key_only=True, login_present=True).mode == "browser_key"
    assert auth.detect({"ANTHROPIC_API_KEY": key}, None, login_present=True).mode == "server_key"
    assert auth.detect({}, None, key_only=True, login_present=True).needs_key
    assert auth.detect({}, None, login_present=True).mode == "claude_login"
    assert auth.detect({}, None, login_present=True, reason="login_expired").needs_key
    assert auth.detect({}, None, login_present=False).reason == "no_login"


def test_key_shape_and_rejection_text():
    assert auth.looks_like_api_key("sk-ant-api03-" + "a" * 30)
    assert not auth.looks_like_api_key("sk-proj-123") and not auth.looks_like_api_key("")
    assert auth.is_api_key_rejected("Error: 401 {'type': 'authentication_error', 'message': 'invalid x-api-key'}")
    assert not auth.is_api_key_rejected("rate limited")
