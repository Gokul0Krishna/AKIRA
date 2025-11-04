from flask import Flask, request, render_template
from imixs_client import create_workitem, update_workitem
from utils import generate_summary, send_email

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('form.html')

@app.route('/submit', methods=['POST'])
def submit_form():
    name = request.form['name']
    content = request.form['content']

    # Simulate AI letter generation
    letter = f"Dear Manager,\n\n{content}\n\nSincerely,\n{name}"

    workitem = create_workitem(subject="Letter from " + name,
                               applicant=name,
                               data={"letter": letter})
    return f"Letter submitted! Workflow ID: {workitem['itemid']}"

@app.route('/approve/<int:workitem_id>/<role>')
def approve(workitem_id, role):
    if role == 'B':
        update_workitem(workitem_id, 'approveB')
    elif role == 'C':
        update_workitem(workitem_id, 'approveC')
        # Generate summary for D
        summary = generate_summary("Sample letter content for D")
        print(f"Summary sent to D: {summary}")
    elif role == 'D':
        update_workitem(workitem_id, 'approveD')
        send_email("A@example.com", "Final Decision", "Your letter was approved by D.")
    return f"{role} approved workitem #{workitem_id}"

if __name__ == '__main__':
    app.run(debug=True)
