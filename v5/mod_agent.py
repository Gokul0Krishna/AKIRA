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
    modification_request: str
    analysis: Dict[str, Any]
    clarifying_questions: List[Dict[str, Any]]
    user_answers: Dict[str, Any]
    modification_plan: Dict[str, Any]
    modified_workflow: Dict[str, Any]
    validation_result: Dict[str, Any]
    iteration_count: int
    changes_applied: List[str]
    last_message: str
    last_user_message: str
    chat_id: str
    current_question_index: int
    logs: List[str]

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
        config = {"configurable": {"thread_id": thread_id}}
        
        # Check current state
        state = self.app.get_state(config)
        
        if not state.values:
            # First run
            initial_state = {
                "original_workflow": original_workflow or {},
                "modification_request": user_input,
                "user_answers": {},
                "chat_id": thread_id,
                "current_question_index": 0,
                "logs": [],
                "iteration_count": 0,
                "changes_applied": []
            }
            # Run until interrupt (collect_clarifications) or End
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
        config = {"configurable": {"thread_id": thread_id}}
        state = self.app.get_state(config)
        if not state.values:
            initial_state = {
                "original_workflow": original_workflow or {},
                "modification_request": user_input,
                "user_answers": {},
                "chat_id": thread_id,
                "current_question_index": 0,
                "logs": [],
                "iteration_count": 0,
                "changes_applied": []
            }
            self.app.invoke(initial_state, config=config)
        else:
            self.app.update_state(config, {"last_user_message": user_input})
            self.app.invoke(None, config=config)
        
        final_state = self.app.get_state(config)
        return final_state.values.get("last_message", "Processing completed.")

    def _load_existing_workflow(self, state: ModificationState):
        original_workflow = state.get("original_workflow", {})
        metadata = original_workflow.get("metadata", {})
        workflow_name = metadata.get("workflow_name", "Unknown")
        
        log_msg = f"Loading Workflow: {workflow_name}"
        print(f"\n[INFO] {log_msg}")
        
        return {
            "iteration_count": 0,
            "changes_applied": [],
            "last_message": log_msg
        }

    def _analyze_modification_request(self, state: ModificationState):
        original_workflow = state.get("original_workflow", {})
        modification_request = state.get("modification_request", "")
        
        print("\n[LLM] Analyzing modification request...")
        
        prompt = f"""
You are a workflow modification expert. Analyze what needs to be changed in this workflow.

CURRENT WORKFLOW:
{json.dumps(original_workflow, indent=2)}

USER'S MODIFICATION REQUEST:
"{modification_request}"

Analyze and return ONLY valid JSON:
{{
  "modification_type": "add_approver|remove_approver|change_sequence|add_field|modify_notification|add_condition|other",
  "affected_components": ["approval_chain", "form_schema", "excel_schema", "workflow_steps"],
  "complexity": "simple|moderate|complex",
  "changes_needed": [
    {{
      "component": "approval_chain",
      "action": "add|remove|modify|reorder",
      "details": "specific description of change"
    }}
  ],
  "potential_conflicts": ["list any issues"],
  "requires_clarification": true/false,
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
            return {
                "analysis": analysis,
                "last_message": f"Analysis complete: {analysis.get('summary')}"
            }
        except Exception as e:
            print(f"[ERROR] Analysis failed: {e}")
            return {
                "analysis": {"requires_clarification": False, "summary": "Manual override due to error"},
                "last_message": "Analysis failed, proceeding with manual defaults."
            }

    def _generate_clarifying_questions(self, state: ModificationState):
        analysis = state.get("analysis", {})
        if not analysis.get("requires_clarification", False):
            return {"clarifying_questions": [], "last_message": "No clarification needed."}
            
        modification_request = state.get("modification_request", "")
        original_workflow = state.get("original_workflow", {})
        
        print("\n[LLM] Generating clarifying questions...")
        
        prompt = f"""
You need to clarify the user's modification request.

MODIFICATION REQUEST: {modification_request}
ANALYSIS: {json.dumps(analysis, indent=2)}

CURRENT WORKFLOW STRUCTURE:
- Approval Chain: {len(original_workflow.get('workflow_analysis', {}).get('approval_chain', []))} levels
- Form Fields: {len(original_workflow.get('microsoft_forms', {}).get('questions', []))} questions

Generate 2-4 specific clarifying questions. Return ONLY valid JSON:
{{
  "questions": [
    {{
      "id": "q1",
      "question": "...",
      "type": "choice|text",
      "options": ["opt1", "opt2"],
      "required": true
    }}
  ]
}}
"""
        try:
            messages = [HumanMessage(content=prompt)]
            response = self.model.invoke(messages)
            txt = response.content.strip().replace("```json","").replace("```","")
            questions = json.loads(txt).get("questions", [])
            
            first_q = questions[0]['question'] if questions else "Could you provide more details?"
            return {
                "clarifying_questions": questions,
                "current_question_index": 0,
                "last_message": f"Clarifying Question [1/{len(questions)}]:\n\n{first_q}"
            }
        except Exception:
            return {"clarifying_questions": [], "last_message": "Error generating questions, proceeding."}

    def _collect_clarifications(self, state: ModificationState):
        questions = state.get("clarifying_questions", [])
        index = state.get("current_question_index", 0)
        user_input = state.get("last_user_message", "")
        answers = state.get("user_answers", {})
        
        if not questions or index >= len(questions):
            return {"user_answers": answers}
            
        current_q = questions[index]
        new_answers = answers.copy()
        new_answers[current_q['id']] = user_input
        
        new_index = index + 1
        if new_index < len(questions):
            next_q = questions[new_index]['question']
            return {
                "user_answers": new_answers,
                "current_question_index": new_index,
                "last_message": f"Clarifying Question [{new_index + 1}/{len(questions)}]:\n\n{next_q}"
            }
        else:
            return {
                "user_answers": new_answers,
                "current_question_index": new_index,
                "last_message": "All clarifications collected. Creating plan..."
            }

    def _create_modification_plan(self, state: ModificationState):
        original_workflow = state.get("original_workflow", {})
        modification_request = state.get("modification_request", "")
        analysis = state.get("analysis", {})
        user_answers = state.get("user_answers", {})
        
        print("\n[LLM] Creating modification plan...")
        
        prompt = f"""
You are creating a detailed modification plan for a workflow.

ORIGINAL WORKFLOW:
{json.dumps(original_workflow, indent=2)}

MODIFICATION REQUEST: {modification_request}
ANALYSIS: {json.dumps(analysis, indent=2)}
USER CLARIFICATIONS: {json.dumps(user_answers, indent=2)}

Create a detailed step-by-step modification plan. Return ONLY valid JSON:
{{
  "modifications": [
    {{
      "step": 1,
      "component": "approval_chain|form_schema|excel_schema|workflow_steps|notifications",
      "action": "add_approver|remove_approver|add_field|remove_field|add_step|remove_step|add_notification",
      "details": {{ ... }},
      "reason": "..."
    }}
  ],
  "cascading_changes": [ ... ],
  "estimated_impact": "low|moderate|high"
}}
"""
        try:
            messages = [HumanMessage(content=prompt)]
            response = self.model.invoke(messages)
            txt = response.content.strip().replace("```json","").replace("```","")
            plan = json.loads(txt)
            return {
                "modification_plan": plan,
                "last_message": f"Plan created with {len(plan.get('modifications', []))} changes."
            }
        except Exception:
            return {"modification_plan": {"modifications": []}, "last_message": "Error creating plan."}

    def _apply_modifications(self, state: ModificationState):
        modified_workflow = json.loads(json.dumps(state.get("original_workflow", {})))
        plan = state.get("modification_plan", {})
        changes_applied = []
        
        print("\n[INFO] Applying modifications...")
        
        for mod in plan.get("modifications", []):
            comp = mod.get("component")
            action = mod.get("action")
            details = mod.get("details", {})
            
            try:
                if comp == "approval_chain":
                    modified_workflow = self._modify_approval_chain(modified_workflow, action, details)
                elif comp == "form_schema":
                    modified_workflow = self._modify_form_schema(modified_workflow, action, details)
                elif comp == "excel_schema":
                    modified_workflow = self._modify_excel_schema(modified_workflow, action, details)
                elif comp == "workflow_steps":
                    modified_workflow = self._modify_workflow_steps(modified_workflow, action, details)
                elif comp == "notifications":
                    modified_workflow = self._modify_notifications(modified_workflow, action, details)
                
                changes_applied.append(f"{action} in {comp}")
            except Exception as e:
                print(f"[ERROR] Failed to apply {action} to {comp}: {e}")
                
        # Update metadata
        if "metadata" in modified_workflow:
            modified_workflow["metadata"]["version"] = self._increment_version(modified_workflow["metadata"].get("version", "1.0"))
            modified_workflow["metadata"]["modification_history"] = modified_workflow["metadata"].get("modification_history", [])
            modified_workflow["metadata"]["modification_history"].append({
                "timestamp": "2024-12-03T00:00:00Z",
                "changes": changes_applied
            })
            
        return {
            "modified_workflow": modified_workflow,
            "changes_applied": changes_applied,
            "last_message": f"Applied {len(changes_applied)} changes successfully."
        }

    def _validate_modifications(self, state: ModificationState):
        modified_workflow = state.get("modified_workflow", {})
        approval_chain = modified_workflow.get("workflow_analysis", {}).get("approval_chain", [])
        
        issues = []
        levels = [a["level"] for a in approval_chain]
        if levels != list(range(1, len(levels) + 1)):
            issues.append("Approval levels are not sequential")
            
        return {
            "validation_result": {"valid": len(issues) == 0, "issues": issues},
            "last_message": "Validation complete." if not issues else f"Validation failed: {', '.join(issues)}"
        }

    def _display_results(self, state: ModificationState):
        modified_workflow = state.get("modified_workflow", {})
        chat_id = state.get("chat_id", "modified_workflow")
        metadata = modified_workflow.get("metadata", {})
        workflow_name = metadata.get("workflow_name", metadata.get("workflow_title", "Unknown Workflow"))
        
        # Save to file (Overwrite original)
        workflows_dir = os.path.join(os.path.dirname(__file__), 'workflows')
        os.makedirs(workflows_dir, exist_ok=True)
        filepath = os.path.join(workflows_dir, f"{chat_id}.json")
        
        try:
            with open(filepath, 'w') as f:
                json.dump(modified_workflow, f, indent=2)
            print(f"\n[SAVE] Modified Workflow saved to: {filepath}")
            
            # Database Insertion: Log the updated state with incremented version
            try:
                db_path = os.path.join(os.path.dirname(__file__), 'database')
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                workflow_json = json.dumps(modified_workflow)
                
                # Get the latest version for this chatid
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
                print(f"[DB] Workflow modification logged (v{new_version}) for chat_id: {chat_id}")
            except Exception as db_e:
                print(f"[ERROR] Failed to log modified state to database: {db_e}")
                
        except Exception as e:
            print(f"[ERROR] Failed to save modified JSON: {e}")
            
        return {
            "last_message": f"Workflow Modification Complete!\n\nVersion: {metadata.get('version')}\nChanges Applied: {len(state.get('changes_applied', []))}\n\nModified structure is saved and updated."
        }

    # Helper Modification Methods
    def _modify_approval_chain(self, workflow, action, details):
        chain = workflow.get("workflow_analysis", {}).get("approval_chain", [])
        if action == "add_approver":
            new_approver = {
                "level": details.get("level", len(chain) + 1),
                "approver_role": details.get("new_approver", "New Approver"),
                "approver_type": "single",
                "source": "from_form",
                "conditions": [f"Level {details.get('level')} approver"],
                "rejection_behavior": "end_workflow",
                "notification_rules": [],
                "timeout_hours": 48
            }
            chain.insert(new_approver["level"] - 1, new_approver)
            for idx, a in enumerate(chain, 1): a["level"] = idx
            
            # Add form fields
            role_field = new_approver["approver_role"].replace(" ", "_").lower()
            form_qs = workflow.get("microsoft_forms", {}).get("questions", [])
            form_qs.extend([
                {"id": f"q{len(form_qs)+1}", "field_name": f"{role_field}_name", "type": "text", "title": f"{new_approver['approver_role']} Name", "purpose": "approver_identification"},
                {"id": f"q{len(form_qs)+2}", "field_name": f"{role_field}_email", "type": "email", "title": f"{new_approver['approver_role']} Email", "purpose": "approver_contact"}
            ])
        elif action == "remove_approver":
            level = details.get("level")
            chain = [a for a in chain if a["level"] != level]
            for idx, a in enumerate(chain, 1): a["level"] = idx
            workflow["workflow_analysis"]["approval_chain"] = chain
        return workflow

    def _modify_form_schema(self, workflow, action, details):
        qs = workflow.get("microsoft_forms", {}).get("questions", [])
        if action == "add_field":
            qs.append({
                "id": f"q{len(qs)+1}",
                "field_name": details.get("field_name"),
                "type": details.get("type", "text"),
                "title": details.get("label"),
                "required": details.get("required", False)
            })
        return workflow

    def _modify_excel_schema(self, workflow, action, details):
        cols = workflow.get("excel_tracker", {}).get("columns", [])
        if action == "add_column":
            cols.append({"name": details.get("column_name"), "type": details.get("type", "text")})
        return workflow

    def _modify_workflow_steps(self, workflow, action, details):
        steps = workflow.get("power_automate_workflow", {}).get("steps", [])
        if action == "add_step":
            new_step = {
                "step_number": details.get("position", len(steps) + 1),
                "name": details.get("name"),
                "type": details.get("type", "action"),
                "connector": details.get("connector", "")
            }
            steps.insert(new_step["step_number"] - 1, new_step)
            for idx, s in enumerate(steps, 1): s["step_number"] = idx
        return workflow

    def _modify_notifications(self, workflow, action, details):
        notifs = workflow.get("workflow_analysis", {}).get("notifications", [])
        if action == "add_notification":
            notifs.append({
                "trigger": details.get("trigger"),
                "recipients": details.get("recipients", []),
                "platform": "Outlook",
                "template": details.get("template", "notification")
            })
        return workflow

    def _increment_version(self, version):
        parts = str(version).split(".")
        if len(parts) >= 2:
            parts[-1] = str(int(parts[-1]) + 1)
            return ".".join(parts)
        return f"{version}.1"

    def _should_ask_questions(self, state: ModificationState) -> str:
        analysis = state.get("analysis", {})
        return "ask" if analysis.get("requires_clarification", False) else "proceed"

    def _build_graph(self):
        workflow = StateGraph(ModificationState)
        
        workflow.add_node("load_workflow", self._load_existing_workflow)
        workflow.add_node("analyze_request", self._analyze_modification_request)
        workflow.add_node("generate_questions", self._generate_clarifying_questions)
        workflow.add_node("collect_clarifications", self._collect_clarifications)
        workflow.add_node("create_plan", self._create_modification_plan)
        workflow.add_node("apply_modifications", self._apply_modifications)
        workflow.add_node("validate", self._validate_modifications)
        workflow.add_node("display", self._display_results)
        
        workflow.set_entry_point("load_workflow")
        workflow.add_edge("load_workflow", "analyze_request")
        
        workflow.add_conditional_edges(
            "analyze_request",
            self._should_ask_questions,
            {"ask": "generate_questions", "proceed": "create_plan"}
        )
        
        workflow.add_edge("generate_questions", "collect_clarifications")
        # Interrupt at collect_clarifications if questions exist
        
        workflow.add_edge("collect_clarifications", "create_plan")
        workflow.add_edge("create_plan", "apply_modifications")
        workflow.add_edge("apply_modifications", "validate")
        workflow.add_edge("validate", "display")
        workflow.add_edge("display", END)
        
        return workflow.compile(checkpointer=self.checkpointer, interrupt_before=["collect_clarifications"])
