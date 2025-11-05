from temporalio import activity

@activity.defn
async def generate_letter(form_data: dict):
    # You could replace this with an AI model call
    letter = f"Dear {form_data['name']},\nThis is your approval request letter.\nRegards."
    print("Generated letter:", letter)
    return letter
