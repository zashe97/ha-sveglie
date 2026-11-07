"""Configurazione dei test con un Home Assistant vero (pytest-homeassistant-custom-component)."""

import pathlib

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

_NOSTRA = str(pathlib.Path(__file__).resolve().parents[1] / "custom_components")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    import custom_components  # quello del plugin: gli si aggiunge la nostra cartella

    if _NOSTRA not in custom_components.__path__:
        custom_components.__path__.insert(0, _NOSTRA)
    yield
