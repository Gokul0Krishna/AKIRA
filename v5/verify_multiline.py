from agent import WorkflowAgent
import json

def verify_multiline_parsing():
    print("Testing Multi-line Parsing robustness...")
    agent = WorkflowAgent()
    
    # Simulate a conversational multi-line input
    multiline_input = """
Hi, I want to build a Travel Reimbursement workflow.
The people involved are: Employee -> Department Manager -> Finance Office.
Also, if Finance rejects it, they should be able to send it back for corrections.
    """
    
    print(f"Input text:\n{multiline_input}")
    
    # Internal state for _analyze_request
    state = {"user_request": multiline_input}
    
    # Run analysis
    result = agent._analyze_request(state)
    
    analysis = result.get("workflow_analysis", {})
    chain = result.get("approval_chain", [])
    
    print("\nExtraction Results:")
    print(f"Title: {analysis.get('workflow_title')}")
    print(f"Chain Roles: {[a['approver_role'] for a in chain]}")
    
    # Check if Title and Chain were extracted (loosely)
    success = True
    if "travel" not in analysis.get('workflow_title', '').lower():
        print("FAILURE: Title extraction failed.")
        success = False
    
    if len(chain) < 2:
        print("FAILURE: Approval chain extraction seems insufficient.")
        success = False
        
    if success:
        print("\nSUCCESS: Agent successfully parsed multi-line conversational input.")
    else:
        print("\nFAILURE: Agent parsing was not robust enough.")

if __name__ == "__main__":
    verify_multiline_parsing()
