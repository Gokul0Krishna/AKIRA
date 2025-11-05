from temporalio import activity
import random

@activity.defn
async def request_approval(approver: str, letter: str):
    print(f"Sent letter to {approver} for approval...")
    approved = random.choice([True, False])  # simulate approval
    print(f"{approver} {'approved' if approved else 'rejected'} the letter.")
    return approved

@activity.defn
async def request_final_decision(approver: str, letter: str):
    print(f"{approver} reviewing final letter...")
    decision = random.choice(["Approved", "Needs revision", "Rejected"])
    print(f"{approver}'s final decision: {decision}")
    return decision
