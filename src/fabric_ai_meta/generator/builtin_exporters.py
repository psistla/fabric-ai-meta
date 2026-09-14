"""Built-in `BaseExporter` subclasses for the four bundled framework exporters.

These wrap the existing function-style exporters so they participate in the
plugin registry alongside any third-party plugins. The function-style API
(`to_langchain_tool_definition`, `to_openai_function`, `to_semantic_kernel_plugin`,
`to_autogen_tool`) is preserved unchanged so existing user code keeps working.
"""

from fabric_ai_meta.analyzer.agent_readiness import assess_agent_readiness
from fabric_ai_meta.analyzer.capability_manifest import generate_capability_manifest
from fabric_ai_meta.generator.base import BaseExporter
from fabric_ai_meta.generator.export_autogen import to_autogen_tool
from fabric_ai_meta.generator.export_copilot import CopilotExporter
from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
from fabric_ai_meta.generator.export_openai import to_openai_function
from fabric_ai_meta.generator.export_semantic_kernel import to_semantic_kernel_plugin


class LangChainExporter(BaseExporter):
    name = "langchain"
    output_filename = "langchain-tool.json"
    description = "LangChain StructuredTool definition"

    def generate(self, model):
        return to_langchain_tool_definition(model)


class OpenAIExporter(BaseExporter):
    name = "openai"
    output_filename = "openai-function.json"
    description = "OpenAI function calling schema"

    def generate(self, model):
        return to_openai_function(model)


class SemanticKernelExporter(BaseExporter):
    name = "semantic-kernel"
    output_filename = "semantic-kernel-plugin.json"
    description = "Microsoft Semantic Kernel plugin manifest"

    def generate(self, model):
        return to_semantic_kernel_plugin(model)


class AutoGenExporter(BaseExporter):
    name = "autogen"
    output_filename = "autogen-tool.json"
    description = "AutoGen v0.4+ tool definition"

    def generate(self, model):
        return to_autogen_tool(model)


class CapabilityManifestExporter(BaseExporter):
    name = "capability-manifest"
    output_filename = "capability-manifest.json"
    description = "Capability manifest: which measures this model can answer"

    def generate(self, model):
        return generate_capability_manifest(model)


class AgentReadinessExporter(BaseExporter):
    name = "agent-readiness"
    output_filename = "agent-readiness.json"
    description = "Agent-readiness report: ranked findings and fixes for this model"

    def generate(self, model):
        return assess_agent_readiness(model)


BUILTIN_EXPORTERS: tuple[type[BaseExporter], ...] = (
    LangChainExporter,
    OpenAIExporter,
    SemanticKernelExporter,
    AutoGenExporter,
    CopilotExporter,
    CapabilityManifestExporter,
    AgentReadinessExporter,
)
