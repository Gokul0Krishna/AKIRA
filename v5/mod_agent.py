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

class ModificationState(TypedDict):
    original_workflow: Dict[str, Any]
    workflow_summary: str  # Token-efficient summary of workflow
    modification_request: str
    analysis: Dict[str, Any]
    clarifying_questions: List[Dict[str, Any]]
    user_answers: Dict[str, Any]
    validation_result: Dict[str, Any]
    question_iteration: int
    modification_plan: Dict[str, Any]
    modified_workflow: Dict[str, Any]
    changes_applied: List[str]
    last_message: str
    last_user_message: str
    chat_id: str
    current_question_index: int
    logs: List[str]
    question_history: List[Dict]  # Track all questions asked

class WorkflowModificationAgent:
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

    def run_step_stream(self, user_input: str, thread_id: str, original_workflow: Dict[str, Any] = None):
        """
        Streaming execution with interrupts for question collection
        """
        config = {"configurable": {"thread_id": thread_id}}
        
        # Check current state
        state = self.app.get_state(config)
        
        if not state.values:
            # First run - create workflow summary for token efficiency
            workflow_summary = self._create_workflow_summary(original_workflow) if original_workflow else ""
            
            initial_state = {
                "original_workflow": original_workflow or {},
                "workflow_summary": workflow_summary,
                "modification_request": user_input,
                "question_iteration": 0,
                "user_answers": {},
                "chat_id": thread_id,
                "current_question_index": 0,
                "last_user_message": "",
                "logs": [],
                "changes_applied": [],
                "question_history": [],
                "validation_result": {}
            }
            # Run until interrupt (collect_answers) or End
            for event in self.app.stream(initial_state, config=config):
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

    def run_step(self, user_input: str, thread_id: str, original_workflow: Dict[str, Any] = None):
        """
        Non-streaming fallback
        """
        config = {"configurable": {"thread_id": thread_id}}
        state = self.app.get_state(config)
        
        if not state.values:
            workflow_summary = self._create_workflow_summary(original_workflow) if original_workflow else ""
            initial_state = {
                "original_workflow": original_workflow or {},
                "workflow_summary": workflow_summary,
                "modification_request": user_input,
                "question_iteration": 0,
                "user_answers": {},
                "chat_id": thread_id,
                "current_question_index": 0,
                "last_user_message": "",
                "logs": [],
                "changes_applied": [],
                "question_history": []
            }
            self.app.invoke(initial_state, config=config)
        else:
            self.app.update_state(config, {"last_user_message": user_input})
            self.app.invoke(None, config=config)
        
        final_state = self.app.get_state(config)
        return final_state.values.get("last_message", "Processing completed.")

    def _create_workflow_summary(self, workflow: Dict[str, Any]) -> str:
        """
        Create a token-efficient summary of the workflow for context
        This reduces token usage while keeping essential information
        """
        if not workflow:
            return ""
        
        summary_parts = []
        
        # Metadata
        metadata = workflow.get("metadata", {})
        summary_parts.append(f"Workflow: {metadata.get('workflow_name', 'Unknown')}")
        summary_parts.append(f"Description: {metadata.get('description', 'N/A')}")
        
        # Approval chain summary
        approval_chain = workflow.get("workflow_analysis", {}).get("approval_chain", [])
        if approval_chain:
            approvers = " -> ".join([a.get("approver_role", "Unknown") for a in approval_chain])
            summary_parts.append(f"Approval Chain: {approvers}")
        
        # Form fields count
        form_questions = workflow.get("microsoft_forms", {}).get("questions", [])
        summary_parts.append(f"Form Fields: {len(form_questions)}")
        
        # Excel columns count
        excel_cols = workflow.get("excel_tracker", {}).get("columns", [])
        summary_parts.append(f"Excel Columns: {len(excel_cols)}")
        
        # Workflow steps count
        workflow_steps = workflow.get("power_automate_workflow", {}).get("steps", [])
        summary_parts.append(f"Workflow Steps: {len(workflow_steps)}")
        
        return "\n".join(summary_parts)

    def _analyze_modification_request(self, state: ModificationState):
        """
        Analyze what needs to be modified using workflow summary for efficiency
        """
        workflow_summary = state.get("workflow_summary", "")
        modification_request = state.get("modification_request", "")
        
        print("\n[LLM] Analyzing modification request...")
        
        # Use summary instead of full workflow to save tokens
        prompt = f"""
You are a workflow modification expert. Analyze what needs to be changed.

CURRENT WORKFLOW SUMMARY:
{workflow_summary}

USER'S MODIFICATION REQUEST:
"{modification_request}"

Analyze and return ONLY valid JSON:
{{
  "modification_type": "add_approver|remove_approver|change_sequence|add_field|modify_notification|add_condition|other",
  "affected_components": ["approval_chain", "form_schema", "excel_schema", "workflow_steps"],
  "complexity": "simple|moderate|complex",
  "requires_clarification": true/false,
  "clarification_topics": ["list topics needing clarification"],
  "summary": "Brief summary of what will be changed"
}}

Return ONLY the JSON, no other text.
"""
        try:
            messages = [
                SystemMessage(content="You are a workflow analysis expert. Always return valid JSON only."),
                HumanMessage(content=prompt)
            ]
            response = self.model.invoke(messages)
            response_text = response.content.strip()
            
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            analysis = json.loads(response_text)
            
            print(f"[ANALYSIS] Type: {analysis.get('modification_type')}")
            print(f"[ANALYSIS] Complexity: {analysis.get('complexity')}")
            print(f"[ANALYSIS] Requires clarification: {analysis.get('requires_clarification')}")
            
            return {
                "analysis": analysis,
                "question_iteration": 0,
                "last_message": f"Analysis complete: {analysis.get('summary')}"
            }
        except Exception as e:
            print(f"[ERROR] Analysis failed: {e}")
            return {
                "analysis": {
                    "requires_clarification": True,
                    "summary": "Manual override due to error",
                    "modification_type": "other"
                },
                "last_message": "Analysis completed with defaults."
            }

    def _generate_clarifying_questions(self, state: ModificationState):
        """
        Generate questions based on analysis and workflow context
        Similar to agent.py but uses workflow summary for efficiency
        """
        index = state.get("current_question_index", 0)
        questions = state.get("clarifying_questions", [])
        iteration = state.get("question_iteration", 0)
        
        # If we have questions and haven't finished them, just move to next
        if index < len(questions):
            current_q = questions[index]
            print(f"\n[QUESTION {index + 1}/{len(questions)}] {current_q['question']}")
            
            return {
                "last_message": f"Question {index + 1}/{len(questions)}: {current_q['question']}"
            }
        
        # Need to generate new batch of questions
        analysis = state.get("analysis", {})
        workflow_summary = state.get("workflow_summary", "")
        modification_request = state.get("modification_request", "")
        user_answers = state.get("user_answers", {})
        
        print(f"\n[LLM] Generating clarifying questions (iteration {iteration})...")
        
        # Build context about what we already know
        answered_summary = ""
        if user_answers:
            answered_summary = "\n\nALREADY ANSWERED:\n"
            for qid, answer in user_answers.items():
                answered_summary += f"- {qid}: {answer}\n"
        
        prompt = f"""
You are helping modify a workflow. Generate clarifying questions to ensure accurate modifications.

WORKFLOW SUMMARY:
{workflow_summary}

MODIFICATION REQUEST:
"{modification_request}"

ANALYSIS:
- Type: {analysis.get('modification_type')}
- Affected: {', '.join(analysis.get('affected_components', []))}
- Topics needing clarification: {', '.join(analysis.get('clarification_topics', []))}
{answered_summary}

Generate 2-4 clarifying questions to ensure proper modification. Focus on:
1. Specific details needed for the modification
2. Placement/ordering if relevant
3. Dependencies or impacts on other components
4. Any ambiguities in the request

Return ONLY valid JSON array:
[
  {{
    "id": "q1",
    "question": "Clear, specific question",
    "purpose": "Why this question is important",
    "answer_type": "text|number|choice",
    "options": ["if choice type"],
    "validation": "What makes a valid answer"
  }}
]
"""
        try:
            messages = [
                SystemMessage(content="You are a workflow clarification expert. Return valid JSON array only."),
                HumanMessage(content=prompt)
            ]
            response = self.model.invoke(messages)
            response_text = response.content.strip()
            
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            new_questions = json.loads(response_text)
            
            if not isinstance(new_questions, list):
                new_questions = []
            
            print(f"[INFO] Generated {len(new_questions)} questions")
            
            # Add to question history
            question_history = state.get("question_history", [])
            question_history.extend(new_questions)
            
            if new_questions:
                first_q = new_questions[0]
                return {
                    "clarifying_questions": new_questions,
                    "current_question_index": 0,
                    "question_history": question_history,
                    "last_message": f"Question 1/{len(new_questions)}: {first_q['question']}"
                }
            else:
                return {
                    "clarifying_questions": [],
                    "current_question_index": 0,
                    "question_history": question_history,
                    "last_message": "No clarifying questions needed."
                }
                
        except Exception as e:
            print(f"[ERROR] Failed to generate questions: {e}")
            return {
                "clarifying_questions": [],
                "current_question_index": 0,
                "last_message": "Proceeding without additional questions."
            }

    def _collect_user_answers(self, state: ModificationState):
        """
        Collect answer for current question - INTERRUPT POINT
        Similar to agent.py's collect_answers
        """
        questions = state.get("clarifying_questions", [])
        index = state.get("current_question_index", 0)
        user_message = state.get("last_user_message", "").strip()
        
        if index >= len(questions):
            return {"last_message": "All questions answered."}
        
        current_q = questions[index]
        
        # If no user message yet, we're waiting for answer
        if not user_message:
            return {
                "last_message": f"Waiting for answer to: {current_q['question']}"
            }
        
        # Store the answer
        user_answers = state.get("user_answers", {})
        user_answers[current_q["id"]] = user_message
        
        print(f"[ANSWER] {current_q['id']}: {user_message}")
        
        # Move to next question
        next_index = index + 1
        
        if next_index < len(questions):
            next_q = questions[next_index]
            return {
                "user_answers": user_answers,
                "current_question_index": next_index,
                "last_user_message": "",  # Clear for next question
                "last_message": f"Question {next_index + 1}/{len(questions)}: {next_q['question']}"
            }
        else:
            return {
                "user_answers": user_answers,
                "current_question_index": next_index,
                "last_user_message": "",
                "last_message": "All questions in this batch answered."
            }

    def _validate_user_answers(self, state: ModificationState):
        """
        Validate collected answers using workflow summary
        Similar to agent.py's validation
        """
        user_answers = state.get("user_answers", {})
        workflow_summary = state.get("workflow_summary", "")
        modification_request = state.get("modification_request", "")
        analysis = state.get("analysis", {})
        
        print("\n[LLM] Validating answers...")
        
        prompt = f"""
You are validating answers for a workflow modification.

WORKFLOW SUMMARY:
{workflow_summary}

MODIFICATION REQUEST:
"{modification_request}"

MODIFICATION TYPE: {analysis.get('modification_type')}

USER ANSWERS:
{json.dumps(user_answers, indent=2)}

Determine if we have enough information to proceed with the modification.

Return ONLY valid JSON:
{{
  "can_proceed": true/false,
  "validation_summary": "Brief explanation",
  "missing_information": ["list any critical missing info"],
  "concerns": ["any potential issues or ambiguities"]
}}
"""
        try:
            messages = [
                SystemMessage(content="You are a validation expert. Return valid JSON only."),
                HumanMessage(content=prompt)
            ]
            response = self.model.invoke(messages)
            response_text = response.content.strip()
            
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            validation = json.loads(response_text)
            
            print(f"[VALIDATION] Can proceed: {validation.get('can_proceed')}")
            if validation.get('missing_information'):
                print(f"[VALIDATION] Missing: {', '.join(validation['missing_information'])}")
            
            return {
                "validation_result": validation,
                "last_message": validation.get("validation_summary", "Validation complete.")
            }
            
        except Exception as e:
            print(f"[ERROR] Validation failed: {e}")
            return {
                "validation_result": {"can_proceed": True, "validation_summary": "Proceeding with available info"},
                "last_message": "Validation completed with defaults."
            }

    def _create_modification_plan(self, state: ModificationState):
        """
        Create detailed modification plan using workflow summary and validated answers
        """
        analysis = state.get("analysis", {})
        user_answers = state.get("user_answers", {})
        workflow_summary = state.get("workflow_summary", "")
        modification_request = state.get("modification_request", "")
        
        print("\n[LLM] Creating modification plan...")
        
        prompt = f"""
You are creating a detailed modification plan for a workflow.

WORKFLOW SUMMARY:
{workflow_summary}

MODIFICATION REQUEST:
"{modification_request}"

USER ANSWERS:
{json.dumps(user_answers, indent=2)}

ANALYSIS:
{json.dumps(analysis, indent=2)}

Create a detailed step-by-step modification plan.

Return ONLY valid JSON:
{{
  "changes": [
    {{
      "component": "approval_chain|form_schema|excel_schema|workflow_steps|notifications",
      "action": "add|remove|modify|reorder",
      "details": {{
        "specific_field": "value",
        "position": "where applicable",
        "new_value": "if modifying"
      }},
      "rationale": "why this change"
    }}
  ],
  "version_change": "1.0 -> 1.1",
  "impact_assessment": "Brief description of impact"
}}
"""
        try:
            messages = [
                SystemMessage(content="You are a modification planning expert. Return valid JSON only."),
                HumanMessage(content=prompt)
            ]
            response = self.model.invoke(messages)
            response_text = response.content.strip()
            
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            plan = json.loads(response_text)
            
            print(f"[PLAN] {len(plan.get('changes', []))} changes planned")
            
            return {
                "modification_plan": plan,
                "last_message": f"Plan created: {len(plan.get('changes', []))} changes"
            }
            
        except Exception as e:
            print(f"[ERROR] Planning failed: {e}")
            return {
                "modification_plan": {"changes": []},
                "last_message": "Plan created with defaults."
            }

    def _apply_modifications(self, state: ModificationState):
        """
        Apply the modifications to the actual workflow
        Uses full workflow (not summary) to make actual changes
        """
        original_workflow = state.get("original_workflow", {})
        plan = state.get("modification_plan", {})
        changes = plan.get("changes", [])
        
        print("\n[INFO] Applying modifications...")
        
        # Deep copy the workflow
        modified_workflow = json.loads(json.dumps(original_workflow))
        changes_applied = []
        
        for change in changes:
            component = change.get("component")
            action = change.get("action")
            details = change.get("details", {})
            
            try:
                if component == "approval_chain":
                    modified_workflow = self._modify_approval_chain(modified_workflow, action, details)
                    changes_applied.append(f"{action} in approval chain")
                    
                elif component == "form_schema":
                    modified_workflow = self._modify_form_schema(modified_workflow, action, details)
                    changes_applied.append(f"{action} in form schema")
                    
                elif component == "excel_schema":
                    modified_workflow = self._modify_excel_schema(modified_workflow, action, details)
                    changes_applied.append(f"{action} in excel schema")
                    
                elif component == "workflow_steps":
                    modified_workflow = self._modify_workflow_steps(modified_workflow, action, details)
                    changes_applied.append(f"{action} in workflow steps")
                    
                elif component == "notifications":
                    modified_workflow = self._modify_notifications(modified_workflow, action, details)
                    changes_applied.append(f"{action} in notifications")
                    
            except Exception as e:
                print(f"[ERROR] Failed to apply {component} {action}: {e}")
                changes_applied.append(f"FAILED: {component} {action}")
        
        # Update version
        if "metadata" in modified_workflow:
            current_version = modified_workflow["metadata"].get("version", "1.0")
            modified_workflow["metadata"]["version"] = self._increment_version(current_version)
        
        print(f"[INFO] Applied {len(changes_applied)} changes")
        
        return {
            "modified_workflow": modified_workflow,
            "changes_applied": changes_applied,
            "last_message": f"Applied {len(changes_applied)} modifications"
        }

    def _validate_modifications(self, state: ModificationState):
        """
        Validate the modified workflow
        """
        modified_workflow = state.get("modified_workflow", {})
        
        print("\n[INFO] Validating modifications...")
        
        issues = []
        
        # Check approval chain consistency
        approval_chain = modified_workflow.get("workflow_analysis", {}).get("approval_chain", [])
        levels = [a["level"] for a in approval_chain]
        if levels and levels != list(range(1, len(levels) + 1)):
            issues.append("Approval levels are not sequential")
        
        # Check form-approver consistency
        form_questions = modified_workflow.get("microsoft_forms", {}).get("questions", [])
        approver_emails = [q for q in form_questions if "email" in q.get("field_name", "")]
        if len(approver_emails) != len(approval_chain):
            issues.append("Form approver fields don't match approval chain")
        
        validation_result = {
            "valid": len(issues) == 0,
            "issues": issues
        }
        
        if issues:
            print(f"[WARNING] Validation issues: {', '.join(issues)}")
        else:
            print("[SUCCESS] Validation passed")
        
        return {
            "validation_result": validation_result,
            "last_message": "Validation complete." if not issues else f"Validation warnings: {len(issues)}"
        }

    def _display_results(self, state: ModificationState):
        """
        Save modified workflow and display results
        """
        modified_workflow = state.get("modified_workflow", {})
        chat_id = state.get("chat_id", "modified_workflow")
        changes_applied = state.get("changes_applied", [])
        metadata = modified_workflow.get("metadata", {})
        workflow_name = metadata.get("workflow_name", "Unknown Workflow")
        
        print("\n" + "="*80)
        print("[SUCCESS] WORKFLOW MODIFICATION COMPLETE")
        print("="*80)
        print(f"\n[TITLE] {workflow_name}")
        print(f"[VERSION] {metadata.get('version')}")
        print(f"[CHANGES] {len(changes_applied)}")
        
        # Save to file
        workflows_dir = os.path.join(os.path.dirname(__file__), 'workflows')
        os.makedirs(workflows_dir, exist_ok=True)
        filepath = os.path.join(workflows_dir, f"{chat_id}.json")
        
        try:
            with open(filepath, 'w') as f:
                json.dump(modified_workflow, f, indent=2)
            print(f"\n[SAVE] Modified workflow saved to: {filepath}")
            
            # Database logging
            try:
                db_path = os.path.join(os.path.dirname(__file__), 'database')
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                workflow_json = json.dumps(modified_workflow)
                
                # Get latest version
                cursor.execute("SELECT MAX(CAST(version AS INTEGER)) FROM state WHERE chatid = ?", (chat_id,))
                max_version_row = cursor.fetchone()
                
                new_version = 1
                if max_version_row and max_version_row[0] is not None:
                    new_version = max_version_row[0] + 1
                
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                cursor.execute('''
                    INSERT INTO state (chatid, workflow, version, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (chat_id, workflow_json, str(new_version), timestamp))
                
                conn.commit()
                conn.close()
                print(f"[DB] Workflow logged (v{new_version}) for chat_id: {chat_id}")
            except Exception as db_e:
                print(f"[ERROR] Failed to log to database: {db_e}")
                
        except Exception as e:
            print(f"[ERROR] Failed to save JSON: {e}")
        
        print("\n" + "="*80)
        
        changes_summary = "\n".join([f"- {c}" for c in changes_applied])
        
        return {
            "last_message": f"Workflow Modification Complete!\n\nName: {workflow_name}\nVersion: {metadata.get('version')}\n\nChanges Applied:\n{changes_summary}\n\nModified workflow saved successfully."
        }

    # Helper modification methods (same as before but included for completeness)
    def _modify_approval_chain(self, workflow, action, details):
        """Modify approval chain"""
        chain = workflow.get("workflow_analysis", {}).get("approval_chain", [])
        
        if action == "add":
            new_level = details.get("level", len(chain) + 1)
            new_approver = {
                "level": new_level,
                "approver_role": details.get("role", "New Approver"),
                "approver_type": "single",
                "source": "from_form",
                "conditions": [f"Level {new_level} approver"],
                "rejection_behavior": details.get("rejection_behavior", "end_workflow"),
                "notification_rules": [],
                "timeout_hours": details.get("timeout_hours", 48)
            }
            chain.insert(new_level - 1, new_approver)
            # Renumber levels
            for idx, a in enumerate(chain, 1):
                a["level"] = idx
            
            # Add corresponding form fields
            role_field = new_approver["approver_role"].replace(" ", "_").lower()
            form_qs = workflow.get("microsoft_forms", {}).get("questions", [])
            form_qs.extend([
                {
                    "id": f"q{len(form_qs)+1}",
                    "field_name": f"{role_field}_name",
                    "type": "text",
                    "title": f"{new_approver['approver_role']} Name",
                    "required": True,
                    "purpose": "approver_identification"
                },
                {
                    "id": f"q{len(form_qs)+2}",
                    "field_name": f"{role_field}_email",
                    "type": "email",
                    "title": f"{new_approver['approver_role']} Email",
                    "required": True,
                    "purpose": "approver_contact"
                }
            ])
            
        elif action == "remove":
            level = details.get("level")
            chain = [a for a in chain if a["level"] != level]
            # Renumber levels
            for idx, a in enumerate(chain, 1):
                a["level"] = idx
            workflow["workflow_analysis"]["approval_chain"] = chain
            
        elif action == "modify":
            level = details.get("level")
            for approver in chain:
                if approver["level"] == level:
                    if "role" in details:
                        approver["approver_role"] = details["role"]
                    if "timeout_hours" in details:
                        approver["timeout_hours"] = details["timeout_hours"]
                    if "rejection_behavior" in details:
                        approver["rejection_behavior"] = details["rejection_behavior"]
                    break
        
        return workflow

    def _modify_form_schema(self, workflow, action, details):
        """Modify form schema"""
        qs = workflow.get("microsoft_forms", {}).get("questions", [])
        
        if action == "add":
            qs.append({
                "id": f"q{len(qs)+1}",
                "field_name": details.get("field_name", "new_field"),
                "type": details.get("type", "text"),
                "title": details.get("title", "New Field"),
                "required": details.get("required", False),
                "purpose": details.get("purpose", "general")
            })
        elif action == "remove":
            field_name = details.get("field_name")
            qs = [q for q in qs if q.get("field_name") != field_name]
            workflow["microsoft_forms"]["questions"] = qs
            
        return workflow

    def _modify_excel_schema(self, workflow, action, details):
        """Modify excel schema"""
        cols = workflow.get("excel_tracker", {}).get("columns", [])
        
        if action == "add":
            cols.append({
                "name": details.get("name", "New Column"),
                "type": details.get("type", "text"),
                "source": details.get("source", "form_field")
            })
        elif action == "remove":
            col_name = details.get("name")
            cols = [c for c in cols if c.get("name") != col_name]
            workflow["excel_tracker"]["columns"] = cols
            
        return workflow

    def _modify_workflow_steps(self, workflow, action, details):
        """Modify workflow steps"""
        steps = workflow.get("power_automate_workflow", {}).get("steps", [])
        
        if action == "add":
            position = details.get("position", len(steps) + 1)
            new_step = {
                "step_number": position,
                "name": details.get("name", "New Step"),
                "type": details.get("type", "action"),
                "connector": details.get("connector", "")
            }
            steps.insert(position - 1, new_step)
            # Renumber steps
            for idx, s in enumerate(steps, 1):
                s["step_number"] = idx
        elif action == "remove":
            step_number = details.get("step_number")
            steps = [s for s in steps if s.get("step_number") != step_number]
            # Renumber steps
            for idx, s in enumerate(steps, 1):
                s["step_number"] = idx
            workflow["power_automate_workflow"]["steps"] = steps
            
        return workflow

    def _modify_notifications(self, workflow, action, details):
        """Modify notifications"""
        notifs = workflow.get("workflow_analysis", {}).get("notifications", [])
        
        if action == "add":
            notifs.append({
                "trigger": details.get("trigger", "on_action"),
                "recipients": details.get("recipients", []),
                "platform": details.get("platform", "Outlook"),
                "template": details.get("template", "notification")
            })
            
        return workflow

    def _increment_version(self, version):
        """Increment version number"""
        parts = str(version).split(".")
        if len(parts) >= 2:
            parts[-1] = str(int(parts[-1]) + 1)
            return ".".join(parts)
        return f"{version}.1"

    def _check_batch_status(self, state: ModificationState) -> str:
        """
        Check if current batch of questions is complete
        """
        questions = state.get("clarifying_questions", [])
        index = state.get("current_question_index", 0)
        
        if index < len(questions):
            return "next_question"
        else:
            return "batch_done"

    def _should_ask_more_questions(self, state: ModificationState) -> str:
        """
        Decide if more questions needed after validation
        Similar to agent.py logic
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
            print("\n[INFO] Need more information, generating new batch...")
            return "ask_more"

    def _increment_question_iteration(self, state: ModificationState):
        """
        Increment the question iteration count
        """
        iteration = state.get("question_iteration", 0)
        return {
            "question_iteration": iteration + 1,
            "clarifying_questions": [], # Clear old batch
            "current_question_index": 0  # Reset index for new batch
        }

    def _build_graph(self):
        """
        Build graph with question-answer-validate loop like agent.py
        """
        graph = StateGraph(ModificationState)
        
        # Add nodes
        graph.add_node("analyze_request", self._analyze_modification_request)
        graph.add_node("generate_questions", self._generate_clarifying_questions)
        graph.add_node("collect_answers", self._collect_user_answers)
        graph.add_node("validate_answers", self._validate_user_answers)
        graph.add_node("create_plan", self._create_modification_plan)
        graph.add_node("apply_modifications", self._apply_modifications)
        graph.add_node("validate", self._validate_modifications)
        graph.add_node("display", self._display_results)
        
        # Define flow
        graph.set_entry_point("analyze_request")
        graph.add_edge("analyze_request", "generate_questions")
        graph.add_edge("generate_questions", "collect_answers")
        
        # Per-question loop - like agent.py
        graph.add_conditional_edges(
            "collect_answers",
            self._check_batch_status,
            {
                "next_question": "generate_questions",
                "batch_done": "validate_answers"
            }
        )
        
        # Conditional: ask more (new batch) or proceed - like agent.py
        graph.add_node("increment_iteration", self._increment_question_iteration)
        
        graph.add_conditional_edges(
            "validate_answers",
            self._should_ask_more_questions,
            {
                "ask_more": "increment_iteration",
                "proceed": "create_plan"
            }
        )
        
        graph.add_edge("increment_iteration", "generate_questions")
        
        # Rest of the flow
        graph.add_edge("create_plan", "apply_modifications")
        graph.add_edge("apply_modifications", "validate")
        graph.add_edge("validate", "display")
        graph.add_edge("display", END)
        
        return graph.compile(
            checkpointer=self.checkpointer,
            interrupt_before=["collect_answers"]  # Interrupt at same point as agent.py
        )

    def run(self, initial_state: ModificationState):
        return self.app.invoke(initial_state)