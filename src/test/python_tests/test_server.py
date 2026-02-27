"""Tests for the Litestar language server."""

from threading import Event

from hamcrest import assert_that, greater_than, has_entry, has_item, has_length, is_

from .lsp_test_client import constants, defaults, session, utils

TEST_FILE_PATH = constants.TEST_DATA / "sample1" / "sample.py"
TEST_FILE_URI = utils.as_uri(str(TEST_FILE_PATH))
SERVER_INFO = utils.get_server_info_defaults()
TIMEOUT = 10


def test_diagnostics_on_open():
    """Test that diagnostics are published when a file is opened."""
    contents = TEST_FILE_PATH.read_text()

    actual = {}
    with session.LspSession() as ls_session:
        ls_session.initialize(defaults.VSCODE_DEFAULT_INITIALIZE)

        done = Event()

        def _handler(params):
            nonlocal actual
            actual = params
            done.set()

        ls_session.set_notification_callback(session.PUBLISH_DIAGNOSTICS, _handler)

        ls_session.notify_did_open(
            {
                "textDocument": {
                    "uri": TEST_FILE_URI,
                    "languageId": "python",
                    "version": 1,
                    "text": contents,
                }
            }
        )

        done.wait(TIMEOUT)

    assert_that(actual, has_entry("uri", TEST_FILE_URI))
    assert_that(actual, has_entry("diagnostics", has_length(greater_than(0))))

    diag_codes = [d["code"] for d in actual["diagnostics"]]
    assert_that(diag_codes, has_item("LITESTAR001"))
    assert_that(diag_codes, has_item("LITESTAR002"))


def test_diagnostics_clear_on_close():
    """Test that diagnostics are cleared when a file is closed."""
    contents = TEST_FILE_PATH.read_text()

    actual = {}
    with session.LspSession() as ls_session:
        ls_session.initialize(defaults.VSCODE_DEFAULT_INITIALIZE)

        done_open = Event()
        done_close = Event()

        def _open_handler(params):
            nonlocal actual
            actual = params
            done_open.set()

        def _close_handler(params):
            nonlocal actual
            actual = params
            done_close.set()

        ls_session.set_notification_callback(session.PUBLISH_DIAGNOSTICS, _open_handler)

        ls_session.notify_did_open(
            {
                "textDocument": {
                    "uri": TEST_FILE_URI,
                    "languageId": "python",
                    "version": 1,
                    "text": contents,
                }
            }
        )
        done_open.wait(TIMEOUT)

        ls_session.set_notification_callback(
            session.PUBLISH_DIAGNOSTICS, _close_handler
        )
        ls_session.notify_did_close({"textDocument": {"uri": TEST_FILE_URI}})
        done_close.wait(TIMEOUT)

    assert_that(actual, has_entry("uri", TEST_FILE_URI))
    assert_that(actual, has_entry("diagnostics", is_([])))
