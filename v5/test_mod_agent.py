import json
from v5.mod_agent import WorkflowModificationAgent

def test_modification():
    agent = WorkflowModificationAgent()
    
    # Load sample workflow
    with open('v5/workflows/be9f7f95-f913-45ad-b23d-3642c1cded81.json', 'r') as f:
        original_workflow = json.load(f)
        
    thread_id = "test_thread_1"
    user_request = "Add a supervisor approval level after the class teacher"
    
    print("\n--- Starting Modification Process ---")
    for event in agent.run_step_stream(user_request, thread_id, original_workflow):
        if isinstance(event, str):
            print(event)
        else:
            print(f"\nFinal Message: {event['final_message']}")

if __name__ == "__main__":
    test_modification()
