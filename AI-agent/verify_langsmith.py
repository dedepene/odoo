"""Simple script to verify LangSmith configuration is working.

Run this script to test that your LangSmith credentials are properly configured
and that traces can be sent to your LangSmith project.

Usage:
    python verify_langsmith.py
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def verify_environment_variables():
    """Check that all required LangSmith environment variables are set."""
    print("🔍 Checking LangSmith environment variables...")
    
    required_vars = {
        "LANGSMITH_TRACING": os.getenv("LANGSMITH_TRACING"),
        "LANGSMITH_API_KEY": os.getenv("LANGSMITH_API_KEY"),
        "LANGSMITH_ENDPOINT": os.getenv("LANGSMITH_ENDPOINT"),
        "LANGSMITH_PROJECT": os.getenv("LANGSMITH_PROJECT"),
    }
    
    all_set = True
    for var_name, var_value in required_vars.items():
        if var_value:
            # Mask API key for security
            display_value = var_value if var_name != "LANGSMITH_API_KEY" else f"{var_value[:10]}...{var_value[-4:]}"
            print(f"  ✅ {var_name}: {display_value}")
        else:
            print(f"  ❌ {var_name}: Not set")
            all_set = False
    
    return all_set


def test_langsmith_connection():
    """Test that we can connect to LangSmith and send a trace."""
    print("\n🚀 Testing LangSmith connection...")
    
    try:
        from langsmith import Client
        
        client = Client(
            api_key=os.getenv("LANGSMITH_API_KEY"),
            api_url=os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        )
        
        # Try to list projects to verify connection
        projects = list(client.list_projects(limit=1))
        print(f"  ✅ Successfully connected to LangSmith!")
        print(f"  ✅ Found {len(projects)} project(s)")
        
        return True
    except Exception as e:
        print(f"  ❌ Failed to connect to LangSmith: {e}")
        return False


def test_simple_trace():
    """Send a simple test trace to LangSmith."""
    print("\n📝 Sending test trace...")
    
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
        
        # This will automatically trace to LangSmith if env vars are set
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        
        response = llm.invoke([HumanMessage(content="Say 'LangSmith test successful' if you can read this.")])
        
        print(f"  ✅ Trace sent successfully!")
        print(f"  ✅ LLM Response: {response.content}")
        print(f"\n🎉 Check your LangSmith dashboard at https://smith.langchain.com")
        print(f"   Project: {os.getenv('LANGSMITH_PROJECT')}")
        
        return True
    except Exception as e:
        print(f"  ❌ Failed to send trace: {e}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("LangSmith Configuration Verification")
    print("=" * 60)
    
    # Step 1: Check environment variables
    if not verify_environment_variables():
        print("\n❌ Environment variables not properly configured.")
        print("Please update your .env file with LangSmith credentials.")
        sys.exit(1)
    
    # Step 2: Test connection
    if not test_langsmith_connection():
        print("\n❌ Could not connect to LangSmith.")
        print("Please verify your API key and endpoint are correct.")
        sys.exit(1)
    
    # Step 3: Send test trace
    if not test_simple_trace():
        print("\n❌ Could not send test trace.")
        print("Please verify your OpenAI API key is set.")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✅ All checks passed! LangSmith is properly configured.")
    print("=" * 60)


if __name__ == "__main__":
    main()
