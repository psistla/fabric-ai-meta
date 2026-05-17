"""Tests for fabric_ai_meta.models.copilot dataclasses."""

import pytest


def test_module_exposes_all_dataclasses():
    from fabric_ai_meta.models.copilot import (
        AIDataSchema,
        AIInstructions,
        CopilotBundle,
        CopilotSettings,
        CopilotVersion,
        ExamplePrompts,
        VerifiedAnswer,
    )
    assert AIInstructions is not None
    assert VerifiedAnswer is not None
    assert AIDataSchema is not None
    assert ExamplePrompts is not None
    assert CopilotSettings is not None
    assert CopilotVersion is not None
    assert CopilotBundle is not None
