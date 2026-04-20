"""Prompt templates for LLM-assisted classification and description generation."""

TABLE_CLASSIFICATION_PROMPT = """You are classifying a table in a Power BI / Microsoft Fabric semantic model.

Table name: {table_name}

Columns (name, data type):
{column_list}

Relationship summary:
{relationship_summary}

Possible table types: {possible_types}

Based on the table name, column composition, and relationship patterns, classify this table.

Return your answer as JSON:
{{"table_type": "fact|dimension|bridge|configuration|aggregate|staging", "confidence": 0.0-1.0, "reasoning": "..."}}"""

GRAIN_DETECTION_PROMPT = """You are detecting the grain (level of detail) of a fact table in a Power BI semantic model.

Table name: {table_name}

Columns (name, data type):
{column_list}

Estimated row count: {row_count}

Sample values:
{sample_values}

Determine the grain of this table, what does one row represent?

Return your answer as JSON:
{{"grain": "natural language grain statement", "confidence": 0.0-1.0}}"""

DESCRIPTION_GENERATION_PROMPT = """You are generating a concise business description for a {obj_type} in a Power BI semantic model.

Object name: {name}
Parent table: {parent_table}
{type_info}

Context from sibling descriptions:
{sibling_context}

Generate a clear, concise business description (max 150 characters) that explains the purpose of this {obj_type} in business terms.

Return your answer as JSON:
{{"description": "concise business description, max 150 chars"}}"""

BATCH_DESCRIPTION_PROMPT = """You are generating concise business descriptions for metadata objects in a Power BI semantic model named "{model_name}".

For each item below, generate a clear description (max 150 characters) explaining its business meaning. Use surrounding context (table name, data type, sibling columns) to infer purpose.

Items:
{items_json}

Each item: "id" (return unchanged), "type" (table|column|measure), "name", "parent_table", "data_type" or "dax", "siblings" (context).

Return ONLY a JSON array: [{{"id": "...", "description": "..."}}]
No preamble, no markdown fences."""

AI_INSTRUCTIONS_PROMPT = """You are generating AI Instructions for a Power BI semantic model named "{model_name}".

Model context:
- Tables: {table_summary}
- Key measures: {measure_summary}
- Relationships: {relationship_summary}

Generate concise AI Instructions that:
1. Define which tables/columns answer which types of questions
2. Specify metric preferences (e.g., "For profitability questions, use [Contribution Margin]")
3. Define default groupings (e.g., "Analyze revenue by fiscal quarter unless specified")
4. List common abbreviations and synonyms
5. Document business rules not obvious from column names

Output format: Plain text instructions, max 2000 characters."""
