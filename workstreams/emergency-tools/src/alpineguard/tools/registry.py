"""
Tool registry: function declarations for Gemini and safe tool execution.

Architecture
------------
The registry holds the ``ToolSpec`` of every tool and is the only way agents run tools.
``declarations(role)`` returns the provider-neutral function declarations (name,
description, JSON schema) for one agent role. ``execute(name, arguments, role)``:
1. checks that the tool exists and that the role may call it,
2. validates and coerces the arguments against the JSON schema,
3. runs the handler with the shared ``ToolContext``,
4. for OPERATOR_APPROVES tools, sends the returned ``ProposedAction`` to the approval
   queue and returns only a pending-approval result (the effect has not happened),
5. writes every call to the audit trail with role, arguments, status and duration.
Errors are returned as error results so the model can correct its call.

Use cases
---------
1. Background agent: ``build_registry(ctx).declarations(AgentRole.BACKGROUND)`` for Gemini.
2. Voice agent (Phase 4): the same registry with ``AgentRole.VOICE`` gets five fast tools.
3. Tests call ``execute`` directly without a model.
"""

import time
from typing import Any, Dict, Iterable, List, Optional

from alpineguard.audit import logger
from alpineguard.models.approvals import ProposedAction
from alpineguard.models.audit import AuditEventKind
from alpineguard.models.domain import IncidentStatus
from alpineguard.models.tooling import AgentRole, ToolName, ToolResultStatus, ToolSpec, ToolTier
from alpineguard.tools.arguments import validate_arguments
from alpineguard.tools.context import ToolContext
from alpineguard.tools.results import ToolInputError, error


class ToolRegistry:
    """All tools of the agents, with validation, approval gate and audit."""

    def __init__(self, ctx: ToolContext, specs: Iterable[ToolSpec]) -> None:
        """
        Create the registry.

        Parameters:
            ctx: Shared tool context.
            specs: Tool specs; names must be unique.

        Raises:
            ValueError: If two specs have the same name.
        """
        self.ctx = ctx
        self._specs: Dict[ToolName, ToolSpec] = {}
        for spec in specs:
            if spec.name in self._specs:
                raise ValueError(f"Duplicate tool name '{spec.name.value}'")
            self._specs[spec.name] = spec

    def specs(self, role: Optional[AgentRole] = None) -> List[ToolSpec]:
        """
        Return tool specs, optionally only those a role may call.

        Parameters:
            role: Agent role, or None for all tools.

        Returns:
            Tool specs in registration order.
        """
        return [s for s in self._specs.values() if role is None or role in s.roles]

    def declarations(self, role: AgentRole) -> List[Dict[str, Any]]:
        """
        Return function declarations for one agent role.

        Parameters:
            role: Agent role.

        Returns:
            Declarations with "name", "description" and "parameters" (JSON schema).
        """
        return [s.declaration() for s in self.specs(role)]

    def execute(self, name: str, arguments: Optional[Dict[str, Any]], role: AgentRole) -> Dict[str, Any]:
        """
        Run one tool call from an agent.

        Parameters:
            name: Tool name sent by the model.
            arguments: Arguments sent by the model.
            role: Role of the calling agent.

        Returns:
            JSON-ready result with "status" "ok", "error" or "pending_approval".
        """
        started = time.perf_counter()
        raw_args = dict(arguments or {})
        coerced: Dict[str, Any] = {}
        try:
            tool_name = ToolName(name)
        except ValueError:
            result = error(f"Unknown tool '{name}'.")
            tool_name = None
        if tool_name is not None:
            spec = self._specs.get(tool_name)
            if spec is None:
                result = error(f"Tool '{name}' is not registered.")
            elif role not in spec.roles:
                result = error(f"Tool '{name}' is not available to the {role.value} agent.")
            else:
                coerced, problems = validate_arguments(spec.parameters, raw_args)
                if problems:
                    result = error("Invalid arguments: " + "; ".join(problems))
                else:
                    result = self._run(spec, coerced, role)

        self.ctx.audit.record(
            AuditEventKind.TOOL_CALL,
            actor=f"{role.value}_agent",
            name=name,
            details={
                "arguments": raw_args,
                "status": result.get("status"),
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "result": result,
            },
            reason=coerced.get("reason"),
            incident_id=coerced.get("incident_id"),
        )
        return result

    def _run(self, spec: ToolSpec, args: Dict[str, Any], role: AgentRole) -> Dict[str, Any]:
        try:
            if spec.tier == ToolTier.OPERATOR_APPROVES:
                proposal = spec.handler(self.ctx, **args)
                if not isinstance(proposal, ProposedAction):
                    raise TypeError(f"Approval tool '{spec.name.value}' must return a ProposedAction")
                action = self.ctx.approvals.submit(
                    tool_name=spec.name,
                    arguments=args,
                    reason=str(args.get("reason", "")),
                    requested_by=f"{role.value}_agent",
                    proposal=proposal,
                )
                incident = self.ctx.incidents.get(proposal.incident_id or "")
                if incident is not None and incident.status in (IncidentStatus.DETECTED, IncidentStatus.EVALUATING):
                    incident.status = IncidentStatus.AWAITING_APPROVAL
                return {
                    "status": ToolResultStatus.PENDING_APPROVAL.value,
                    "action_id": action.action_id,
                    "summary": action.summary,
                    "note": "Nothing has happened yet. The operator must approve this action.",
                }
            return spec.handler(self.ctx, **args)
        except ToolInputError as exc:
            return error(str(exc))
        except Exception as exc:  # a broken tool must not stop the agent; the error goes back to the model
            logger.exception("Tool %s failed", spec.name.value)
            return error(f"Tool failed: {type(exc).__name__}: {exc}")


def build_registry(ctx: ToolContext) -> ToolRegistry:
    """
    Create the registry with all core, cardiac arrest and forest fire tools.

    Parameters:
        ctx: Shared tool context.

    Returns:
        Registry with 20 tools.
    """
    from alpineguard.tools import cardiac_tools, core_tools, fire_tools

    return ToolRegistry(ctx, [*core_tools.specs(), *cardiac_tools.specs(), *fire_tools.specs()])
