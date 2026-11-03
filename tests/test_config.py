"""Tests for configuration helpers."""

import config


def test_normalise_ollama_host_rewrites_bind_address():
    assert config._normalise_ollama_host("0.0.0.0:11434") == "http://127.0.0.1:11434"


def test_normalise_ollama_host_adds_scheme():
    assert config._normalise_ollama_host("localhost:11434") == "http://localhost:11434"


def test_normalise_ollama_host_keeps_full_url():
    assert (
        config._normalise_ollama_host("http://localhost:11434")
        == "http://localhost:11434"
    )
