"""
Shared state that all tool handlers receive.

Architecture
------------
``ToolContext`` bundles the simulated world (external systems), the approval queue, the
audit trail, the optional vision analyzer and the stores of things the tools create
during a run: incidents, spread forecasts, evacuation routes, public alert drafts and
media artifacts. The registry passes the same context to every handler, so tools can
refer to each other's results by id (for example ``plan_evacuation`` uses a
``forecast_id`` from ``predict_spread``).

Use cases
---------
1. One context per demo run or per operator session.
2. Tests create a context around a scenario and inspect its stores.
3. The operator console reads incidents, approvals and audit entries from it.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

from alpineguard.audit import AuditLog
from alpineguard.models.alerts import PublicAlertDraft
from alpineguard.models.domain import EvacuationRoute, Incident, MultimodalArtifact
from alpineguard.models.fire import SpreadForecast
from alpineguard.simulation.world import SimulatedWorld
from alpineguard.tools.approvals import ApprovalQueue
from alpineguard.tools.vision import GeminiVisionAnalyzer


@dataclass
class ToolContext:
    """State shared by all tool handlers during one session."""

    world: SimulatedWorld
    audit: AuditLog
    approvals: ApprovalQueue
    vision: Optional[GeminiVisionAnalyzer] = None
    incidents: Dict[str, Incident] = field(default_factory=dict)
    forecasts: Dict[str, SpreadForecast] = field(default_factory=dict)
    routes: Dict[str, EvacuationRoute] = field(default_factory=dict)
    route_forecast_ids: Dict[str, str] = field(default_factory=dict)
    alerts: Dict[str, PublicAlertDraft] = field(default_factory=dict)
    artifacts: Dict[str, MultimodalArtifact] = field(default_factory=dict)

    @classmethod
    def for_world(cls, world: SimulatedWorld, vision: Optional[GeminiVisionAnalyzer] = None) -> "ToolContext":
        """
        Create a context with a new audit trail and approval queue.

        Parameters:
            world: Simulated world of the scenario.
            vision: Vision analyzer for frames with image files, or None for scripted frames only.

        Returns:
            New tool context.
        """
        audit = AuditLog()
        return cls(world=world, audit=audit, approvals=ApprovalQueue(audit), vision=vision)
