import os
import json
import sqlite3
from datetime import datetime
from typing import TypedDict, Dict, List, Any
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# Load environment variables
load_dotenv()

class GraphState(TypedDict):
    user_request: str
    workflow_analysis: Dict[str, Any]
    approval_chain: List[Dict[str, Any]]
    clarifying_questions: List[Dict[str, Any]]
    user_answers: Dict[str, Any]
    validation_result: Dict[str, Any]
    question_iteration: int
    form_schema: Dict[str, Any]
    excel_schema: Dict[str, Any]
    workflow: Dict[str, Any]
    master_json: Dict[str, Any]
    sanity_check: Dict[str, Any]
    sanity_issues: List[str]
    regeneration_count: int
    last_message: str
    last_user_message: str
    chat_id: str
    current_question_index: int
    logs: List[str]
    approval_chain_summary: str
    question_history: List[Dict] # Complete history of all questions asked
    validation_result: Dict # Latest validation result # Added to track for UI display

class WorkflowAgent:
    def __init__(self):
        self.llm_key = os.getenv('llm_key')
        self.model = ChatOpenAI(
            model="openai/gpt-oss-20b:free",
            api_key=self.llm_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0.7
        )
        self.checkpointer = MemorySaver()
        self.app = self._build_graph()

    def run_step_stream(self, user_input: str, thread_id: str):
        config = {"configurable": {"thread_id": thread_id}}
        
        # Check current state
        state = self.app.get_state(config)
        
        if not state.values:
            # First run
            initial_state = {
                "user_request": user_input,
                "question_iteration": 0,
                "user_answers": {},
                "chat_id": thread_id,
                "current_question_index": 0,
                "logs": [],
                "approval_chain_summary": "",
                "question_history": [],
                "validation_result": {}
            }
            # Run until interrupt (collect_answers) or End
            for event in self.app.stream(initial_state, config=config):
                # Look for node transitions and yield them
                for node_name, output in event.items():
                    if "last_message" in output:
                        yield f"Status: {output['last_message']}"
                    else:
                        yield f"Status: {node_name.replace('_', ' ').title()}..."

        else:
            # Resume with user input
            self.app.update_state(config, {"last_user_message": user_input})
            # Resume execution
            for event in self.app.stream(None, config=config):
                for node_name, output in event.items():
                    if "last_message" in output:
                        yield f"Status: {output['last_message']}"
                    else:
                        yield f"Status: {node_name.replace('_', ' ').title()}..."
                
        # Get final state to retrieve response
        final_state = self.app.get_state(config)
        yield {"final_message": final_state.values.get("last_message", "Processing completed.")}

    def run_step(self, user_input: str, thread_id: str):
        # Fallback non-streaming version
        config = {"configurable": {"thread_id": thread_id}}
        state = self.app.get_state(config)
        if not state.values:
            initial_state = {
                "user_request": user_input, "question_iteration": 0, "user_answers": {},
                "chat_id": thread_id, "current_question_index": 0, "logs": []
            }
            self.app.invoke(initial_state, config=config)
        else:
            self.app.update_state(config, {"last_user_message": user_input})
            self.app.invoke(None, config=config)
        
        final_state = self.app.get_state(config)
        return final_state.values.get("last_message", "Processing completed.")

    def _analyze_request(self, state: GraphState):
        """
        Intelligently parse user request using LLM
        """
        user_input = state.get('user_request', '').strip()
        
        print("\n[LLM] Analyzing user request...")
        
        prompt = f"""
Analyze the following user request for a workflow and extract key information.

USER REQUEST:
"{user_input}"

Extract:
1. A concise Workflow Title.
2. The Approval Sequence (ordered list of roles/approvers).
3. Any additional requirements (notifications, special rules, etc.).

Return ONLY valid JSON:
{{
  "workflow_title": "Title",
  "approval_sequence": ["Role 1", "Role 2", "Role 3"],
  "additional_requirements": ["Rule 1", "Rule 2"]
}}
"""
        try:
            messages = [
                SystemMessage(content="You are a workflow analyst assistant. Always respond with valid JSON only."),
                HumanMessage(content=prompt)
            ]
            response = self.model.invoke(messages)
            response_text = response.content.strip()
            
            # Clean response
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            analysis = json.loads(response_text)
            
            workflow_title = analysis.get("workflow_title", "University Workflow")
            approval_sequence = analysis.get("approval_sequence", [])
            additional_reqs = analysis.get("additional_requirements", [])
            
            # Build approval chain
            approval_chain = []
            for idx, role in enumerate(approval_sequence, 1):
                role_title = role.strip().title()
                rejection_behavior = "end_workflow"
                notification_rules = []
                
                for req in additional_reqs:
                    if "reject" in req.lower() and role.lower() in req.lower():
                        notification_rules.append(f"notify {role} on rejection")
                        rejection_behavior = "special_rejection_logic"
                
                approval_chain.append({
                    "level": idx,
                    "approver_role": role_title,
                    "approver_type": "single",
                    "source": "from_form",
                    "conditions": [f"Level {idx} approver", "Can approve/reject with comments"],
                    "rejection_behavior": rejection_behavior,
                    "notification_rules": notification_rules,
                    "timeout_hours": 48
                })
            
            summary = ' -> '.join([r.strip().title() for r in approval_sequence])
            print("[ANALYSIS] INITIAL ANALYSIS COMPLETE")
            print(f"   Workflow: {workflow_title}")
            print(f"   Approval Chain: {summary}")
            
            return {
                "workflow_analysis": analysis,
                "approval_chain": approval_chain,
                "question_iteration": 0,
                "approval_chain_summary": summary
            }
            
        except Exception as e:
            print(f"\n[ERROR] Initial analysis failed: {e}")
            # Fallback to basic (previous logic)
            workflow_title = "University Workflow"
            approval_chain = []
            return {
                "workflow_analysis": {"workflow_title": workflow_title},
                "approval_chain": approval_chain,
                "question_iteration": 0
            }

    def _generate_clarifying_questions(self, state: GraphState):
        """
        Use LLM to generate clarifying questions or select current one
        """
        analysis = state.get("workflow_analysis", {})
        workflow_title = analysis.get("workflow_title", "")
        approval_chain = state.get("approval_chain", [])
        previous_answers = state.get("user_answers", {})
        questions = state.get("clarifying_questions", [])
        history = state.get("question_history", [])
        index = state.get("current_question_index", 0)
        
        # 1. Generate new batch if empty OR if we've exhausted the current batch
        if not questions or index >= len(questions):
            print("\n[LLM] Generating a new batch of clarifying questions...")
            
            # Format history for prompt
            history_text = "\n".join([f"- Q: {item['question']}\n  A: {previous_answers.get(item['id'], 'No answer yet')}" for item in history])
            
            prompt = f"""
You are a workflow design expert.
WORKFLOW: {workflow_title}
CHAIN: {' → '.join([a['approver_role'] for a in approval_chain])}

HISTORY OF QUESTIONS ASKED AND ANSWERS RECEIVED:
{history_text if history_text else "None"}

Generate a minimum of 1 and a maximum of 5 NEW, SPECIFIC clarifying questions. 
CRITICAL: 
- Do NOT repeat any questions already asked in the history above. 
- Do NOT ask about the internal evaluation criteria or decision logic used by human approvers (e.g., "What criteria does the Dean use to approve?"). Focus only on the technical workflow structure, form fields, notifications, and data requirements.
- Focus on missing details or areas needing deeper clarification based on previous answers.

Return ONLY valid JSON:
{{
  "questions": [
    {{"id": "q_{len(history)+1}", "question": "...", "category": "form_fields", "required": true}},
    ...
  ]
}}
"""
            try:
                messages = [HumanMessage(content=prompt)]
                response = self.model.invoke(messages)
                txt = response.content.strip().replace("```json","").replace("```","")
                new_batch = json.loads(txt).get("questions", [])
                
                # Update history with new questions
                history.extend(new_batch)
                questions = new_batch # Current batch is the new questions
            except Exception:
                # Fallback
                new_batch = [{"id": f"q_{len(history)+1}", "question": "Could you provide more details on the submission requirements?", "category": "general", "required": True}]
                history.extend(new_batch)
                questions = new_batch
            
            # Reset index for new batch
            index = 0

        # 2. Select current question
        if index < len(questions):
            q_current = questions[index]
            
            # Show approval chain on the very first question of the first batch
            prefix = ""
            if index == 0:
                # 1. Show approval chain if first batch
                if state.get("question_iteration", 0) <= 1:
                    summary = state.get("approval_chain_summary")
                    if summary:
                        prefix = f"**Identified Approval Chain:**\n{summary}\n\n"
                
                # 2. Show validation report if looping back
                report = state.get("validation_report")
                if report:
                    prefix += f"{report}\n\n"
                elif state.get("question_iteration", 0) > 1:
                    # Fallback if report missing but iteration > 1
                    validation = state.get("validation_result", {})
                    prefix += "**[WARNING] More information needed**\n"
                    if validation.get("missing_info"):
                        prefix += f"   *Missing:* {', '.join(validation['missing_info'])}\n"
                    prefix += "\n"
            
            display_text = f"{prefix}Clarifying Question [{index + 1}/{len(questions)}]:\n\n{q_current['question']}"
            
            return {
                "clarifying_questions": questions,
                "current_question_index": index,
                "question_history": history,
                "question_iteration": state.get("question_iteration", 0) + (1 if index == 0 else 0),
                "last_message": display_text
            }
        
        # This fallback should ideally not be reached with the new loop logic, 
        # but we'll return a neutral status just in case.
        return {"last_message": "Checking validation status..."}

    def _collect_user_answers(self, state: GraphState):
        """
        Store user answer for the current question
        """
        questions = state.get("clarifying_questions", [])
        user_input = state.get("last_user_message", "")
        existing_answers = state.get("user_answers", {})
        index = state.get("current_question_index", 0)
        
        if not questions or index >= len(questions):
            return {"user_answers": existing_answers}

        current_q = questions[index]
        print(f"\n[INFO] Collecting answer for: {current_q['id']}")
        
        # Store answer directly
        new_answers = existing_answers.copy()
        new_answers[current_q['id']] = user_input
        
        return {
            "user_answers": new_answers,
            "current_question_index": index + 1
        }

    def _validate_user_answers(self, state: GraphState):
        """
        Use LLM to validate if answers are sufficient
        """
        questions = state.get("clarifying_questions", [])
        answers = state.get("user_answers", {})
        workflow_analysis = state.get("workflow_analysis", {})
        
        print("\n[LLM] Validating your answers...")
        
        prompt = f"""
You are validating user responses for workflow design.

WORKFLOW: {workflow_analysis.get('workflow_title', '')}

QUESTIONS ASKED:
{json.dumps(questions, indent=2)}

USER ANSWERS:
{json.dumps(answers, indent=2)}

Validate if the answers are sufficient to proceed with workflow generation. Check:
1. Are required questions answered?
2. Are answers clear and specific enough?
3. Are there any contradictions?
4. Is any critical information missing?

IMPORTANT: Do NOT consider the "evaluation criteria" or "decision logic" of human approvers as missing information. We only care about the technical structure, form fields, and communication flow. If the only thing missing is "how the advisor decides", consider the validation complete/valid.

Return ONLY valid JSON:
{{
  "valid": true/false,
  "missing_info": ["list of missing information"],
  "follow_up_needed": ["list of areas needing clarification"],
  "can_proceed": true/false
}}

Return ONLY the JSON, no other text.
"""
        
        try:
            messages = [
                SystemMessage(content="You are a validation assistant. Always respond with valid JSON only."),
                HumanMessage(content=prompt)
            ]
            
            response = self.model.invoke(messages)
            response_text = response.content.strip()
            
            # Clean response
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            validation = json.loads(response_text)
            
            if validation.get("valid") and validation.get("can_proceed"):
                print("   [VALIDATION] Validation passed - proceeding to generation")
            else:
                print("   [WARNING] More information needed")
                if validation.get("missing_info"):
                    print(f"   Missing: {', '.join(validation['missing_info'])}")
            
            # Detailed log for the "Thinking..." indicator
            log_msg = "[LLM] Validating your answers..."
            if not validation.get("can_proceed", True):
                log_msg = "[WARNING] More information needed"
            
            # Create a structured validation report for the UI
            report = "**Validation Status Report**\n"
            report += "---"
            if validation.get("can_proceed", True):
                report += "\n✅ Sufficient information collected.\n"
            else:
                report += "\n⚠️ Some details are still missing.\n"
                if validation.get("missing_info"):
                    report += "\n**Missing Information:**\n" + "\n".join([f"- {i}" for i in validation['missing_info']])
                if validation.get("follow_up_needed"):
                    report += "\n**Follow-up Areas:**\n" + "\n".join([f"- {i}" for i in validation['follow_up_needed']])
            
            return {
                "validation_result": validation,
                "last_message": log_msg,
                "validation_report": report
            }
            
        except Exception as e:
            print(f"\n[ERROR] Validation failed: {e}")
            # Default to valid if LLM fails
            return {
                "validation_result": {
                    "valid": True,
                    "can_proceed": True,
                    "missing_info": [],
                    "follow_up_needed": []
                }
            }

    def _enrich_workflow_analysis(self, state: GraphState):
        """
        Use LLM to enrich workflow analysis with user answers
        """
        initial_analysis = state.get("workflow_analysis", {})
        user_answers = state.get("user_answers", {})
        approval_chain = state.get("approval_chain", [])
        
        print("\n[LLM] Enriching workflow analysis...")
        
        prompt = f"""
You are a workflow architect. Based on the user's answers, create a comprehensive workflow specification.

INITIAL ANALYSIS:
{json.dumps(initial_analysis, indent=2)}

APPROVAL CHAIN:
{json.dumps(approval_chain, indent=2)}

USER ANSWERS:
{json.dumps(user_answers, indent=2)}

Generate a complete workflow specification in VALID JSON format:
{{
  "workflow_name": "Workflow Title",
  "workflow_description": "Detailed description",
  "data_to_collect": [
    {{
      "field_name": "submitter_name",
      "label": "Your Full Name",
      "type": "text",
      "required": true,
      "validation": "string",
      "purpose": "identification"
    }}
  ],
  "business_rules": ["list of rules"],
  "notifications": [
    {{
      "trigger": "form_submitted",
      "recipients": ["submitter", "first_approver"],
      "platform": "Outlook",
      "template": "confirmation"
    }}
  ],
  "special_requirements": ["any special requirements from answers"]
}}

Include all necessary form fields based on user answers. Return ONLY valid JSON.
"""
        
        try:
            messages = [
                SystemMessage(content="You are a workflow specification generator. Always return valid JSON only."),
                HumanMessage(content=prompt)
            ]
            
            response = self.model.invoke(messages)
            response_text = response.content.strip()
            
            # Clean response
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            enriched_analysis = json.loads(response_text)
            
            # Merge with existing analysis
            enriched_analysis["approval_chain"] = approval_chain
            enriched_analysis["platform_requirements"] = {
                "form_platform": "Microsoft Forms",
                "tracking_platform": "Excel Online (Business)",
                "approval_platform": "Microsoft Teams - Approvals",
                "email_platform": "Office 365 Outlook"
            }
            
            print("   [INFO] Workflow analysis enriched")
            
            return {"workflow_analysis": enriched_analysis}
            
        except Exception as e:
            print(f"\n[ERROR] Enrichment failed: {e}, using basic analysis")
            # Return basic structure
            return {
                "workflow_analysis": {
                    **initial_analysis,
                    "data_to_collect": [
                        {"field_name": "submitter_name", "label": "Your Full Name", "type": "text", "required": True},
                        {"field_name": "submitter_email", "label": "Your Email", "type": "email", "required": True},
                        {"field_name": "request_details", "label": "Request Details", "type": "textarea", "required": True}
                    ],
                    "business_rules": [],
                    "notifications": []
                }
            }

    def _generate_form_schema(self, state: GraphState):
        """
        Generate Microsoft Forms schema
        """
        analysis = state.get("workflow_analysis", {})
        data_fields = analysis.get("data_to_collect", [])
        approval_chain = state.get("approval_chain", [])
        
        form_schema = {
            "title": analysis.get("workflow_name", "Workflow Form"),
            "description": analysis.get("workflow_description", ""),
            "platform": "Microsoft Forms",
            "settings": {
                "one_response_per_user": True,
                "allow_anonymous": False,
                "confirmation_message": "Your request has been submitted successfully!"
            },
            "questions": []
        }
        
        # Add user-specified fields
        for idx, field in enumerate(data_fields, 1):
            form_schema["questions"].append({
                "id": f"q{idx}",
                "field_name": field["field_name"],
                "type": field["type"],
                "title": field["label"],
                "required": field.get("required", True),
                "validation": field.get("validation", ""),
                "purpose": field.get("purpose", "user_data")
            })
        
        # Add approver fields
        question_num = len(form_schema["questions"]) + 1
        for approver in approval_chain:
            role = approver["approver_role"].replace(" ", "_").lower()
            form_schema["questions"].extend([
                {
                    "id": f"q{question_num}",
                    "field_name": f"{role}_name",
                    "type": "text",
                    "title": f"{approver['approver_role']} Name",
                    "required": True,
                    "purpose": "approver_identification"
                },
                {
                    "id": f"q{question_num + 1}",
                    "field_name": f"{role}_email",
                    "type": "email",
                    "title": f"{approver['approver_role']} Email",
                    "required": True,
                    "purpose": "approver_contact"
                }
            ])
            question_num += 2
        
        print(f"\n[SCHEMA] Form Schema: {len(form_schema['questions'])} questions")
        
        return {"form_schema": form_schema}

    def _generate_excel_schema(self, state: GraphState):
        """
        Generate Excel tracking schema
        """
        analysis = state.get("workflow_analysis", {})
        approval_chain = state.get("approval_chain", [])
        form_schema = state.get("form_schema", {})
        
        columns = [
            {"name": "SubmissionID", "type": "text"},
            {"name": "SubmissionTimestamp", "type": "datetime"},
            {"name": "CurrentStatus", "type": "choice", "choices": ["Submitted", "Pending", "Approved", "Rejected"]}
        ]
        
        # Add form fields
        for question in form_schema.get("questions", []):
            if question.get("purpose") not in ["approver_identification", "approver_contact"]:
                columns.append({
                    "name": question["field_name"],
                    "type": "text"
                })
        
        # Add approval tracking
        for approver in approval_chain:
            role = approver["approver_role"].replace(" ", "_")
            columns.extend([
                {"name": f"{role}_Status", "type": "choice", "choices": ["Pending", "Approved", "Rejected"]},
                {"name": f"{role}_Name", "type": "text"},
                {"name": f"{role}_Timestamp", "type": "datetime"},
                {"name": f"{role}_Comments", "type": "text"}
            ])
        
        columns.extend([
            {"name": "FinalDecision", "type": "choice", "choices": ["Approved", "Rejected"]},
            {"name": "FinalDecisionDate", "type": "datetime"}
        ])
        
        excel_schema = {
            "table_name": f"{analysis.get('workflow_name', '').replace(' ', '_')}_Tracker",
            "platform": "Excel Online (Business)",
            "location": "SharePoint/Shared Documents",
            "columns": columns
        }
        
        print(f"\n[SCHEMA] Excel Schema: {len(columns)} columns")
        
        return {"excel_schema": excel_schema}

    def _generate_workflow(self, state: GraphState):
        """
        Generate Power Automate workflow
        """
        analysis = state.get("workflow_analysis", {})
        form_schema = state.get("form_schema", {})
        excel_schema = state.get("excel_schema", {})
        approval_chain = state.get("approval_chain", [])
        
        workflow = {
            "name": analysis.get("workflow_name", ""),
            "description": analysis.get("workflow_description", ""),
            "platform": "Microsoft Power Automate",
            "trigger": {
                "type": "Microsoft Forms",
                "operation": "When a new response is submitted",
                "form_name": form_schema.get("title", "")
            },
            "steps": []
        }
        
        step_num = 1
        
        # Get form response
        workflow["steps"].append({
            "step_number": step_num,
            "name": "Get Form Response",
            "type": "Microsoft Forms - Get response details",
            "connector": "Microsoft Forms"
        })
        step_num += 1
        
        # Create Excel row
        workflow["steps"].append({
            "step_number": step_num,
            "name": "Create Excel Tracking Row",
            "type": "Excel Online - Add row",
            "connector": "Excel Online (Business)"
        })
        step_num += 1
        
        # Send confirmation
        workflow["steps"].append({
            "step_number": step_num,
            "name": "Send Confirmation Email",
            "type": "Outlook - Send email",
            "connector": "Office 365 Outlook"
        })
        step_num += 1
        
        # Approval flow
        for approver in approval_chain:
            workflow["steps"].append({
                "step_number": step_num,
                "name": f"Approval - {approver['approver_role']}",
                "type": "Teams - Start approval",
                "connector": "Microsoft Teams Approvals",
                "level": approver["level"]
            })
            step_num += 1
            
            workflow["steps"].append({
                "step_number": step_num,
                "name": f"Update Excel - {approver['approver_role']}",
                "type": "Excel Online - Update row",
                "connector": "Excel Online (Business)"
            })
            step_num += 1
        
        # Final notification
        workflow["steps"].append({
            "step_number": step_num,
            "name": "Send Final Notification",
            "type": "Outlook - Send email",
            "connector": "Office 365 Outlook"
        })
        
        print(f"\n[INFO] Workflow: {len(workflow['steps'])} steps")
        
        return {"workflow": workflow}

    def _generate_master_json(self, state: GraphState):
        """
        Create master JSON output
        """
        analysis = state.get("workflow_analysis", {})
        form_schema = state.get("form_schema", {})
        excel_schema = state.get("excel_schema", {})
        workflow = state.get("workflow", {})
        user_answers = state.get("user_answers", {})
        
        master_json = {
            "metadata": {
                "workflow_name": analysis.get("workflow_name", ""),
                "description": analysis.get("workflow_description", ""),
                "version": "1.0",
                "generated_with": "LLM-Enhanced Workflow Generator",
                "platform": "Microsoft 365"
            },
            "user_requirements": {
                "questions_answered": user_answers
            },
            "workflow_analysis": {
                "approval_chain": state.get("approval_chain", []),
                "business_rules": analysis.get("business_rules", []),
                "notifications": analysis.get("notifications", [])
            },
            "microsoft_forms": form_schema,
            "excel_tracker": excel_schema,
            "power_automate_workflow": workflow
        }
        
        print("\n[INFO] Master JSON generated")
        
        return {"master_json": master_json}

    def _display_output(self, state: GraphState):
        """
        Save master JSON to file and prepare message
        """
        master_json = state.get("master_json", {})
        chat_id = state.get("chat_id", "workflow")
        
        print("\n" + "="*80)
        print("[SUCCESS] WORKFLOW GENERATION COMPLETE")
        print("="*80)
        
        metadata = master_json.get("metadata", {})
        print(f"\n[TITLE] {metadata.get('workflow_name', '')}")
        print(f"[DESC] {metadata.get('description', '')}")
        
        # Save to file
        workflows_dir = os.path.join(os.path.dirname(__file__), 'workflows')
        os.makedirs(workflows_dir, exist_ok=True)
        filename = f"{chat_id}.json"
        filepath = os.path.join(workflows_dir, filename)
        
        try:
            with open(filepath, 'w') as f:
                json.dump(master_json, f, indent=2)
            print(f"\n[SAVE] Master JSON saved to: {filepath}")
            
            # Database Insertion: Log the generated workflow state
            try:
                db_path = os.path.join(os.path.dirname(__file__), 'database')
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                workflow_name = metadata.get('workflow_name', metadata.get('workflow_title', 'Unknown Workflow'))
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                cursor.execute('''
                    INSERT INTO state (chatid, workflow, version, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (chat_id, workflow_name, "0", timestamp))
                
                conn.commit()
                conn.close()
                print(f"[DB] Workflow state logged for chat_id: {chat_id}")
            except Exception as db_e:
                print(f"[ERROR] Failed to log workflow state to database: {db_e}")
                
        except Exception as e:
            print(f"\n[ERROR] Failed to save JSON file: {e}")
        
        print("\n" + "="*80)
        
        return {
            "master_json": master_json,
            "last_message": f"Workflow Generation Complete!\n\nName: {metadata.get('workflow_name', metadata.get('workflow_title'))}\nDescription: {metadata.get('description')}\n\nWorkflow structure is available for viewing."
        }

    def _should_ask_more_questions(self, state: GraphState) -> str:
        """
        Decide if more questions needed after validation
        """
        validation = state.get("validation_result", {})
        iteration = state.get("question_iteration", 0)
        
        if validation.get("can_proceed", True):
            print("\n[INFO] Sufficient information collected")
            return "proceed"
        elif iteration >= 2:
            print("\n[WARNING] Max question iterations reached, proceeding anyway")
            return "proceed"
        else:
            print("\n[INFO] Need more information, resetting for new batch...")
            return "ask_more"

    def _should_ask_more_questions_logic(self, state: GraphState) -> str:
        """
        Intermediate check to clear state before looping
        """
        # Note: In a real graph we'd use another node to reset, 
        # but for simplicity we inject the clear command here or in generate_questions.
        # Let's handle it in generate_questions (if index >= len, gen new).
        # But we need to signal generate_questions to actually generate new ones.
        return self._should_ask_more_questions(state)

    def _check_batch_status(self, state: GraphState) -> str:
        """
        Decide if batch is finished
        """
        questions = state.get("clarifying_questions", [])
        index = state.get("current_question_index", 0)
        
        if index < len(questions):
            return "next_question"
        else:
            return "batch_done"

    def _build_graph(self):
        """
        Build graph with question-answer loop
        """
        graph = StateGraph(GraphState)
        
        # Add nodes
        graph.add_node("analyze", self._analyze_request)
        graph.add_node("generate_questions", self._generate_clarifying_questions)
        graph.add_node("collect_answers", self._collect_user_answers)
        graph.add_node("validate_answers", self._validate_user_answers)
        graph.add_node("enrich_analysis", self._enrich_workflow_analysis)
        graph.add_node("generate_form", self._generate_form_schema)
        graph.add_node("generate_excel", self._generate_excel_schema)
        graph.add_node("generate_workflow", self._generate_workflow)
        graph.add_node("create_master", self._generate_master_json)
        graph.add_node("display", self._display_output)
        
        # Define flow
        graph.set_entry_point("analyze")
        graph.add_edge("analyze", "generate_questions")
        graph.add_edge("generate_questions", "collect_answers")
        
        # Per-question loop
        graph.add_conditional_edges(
            "collect_answers",
            self._check_batch_status,
            {
                "next_question": "generate_questions",
                "batch_done": "validate_answers"
            }
        )
        
        # Conditional: ask more (new batch) or proceed
        graph.add_conditional_edges(
            "validate_answers",
            self._should_ask_more_questions,
            {
                "ask_more": "generate_questions",
                "proceed": "enrich_analysis"
            }
        )
        
        graph.add_edge("enrich_analysis", "generate_form")
        graph.add_edge("generate_form", "generate_excel")
        graph.add_edge("generate_excel", "generate_workflow")
        graph.add_edge("generate_workflow", "create_master")
        graph.add_edge("create_master", "display")
        graph.add_edge("display", END)
        
        return graph.compile(
            checkpointer=self.checkpointer,
            interrupt_before=["collect_answers"]
        )

    def run(self, initial_state: GraphState):
        return self.app.invoke(initial_state)
