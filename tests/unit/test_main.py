"""Tests for the example application."""

import pytest

from main import greeting, main


def test_greeting() -> None:
    assert greeting() == "Hello, World!"


def test_main(capsys: pytest.CaptureFixture[str]) -> None:
    main()
    captured = capsys.readouterr()
    assert captured.out == "Hello, World!\n"
