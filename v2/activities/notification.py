from temporalio import activity

@activity.defn
async def notify(target: str, message: str):
    print(f"Notification to {target}: {message}")
