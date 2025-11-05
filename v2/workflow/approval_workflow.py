from temporalio import workflow
from datetime import timedelta
from activities import letter_gen, approvals, notifications

@workflow.defn
class ApprovalWorkflow:
    @workflow.run
    async def run(self, form_data: dict):
        # Step 1: Generate letter using AI
        letter = await workflow.execute_activity(
            letter_gen.generate_letter,
            form_data,
            start_to_close_timeout=timedelta(seconds=30)
        )

        # Step 2: Approval from B
        b_approved = await workflow.execute_activity(
            approvals.request_approval,
            "B", letter,
            start_to_close_timeout=timedelta(seconds=20)
        )
        if not b_approved:
            await workflow.execute_activity(notifications.notify, ("A", "Rejected by B"))
            return "Rejected"

        # Step 3: Approval from C
        c_approved = await workflow.execute_activity(
            approvals.request_approval,
            "C", letter,
            start_to_close_timeout=timedelta(seconds=20)
        )
        if not c_approved:
            await workflow.execute_activity(notifications.notify, ("A", "Rejected by C"))
            return "Rejected"

        # Step 4: Send summary to D for final decision
        d_decision = await workflow.execute_activity(
            approvals.request_final_decision,
            "D", letter,
            start_to_close_timeout=timedelta(seconds=20)
        )

        # Step 5: Notify A
        await workflow.execute_activity(
            notifications.notify,
            ("A", f"Final decision from D: {d_decision}")
        )

        return f"Workflow completed with D's decision: {d_decision}"
