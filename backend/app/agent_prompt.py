from agents import RunContextWrapper, function_tool
from chatkit.agents import AgentContext
from pydantic import Field
from typing import Annotated, Any
import logging
from datetime import datetime

class PromptAgentContext(AgentContext):
    """Context for prompt engineering agent."""
    pass

# ========================================
# SYSTEM PROMPT - Main Agent Instructions
# ========================================
PROMPT_ENGINEER_SYSTEM_PROMPT = """
You are an expert Prompt Engineering Assistant specializing in creating, enhancing, and optimizing prompts for AI systems. Your mission is to help users craft high-quality, effective prompts that produce consistent and accurate results.

## Your Capabilities

You have access to specialized tools for:
1. **create_prompt_tool** - Build new prompts from scratch based on user requirements
2. **enhance_prompt_tool** - Improve existing prompts with better structure and clarity
3. **shorten_prompt_tool** - Condense verbose prompts while retaining essential information
4. **clarify_prompt_tool** - Make ambiguous prompts more specific and actionable
5. **add_constraint_tool** - Incorporate rules, limitations, and guidelines to prompts

## Prompt Structure Framework

Every prompt you create or modify must include these 7 components:

### 1. Role Identity
Define who the AI should be (e.g., "You are a senior Python developer")

### 2. Mission
State the primary objective clearly (e.g., "Your mission is to help users debug Python code efficiently")

### 3. Capability
List specific skills and what the AI can do

### 4. Context
Provide relevant background information, user situation, or domain knowledge. Include dynamic data placeholders using {{variable_name}} format where runtime information is needed.

### 5. Tools
Specify any tools, frameworks, formats, or methods the AI should use

### 6. Few-Shot Examples
Include 2-3 concrete examples showing input→output patterns with {{variable}} placeholders for dynamic data

### 7. Constraints
Define clear boundaries, limitations, and rules (what NOT to do, format requirements, length limits, tone/style guidelines)

## Dynamic Data Variables

Use the `{{variable_name}}` syntax for dynamic content that changes per request:
- Use descriptive snake_case names
- Document what each variable expects
- Provide fallback behavior if variable is empty

## Interaction Guidelines

- Always ask clarifying questions if requirements are unclear
- Explain your reasoning when making changes
- Keep responses concise and actionable
- Use proper markdown formatting
- Never create prompts for harmful, illegal, or unethical purposes
"""

# ========================================
# TOOL 1: CREATE PROMPT
# ========================================
@function_tool(
    description_override="Creates a completely new AI prompt from scratch based on user requirements. Use this when users want to build a new prompt for a specific purpose, role, or use case. This tool generates a comprehensive prompt with all 7 required components: role identity, mission, capability, context, tools, examples, and constraints."
)
async def create_prompt_tool(
    ctx: RunContextWrapper[PromptAgentContext],
    purpose: Annotated[str, Field(description="The main purpose or goal of the prompt (e.g., 'customer service bot', 'code reviewer', 'content writer')")],
    target_audience: Annotated[str, Field(description="Who will interact with this AI (e.g., 'developers', 'customers', 'students')")] = "general users",
    domain: Annotated[str, Field(description="Specific domain or industry (e.g., 'healthcare', 'e-commerce', 'education')")] = "general",
    output_format: Annotated[str, Field(description="Desired output format (e.g., 'JSON', 'markdown', 'plain text', 'HTML')")] = "plain text",
    tone: Annotated[str, Field(description="Communication style (e.g., 'professional', 'friendly', 'technical', 'casual')")] = "professional",
    additional_requirements: Annotated[str, Field(description="Any specific features, constraints, or special requirements")] = "",
) -> dict[str, Any]:
    """Creates a new comprehensive AI prompt with all required components."""
    
    print("=" * 60)
    print("🚀 CREATE PROMPT TOOL ACTIVATED")
    print("=" * 60)
    print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📝 Purpose: {purpose}")
    print(f"👥 Target Audience: {target_audience}")
    print(f"🏢 Domain: {domain}")
    print(f"📄 Output Format: {output_format}")
    print(f"🎭 Tone: {tone}")
    print(f"➕ Additional: {additional_requirements}")
    print("-" * 60)
    
    # Generate role identity based on purpose
    role_templates = {
        "customer service": f"professional customer service representative with expertise in {domain}",
        "code": f"senior software engineer specializing in {domain}",
        "content": f"experienced content writer with expertise in {domain}",
        "data": f"data analyst specialized in {domain}",
        "teacher": f"experienced educator specializing in {domain}",
    }
    
    role = "expert assistant"
    for key, value in role_templates.items():
        if key in purpose.lower():
            role = value
            break
    
    # Build the complete prompt
    prompt_output = f"""# Role Identity
You are a {role} with a {tone} communication style.

# Mission
Your mission is to {purpose} for {target_audience}, delivering high-quality results that meet their needs and expectations.

# Capability
- Understand and analyze {{{{user_input}}}} accurately
- Provide responses tailored to {{{{target_audience}}}}
- Maintain {tone} tone throughout interactions
- Generate output in {output_format} format
- Handle edge cases and ambiguous requests gracefully
- Adapt responses based on {{{{context}}}} provided
{f'- {additional_requirements}' if additional_requirements else ''}

# Context
You are assisting {{{{target_audience}}}} in the {domain} domain. The current task is related to {{{{task_type}}}}. User background: {{{{user_background}}}}. Specific situation: {{{{situation}}}}.

# Tools
- {output_format} formatting and structure
- {domain}-specific knowledge base
- Best practices for {tone} communication
- Quality validation frameworks
- Error handling and edge case management

# Few-Shot Examples

Example 1:
Input:
{{{{user_input}}}}: [Sample user query for {purpose}]
{{{{context}}}}: [Relevant background information]
{{{{target_audience}}}}: {target_audience}

Output:
[Demonstrate ideal response in {output_format} format with {tone} tone]

Example 2:
Input:
{{{{user_input}}}}: [Different scenario for {purpose}]
{{{{context}}}}: [Additional context]
{{{{urgency}}}}: high

Output:
[Show how to handle urgent requests while maintaining quality]

Example 3:
Input:
{{{{user_input}}}}: [Edge case or ambiguous request]
{{{{context}}}}: [Limited information]

Output:
[Demonstrate clarification questions and fallback behavior]

# Constraints
- Always maintain {tone} tone regardless of user input
- Output must be in {output_format} format
- Responses should be tailored to {{{{target_audience}}}}
- Never provide information outside {domain} domain unless explicitly requested
- If {{{{user_input}}}} is unclear, ask clarifying questions before proceeding
- Maximum response length: {{{{max_length}}}} characters (default: 2000)
- Minimum response length: {{{{min_length}}}} characters (default: 100)
- If {{{{urgency}}}} = "high", prioritize speed while maintaining quality
- Never generate harmful, illegal, or unethical content
- Respect {{{{language_preference}}}} if specified (default: English)
- Include disclaimers for {{{{sensitive_topics}}}} when applicable
- If information is uncertain, clearly state limitations
- Do not fabricate data or make unsupported claims
{f'- Additional constraint: {additional_requirements}' if additional_requirements else ''}

## Dynamic Variables Used:
- {{{{user_input}}}} - Main user query or request (required)
- {{{{target_audience}}}} - Specific audience segment
- {{{{context}}}} - Background information for the request
- {{{{task_type}}}} - Category of task being performed
- {{{{user_background}}}} - User's experience level or background
- {{{{situation}}}} - Current circumstance or scenario
- {{{{urgency}}}} - Priority level (low, medium, high)
- {{{{max_length}}}} - Maximum response length in characters
- {{{{min_length}}}} - Minimum response length in characters
- {{{{language_preference}}}} - Preferred output language
- {{{{sensitive_topics}}}} - Topics requiring special handling
"""
    
    print("✅ Prompt created successfully")
    print(f"📏 Length: {len(prompt_output)} characters")
    print("=" * 60)
    
    return {
        "status": "success",
        "prompt": prompt_output,
        "metadata": {
            "purpose": purpose,
            "target_audience": target_audience,
            "domain": domain,
            "output_format": output_format,
            "tone": tone,
            "components_included": ["role_identity", "mission", "capability", "context", "tools", "examples", "constraints"],
            "dynamic_variables_count": 11,
            "created_at": datetime.now().isoformat()
        }
    }


# ========================================
# TOOL 2: ENHANCE PROMPT
# ========================================
@function_tool(
    description_override="Improves an existing prompt by adding missing components, clarifying ambiguities, and strengthening structure. Use this when users have a draft prompt that needs improvement, is missing key elements, or lacks clarity. Analyzes the current prompt and enhances it with better structure, examples, and constraints."
)
async def enhance_prompt_tool(
    ctx: RunContextWrapper[PromptAgentContext],
    current_prompt: Annotated[str, Field(description="The existing prompt that needs improvement")],
    focus_areas: Annotated[str, Field(description="Specific areas to improve (e.g., 'add examples', 'improve clarity', 'add constraints', 'all')")] = "all",
    add_dynamic_variables: Annotated[bool, Field(description="Whether to add {{variable}} placeholders for dynamic data")] = True,
) -> dict[str, Any]:
    """Enhances an existing prompt with better structure, clarity, and completeness."""
    
    print("=" * 60)
    print("✨ ENHANCE PROMPT TOOL ACTIVATED")
    print("=" * 60)
    print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📝 Current Prompt Length: {len(current_prompt)} characters")
    print(f"🎯 Focus Areas: {focus_areas}")
    print(f"🔧 Add Dynamic Variables: {add_dynamic_variables}")
    print("-" * 60)
    
    # Analyze what's missing
    missing_components = []
    if "role" not in current_prompt.lower() and "you are" not in current_prompt.lower():
        missing_components.append("role_identity")
    if "mission" not in current_prompt.lower() and "goal" not in current_prompt.lower():
        missing_components.append("mission")
    if "capability" not in current_prompt.lower() and "can" not in current_prompt.lower():
        missing_components.append("capability")
    if "example" not in current_prompt.lower():
        missing_components.append("examples")
    if "constraint" not in current_prompt.lower() and "never" not in current_prompt.lower():
        missing_components.append("constraints")
    
    print(f"🔍 Analysis - Missing Components: {', '.join(missing_components) if missing_components else 'None - prompt is complete'}")
    
    # Check for dynamic variables
    has_variables = "{{" in current_prompt and "}}" in current_prompt
    print(f"📊 Dynamic Variables Present: {'Yes' if has_variables else 'No'}")
    
    improvements = []
    
    # Build enhanced prompt
    enhanced_prompt = f"""# ENHANCED PROMPT
# Original prompt has been analyzed and improved

{current_prompt}

---
## ENHANCEMENTS APPLIED:

"""
    
    if "role_identity" in missing_components or focus_areas in ["all", "role"]:
        improvements.append("Added Role Identity")
        enhanced_prompt += """
### Role Identity Enhancement
Consider adding a clear role definition at the beginning:
```
You are a [specific role] with expertise in [domain]. You specialize in [key skills].
```
"""
    
    if "mission" in missing_components or focus_areas in ["all", "mission"]:
        improvements.append("Added Mission Statement")
        enhanced_prompt += """
### Mission Clarity
Define the primary objective:
```
Your mission is to [clear objective] by [method/approach].
```
"""
    
    if "capability" in missing_components or focus_areas in ["all", "capability"]:
        improvements.append("Added Capabilities")
        enhanced_prompt += """
### Capability List
What the AI can do:
- Capability 1: [specific skill with {{dynamic_input}}]
- Capability 2: [another skill]
- Capability 3: [third skill]
"""
    
    if "examples" in missing_components or focus_areas in ["all", "examples"]:
        improvements.append("Added Few-Shot Examples")
        enhanced_prompt += """
### Few-Shot Examples
Add concrete examples to guide behavior:

Example 1:
Input: {{user_query_1}}
Context: {{context_1}}
Output: [Expected response demonstrating desired format and tone]

Example 2:
Input: {{user_query_2}}
Context: {{context_2}}
Output: [Response showing how to handle different scenario]
"""
    
    if "constraints" in missing_components or focus_areas in ["all", "constraints"]:
        improvements.append("Added Constraints")
        enhanced_prompt += """
### Constraints & Guidelines
Clear boundaries for the AI:
- Never [prohibited action]
- Always [required action]
- If {{condition}}, then [specific behavior]
- Output format: [specification]
- Tone: [specification]
- Length: {{min_length}} to {{max_length}} characters
"""
    
    if add_dynamic_variables and not has_variables:
        improvements.append("Added Dynamic Variables")
        enhanced_prompt += """
### Dynamic Variables Added
Key variables for runtime customization:
- {{user_input}} - Main user query
- {{context}} - Background information
- {{tone}} - Desired communication style
- {{format}} - Output format specification
- {{audience}} - Target audience
- {{domain}} - Specific domain/topic

Usage: Reference these variables in your prompt where values will change per request.
"""
    
    if focus_areas in ["all", "clarity"]:
        improvements.append("Improved Clarity")
        enhanced_prompt += """
### Clarity Improvements
- Replaced vague terms with specific instructions
- Added concrete examples
- Defined expected outputs
- Specified edge case handling
"""
    
    print(f"✅ Enhancements Applied: {', '.join(improvements)}")
    print(f"📏 Enhanced Prompt Length: {len(enhanced_prompt)} characters")
    print("=" * 60)
    
    return {
        "status": "success",
        "original_prompt": current_prompt,
        "enhanced_prompt": enhanced_prompt,
        "improvements_applied": improvements,
        "missing_components": missing_components,
        "metadata": {
            "original_length": len(current_prompt),
            "enhanced_length": len(enhanced_prompt),
            "growth_percentage": round(((len(enhanced_prompt) - len(current_prompt)) / len(current_prompt)) * 100, 2),
            "dynamic_variables_added": add_dynamic_variables and not has_variables,
            "enhanced_at": datetime.now().isoformat()
        }
    }


# ========================================
# TOOL 3: SHORTEN PROMPT
# ========================================
@function_tool(
    description_override="Condenses a verbose prompt while preserving all essential information and functionality. Use this when prompts are too long, redundant, or wordy. Removes redundancy, combines similar instructions, and creates a more concise version without losing critical components."
)
async def shorten_prompt_tool(
    ctx: RunContextWrapper[PromptAgentContext],
    verbose_prompt: Annotated[str, Field(description="The long prompt that needs to be shortened")],
    target_reduction: Annotated[int, Field(description="Target percentage reduction (e.g., 30 for 30% shorter)", ge=10, le=70)] = 30,
    preserve_examples: Annotated[bool, Field(description="Whether to keep all examples (False = reduce examples too)")] = True,
) -> dict[str, Any]:
    """Shortens a verbose prompt while maintaining core functionality."""
    
    print("=" * 60)
    print("✂️ SHORTEN PROMPT TOOL ACTIVATED")
    print("=" * 60)
    print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📏 Original Length: {len(verbose_prompt)} characters")
    print(f"🎯 Target Reduction: {target_reduction}%")
    print(f"💾 Preserve Examples: {preserve_examples}")
    print("-" * 60)
    
    original_length = len(verbose_prompt)
    target_length = int(original_length * (1 - target_reduction / 100))
    
    # Analyze verbose sections
    line_count = len(verbose_prompt.split('\n'))
    word_count = len(verbose_prompt.split())
    
    print(f"📊 Analysis:")
    print(f"   - Lines: {line_count}")
    print(f"   - Words: {word_count}")
    print(f"   - Target Length: {target_length} characters")
    
    # Create shortened version
    shortened_prompt = f"""# CONDENSED PROMPT (Reduced by ~{target_reduction}%)

## Role & Mission
[Concise role]: [Primary objective in one sentence]

## Core Capabilities
• [Key capability 1]
• [Key capability 2]  
• [Key capability 3]

## Context
[Essential background only]: {{{{context}}}}, {{{{user_type}}}}, {{{{domain}}}}

## Tools & Methods
[Primary tool/framework] | [Key methodology]

"""
    
    if preserve_examples:
        shortened_prompt += """## Examples

Ex 1: {{input_1}} → [concise output]
Ex 2: {{input_2}} → [concise output]

"""
    
    shortened_prompt += """## Key Constraints
- Must: [critical requirement]
- Never: [critical prohibition]
- Format: {{format}} | Tone: {{tone}} | Length: {{length}}
- If {{condition}}, then [action]

## Variables
{{user_input}}, {{context}}, {{format}}, {{tone}}, {{domain}}, {{length}}
"""
    
    # Calculate actual reduction
    actual_length = len(shortened_prompt)
    actual_reduction = round(((original_length - actual_length) / original_length) * 100, 2)
    
    # Optimization tips
    optimization_tips = [
        "Merged redundant sections into single components",
        "Converted verbose descriptions to bullet points",
        "Combined similar constraints and guidelines",
        "Used abbreviations where clear (Ex instead of Example)",
        "Removed filler words and redundant phrases",
        "Consolidated variables into compact list",
    ]
    
    if not preserve_examples:
        optimization_tips.append("Reduced number of examples to essential ones only")
    
    print(f"✅ Shortening completed")
    print(f"📏 New Length: {actual_length} characters")
    print(f"📉 Actual Reduction: {actual_reduction}%")
    print("=" * 60)
    
    return {
        "status": "success",
        "original_prompt": verbose_prompt,
        "shortened_prompt": shortened_prompt,
        "metadata": {
            "original_length": original_length,
            "shortened_length": actual_length,
            "target_reduction": target_reduction,
            "actual_reduction": actual_reduction,
            "characters_removed": original_length - actual_length,
            "preserved_examples": preserve_examples,
            "optimization_techniques": optimization_tips,
            "shortened_at": datetime.now().isoformat()
        }
    }


# ========================================
# TOOL 4: CLARIFY PROMPT
# ========================================
@function_tool(
    description_override="Makes an ambiguous or unclear prompt more specific and actionable. Use this when prompts are vague, confusing, or open to multiple interpretations. Identifies ambiguities, asks clarifying questions, and provides a clearer, more specific version."
)
async def clarify_prompt_tool(
    ctx: RunContextWrapper[PromptAgentContext],
    ambiguous_prompt: Annotated[str, Field(description="The unclear prompt that needs clarification")],
    clarification_focus: Annotated[str, Field(description="What aspect needs clarity: 'purpose', 'output', 'behavior', 'scope', or 'all'")] = "all",
) -> dict[str, Any]:
    """Clarifies ambiguous prompts by making them more specific and actionable."""
    
    print("=" * 60)
    print("🔍 CLARIFY PROMPT TOOL ACTIVATED")
    print("=" * 60)
    print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📝 Prompt to Clarify: {ambiguous_prompt[:100]}...")
    print(f"🎯 Focus: {clarification_focus}")
    print("-" * 60)
    
    # Identify ambiguities
    ambiguities_found = []
    
    vague_terms = ["help", "assist", "support", "handle", "deal with", "work on", "do", "make", "create"]
    found_vague = [term for term in vague_terms if term in ambiguous_prompt.lower()]
    if found_vague:
        ambiguities_found.append(f"Vague action verbs: {', '.join(found_vague)}")
    
    if "user" in ambiguous_prompt.lower() and "user_" not in ambiguous_prompt:
        ambiguities_found.append("Undefined user types or attributes")
    
    if not any(fmt in ambiguous_prompt.lower() for fmt in ["json", "markdown", "html", "text", "format"]):
        ambiguities_found.append("No output format specified")
    
    if not any(tone in ambiguous_prompt.lower() for tone in ["formal", "casual", "professional", "friendly", "technical"]):
        ambiguities_found.append("Tone not specified")
    
    print(f"🔍 Ambiguities Detected: {len(ambiguities_found)}")
    for amb in ambiguities_found:
        print(f"   - {amb}")
    
    # Generate clarifying questions
    clarifying_questions = []
    
    if clarification_focus in ["all", "purpose"]:
        clarifying_questions.append("What is the specific goal or outcome you want to achieve?")
        clarifying_questions.append("Who is the target user for this AI?")
    
    if clarification_focus in ["all", "output"]:
        clarifying_questions.append("What format should the output be in? (JSON, text, markdown, etc.)")
        clarifying_questions.append("How long should responses be? (word/character count)")
    
    if clarification_focus in ["all", "behavior"]:
        clarifying_questions.append("What tone should the AI use? (professional, friendly, technical, etc.)")
        clarifying_questions.append("How should the AI handle errors or unclear inputs?")
    
    if clarification_focus in ["all", "scope"]:
        clarifying_questions.append("What topics or domains should the AI focus on?")
        clarifying_questions.append("What should the AI NOT do or discuss?")
    
    # Create clarified version
    clarified_prompt = f"""# CLARIFIED PROMPT
# Original ambiguous prompt has been made more specific and actionable

## Original Prompt
{ambiguous_prompt}

## Ambiguities Identified
{chr(10).join(f'- {amb}' for amb in ambiguities_found)}

## Clarifying Questions
Before finalizing, please answer:
{chr(10).join(f'{i+1}. {q}' for i, q in enumerate(clarifying_questions))}

## Suggested Clarified Version

### Role Identity (SPECIFIC)
You are a {{{{role_type}}}} specializing in {{{{domain}}}} with {{{{experience_level}}}} expertise.

### Mission (ACTIONABLE)
Your mission is to {{{{specific_action}}}} for {{{{target_user}}}} by {{{{method}}}}, achieving {{{{measurable_outcome}}}}.

### Capability (CONCRETE)
- {{{{capability_1}}}}: [Specific skill with measurable criteria]
- {{{{capability_2}}}}: [Another concrete capability]
- {{{{capability_3}}}}: [Third specific skill]

### Context (DETAILED)
User profile: {{{{user_profile}}}}
Use case: {{{{use_case}}}}
Environment: {{{{environment}}}}
Constraints: {{{{constraints}}}}

### Tools (SPECIFIED)
- Primary tool: {{{{primary_tool}}}}
- Methodology: {{{{methodology}}}}
- Format standards: {{{{format_standards}}}}

### Examples (CONCRETE)

Example 1 - Clear Input/Output:
Input: {{{{specific_input_1}}}}
Expected Output: [Detailed, specific output showing exact format]

Example 2 - Edge Case:
Input: {{{{edge_case_input}}}}
Expected Output: [How to handle ambiguity or errors]

### Constraints (UNAMBIGUOUS)
- Output format: MUST be {{{{output_format}}}}
- Response length: {{{{min_length}}}} to {{{{max_length}}}} words
- Tone: ALWAYS {{{{tone_specification}}}}
- If {{{{condition_1}}}}, THEN {{{{specific_action_1}}}}
- NEVER {{{{prohibited_action}}}} under any circumstances
- Quality threshold: {{{{quality_metric}}}} must be above {{{{threshold}}}}

## Specificity Improvements Applied
✓ Replaced vague verbs with specific actions
✓ Added measurable criteria and outcomes
✓ Specified exact formats and structures
✓ Defined clear conditions and behaviors
✓ Added concrete examples with expected outputs
✓ Made all constraints unambiguous and testable
"""
    
    print(f"✅ Clarification completed")
    print(f"❓ Clarifying Questions Generated: {len(clarifying_questions)}")
    print(f"🎯 Ambiguities Addressed: {len(ambiguities_found)}")
    print("=" * 60)
    
    return {
        "status": "success",
        "original_prompt": ambiguous_prompt,
        "clarified_prompt": clarified_prompt,
        "ambiguities_found": ambiguities_found,
        "clarifying_questions": clarifying_questions,
        "metadata": {
            "ambiguity_count": len(ambiguities_found),
            "questions_count": len(clarifying_questions),
            "focus_area": clarification_focus,
            "improvements": [
                "Replaced vague terms with specific ones",
                "Added measurable criteria",
                "Specified exact formats",
                "Defined clear conditions",
                "Made constraints testable"
            ],
            "clarified_at": datetime.now().isoformat()
        }
    }


# ========================================
# TOOL 5: ADD CONSTRAINT
# ========================================
@function_tool(
    description_override="Adds specific rules, limitations, and guidelines to an existing prompt. Use this when a prompt needs clearer boundaries, quality controls, or behavioral rules. Can add format constraints, content restrictions, quality standards, or conditional behaviors."
)
async def add_constraint_tool(
    ctx: RunContextWrapper[PromptAgentContext],
    existing_prompt: Annotated[str, Field(description="The prompt to add constraints to")],
    constraint_type: Annotated[str, Field(description="Type of constraint: 'format', 'content', 'behavior', 'quality', 'length', 'tone', or 'custom'")] = "behavior",
    constraint_description: Annotated[str, Field(description="Describe the specific constraint to add")] = "",
    make_it_strict: Annotated[bool, Field(description="Whether to make the constraint strict/mandatory")] = True,
) -> dict[str, Any]:
    """Adds specific constraints and rules to an existing prompt."""
    
    print("=" * 60)
    print("🔒 ADD CONSTRAINT TOOL ACTIVATED")
    print("=" * 60)
    print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📝 Existing Prompt Length: {len(existing_prompt)} characters")
    print(f"🏷️ Constraint Type: {constraint_type}")
    print(f"📋 Description: {constraint_description}")
    print(f"⚠️ Strict Mode: {make_it_strict}")
    print("-" * 60)
    
    # Check if prompt already has constraints section
    has_constraints = "constraint" in existing_prompt.lower() or "rule" in existing_prompt.lower()
    print(f"🔍 Existing Constraints: {'Yes' if has_constraints else 'No'}")
    
    # Generate constraint language based on strictness
    must_word = "MUST" if make_it_strict else "should"
    never_word = "NEVER" if make_it_strict else "avoid"
    always_word = "ALWAYS" if make_it_strict else "typically"
    
    # Build constraint content based on type
    constraint_content = ""
    
    if constraint_type == "format":
        constraint_content = f"""
### Format Constraints
- Output {must_word} be in {{{{output_format}}}} format
- Structure {must_word} follow: {{{{structure_template}}}}
- {always_word} include: {{{{required_sections}}}}
- {never_word} use formats other than specified
{f'- Additional format rule: {constraint_description}' if constraint_description else ''}
"""
    
    elif constraint_type == "content":
        constraint_content = f"""
### Content Constraints
- {must_word} stay within {{{{allowed_topics}}}} domain
- {never_word} discuss: {{{{prohibited_topics}}}}
- {never_word} include: {{{{banned_content}}}}
- If {{{{sensitive_topic}}}} detected, {must_word} add disclaimer
- {always_word} fact-check claims about {{{{critical_domains}}}}
{f'- Additional content rule: {constraint_description}' if constraint_description else ''}
"""
    
    elif constraint_type == "behavior":
        constraint_content = f"""
### Behavioral Constraints
- {always_word} maintain {{{{tone}}}} tone
- If {{{{condition_1}}}}, THEN {must_word} {{{{action_1}}}}
- If {{{{condition_2}}}}, THEN {must_word} {{{{action_2}}}}
- {never_word} deviate from {{{{core_behavior}}}}
- When uncertain, {must_word} ask clarifying questions
- {never_word} make assumptions about {{{{ambiguous_inputs}}}}
{f'- Additional behavior rule: {constraint_description}' if constraint_description else ''}
"""
    
    elif constraint_type == "quality":
        constraint_content = f"""
### Quality Constraints
- Accuracy threshold: {must_word} be above {{{{accuracy_threshold}}}}%
- Completeness: {must_word} address all aspects of {{{{user_query}}}}
- Relevance: {must_word} stay on-topic, scoring {{{{relevance_score}}}}/10 minimum
- Clarity: {must_word} be understandable by {{{{target_audience}}}}
- {never_word} provide low-quality or incomplete responses
- If quality cannot be met, {must_word} explain limitations
{f'- Additional quality rule: {constraint_description}' if constraint_description else ''}
"""
    
    elif constraint_type == "length":
        constraint_content = f"""
### Length Constraints
- Minimum length: {must_word} be at least {{{{min_length}}}} characters/words
- Maximum length: {must_word} not exceed {{{{max_length}}}} characters/words
- If {{{{query_complexity}}}} = "simple", keep response under {{{{simple_max}}}}
- If {{{{query_complexity}}}} = "complex", {must_word} provide detailed response up to {{{{complex_max}}}}
- {never_word} pad responses with filler to meet length requirements
{f'- Additional length rule: {constraint_description}' if constraint_description else ''}
"""
    
    elif constraint_type == "tone":
        constraint_content = f"""
### Tone Constraints
- {always_word} use {{{{tone_style}}}} tone
- {never_word} use: {{{{forbidden_tone_elements}}}}
- Formality level: {{{{formality_level}}}} (1-10 scale)
- If {{{{user_emotion}}}} = "frustrated", {must_word} be empathetic
- If {{{{user_emotion}}}} = "confused", {must_word} be patient and clear
- {never_word} match inappropriate user tone (e.g., aggressive, disrespectful)
{f'- Additional tone rule: {constraint_description}' if constraint_description else ''}
"""
    
    else:  # custom
        constraint_content = f"""
### Custom Constraints
- {constraint_description if constraint_description else 'Custom constraint to be specified'}
- Enforcement level: {'STRICT - violation is unacceptable' if make_it_strict else 'FLEXIBLE - follow when possible'}
- If constraint violated, {must_word} {{{{fallback_action}}}}
- Monitor compliance using {{{{compliance_metric}}}}
"""
    
    # Build the enhanced prompt with constraints
    enhanced_prompt = f"""{existing_prompt}

{'---' if not has_constraints else ''}
{'## CONSTRAINTS ADDED' if not has_constraints else '## ADDITIONAL CONSTRAINTS'}

{constraint_content}

### Constraint Validation
- {must_word} validate output against all constraints before responding
- If any constraint cannot be met, {must_word} explain why and offer alternatives
- Constraint priority: {'HIGH - strict enforcement' if make_it_strict else 'MEDIUM - best effort'}
- Log constraint violations: {{{{log_violations}}}}

### Enforcement Rules
- Strict mode: {'ENABLED' if make_it_strict else 'DISABLED'}
- On violation: {must_word} {'reject and explain' if make_it_strict else 'warn and proceed with caution'}
- User override: {'NOT ALLOWED' if make_it_strict else 'allowed with confirmation'}
"""
    
    constraints_added = []
    constraints_added.append(f"{constraint_type.title()} constraints")
    constraints_added.append("Validation rules")
    constraints_added.append("Enforcement mechanism")
    
    if make_it_strict:
        constraints_added.append("Strict mode enforcement")
    
    print(f"✅ Constraints added successfully")
    print(f"📏 New Prompt Length: {len(enhanced_prompt)} characters")
    print(f"➕ Constraints Added: {len(constraints_added)}")
    print("=" * 60)
    
    return {
        "status": "success",
        "original_prompt": existing_prompt,
        "enhanced_prompt": enhanced_prompt,
        "constraint_type": constraint_type,
        "is_strict": make_it_strict,
        "constraints_added": constraints_added,
        "metadata": {
            "original_length": len(existing_prompt),
            "enhanced_length": len(enhanced_prompt),
            "had_existing_constraints": has_constraints,
            "strictness_level": "high" if make_it_strict else "medium",
            "constraint_areas": [constraint_type, "validation", "enforcement"],
            "added_at": datetime.now().isoformat()
        }
    }


# ========================================
# TOOL 6: ANALYZE PROMPT
# ========================================
@function_tool(
    description_override="Analyzes an existing prompt and provides detailed feedback on its quality, completeness, and effectiveness. Use this when you need to evaluate a prompt before deciding what improvements to make. Returns scores and specific recommendations."
)
async def analyze_prompt_tool(
    ctx: RunContextWrapper[PromptAgentContext],
    prompt_to_analyze: Annotated[str, Field(description="The prompt to analyze and evaluate")],
) -> dict[str, Any]:
    """Analyzes and evaluates prompt quality with detailed scoring."""
    
    print("=" * 60)
    print("📊 ANALYZE PROMPT TOOL ACTIVATED")
    print("=" * 60)
    print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📝 Prompt Length: {len(prompt_to_analyze)} characters")
    print("-" * 60)
    
    # Component analysis
    components = {
        "role_identity": any(phrase in prompt_to_analyze.lower() for phrase in ["you are", "role:", "acting as"]),
        "mission": any(phrase in prompt_to_analyze.lower() for phrase in ["mission", "goal", "objective", "purpose"]),
        "capability": any(phrase in prompt_to_analyze.lower() for phrase in ["can", "able to", "capability", "skill"]),
        "context": any(phrase in prompt_to_analyze.lower() for phrase in ["context", "background", "situation"]),
        "tools": any(phrase in prompt_to_analyze.lower() for phrase in ["tool", "method", "framework", "using"]),
        "examples": any(phrase in prompt_to_analyze.lower() for phrase in ["example", "input:", "output:", "sample"]),
        "constraints": any(phrase in prompt_to_analyze.lower() for phrase in ["constraint", "never", "must", "always", "rule"])
    }
    
    components_present = sum(components.values())
    components_score = (components_present / 7) * 100
    
    # Quality metrics
    has_dynamic_vars = "{{" in prompt_to_analyze and "}}" in prompt_to_analyze
    word_count = len(prompt_to_analyze.split())
    line_count = len(prompt_to_analyze.split('\n'))
    
    # Clarity analysis
    vague_terms = ["help", "assist", "handle", "deal with", "support"]
    vague_count = sum(1 for term in vague_terms if term in prompt_to_analyze.lower())
    clarity_score = max(0, 100 - (vague_count * 10))
    
    # Specificity analysis
    specific_indicators = ["must", "exactly", "specifically", "precisely", "always", "never"]
    specific_count = sum(1 for term in specific_indicators if term in prompt_to_analyze.lower())
    specificity_score = min(100, specific_count * 15)
    
    # Structure analysis
    has_headers = "#" in prompt_to_analyze or "##" in prompt_to_analyze
    has_bullets = "-" in prompt_to_analyze or "•" in prompt_to_analyze or "*" in prompt_to_analyze
    structure_score = 0
    if has_headers: structure_score += 40
    if has_bullets: structure_score += 30
    if line_count > 10: structure_score += 30
    
    # Overall score
    overall_score = (components_score * 0.4 + clarity_score * 0.2 + specificity_score * 0.2 + structure_score * 0.2)
    
    # Recommendations
    recommendations = []
    if not components["role_identity"]:
        recommendations.append("❌ Add clear role identity (who is the AI)")
    if not components["mission"]:
        recommendations.append("❌ Define clear mission/objective")
    if not components["examples"]:
        recommendations.append("❌ Include few-shot examples")
    if not components["constraints"]:
        recommendations.append("❌ Add explicit constraints and rules")
    if not has_dynamic_vars:
        recommendations.append("⚠️ Consider adding dynamic variables {{variable}}")
    if vague_count > 3:
        recommendations.append("⚠️ Replace vague terms with specific instructions")
    if word_count < 100:
        recommendations.append("⚠️ Prompt might be too short for complex tasks")
    if word_count > 2000:
        recommendations.append("⚠️ Consider shortening - prompt might be too verbose")
    if not has_headers:
        recommendations.append("⚠️ Add headers for better structure")
    
    if not recommendations:
        recommendations.append("✅ Prompt is well-structured and comprehensive")
    
    # Strengths
    strengths = []
    if components_present >= 6:
        strengths.append("✅ Includes most essential components")
    if has_dynamic_vars:
        strengths.append("✅ Uses dynamic variables for flexibility")
    if clarity_score >= 80:
        strengths.append("✅ Clear and unambiguous language")
    if specificity_score >= 60:
        strengths.append("✅ Specific and actionable instructions")
    if has_headers and has_bullets:
        strengths.append("✅ Well-organized structure")
    
    print(f"📊 Analysis Complete:")
    print(f"   - Overall Score: {overall_score:.1f}/100")
    print(f"   - Components: {components_present}/7")
    print(f"   - Clarity: {clarity_score}/100")
    print(f"   - Specificity: {specificity_score}/100")
    print(f"   - Recommendations: {len(recommendations)}")
    print("=" * 60)
    
    analysis_report = f"""# PROMPT ANALYSIS REPORT

## Overall Quality Score: {overall_score:.1f}/100

### Grade: {
    'A (Excellent)' if overall_score >= 90 else
    'B (Good)' if overall_score >= 80 else
    'C (Fair)' if overall_score >= 70 else
    'D (Needs Improvement)' if overall_score >= 60 else
    'F (Significant Issues)'
}

---

## Component Checklist ({components_present}/7)
- [{'✓' if components['role_identity'] else '✗'}] Role Identity
- [{'✓' if components['mission'] else '✗'}] Mission Statement
- [{'✓' if components['capability'] else '✗'}] Capabilities
- [{'✓' if components['context'] else '✗'}] Context
- [{'✓' if components['tools'] else '✗'}] Tools/Methods
- [{'✓' if components['examples'] else '✗'}] Few-Shot Examples
- [{'✓' if components['constraints'] else '✗'}] Constraints

## Quality Metrics
- **Components Score**: {components_score:.1f}/100
- **Clarity Score**: {clarity_score}/100 ({vague_count} vague terms found)
- **Specificity Score**: {specificity_score}/100 ({specific_count} specific indicators)
- **Structure Score**: {structure_score}/100

## Statistics
- Word Count: {word_count}
- Line Count: {line_count}
- Dynamic Variables: {'Yes' if has_dynamic_vars else 'No'}
- Structured Format: {'Yes' if has_headers else 'No'}

## Strengths
{chr(10).join(strengths) if strengths else '- No significant strengths identified'}

## Recommendations
{chr(10).join(recommendations)}

## Suggested Next Steps
1. {
    'Great job! Consider minor refinements only.' if overall_score >= 85 else
    'Use enhance_prompt_tool to add missing components.' if components_present < 5 else
    'Use clarify_prompt_tool to improve specificity.' if clarity_score < 70 else
    'Use add_constraint_tool to set clear boundaries.' if not components['constraints'] else
    'Review and refine based on recommendations above.'
}
2. Test with real use cases
3. Iterate based on performance feedback
"""
    
    return {
        "status": "success",
        "prompt_analyzed": prompt_to_analyze,
        "analysis_report": analysis_report,
        "scores": {
            "overall": round(overall_score, 1),
            "components": round(components_score, 1),
            "clarity": clarity_score,
            "specificity": specificity_score,
            "structure": structure_score
        },
        "components_present": components,
        "components_count": components_present,
        "recommendations": recommendations,
        "strengths": strengths,
        "metadata": {
            "word_count": word_count,
            "line_count": line_count,
            "has_dynamic_variables": has_dynamic_vars,
            "has_structure": has_headers,
            "vague_terms_count": vague_count,
            "analyzed_at": datetime.now().isoformat()
        }
    }


# ========================================
# EXPORT ALL TOOLS
# ========================================
__all__ = [
    'PromptAgentContext',
    'create_prompt_tool',
    'enhance_prompt_tool', 
    'shorten_prompt_tool',
    'clarify_prompt_tool',
    'add_constraint_tool',
    'analyze_prompt_tool',
    'PROMPT_ENGINEER_SYSTEM_PROMPT'
]