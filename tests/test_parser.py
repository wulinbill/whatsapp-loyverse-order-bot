import importlib
import os
import sys
import types
import pytest
import json

@pytest.fixture()
def parser(monkeypatch):
    # Create dummy openai module to satisfy gpt_parser imports
    openai_mod = types.ModuleType("openai")
    openai_mod.OpenAI = lambda *args, **kwargs: object()

    types_mod = types.ModuleType("openai.types")
    chat_mod = types.ModuleType("openai.types.chat")
    class DummyChatCompletion:  # pragma: no cover - simple stub
        pass
    chat_mod.ChatCompletion = DummyChatCompletion
    types_mod.chat = chat_mod
    openai_mod.types = types_mod

    dotenv_mod = types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda *args, **kwargs: None

    monkeypatch.setitem(sys.modules, "openai", openai_mod)
    monkeypatch.setitem(sys.modules, "openai.types", types_mod)
    monkeypatch.setitem(sys.modules, "openai.types.chat", chat_mod)
    monkeypatch.setitem(sys.modules, "dotenv", dotenv_mod)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    if "gpt_parser" in sys.modules:
        del sys.modules["gpt_parser"]
    root_dir = os.path.dirname(os.path.dirname(__file__))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    parser = importlib.import_module("gpt_parser")
    return parser

def test_validate_order_json_valid(parser):
    order_json = '{"items": [{"name": "Burger", "quantity": 2}], "note": "extra"}'
    result = parser.validate_order_json(order_json)
    assert result == {"items": [{"name": "Burger", "quantity": 2}], "note": "extra"}


def test_validate_order_json_malformed(parser):
    malformed_json = '{"items": [{"name": "Burger", "quantity": 2], "note": "no"}'
    with pytest.raises(json.JSONDecodeError):
        parser.validate_order_json(malformed_json)


def test_validate_order_json_missing_field(parser):
    missing_note = '{"items": [{"name": "Burger", "quantity": 2}]}'
    with pytest.raises(ValueError):
        parser.validate_order_json(missing_note)
