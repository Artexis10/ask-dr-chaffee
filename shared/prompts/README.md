# Emulated Dr. Chaffee Prompt Engineering System

This directory contains the new prompt engineering system for the Ask Dr. Chaffee AI, designed to provide consistent, high-quality responses that emulate Dr. Anthony Chaffee's voice and evidence-based approach.

## Overview

The system consists of three main components:

1. **System Prompt** (`chaffee_persona.md`) - Defines Dr. Chaffee's AI persona, tone, and priorities
2. **Response Schema** (`chaffee_developer_schema.json`) - Strict JSON schema for structured responses
3. **User Template** (`user_template.md`) - Template for formatting user queries with context

## Key Features

- **Evidence-First Approach**: Prioritizes controlled experimental evidence over speculation
- **Structured Responses**: JSON schema ensures consistent output format
- **Three Response Modes**: Concise, Expanded, and Deep Dive
- **Citation Requirements**: All claims must be grounded in Dr. Chaffee's content or primary research
- **Disclaimers**: Built-in medical and AI disclaimers

## Response Schema

Every response includes these required fields:

```json
{
  "role_label": "Emulated Dr. Anthony Chaffee (AI)",
  "answer_mode": "concise|expanded|deep_dive",
  "summary_short": "1-2 sentence direct answer",
  "summary_long": "Detailed explanation (required for expanded/deep_dive)",
  "key_points": ["Main takeaways as bullet points"],
  "chaffee_quotes": [
    {
      "quote": "Direct quote from Dr. Chaffee",
      "video_id": "YouTube video ID",
      "timestamp": "MM:SS format",
      "context": "Brief context"
    }
  ],
  "evidence": {
    "chaffee_content_available": true|false,
    "primary_studies_cited": 0,
    "evidence_strength": "strong|moderate|limited|insufficient",
    "uncertainties": ["Known limitations"]
  },
  "clips": [
    {
      "video_id": "YouTube video ID",
      "title": "Video title",
      "start_time": "MM:SS",
      "relevance_score": 0.95
    }
  ],
  "disclaimers": ["Required disclaimers"]
}
```

## Answer Modes

### Concise Mode
- Brief, direct answers
- 1-2 key points
- Essential quotes only
- Minimal disclaimers

### Expanded Mode (Default)
- Detailed explanations
- 3-5 key points
- Multiple quotes with context
- Comprehensive disclaimers
- **Requires `summary_long` field**

### Deep Dive Mode
- Comprehensive analysis
- 5-8 detailed points
- Full quote context
- Thorough evidence assessment
- Multiple video segments
- **Requires `summary_long` field**

## Usage

### Basic Usage

```python
from shared.prompts.prompt_loader import ChaffeePromptLoader

# Initialize loader
loader = ChaffeePromptLoader()

# Create OpenAI-compatible messages
messages = loader.create_full_prompt(
    user_input="What are the benefits of a carnivore diet?",
    chaffee_snippets=[
        {
            "text": "The carnivore diet is species-appropriate...",
            "video_id": "abc123",
            "timestamp": "12:34",
            "title": "Why Carnivore Works"
        }
    ],
    answer_mode="expanded"
)

# Use with OpenAI API
response = openai.ChatCompletion.create(
    model="gpt-4-turbo-preview",
    messages=messages,
    response_format={"type": "json_object"}
)
```

### Advanced Usage

```python
# Load individual components
system_prompt = loader.load_system_prompt()
schema = loader.load_response_schema()
template = loader.load_user_template()

# Custom formatting
formatted_prompt = loader.format_user_prompt(
    user_input="Question here",
    chaffee_snippets=snippets,
    primary_studies=["RCT data..."],
    answer_mode="deep_dive"
)
```

## Integration with Existing Services

### Enhanced RAG Service

The new `enhanced_rag_service.py` demonstrates full integration:

- Searches for Dr. Chaffee-attributed content
- Uses the prompt system for structured responses
- Validates JSON output against schema
- Provides fallback for development mode

### Starting the Enhanced Service

```bash
python enhanced_rag_service.py
```

Access at: `http://localhost:5002`

### API Endpoints

- `POST /search` - Enhanced search with structured responses
- `GET /prompts/info` - Information about loaded prompts
- `GET /stats` - Enhanced database statistics

## Content Guidelines

### Dr. Chaffee's Voice
- **Tone**: Calm, direct, plain-spoken
- **Confidence**: Evidence-based, not absolutist
- **Priorities**: RCTs > metabolic studies > epidemiology
- **Nutrition**: Animal-based, eliminate seed oils and refined carbs

### Evidence Hierarchy
1. **Strongest**: RCTs, metabolic ward studies, controlled N=1
2. **Moderate**: High-quality observational studies
3. **Context Only**: Epidemiology, mechanistic speculation
4. **Acknowledge**: Uncertainties and limitations

### Required Disclaimers
- "This is an AI emulation based on publicly available content, not medical advice"
- "Consult healthcare providers before making significant dietary changes"
- "Individual results may vary"

## Testing

Run the test suite to validate the system:

```bash
python test_enhanced_prompts.py
```

This validates:
- Prompt loading functionality
- Message formatting
- Schema compliance
- Sample response generation

## File Structure

```
shared/prompts/
├── README.md                        # This file
├── chaffee_persona.md              # System prompt
├── chaffee_developer_schema.json   # Response schema
├── user_template.md                # User prompt template
└── prompt_loader.py                # Utility class
```

## Migration from Simple RAG

To migrate from the existing `simple_rag_service.py`:

1. Update your service to use `ChaffeePromptLoader`
2. Replace hardcoded prompts with the new system
3. Update response handling to use the JSON schema
4. Add validation for required fields
5. Test with the enhanced service

## Development Notes

- Use `gpt-4-turbo-preview` or newer for best JSON compliance
- Set `response_format={"type": "json_object"}` in OpenAI calls
- Always validate responses against the schema
- Provide fallbacks for development/testing modes
- Log prompt performance for optimization

## Troubleshooting

### Common Issues

1. **Missing Fields**: Ensure all required schema fields are present
2. **Unicode Errors**: Use appropriate encoding when reading files
3. **JSON Validation**: Validate responses before returning to clients
4. **Prompt Length**: Monitor token usage for large contexts

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This will show detailed prompt construction and validation steps.

## Future Enhancements

- Dynamic prompt optimization based on query types
- A/B testing framework for prompt variants
- Integration with vector embeddings for better context selection
- Custom fine-tuning based on response quality metrics
