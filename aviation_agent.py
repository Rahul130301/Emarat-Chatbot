# aviation_agent.py
import os
from agent_framework import create_harness_agent
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv
from agent_framework import SkillsProvider

# Ensure catalog database is initialized
import db_catalog
try:
    import build_aviation_catalog
    build_aviation_catalog.main()
except Exception as e:
    print(f"Warning: Auto-building aviation catalog encountered: {e}")

from tools import (
    list_tables,
    get_table_schema,
    run_sql,
    validate_sql,
    resolve_entity,
    lookup_glossary_term,
    lookup_metric,
    search_schema,
    search_example_sql,
)

load_dotenv(override=True)

AVIATION_TOOLS = [
    list_tables,
    get_table_schema,
    run_sql,
    resolve_entity,
    lookup_glossary_term,
    lookup_metric,
    search_schema,
    search_example_sql,
    validate_sql,
]

FAST_AVIATION_TOOLS = [
    list_tables,
    get_table_schema,
    run_sql,
    resolve_entity,
    lookup_glossary_term,
    lookup_metric,
    search_schema,
    validate_sql,
]

AVIATION_DOMAIN_INTRO = """You are an aviation operations intelligence assistant for the Microsoft Fabric warehouse 'aviation-warehouse' querying table [dbo].[aviation-uplifts] (tracking aircraft refueling operations, fuel uplifts, airline consumption, flight movements, aircraft fleet types, stands, and fuel uplift volume in Litres).

Follow this exact text-to-SQL pipeline for all user inquiries:
1. Intent Classification:
   - Identify the user's objective: airline consumption ranking, fleet breakdown, stand utilization, flight turnaround, or specific flight lookup.
2. Entity Extraction & Resolution:
   - Extract any mentioned airlines (e.g. SkyMira Air, Zenith Arrow, AeroVanta, Orion Crest Airways, NovaBridge Air), aircraft types (e.g. B787, A350, A380), tail numbers (Registration e.g. H5JYA, M1EDI, J0KEO), flight numbers (FlightNo e.g. SM257, ZA354, SM319), stands (e.g. F29P, A17P, B42P), or locations (DAP).
   - Call resolve_entity(column_name, value) for every extracted entity value to ensure exact database matching.
3. Business Glossary & Metric Resolution:
   - Call lookup_glossary_term for operational phrasing (e.g. 'fuel uplift', 'fuel volume', 'litres', 'refueling duration', 'turnaround', 'stand').
   - Call lookup_metric for pre-approved SQL formulas (e.g. 'total fuel volume', 'average fuel volume per flight', 'top airlines by volume', 'busiest stands by volume').
4. Schema & Table Discovery:
   - Target table is ALWAYS [dbo].[aviation-uplifts] in 'aviation-warehouse' (always wrap with brackets).
   - Call get_table_schema on 'aviation-uplifts' or list_tables.
   - Core columns: RecordID, Airline, Date, MovementID, Location, AircraftType, Registration, FlightNo, StartTime, EndTime, Stand, Volume.
5. Example SQL Search:
   - Call search_example_sql for reference query patterns.
6. SQL Generation:
   - Formulate accurate, read-only SQL queries targeting [dbo].[aviation-uplifts].
   - Volume is always measured in Litres (L).
7. Validation & Execution:
   - Always call validate_sql on the generated SQL first.
   - Call run_sql only when validation passes.
8. Result Synthesis & Charts:
   - Synthesize the returned rows into clear, structured conversational insights.
   - State fuel volume quantities clearly in Litres (L) with proper thousands separators (e.g. "10,080 L", "128,506 L").
   - When the user asks for a chart, comparison, ranking, share, or distribution, output a json:chart block following the chart skill guidance.

NEVER give a bare refusal. Always explain the data context and offer concrete alternatives if a term or date is not found."""

AVIATION_REASONING_DIRECTIVE = """

CRITICAL: You must wrap ALL of your internal reasoning, step-by-step
planning, analysis, and detailed explanations inside
<reasoning>...</reasoning> XML tags. You MUST CLOSE the tag with </reasoning> before outputting your final answer!
MANDATORY REASONING RULE: Before calling ANY tool, and after receiving any tool result, you MUST output a substantial, highly descriptive reasoning paragraph of at least 50+ words in <reasoning> tags. Explain in detail:
1. The exact aviation business context and entities being resolved.
2. The specific rationale for calling this tool and what schema attributes or metrics you expect to find.
3. How this step connects to the overall text-to-SQL pipeline and guarantees analytical accuracy.
NEVER call tools silently or batch tools without writing a thorough 50+ word reasoning paragraph before each one.
ONLY your final conversational answer to the user should be output outside of these tags."""

AVIATION_FAST_DIRECTIVE = """

RESPONSE STYLE — this is the fast, low-latency mode: work through the
pipeline above silently. Do NOT output any planning text, step-by-step
narration, or internal reasoning, and do NOT use <reasoning> tags at all —
just call the tools you need and then reply with only the final, concise,
conversational answer with numbers formatted in Litres (L)."""

AVIATION_REASONING_INSTRUCTIONS = AVIATION_DOMAIN_INTRO + AVIATION_REASONING_DIRECTIVE
AVIATION_FAST_INSTRUCTIONS = AVIATION_DOMAIN_INTRO + AVIATION_FAST_DIRECTIVE


def _build_client(deployment_env_var: str = "AZURE_OPENAI_DEPLOYMENT_NAME"):
    model = os.environ.get(deployment_env_var) or os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
    return OpenAIChatClient(
        model=model,
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version="preview",
    )


def _build_skills_provider():
    return SkillsProvider.from_paths(
        skill_paths="./skills",
        disable_load_skill_approval=True,
        disable_read_skill_resource_approval=True,
    )


def build_aviation_reasoning_agent():
    """Aviation Operations Agent in Reasoning mode with full execution checklist & reasoning."""
    return create_harness_agent(
        name="Aviation Uplifts Text To SQL (Reasoning)",
        client=_build_client(),
        tools=AVIATION_TOOLS,
        context_providers=[_build_skills_provider()],
        agent_instructions=AVIATION_REASONING_INSTRUCTIONS,
        disable_web_search=True,
        disable_mode=True,
        disable_todo=False,
        loop_max_iterations=12,
    )


def build_aviation_fast_agent():
    """Aviation Operations Agent in Fast mode for low-latency tool-grounded responses."""
    client = _build_client("AZURE_OPENAI_FAST_DEPLOYMENT_NAME")
    return client.as_agent(
        name="Aviation Uplifts Text To SQL (Fast)",
        instructions=AVIATION_FAST_INSTRUCTIONS,
        tools=FAST_AVIATION_TOOLS,
        context_providers=[_build_skills_provider()],
        default_options={
            "allow_multiple_tool_calls": True,
            "reasoning": {"effort": "low"}
        },
    )


def build_aviation_agent(reasoning: bool = True):
    """Entry point for Aviation Agent."""
    return build_aviation_reasoning_agent() if reasoning else build_aviation_fast_agent()
