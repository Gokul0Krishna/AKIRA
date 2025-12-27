from agent import WorkflowAgent
import json
import uuid

def verify_sequential_questions():
    print("Testing Sequential Questioning flow...")
    agent = WorkflowAgent()
    thread_id = str(uuid.uuid4())
    
    # 1. Start Request
    print("\n--- Sending Initial Request ---")
    resp = agent.run_step("I need a University leave request workflow", thread_id)
    print(f"Agent response:\n{resp}")
    
    if "Clarifying Question [1/" not in resp:
        print("FAILURE: Agent did not start sequential questioning.")
        return

    # 2. Answer Question 1
    print("\n--- Answering Question 1 ---")
    resp = agent.run_step("It should collect student name and leave dates.", thread_id)
    print(f"Agent response:\n{resp}")
    
    if "Clarifying Question [2/" not in resp:
        print("FAILURE: Agent did not move to the second question.")
        return

    # 3. Check internal state (simulated)
    config = {"configurable": {"thread_id": thread_id}}
    state = agent.app.get_state(config)
    answers = state.values.get("user_answers", {})
    print(f"\nStored Answers so far: {json.dumps(answers, indent=2)}")
    
    if "q1" in answers:
        print("SUCCESS: Question 1 answer stored correctly.")
    else:
        print("FAILURE: Question 1 answer missing from state.")

if __name__ == "__main__":
    verify_sequential_questions()
