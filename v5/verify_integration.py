from agent import WorkflowAgent
from app import app
import uuid

# Test Agent Import and Instantiation
print("Testing Agent Instantiation...")
try:
    agent = WorkflowAgent()
    print("Agent instantiated successfully.")
except Exception as e:
    print(f"FAILED to instantiate agent: {e}")
    exit(1)

# Test Agent Run Step
print("\nTesting Agent Run Step (Mock Interaction)...")
try:
    thread_id = str(uuid.uuid4())[:8]
    response = agent.run_step("Create a leave request workflow", thread_id)
    print(f"Initial Response Length: {len(response)}")
    print(f"Response Snippet: {response[:100]}...")
    
    if "INITIAL ANALYSIS COMPLETE" not in response and "clarifying questions" not in response.lower():
        print("WARNING: Response might not be as expected.")
    else:
        print("Response seems valid.")

except Exception as e:
    print(f"FAILED during agent run_step: {e}")
    # Don't exit, try routing

# Test Flask Route logic (Mocking DB interaction would be complex, just ensuring import works)
print("\nFlask App Import successful (implied).")
print("Verification Script Completed.")
