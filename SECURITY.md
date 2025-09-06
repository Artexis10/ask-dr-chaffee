# Security Guidelines

This document outlines security best practices for the Ask Dr. Chaffee project, with a focus on preventing API key exposure and other sensitive information leaks.

## API Key Management

### DO:
- ✅ Store API keys in environment variables
- ✅ Use `.env` files for local development (already in `.gitignore`)
- ✅ Use the `dotenv` package to load environment variables
- ✅ Add validation to check if required API keys are present
- ✅ Use specific environment variable names (e.g., `YOUTUBE_API_KEY` instead of generic `API_KEY`)

### DON'T:
- ❌ Hardcode API keys in source code
- ❌ Store API keys in public repositories
- ❌ Include API keys in code comments
- ❌ Log API keys to console or log files
- ❌ Share API keys in screenshots or documentation

## Example: Loading API Keys Correctly

```python
# Python example
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key from environment variable
api_key = os.getenv('YOUTUBE_API_KEY')
if not api_key:
    raise ValueError("YOUTUBE_API_KEY environment variable is not set")

# Use the API key
youtube = build('youtube', 'v3', developerKey=api_key)
```

```javascript
// JavaScript/TypeScript example
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

// Get API key from environment variable
const apiKey = process.env.YOUTUBE_API_KEY;
if (!apiKey) {
  throw new Error("YOUTUBE_API_KEY environment variable is not set");
}

// Use the API key
const youtubeClient = new YouTube(apiKey);
```

## API Key Restrictions

When creating API keys in Google Cloud Console:

1. **Apply API restrictions**:
   - Restrict to specific APIs (e.g., YouTube Data API v3)
   - Set quotas and limits appropriate for your use case

2. **Apply application restrictions**:
   - HTTP referrers: Limit to specific domains
   - IP addresses: Limit to specific IP addresses or ranges
   - Android/iOS: Use application-specific restrictions

## Pre-commit Hooks

We've implemented pre-commit hooks to prevent accidental commits of sensitive information:

1. **detect-secrets**: Custom hook to detect API keys and other secrets
2. **detect-private-key**: Prevents committing private keys

To use the pre-commit hooks:

```bash
# Install pre-commit
pip install pre-commit

# Install the hooks
pre-commit install
```

## Security Incident Response

If you discover a security vulnerability or an exposed API key:

1. **Revoke the compromised key immediately**
2. **Create a new key** with proper restrictions
3. **Update all environments** with the new key
4. **Audit usage** to detect any unauthorized access
5. **Document the incident** and improve processes

## Additional Resources

- [Google API Key Best Practices](https://cloud.google.com/docs/authentication/api-keys)
- [OWASP Secrets Management Guide](https://owasp.org/www-project-cheat-sheets/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security/secret-scanning/about-secret-scanning)
