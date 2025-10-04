#!/usr/bin/env python3
"""
Test script for the Enhanced Dr. Chaffee Prompt System
Demonstrates the new prompt engineering and validates the system
"""

import json
import sys
from pathlib import Path

# Import our prompt loader
sys.path.append(str(Path(__file__).parent))
from shared.prompts.prompt_loader import ChaffeePromptLoader

def test_prompt_loading():
    """Test basic prompt loading functionality"""
    print("Testing Prompt Loading...")
    
    try:
        loader = ChaffeePromptLoader()
        
        # Test system prompt
        system_prompt = loader.load_system_prompt()
        print(f"[OK] System prompt loaded: {len(system_prompt)} characters")
        print(f"   Preview: {system_prompt[:100]}...")
        
        # Test schema
        schema = loader.load_response_schema()
        print(f"[OK] Response schema loaded: {len(schema)} properties")
        print(f"   Required fields: {schema['required']}")
        
        # Test user template
        template = loader.load_user_template()
        print(f"[OK] User template loaded: {len(template)} characters")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Prompt loading failed: {e}")
        return False

def test_prompt_formatting():
    """Test prompt formatting with sample data"""
    print("\nTesting Prompt Formatting...")
    
    try:
        loader = ChaffeePromptLoader()
        
        # Sample data
        sample_snippets = [
            {
                "text": "The carnivore diet is the most species-appropriate diet for humans. We evolved eating primarily animal foods.",
                "video_id": "abc123",
                "timestamp": "12:34",
                "title": "Why Carnivore Works"
            },
            {
                "text": "Seed oils are inflammatory and should be completely eliminated from the diet.",
                "video_id": "def456", 
                "timestamp": "5:42",
                "title": "The Dangers of Seed Oils"
            }
        ]
        
        sample_studies = [
            "RCT: 12-week carnivore diet intervention showing improved metabolic markers (n=50)",
            "Metabolic ward study: Seed oil consumption increases inflammatory markers within 2 weeks"
        ]
        
        # Test different answer modes
        for mode in ["concise", "expanded", "deep_dive"]:
            print(f"\n--- Testing {mode.upper()} mode ---")
            
            formatted_prompt = loader.format_user_prompt(
                user_input="What are the benefits of a carnivore diet?",
                chaffee_snippets=sample_snippets,
                primary_studies=sample_studies,
                answer_mode=mode
            )
            
            print(f"[OK] Formatted prompt length: {len(formatted_prompt)} characters")
            print(f"   Mode instruction included: {'Required Answer Mode: ' + mode in formatted_prompt}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Prompt formatting failed: {e}")
        return False

def test_full_message_creation():
    """Test creating full OpenAI-compatible messages"""
    print("\nTesting Full Message Creation...")
    
    try:
        loader = ChaffeePromptLoader()
        
        sample_snippets = [
            {
                "text": "Vegetables contain antinutrients and are not necessary for human health.",
                "video_id": "xyz789",
                "timestamp": "15:20",
                "title": "The Truth About Vegetables"
            }
        ]
        
        messages = loader.create_full_prompt(
            user_input="Are vegetables necessary for health?",
            chaffee_snippets=sample_snippets,
            answer_mode="expanded"
        )
        
        print(f"[OK] Created {len(messages)} messages")
        print(f"   System message: {len(messages[0]['content'])} characters")
        print(f"   User message: {len(messages[1]['content'])} characters")
        
        # Validate message structure
        assert messages[0]['role'] == 'system'
        assert messages[1]['role'] == 'user'
        assert 'Emulated Dr. Anthony Chaffee' in messages[0]['content']
        assert 'JSON schema' in messages[0]['content']
        
        print("[OK] Message structure validation passed")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Full message creation failed: {e}")
        return False

def test_schema_validation():
    """Test the JSON schema structure"""
    print("\nTesting Schema Validation...")
    
    try:
        loader = ChaffeePromptLoader()
        schema = loader.load_response_schema()
        
        # Check required properties
        required_fields = [
            "role_label", "answer_mode", "summary_short", 
            "key_points", "chaffee_quotes", "evidence", 
            "clips", "disclaimers"
        ]
        
        for field in required_fields:
            assert field in schema['required'], f"Missing required field: {field}"
        
        print(f"[OK] All {len(required_fields)} required fields present")
        
        # Check enum values
        answer_modes = schema['properties']['answer_mode']['enum']
        expected_modes = ["concise", "expanded", "deep_dive"]
        
        for mode in expected_modes:
            assert mode in answer_modes, f"Missing answer mode: {mode}"
        
        print(f"[OK] All answer modes present: {answer_modes}")
        
        # Check role_label constraint
        role_const = schema['properties']['role_label']['const']
        assert role_const == "Emulated Dr. Anthony Chaffee (AI)"
        
        print(f"[OK] Role label constraint correct: {role_const}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Schema validation failed: {e}")
        return False

def create_sample_response():
    """Create a sample response that follows the schema"""
    print("\nCreating Sample Response...")
    
    sample_response = {
        "role_label": "Emulated Dr. Anthony Chaffee (AI)",
        "answer_mode": "expanded",
        "summary_short": "The carnivore diet is the most species-appropriate diet for humans, providing all essential nutrients while eliminating inflammatory plant compounds.",
        "summary_long": "Based on evolutionary biology and clinical evidence, humans are adapted to thrive on animal foods. The carnivore diet provides complete nutrition with high bioavailability, eliminates antinutrients found in plants, and can reverse many chronic health conditions. This approach aligns with our ancestral eating patterns and addresses the root causes of modern metabolic dysfunction.",
        "key_points": [
            "Humans evolved as apex predators eating primarily meat",
            "Animal foods provide complete nutrition with optimal bioavailability",
            "Plant antinutrients can interfere with nutrient absorption and cause inflammation",
            "Carnivore diet eliminates common food sensitivities and autoimmune triggers",
            "Clinical improvements often seen in metabolic syndrome, autoimmune conditions"
        ],
        "chaffee_quotes": [
            {
                "quote": "We are apex predators, and we should eat like apex predators",
                "video_id": "abc123",
                "timestamp": "8:45",
                "context": "Discussing human evolutionary diet"
            },
            {
                "quote": "Plants are trying to kill you - they don't want to be eaten",
                "video_id": "def456", 
                "timestamp": "12:30",
                "context": "Explaining plant defense mechanisms"
            }
        ],
        "evidence": {
            "chaffee_content_available": True,
            "primary_studies_cited": 2,
            "evidence_strength": "strong",
            "uncertainties": [
                "Long-term studies on carnivore diet are limited",
                "Individual responses may vary based on genetics"
            ]
        },
        "clips": [
            {
                "video_id": "abc123",
                "title": "Why Carnivore Works",
                "start_time": "8:45",
                "relevance_score": 0.95
            },
            {
                "video_id": "def456",
                "title": "Plant Toxins Explained", 
                "start_time": "12:30",
                "relevance_score": 0.88
            }
        ],
        "disclaimers": [
            "This is an AI emulation based on publicly available content, not medical advice",
            "Consult healthcare providers before making significant dietary changes",
            "Individual results may vary"
        ]
    }
    
    try:
        # Validate it's proper JSON
        json_string = json.dumps(sample_response, indent=2)
        parsed_back = json.loads(json_string)
        
        print(f"[OK] Sample response created: {len(json_string)} characters")
        print(f"   JSON validation: Passed")
        print(f"   All required fields present: {all(field in parsed_back for field in ['role_label', 'answer_mode', 'summary_short', 'key_points', 'chaffee_quotes', 'evidence', 'clips', 'disclaimers'])}")
        
        # Show formatted output
        print(f"\nSample Response Preview:")
        print(f"Role: {parsed_back['role_label']}")
        print(f"Mode: {parsed_back['answer_mode']}")
        print(f"Summary: {parsed_back['summary_short'][:100]}...")
        print(f"Key Points: {len(parsed_back['key_points'])} items")
        print(f"Quotes: {len(parsed_back['chaffee_quotes'])} items")
        print(f"Clips: {len(parsed_back['clips'])} items")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Sample response creation failed: {e}")
        return False

def main():
    """Run all tests"""
    print("Testing Enhanced Dr. Chaffee Prompt System")
    print("=" * 50)
    
    tests = [
        ("Prompt Loading", test_prompt_loading),
        ("Prompt Formatting", test_prompt_formatting), 
        ("Full Message Creation", test_full_message_creation),
        ("Schema Validation", test_schema_validation),
        ("Sample Response", create_sample_response)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        result = test_func()
        results.append((test_name, result))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Results Summary:")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("All tests passed! The prompt system is ready to use.")
    else:
        print("Some tests failed. Check the output above for details.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
