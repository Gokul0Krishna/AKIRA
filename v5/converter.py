import json
import uuid
from typing import Dict, Any, List
from datetime import datetime

# ============================================================================
# CORRECTED POWER AUTOMATE REST API CONVERTER
# ============================================================================
# This generates the EXACT format Power Automate REST API expects

def generate_flow_definition_for_rest_api(master_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert master JSON to Power Automate Flow Definition
    This is the CORRECT format for the REST API
    
    REST API Endpoint:
    POST https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{environmentId}/flows
    """
    
    metadata = master_json.get("metadata", {})
    workflow = master_json.get("power_automate_workflow", {})
    form_schema = master_json.get("microsoft_forms", {})
    excel_schema = master_json.get("excel_tracker", {})
    approval_chain = master_json.get("workflow_analysis", {}).get("approval_chain", [])
    
    # Build connection references
    connection_refs = build_connection_references_rest_api(workflow)
    
    # Build the flow definition
    flow_definition = {
        "properties": {
            "displayName": metadata.get("workflow_name", "Generated Workflow"),
            "description": metadata.get("description", ""),
            "state": "Started",  # Started or Suspended
            "definition": {
                "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
                "contentVersion": "1.0.0.0",
                "parameters": {
                    "$connections": {
                        "defaultValue": {},
                        "type": "Object"
                    },
                    "$authentication": {
                        "defaultValue": {},
                        "type": "SecureObject"
                    }
                },
                "triggers": build_triggers_rest_api(workflow, form_schema),
                "actions": build_actions_rest_api(workflow, form_schema, excel_schema, approval_chain),
                "outputs": {}
            },
            "connectionReferences": connection_refs,
            "apiVersion": "2016-11-01"
        }
    }
    
    return flow_definition


def build_connection_references_rest_api(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build connection references in the format Power Automate expects
    """
    
    # Extract unique connectors from workflow steps
    connectors_used = set()
    
    for step in workflow.get("steps", []):
        connector = step.get("connector", "")
        if "Microsoft Forms" in connector:
            connectors_used.add("shared_microsoftforms")
        elif "Excel" in connector:
            connectors_used.add("shared_excelonlinebusiness")
        elif "Teams" in connector or "Approvals" in connector:
            connectors_used.add("shared_approvals")
        elif "Outlook" in connector:
            connectors_used.add("shared_office365")
    
    # Build connection references
    connection_refs = {}
    
    for connector_id in connectors_used:
        connection_refs[connector_id] = {
            "connection": {
                "id": f"/providers/Microsoft.PowerApps/apis/{connector_id}/connections/{{CONNECTION_ID_{connector_id.upper()}}}"
            },
            "api": {
                "id": f"/providers/Microsoft.PowerApps/apis/{connector_id}"
            },
            "connectionProperties": {}
        }
    
    return connection_refs


def build_triggers_rest_api(workflow: Dict[str, Any], form_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build trigger definition (Microsoft Forms trigger)
    """
    
    trigger_info = workflow.get("trigger", {})
    
    return {
        "When_a_new_response_is_submitted": {
            "type": "OpenApiConnection",
            "inputs": {
                "host": {
                    "apiId": "/providers/Microsoft.PowerApps/apis/shared_microsoftforms",
                    "connectionName": "shared_microsoftforms",
                    "operationId": "CreateFormWebhook"
                },
                "parameters": {
                    "form_id": "{FORM_ID_PLACEHOLDER}"
                },
                "authentication": "@parameters('$authentication')"
            },
            "metadata": {
                "operationMetadataId": str(uuid.uuid4())
            }
        }
    }


def build_actions_rest_api(
    workflow: Dict[str, Any],
    form_schema: Dict[str, Any],
    excel_schema: Dict[str, Any],
    approval_chain: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Build all workflow actions in Power Automate format
    """
    
    actions = {}
    previous_action = None
    action_counter = 1
    
    # Get form response details
    action_name = "Get_response_details"
    actions[action_name] = {
        "type": "OpenApiConnection",
        "inputs": {
            "host": {
                "apiId": "/providers/Microsoft.PowerApps/apis/shared_microsoftforms",
                "connectionName": "shared_microsoftforms",
                "operationId": "GetResponseById"
            },
            "parameters": {
                "form_id": "{FORM_ID_PLACEHOLDER}",
                "response_id": "@triggerBody()?['resourceData']?['responseId']"
            },
            "authentication": "@parameters('$authentication')"
        },
        "runAfter": {},
        "metadata": {
            "operationMetadataId": str(uuid.uuid4())
        }
    }
    previous_action = action_name
    action_counter += 1
    
    # Initialize variables
    action_name = "Initialize_SubmissionID"
    actions[action_name] = {
        "type": "InitializeVariable",
        "inputs": {
            "variables": [
                {
                    "name": "SubmissionID",
                    "type": "string",
                    "value": "@{guid()}"
                }
            ]
        },
        "runAfter": {
            previous_action: ["Succeeded"]
        },
        "metadata": {
            "operationMetadataId": str(uuid.uuid4())
        }
    }
    previous_action = action_name
    action_counter += 1
    
    # Add row to Excel
    action_name = "Add_row_to_Excel"
    
    # Build Excel row data from form fields
    excel_row = {
        "SubmissionID": "@variables('SubmissionID')",
        "SubmissionTimestamp": "@utcNow()",
        "CurrentStatus": "Submitted"
    }
    
    # Add form field values
    for question in form_schema.get("questions", [])[:5]:
        field_name = question.get("field_name", "")
        excel_row[field_name] = f"@{{body('Get_response_details')?['{question.get('id', '')}']?['response']}}"
    
    actions[action_name] = {
        "type": "OpenApiConnection",
        "inputs": {
            "host": {
                "apiId": "/providers/Microsoft.PowerApps/apis/shared_excelonlinebusiness",
                "connectionName": "shared_excelonlinebusiness",
                "operationId": "PostItem"
            },
            "parameters": {
                "source": "SharePoint",
                "drive": "{DRIVE_ID_PLACEHOLDER}",
                "file": "{FILE_ID_PLACEHOLDER}",
                "table": excel_schema.get("table_name", "{TABLE_NAME}"),
                "item": excel_row
            },
            "authentication": "@parameters('$authentication')"
        },
        "runAfter": {
            previous_action: ["Succeeded"]
        },
        "metadata": {
            "operationMetadataId": str(uuid.uuid4())
        }
    }
    previous_action = action_name
    action_counter += 1
    
    # Send confirmation email
    action_name = "Send_confirmation_email"
    actions[action_name] = {
        "type": "OpenApiConnection",
        "inputs": {
            "host": {
                "apiId": "/providers/Microsoft.PowerApps/apis/shared_office365",
                "connectionName": "shared_office365",
                "operationId": "SendEmailV2"
            },
            "parameters": {
                "emailMessage/To": "@body('Get_response_details')?['r2']?['response']",
                "emailMessage/Subject": f"{workflow.get('name', 'Workflow')} - Submission Received",
                "emailMessage/Body": "<p>Your request has been submitted successfully.</p>",
                "emailMessage/Importance": "Normal"
            },
            "authentication": "@parameters('$authentication')"
        },
        "runAfter": {
            previous_action: ["Succeeded"]
        },
        "metadata": {
            "operationMetadataId": str(uuid.uuid4())
        }
    }
    previous_action = action_name
    action_counter += 1
    
    # Build approval flow
    for approver in approval_chain:
        level = approver["level"]
        role = approver["approver_role"]
        role_sanitized = role.replace(" ", "_")
        
        # Start approval
        action_name = f"Approval_{role_sanitized}"
        
        # Get approver email from form
        approver_email_field = f"{role.lower().replace(' ', '_')}_email"
        
        actions[action_name] = {
            "type": "OpenApiConnection",
            "inputs": {
                "host": {
                    "apiId": "/providers/Microsoft.PowerApps/apis/shared_approvals",
                    "connectionName": "shared_approvals",
                    "operationId": "CreateApproval"
                },
                "parameters": {
                    "approvalType": "Approve/Reject - First to respond",
                    "WebhookApprovalCreationInput/title": f"Approval Required - Level {level}",
                    "WebhookApprovalCreationInput/assignedTo": f"@{{body('Get_response_details')?['r{find_question_index(form_schema, approver_email_field)}']?['response']}}",
                    "WebhookApprovalCreationInput/details": f"Please review and approve/reject this request.\n\nSubmission ID: @{{variables('SubmissionID')}}",
                    "WebhookApprovalCreationInput/itemLink": "",
                    "WebhookApprovalCreationInput/itemLinkDescription": "View Request",
                    "WebhookApprovalCreationInput/enableReassignment": False,
                    "WebhookApprovalCreationInput/enableComments": True
                },
                "authentication": "@parameters('$authentication')"
            },
            "runAfter": {
                previous_action: ["Succeeded"]
            },
            "metadata": {
                "operationMetadataId": str(uuid.uuid4())
            }
        }
        previous_action = action_name
        action_counter += 1
        
        # Update Excel with approval result
        action_name = f"Update_Excel_{role_sanitized}"
        actions[action_name] = {
            "type": "OpenApiConnection",
            "inputs": {
                "host": {
                    "apiId": "/providers/Microsoft.PowerApps/apis/shared_excelonlinebusiness",
                    "connectionName": "shared_excelonlinebusiness",
                    "operationId": "PatchItem"
                },
                "parameters": {
                    "source": "SharePoint",
                    "drive": "{DRIVE_ID_PLACEHOLDER}",
                    "file": "{FILE_ID_PLACEHOLDER}",
                    "table": excel_schema.get("table_name", "{TABLE_NAME}"),
                    "idColumn": "SubmissionID",
                    "id": "@variables('SubmissionID')",
                    "item": {
                        f"{role_sanitized}_Status": f"@{{body('Approval_{role_sanitized}')?['outcome']}}",
                        f"{role_sanitized}_Name": f"@{{body('Approval_{role_sanitized}')?['responder']?['displayName']}}",
                        f"{role_sanitized}_Timestamp": "@utcNow()",
                        f"{role_sanitized}_Comments": f"@{{body('Approval_{role_sanitized}')?['comments']}}"
                    }
                },
                "authentication": "@parameters('$authentication')"
            },
            "runAfter": {
                previous_action: ["Succeeded"]
            },
            "metadata": {
                "operationMetadataId": str(uuid.uuid4())
            }
        }
        previous_action = action_name
        action_counter += 1
        
        # Check if rejected
        action_name = f"Condition_Check_Rejection_{role_sanitized}"
        rejection_action_name = f"Send_Rejection_Email_{role_sanitized}"
        
        actions[action_name] = {
            "type": "If",
            "expression": {
                "equals": [
                    f"@body('Approval_{role_sanitized}')?['outcome']",
                    "Reject"
                ]
            },
            "actions": {
                rejection_action_name: {
                    "type": "OpenApiConnection",
                    "inputs": {
                        "host": {
                            "apiId": "/providers/Microsoft.PowerApps/apis/shared_office365",
                            "connectionName": "shared_office365",
                            "operationId": "SendEmailV2"
                        },
                        "parameters": {
                            "emailMessage/To": "@body('Get_response_details')?['r2']?['response']",
                            "emailMessage/Subject": "Request Rejected",
                            "emailMessage/Body": f"<p>Your request was rejected by {role}.</p>",
                            "emailMessage/Importance": "High"
                        },
                        "authentication": "@parameters('$authentication')"
                    },
                    "runAfter": {},
                    "metadata": {
                        "operationMetadataId": str(uuid.uuid4())
                    }
                },
                "Terminate": {
                    "type": "Terminate",
                    "inputs": {
                        "runStatus": "Cancelled"
                    },
                    "runAfter": {
                        rejection_action_name: ["Succeeded"]
                    }
                }
            },
            "runAfter": {
                previous_action: ["Succeeded"]
            },
            "metadata": {
                "operationMetadataId": str(uuid.uuid4())
            }
        }
        previous_action = action_name
        action_counter += 1
    
    # Final approval email
    action_name = "Send_final_approval_email"
    actions[action_name] = {
        "type": "OpenApiConnection",
        "inputs": {
            "host": {
                "apiId": "/providers/Microsoft.PowerApps/apis/shared_office365",
                "connectionName": "shared_office365",
                "operationId": "SendEmailV2"
            },
            "parameters": {
                "emailMessage/To": "@body('Get_response_details')?['r2']?['response']",
                "emailMessage/Subject": "Request Approved",
                "emailMessage/Body": "<p>Congratulations! Your request has been fully approved.</p>",
                "emailMessage/Importance": "High"
            },
            "authentication": "@parameters('$authentication')"
        },
        "runAfter": {
            previous_action: ["Succeeded"]
        },
        "metadata": {
            "operationMetadataId": str(uuid.uuid4())
        }
    }
    
    return actions


def find_question_index(form_schema: Dict[str, Any], field_name: str) -> int:
    """Find the question index (r1, r2, etc.) for a field"""
    for idx, question in enumerate(form_schema.get("questions", []), 1):
        if question.get("field_name") == field_name:
            return idx
    return 1


def save_flow_definition_for_api(master_json: Dict[str, Any], output_file: str = "flow_for_rest_api.json"):
    """
    Save the flow definition in the correct format for REST API
    """
    
    print("\n" + "="*80)
    print("🔄 GENERATING FLOW DEFINITION FOR POWER AUTOMATE REST API")
    print("="*80)
    
    flow_def = generate_flow_definition_for_rest_api(master_json)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(flow_def, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Flow definition saved: {output_file}")
    print("\n📋 DEPLOYMENT INSTRUCTIONS:")
    print("-"*80)
    print("1. This JSON is ready for the Power Automate REST API")
    print("2. Use the PowerAutomateRestClient class to deploy")
    print("3. Required placeholders to configure:")
    print("   • {FORM_ID_PLACEHOLDER}")
    print("   • {DRIVE_ID_PLACEHOLDER}")
    print("   • {FILE_ID_PLACEHOLDER}")
    print("   • {CONNECTION_ID_*}")
    print("\n" + "="*80)
    
    return output_file


# ============================================================================
# USAGE
# ============================================================================

if __name__ == "__main__":
    # Load master JSON from workflow generator
    with open("master_workflow.json", "r") as f:
        master_json = json.load(f)
    
    # Generate proper format for REST API
    output_file = save_flow_definition_for_api(master_json)
    
    print(f"\n✅ Ready for deployment via REST API!")
    print(f"📄 File: {output_file}")