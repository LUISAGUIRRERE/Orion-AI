"""Unit tests for the new ORION Core Domain Skeleton."""

from __future__ import annotations

import unittest

from orion.core.organization import Organization
from orion.core.role import ProfessionalRole
from orion.core.department import Department
from orion.core.capability import Capability
from orion.core.decision import BusinessDecision
from orion.core.meeting import Meeting
from orion.core.opportunity import Opportunity
from orion.core.memory import MemoryLedger
from orion.core.knowledge import KnowledgeFact
from orion.core.goal import BusinessGoal


class TestCoreSkeleton(unittest.TestCase):
    def test_organization_instantiation(self) -> None:
        org = Organization(id="atman", name="ATMAN", industry="B2B SaaS", vision="Autonomous tech", website="https://atman.me")
        self.assertEqual(org.id, "atman")
        self.assertEqual(org.name, "ATMAN")
        self.assertEqual(org.industry, "B2B SaaS")
        self.assertEqual(org.vision, "Autonomous tech")
        self.assertEqual(org.website, "https://atman.me")
        self.assertEqual(org.metadata, {})

    def test_role_instantiation(self) -> None:
        role = ProfessionalRole(
            id="cmo",
            title="Chief Marketing Officer",
            status="active",
            responsibilities=["Acquisition"],
            restrictions=["Budget ceiling"],
            department_id="marketing"
        )
        self.assertEqual(role.id, "cmo")
        self.assertEqual(role.title, "Chief Marketing Officer")
        self.assertEqual(role.status, "active")
        self.assertEqual(role.responsibilities, ["Acquisition"])
        self.assertEqual(role.restrictions, ["Budget ceiling"])
        self.assertEqual(role.department_id, "marketing")

    def test_department_instantiation(self) -> None:
        dept = Department(id="seo", name="SEO Department", purpose="Optimize visibility", executive_owner_id="cmo")
        self.assertEqual(dept.id, "seo")
        self.assertEqual(dept.name, "SEO Department")
        self.assertEqual(dept.purpose, "Optimize visibility")
        self.assertEqual(dept.executive_owner_id, "cmo")

    def test_capability_instantiation(self) -> None:
        cap = Capability(
            id="tech_audit",
            goal="Scan sitemaps",
            department_id="seo",
            required_inputs=["URL"],
            expected_outputs=["Audit JSON"],
            estimated_cost_dollars=0.05,
            estimated_duration_seconds=45
        )
        self.assertEqual(cap.id, "tech_audit")
        self.assertEqual(cap.goal, "Scan sitemaps")
        self.assertEqual(cap.department_id, "seo")
        self.assertEqual(cap.required_inputs, ["URL"])
        self.assertEqual(cap.expected_outputs, ["Audit JSON"])
        self.assertEqual(cap.estimated_cost_dollars, 0.05)
        self.assertEqual(cap.estimated_duration_seconds, 45)

    def test_decision_instantiation(self) -> None:
        dec = BusinessDecision(
            id="DEC-001",
            title="Deploy automatic blog",
            status="accepted",
            author_role_id="cmo",
            risk_level="medium",
            estimated_roi=3.5,
            rationale="High traffic gain",
            consequences="Increased hosting load"
        )
        self.assertEqual(dec.id, "DEC-001")
        self.assertEqual(dec.title, "Deploy automatic blog")
        self.assertEqual(dec.status, "accepted")
        self.assertEqual(dec.author_role_id, "cmo")
        self.assertEqual(dec.risk_level, "medium")
        self.assertEqual(dec.estimated_roi, 3.5)
        self.assertEqual(dec.rationale, "High traffic gain")
        self.assertEqual(dec.consequences, "Increased hosting load")

    def test_decision_superseded_validation(self) -> None:
        # Should instantiate fine when not superseded or when superseded with superseded_by_id
        dec1 = BusinessDecision(
            id="DEC-001",
            title="Deploy automatic blog",
            status="superseded",
            author_role_id="cmo",
            rationale="High traffic gain",
            superseded_by_id="DEC-002"
        )
        self.assertEqual(dec1.status, "superseded")
        self.assertEqual(dec1.superseded_by_id, "DEC-002")

        # Raising ValueError when status is superseded but no superseded_by_id is provided
        with self.assertRaises(ValueError):
            BusinessDecision(
                id="DEC-001",
                title="Deploy automatic blog",
                status="superseded",
                author_role_id="cmo",
                rationale="High traffic gain"
            )

    def test_meeting_instantiation(self) -> None:
        meet = Meeting(
            id="MEET-001",
            title="Sprint Planning",
            participants=["cmo", "cto"],
            agenda=["Goals", "Budget"],
            date_iso="2026-07-21",
            minutes="Decided on $500 blog pilot"
        )
        self.assertEqual(meet.id, "MEET-001")
        self.assertEqual(meet.title, "Sprint Planning")
        self.assertEqual(meet.participants, ["cmo", "cto"])
        self.assertEqual(meet.agenda, ["Goals", "Budget"])
        self.assertEqual(meet.date_iso, "2026-07-21")
        self.assertEqual(meet.minutes, "Decided on $500 blog pilot")

    def test_opportunity_strategic_score(self) -> None:
        opp = Opportunity(
            id="OPP-001",
            title="Niche Blog",
            business_value=9.0,
            risk=2.0,
            cost=100.0,
            urgency=1.0,
            confidence=0.8
        )
        self.assertEqual(opp.id, "OPP-001")
        self.assertEqual(opp.title, "Niche Blog")
        self.assertEqual(opp.business_value, 9.0)
        self.assertEqual(opp.risk, 2.0)
        self.assertEqual(opp.cost, 100.0)
        self.assertEqual(opp.urgency, 1.0)
        self.assertEqual(opp.confidence, 0.8)

        # Score = (Value * ROI * Confidence - Risk) / (Cost * Urgency)
        # ROI = 9.0 / 100 = 0.09
        # Numerator = (9.0 * 0.09 * 0.8) - 2.0 = 0.648 - 2.0 = -1.352
        # Denominator = 100.0 * 1.0 = 100.0
        # Expected Score = -1.352 / 100.0 = -0.014
        self.assertEqual(opp.strategic_score(), -0.014)

    def test_memory_ledger_instantiation(self) -> None:
        ledger = MemoryLedger(
            organization_id="atman",
            competitor_profiles={"competitor1": "poor SEO"},
            brand_guidelines_path="guidelines/atman.md",
            successful_campaigns=["CAMP-01"],
            failed_campaigns=["CAMP-02"],
            business_rules=["Always validate SEO"]
        )
        self.assertEqual(ledger.organization_id, "atman")
        self.assertEqual(ledger.competitor_profiles, {"competitor1": "poor SEO"})
        self.assertEqual(ledger.brand_guidelines_path, "guidelines/atman.md")
        self.assertEqual(ledger.successful_campaigns, ["CAMP-01"])
        self.assertEqual(ledger.failed_campaigns, ["CAMP-02"])
        self.assertEqual(ledger.business_rules, ["Always validate SEO"])

    def test_knowledge_fact_instantiation(self) -> None:
        fact = KnowledgeFact(
            id="FACT-01",
            category="SEO",
            fact="Backlinks drive indexing",
            confidence_score=0.95,
            source_mission_id="MISS-101"
        )
        self.assertEqual(fact.id, "FACT-01")
        self.assertEqual(fact.category, "SEO")
        self.assertEqual(fact.fact, "Backlinks drive indexing")
        self.assertEqual(fact.confidence_score, 0.95)
        self.assertEqual(fact.source_mission_id, "MISS-101")

    def test_goal_instantiation(self) -> None:
        goal = BusinessGoal(
            id="GOAL-01",
            title="Launch MVP",
            status="not_started",
            progress_percentage=45.0,
            parent_goal_id=None
        )
        self.assertEqual(goal.id, "GOAL-01")
        self.assertEqual(goal.title, "Launch MVP")
        self.assertEqual(goal.status, "not_started")
        self.assertEqual(goal.progress_percentage, 45.0)
        self.assertIsNone(goal.parent_goal_id)

    def test_goal_progress_auto_completed_validation(self) -> None:
        # Progress 45.0 should keep status "not_started" or "in_progress"
        goal1 = BusinessGoal(
            id="GOAL-01",
            title="Launch MVP",
            status="in_progress",
            progress_percentage=45.0
        )
        self.assertEqual(goal1.status, "in_progress")

        # Progress >= 100.0 must auto-resolve status to "completed"
        goal2 = BusinessGoal(
            id="GOAL-01",
            title="Launch MVP",
            status="in_progress",
            progress_percentage=100.0
        )
        self.assertEqual(goal2.status, "completed")

        goal3 = BusinessGoal(
            id="GOAL-01",
            title="Launch MVP",
            status="not_started",
            progress_percentage=120.0
        )
        self.assertEqual(goal3.status, "completed")


if __name__ == "__main__":
    unittest.main()
