"""Tests for orion.governance (BETA 010: Autonomous Development Engine).

Standard library unittest only (no pytest, no new dependency), same
convention as every other test module in this repo. Covers the
Change Classifier (all eight categories), Risk Engine (LOW/MEDIUM/
HIGH/CRITICAL, category floors, honest no-data handling, historial),
Confidence Engine (including regression coverage for the real
stopword-overlap false-positive bug found during development),
Execution Mode (the four official modes + persistence), the Policy
Engine (the four worked validation scenarios this Sprint's own brief
specifies), the Decision Engine (the five explicit questions),
Approval Engine, Audit, Rollback (real git, via a disposable clone --
never the real working tree), services.py orchestration, the CLI,
the API, and Runtime integration (the real hard_stop gate).

Run with:

    python3 -m unittest tests.test_governance -v
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orion.governance import (
    approval_engine,
    audit,
    autonomy,
    confidence_engine,
    decision_engine,
    execution_mode,
    policy_engine,
    risk_engine,
    rollback,
    services as governance_services,
    storage,
)
from orion.governance.change_classifier import ChangeCategory, classify_change
from orion.intelligence.impact_analyzer import ImpactReport

REPO_ROOT = Path(__file__).resolve().parent.parent


class IsolatedGovernanceTestCase(unittest.TestCase):
    """Redirects orion.governance.storage's persistence directory at a
    temp path for the duration of each test -- never touches
    Orion-AI's real workspace/governance/."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_dir = storage.GOVERNANCE_DIR
        storage.GOVERNANCE_DIR = Path(self._tmp.name)

    def tearDown(self) -> None:
        storage.GOVERNANCE_DIR = self._orig_dir
        self._tmp.cleanup()


class ChangeClassifierTests(unittest.TestCase):
    def test_all_eight_categories_classify_correctly_on_real_examples(self) -> None:
        cases = {
            "Arregla el bug de login que falla intermitentemente": ChangeCategory.BUG_FIX,
            "Elimina el endpoint viejo, rompe compatibilidad con clientes antiguos": ChangeCategory.BREAKING_CHANGE,
            "Rediseña la arquitectura del modulo de pagos, cambia el stack a microservicios": ChangeCategory.ARCHITECTURE,
            "Construye la pagina de Cursos": ChangeCategory.FEATURE,
            "Optimiza el rendimiento de la consulta de productos, es muy lenta": ChangeCategory.OPTIMIZATION,
            "Refactoriza el modulo de usuarios, hay mucho codigo duplicado": ChangeCategory.REFACTOR,
            "Documenta el modulo de intelligence en el README": ChangeCategory.DOCUMENTATION,
            "Configura el pipeline de CI/CD y el Dockerfile para el despliegue": ChangeCategory.INFRASTRUCTURE,
        }
        for text, expected in cases.items():
            self.assertEqual(classify_change(text).category, expected, text)

    def test_no_signal_falls_back_to_feature_not_a_fabricated_default(self) -> None:
        result = classify_change("hola que tal")
        self.assertEqual(result.category, ChangeCategory.FEATURE)
        self.assertEqual(result.matched_keywords, [])


class RiskEngineTests(unittest.TestCase):
    def _impact(self, files=1, modules=1, tests=("t",), complexity=5, risk="bajo") -> ImpactReport:
        return ImpactReport(
            target_paths=["a.py"],
            affected_modules=[f"m{i}" for i in range(modules)],
            affected_files=[f"f{i}.py" for i in range(files)],
            related_tests=list(tests),
            complexity_sum=complexity,
            risk=risk,
        )

    def test_low_impact_bug_fix_is_low_risk(self) -> None:
        result = risk_engine.assess_risk(ChangeCategory.BUG_FIX, self._impact())
        self.assertEqual(result.level, risk_engine.RiskLevel.LOW)

    def test_wide_impact_is_escalated(self) -> None:
        impact = self._impact(files=15, modules=15, tests=(), complexity=80, risk="alto")
        result = risk_engine.assess_risk(ChangeCategory.FEATURE, impact)
        self.assertEqual(result.level, risk_engine.RiskLevel.CRITICAL)

    def test_no_impact_data_is_never_low(self) -> None:
        result = risk_engine.assess_risk(ChangeCategory.FEATURE, None)
        self.assertEqual(result.level, risk_engine.RiskLevel.MEDIUM)
        self.assertFalse(result.impact_available)

    def test_breaking_change_always_critical_regardless_of_impact(self) -> None:
        result = risk_engine.assess_risk(ChangeCategory.BREAKING_CHANGE, self._impact())
        self.assertEqual(result.level, risk_engine.RiskLevel.CRITICAL)

    def test_architecture_always_at_least_high(self) -> None:
        result = risk_engine.assess_risk(ChangeCategory.ARCHITECTURE, self._impact())
        self.assertEqual(result.level, risk_engine.RiskLevel.HIGH)

    def test_good_history_lowers_risk_bad_history_raises_it(self) -> None:
        good = risk_engine.assess_risk(ChangeCategory.BUG_FIX, self._impact(), history_success_count=5)
        bad = risk_engine.assess_risk(ChangeCategory.BUG_FIX, self._impact(), history_failure_count=2)
        self.assertLessEqual(good.points, bad.points)


class ConfidenceEngineTests(unittest.TestCase):
    def test_similarity_never_matches_on_stopwords_alone(self) -> None:
        """Regression test for a real bug found via smoke-testing this
        Sprint: naive token overlap without stopword filtering matched
        'el bug de login' against unrelated Knowledge Store items
        purely because both strings contained 'el'/'de'. Fixed via
        confidence_engine._significant_tokens(). This test uses real
        KnowledgeItem objects that share only stopwords with the
        request and asserts zero are considered similar."""
        from orion.experience.models import KnowledgeItem, KnowledgeItemType

        items = [
            KnowledgeItem(
                id="1", type=KnowledgeItemType.LESSON,
                title="Riesgo detectado ejecutando misiones de tipo executor",
                description="No se encontro documentacion de arquitectura para este proyecto",
                source_mission_id="m1", confidence=0.9, created_at="2026-01-01",
            ),
        ]
        result = confidence_engine.assess_confidence(
            "Arregla el bug de login", None, risk_engine.RiskLevel.MEDIUM, knowledge_items=items
        )
        self.assertEqual(result.similar_items_found, 0)

    def test_real_keyword_overlap_is_detected(self) -> None:
        from orion.experience.models import KnowledgeItem, KnowledgeItemType

        items = [
            KnowledgeItem(
                id="1", type=KnowledgeItemType.LESSON, title="Bug de login corregido",
                description="se arreglo el bug de login intermitente", source_mission_id="m1",
                confidence=0.9, created_at="2026-01-01",
            ),
        ]
        result = confidence_engine.assess_confidence(
            "Arregla el bug de login otra vez", None, risk_engine.RiskLevel.LOW, knowledge_items=items
        )
        self.assertEqual(result.similar_items_found, 1)

    def test_score_is_always_within_bounds(self) -> None:
        result = confidence_engine.assess_confidence("cualquier cosa", None, risk_engine.RiskLevel.CRITICAL, knowledge_items=[])
        self.assertGreaterEqual(result.score, 0.0)
        self.assertLessEqual(result.score, 1.0)


class ExecutionModeTests(IsolatedGovernanceTestCase):
    def test_default_mode_is_development(self) -> None:
        self.assertEqual(execution_mode.get_mode(), execution_mode.MODE_DEVELOPMENT)

    def test_set_mode_persists_and_is_audited_in_history(self) -> None:
        execution_mode.set_mode(execution_mode.MODE_HARDENING, author="Louis", reason="test")
        self.assertEqual(execution_mode.get_mode(), execution_mode.MODE_HARDENING)
        history = execution_mode.get_mode_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["mode"], execution_mode.MODE_HARDENING)
        self.assertEqual(history[0]["previous_mode"], execution_mode.MODE_DEVELOPMENT)

    def test_unknown_mode_raises(self) -> None:
        with self.assertRaises(ValueError):
            execution_mode.set_mode("MODE_INVENTADO")


class PolicyEngineValidationScenarioTests(unittest.TestCase):
    """The exact four validation scenarios this Sprint's own brief
    specifies (VALIDACION: Caso 1-4)."""

    def _risk(self, level):
        return risk_engine.RiskAssessment(level=level, points=0, factors={})

    def _conf(self, score):
        return confidence_engine.ConfidenceAssessment(score=score, factors={})

    def test_caso1_bug_pequeno_corrige_crea_test_continua(self) -> None:
        hardening = execution_mode.get_profile(execution_mode.MODE_HARDENING)
        outcome = policy_engine.evaluate_policy(
            ChangeCategory.BUG_FIX, self._risk(risk_engine.RiskLevel.LOW), self._conf(0.97), hardening
        )
        self.assertEqual(outcome.action, policy_engine.PolicyAction.AUTO_APPLY_AND_CONTINUE)
        self.assertTrue(outcome.create_test)
        self.assertTrue(outcome.run_suite)
        self.assertTrue(outcome.continue_after)

    def test_caso2_breaking_change_detiene_solicita_aprobacion(self) -> None:
        hardening = execution_mode.get_profile(execution_mode.MODE_HARDENING)
        outcome = policy_engine.evaluate_policy(
            ChangeCategory.BREAKING_CHANGE, self._risk(risk_engine.RiskLevel.LOW), self._conf(0.99), hardening
        )
        decision = decision_engine.decide(outcome, self._risk(risk_engine.RiskLevel.LOW))
        self.assertEqual(outcome.action, policy_engine.PolicyAction.STOP_REQUEST_APPROVAL)
        self.assertTrue(decision.needs_approval)
        self.assertTrue(decision.should_stop)
        self.assertTrue(decision.hard_stop)

    def test_caso3_refactor_seguro_continua(self) -> None:
        hardening = execution_mode.get_profile(execution_mode.MODE_HARDENING)
        outcome = policy_engine.evaluate_policy(
            ChangeCategory.REFACTOR, self._risk(risk_engine.RiskLevel.LOW), self._conf(0.8), hardening
        )
        decision = decision_engine.decide(outcome, self._risk(risk_engine.RiskLevel.LOW))
        self.assertFalse(decision.should_stop)
        self.assertTrue(decision.can_resolve_alone)

    def test_caso4_arquitectura_espera_decision_humana(self) -> None:
        hardening = execution_mode.get_profile(execution_mode.MODE_HARDENING)
        outcome = policy_engine.evaluate_policy(
            ChangeCategory.ARCHITECTURE, self._risk(risk_engine.RiskLevel.LOW), self._conf(0.99), hardening
        )
        decision = decision_engine.decide(outcome, self._risk(risk_engine.RiskLevel.LOW))
        self.assertEqual(outcome.action, policy_engine.PolicyAction.STOP_HUMAN_DECISION)
        self.assertTrue(decision.should_stop)
        self.assertTrue(decision.hard_stop)
        self.assertEqual(outcome.decision_type, "human_decision")

    def test_mode_development_asks_about_everything_but_is_not_a_hard_stop(self) -> None:
        """MODE_DEVELOPMENT's blanket 'pregunta todo' posture is a real,
        audited decision (needs_approval=True) but must never be
        confused with a hard, per-change safety stop -- see
        PolicyOutcome.hard_stop's own docstring for why the Runtime
        integration relies on exactly this distinction."""
        development = execution_mode.get_profile(execution_mode.MODE_DEVELOPMENT)
        outcome = policy_engine.evaluate_policy(
            ChangeCategory.BUG_FIX, self._risk(risk_engine.RiskLevel.LOW), self._conf(0.99), development
        )
        decision = decision_engine.decide(outcome, self._risk(risk_engine.RiskLevel.LOW))
        self.assertTrue(decision.should_stop)
        self.assertFalse(decision.hard_stop)

    def test_critical_risk_always_stops_regardless_of_category(self) -> None:
        hardening = execution_mode.get_profile(execution_mode.MODE_HARDENING)
        outcome = policy_engine.evaluate_policy(
            ChangeCategory.BUG_FIX, self._risk(risk_engine.RiskLevel.CRITICAL), self._conf(0.99), hardening
        )
        self.assertEqual(outcome.action, policy_engine.PolicyAction.STOP_REQUEST_APPROVAL)
        self.assertTrue(outcome.hard_stop)


class DecisionEngineTests(unittest.TestCase):
    def test_wide_high_risk_that_continues_is_flagged_for_split(self) -> None:
        hardening = execution_mode.get_profile(execution_mode.MODE_HARDENING)
        risk = risk_engine.RiskAssessment(
            level=risk_engine.RiskLevel.HIGH, points=4,
            factors={"archivos_afectados": 2, "dependencias": 2, "cobertura_de_pruebas": 0, "complejidad": 1, "historial": 0, "impacto": 1},
        )
        conf = confidence_engine.ConfidenceAssessment(score=0.65, factors={})
        outcome = policy_engine.evaluate_policy(ChangeCategory.OPTIMIZATION, risk, conf, hardening)
        decision = decision_engine.decide(outcome, risk)
        self.assertFalse(decision.should_stop)
        self.assertTrue(decision.should_split_mission)


class AutonomyTests(unittest.TestCase):
    def test_architecture_and_breaking_change_never_act_autonomously(self) -> None:
        release = execution_mode.get_profile(execution_mode.MODE_RELEASE)
        self.assertFalse(autonomy.can_act_autonomously(release, ChangeCategory.ARCHITECTURE))
        self.assertFalse(autonomy.can_act_autonomously(release, ChangeCategory.BREAKING_CHANGE))

    def test_development_mode_never_acts_autonomously_for_anything(self) -> None:
        development = execution_mode.get_profile(execution_mode.MODE_DEVELOPMENT)
        for category in ChangeCategory:
            self.assertFalse(autonomy.can_act_autonomously(development, category))


class ApprovalEngineTests(IsolatedGovernanceTestCase):
    def test_request_then_approve(self) -> None:
        hardening = execution_mode.get_profile(execution_mode.MODE_HARDENING)
        risk = risk_engine.RiskAssessment(level=risk_engine.RiskLevel.CRITICAL, points=0, factors={})
        conf = confidence_engine.ConfidenceAssessment(score=0.9, factors={})
        outcome = policy_engine.evaluate_policy(ChangeCategory.BUG_FIX, risk, conf, hardening)
        decision = decision_engine.decide(outcome, risk)

        req = approval_engine.request_approval("M-1", "algo riesgoso", ChangeCategory.BUG_FIX.value, "CRITICAL", 0.9, decision)
        self.assertEqual(len(approval_engine.list_pending()), 1)

        approved = approval_engine.approve(req.id, "Louis", notes="ok")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(len(approval_engine.list_pending()), 0)

    def test_reject(self) -> None:
        hardening = execution_mode.get_profile(execution_mode.MODE_HARDENING)
        risk = risk_engine.RiskAssessment(level=risk_engine.RiskLevel.CRITICAL, points=0, factors={})
        conf = confidence_engine.ConfidenceAssessment(score=0.9, factors={})
        outcome = policy_engine.evaluate_policy(ChangeCategory.BUG_FIX, risk, conf, hardening)
        decision = decision_engine.decide(outcome, risk)
        req = approval_engine.request_approval("M-2", "algo riesgoso", ChangeCategory.BUG_FIX.value, "CRITICAL", 0.9, decision)
        rejected = approval_engine.reject(req.id, "Louis", notes="no")
        self.assertEqual(rejected["status"], "rejected")

    def test_unknown_request_id_returns_none(self) -> None:
        self.assertIsNone(approval_engine.approve("no-existe", "Louis"))


class AuditTests(IsolatedGovernanceTestCase):
    def test_record_and_close_outcome_feeds_historial(self) -> None:
        hardening = execution_mode.get_profile(execution_mode.MODE_HARDENING)
        risk = risk_engine.RiskAssessment(level=risk_engine.RiskLevel.LOW, points=0, factors={})
        conf = confidence_engine.ConfidenceAssessment(score=0.97, factors={})
        outcome = policy_engine.evaluate_policy(ChangeCategory.BUG_FIX, risk, conf, hardening)
        decision = decision_engine.decide(outcome, risk)

        entry = audit.record_decision("M-1", "Arregla el bug", ChangeCategory.BUG_FIX, risk, conf, decision, hardening.mode)
        self.assertEqual(entry.result, "pending")

        audit.record_outcome(entry.id, "success")
        success, failure = audit.count_outcomes_by_category(ChangeCategory.BUG_FIX)
        self.assertEqual((success, failure), (1, 0))

    def test_pending_entries_never_count_as_historial(self) -> None:
        hardening = execution_mode.get_profile(execution_mode.MODE_HARDENING)
        risk = risk_engine.RiskAssessment(level=risk_engine.RiskLevel.LOW, points=0, factors={})
        conf = confidence_engine.ConfidenceAssessment(score=0.97, factors={})
        outcome = policy_engine.evaluate_policy(ChangeCategory.REFACTOR, risk, conf, hardening)
        decision = decision_engine.decide(outcome, risk)
        audit.record_decision("M-2", "Refactoriza algo", ChangeCategory.REFACTOR, risk, conf, decision, hardening.mode)
        success, failure = audit.count_outcomes_by_category(ChangeCategory.REFACTOR)
        self.assertEqual((success, failure), (0, 0))


class RollbackTests(unittest.TestCase):
    """Real git operations against a disposable clone -- never the
    real working tree, same sandbox-clone discipline established
    throughout this repo's own test history for anything that
    genuinely touches git."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        subprocess.run(["git", "clone", "--quiet", str(REPO_ROOT), str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@orion.local"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Orion Test"], check=True)

        self._gov_tmp = tempfile.TemporaryDirectory()
        self._orig_dir = storage.GOVERNANCE_DIR
        storage.GOVERNANCE_DIR = Path(self._gov_tmp.name)

    def tearDown(self) -> None:
        storage.GOVERNANCE_DIR = self._orig_dir
        self._gov_tmp.cleanup()
        self._tmp.cleanup()

    def test_unmerged_mission_branch_is_safely_abandoned(self) -> None:
        subprocess.run(["git", "-C", str(self.repo), "checkout", "-q", "-b", "mission/TEST-ROLLBACK-1"], check=True)
        (self.repo / "ROLLBACK_TEST.md").write_text("test change\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "-m", "test commit"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "checkout", "-q", "main"], check=True)

        result = rollback.rollback_mission("TEST-ROLLBACK-1", "mission/TEST-ROLLBACK-1", repo_root=self.repo)
        self.assertTrue(result.rolled_back)

        branches = subprocess.run(
            ["git", "-C", str(self.repo), "branch"], capture_output=True, text=True, check=True
        ).stdout
        self.assertNotIn("mission/TEST-ROLLBACK-1", branches)

    def test_already_merged_branch_is_never_force_reverted(self) -> None:
        subprocess.run(["git", "-C", str(self.repo), "checkout", "-q", "-b", "mission/TEST-ROLLBACK-2"], check=True)
        (self.repo / "MERGED_TEST.md").write_text("merged change\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "-m", "test commit"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "checkout", "-q", "main"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "merge", "-q", "mission/TEST-ROLLBACK-2", "--no-edit"], check=True)

        result = rollback.rollback_mission("TEST-ROLLBACK-2", "mission/TEST-ROLLBACK-2", repo_root=self.repo)
        self.assertFalse(result.rolled_back)

        branches = subprocess.run(
            ["git", "-C", str(self.repo), "branch"], capture_output=True, text=True, check=True
        ).stdout
        self.assertIn("mission/TEST-ROLLBACK-2", branches)


class ServicesTests(IsolatedGovernanceTestCase):
    def test_evaluate_change_records_audit_and_returns_real_evaluation(self) -> None:
        governance_services.set_mode(execution_mode.MODE_HARDENING, author="Louis", reason="test")
        impact = ImpactReport(
            target_paths=["a.py"], affected_modules=["a"], affected_files=["a.py"],
            related_tests=["tests/test_a.py"], complexity_sum=5, risk="bajo",
        )
        evaluation = governance_services.evaluate_change("Arregla el bug de login", impact=impact)
        self.assertEqual(evaluation.classification.category, ChangeCategory.BUG_FIX)
        entries = governance_services.list_audit()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], evaluation.audit_entry_id)

    def test_breaking_change_opens_a_real_approval_request(self) -> None:
        governance_services.set_mode(execution_mode.MODE_HARDENING, author="Louis", reason="test")
        evaluation = governance_services.evaluate_change("Elimina el endpoint viejo, rompe compatibilidad")
        self.assertIsNotNone(evaluation.approval_request_id)
        pending = governance_services.list_pending_approvals()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], evaluation.approval_request_id)

    def test_describe_policies_returns_real_rule_descriptions(self) -> None:
        policies = governance_services.describe_policies()
        self.assertGreater(len(policies), 0)
        self.assertTrue(all("rule" in p for p in policies))


class CLITests(unittest.TestCase):
    """Real subprocess invocations of bin/orion, isolated at a temp
    ORION_GOVERNANCE_WORKSPACE."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ)
        self.env["ORION_GOVERNANCE_WORKSPACE"] = str(Path(self._tmp.name) / "governance")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "orion"), *args],
            cwd=str(REPO_ROOT), env=self.env, capture_output=True, text=True, timeout=60,
        )

    def test_mode_show_and_set(self) -> None:
        shown = self._run("mode")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("MODE_DEVELOPMENT", shown.stdout)

        updated = self._run("mode", "--set", "MODE_HARDENING", "--author", "Louis", "--reason", "test")
        self.assertEqual(updated.returncode, 0, updated.stderr)
        self.assertIn("MODE_HARDENING", updated.stdout)

    def test_policy_lists_rules(self) -> None:
        result = self._run("policy")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Architecture", result.stdout)

    def test_risk_and_confidence_and_audit_run_without_crashing(self) -> None:
        for args in (["risk", "Arregla el bug"], ["confidence", "Arregla el bug"], ["audit"]):
            result = self._run(*args)
            self.assertEqual(result.returncode, 0, f"{args}: {result.stderr}")

    def test_approve_list_and_resolve(self) -> None:
        self._run("mode", "--set", "MODE_HARDENING")
        self._run("risk", "Elimina el endpoint viejo, rompe compatibilidad")
        listed = self._run("approve", "--list")
        self.assertEqual(listed.returncode, 0, listed.stderr)

    def test_mode_set_invalid_returns_nonzero(self) -> None:
        result = self._run("mode", "--set", "MODE_INVENTADO")
        self.assertNotEqual(result.returncode, 0)


class APIRouteTests(IsolatedGovernanceTestCase):
    """orion.governance.routes coroutines invoked directly (no
    TestClient/httpx2 dependency -- same technique
    tests/test_business.py::APIRouteTests already established)."""

    def test_policies_and_mode_routes(self) -> None:
        from orion.governance import routes as governance_routes

        policies = governance_routes.get_policies()
        self.assertGreater(len(policies), 0)

        mode = governance_routes.get_mode()
        self.assertEqual(mode["mode"], execution_mode.MODE_DEVELOPMENT)

        updated = governance_routes.post_mode(governance_routes.ModeRequest(mode="MODE_HARDENING", author="Louis"))
        self.assertEqual(updated["mode"], "MODE_HARDENING")

    def test_invalid_mode_raises_400(self) -> None:
        from fastapi import HTTPException

        from orion.governance import routes as governance_routes

        with self.assertRaises(HTTPException) as ctx:
            governance_routes.post_mode(governance_routes.ModeRequest(mode="MODE_INVENTADO"))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_approve_route_404_for_unknown_request(self) -> None:
        from fastapi import HTTPException

        from orion.governance import routes as governance_routes

        with self.assertRaises(HTTPException) as ctx:
            governance_routes.post_approve(governance_routes.ApproveRequest(request_id="no-existe"))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_risk_and_audit_routes(self) -> None:
        from orion.governance import routes as governance_routes

        governance_routes.post_mode(governance_routes.ModeRequest(mode="MODE_HARDENING"))
        risk = governance_routes.get_risk(request="Arregla el bug de login")
        self.assertIn(risk["level"], ("LOW", "MEDIUM", "HIGH", "CRITICAL"))
        entries = governance_routes.get_audit()
        self.assertEqual(len(entries), 1)


class RuntimeIntegrationTests(unittest.TestCase):
    """Real orion.agents.builder.agent.run_claimed_mission() Mission
    Flow integration: a hard_stop Decision (Architecture/Breaking
    Change/CRITICAL risk) must park the Mission at MissionStatus.WAITING
    *before* the Pipeline ever runs (never touching git), while an
    ordinary Mission proceeds exactly as it did before this Sprint.
    Reuses tests.test_runtime.IsolatedRuntimeTestCase's bridge/runtime
    storage isolation rather than duplicating it, plus isolates
    orion.governance.storage and orion.business.storage on top."""

    def setUp(self) -> None:
        from tests.test_runtime import IsolatedRuntimeTestCase

        self._inner = IsolatedRuntimeTestCase()
        self._inner.setUp()

        self._gov_tmp = tempfile.TemporaryDirectory()
        self._orig_gov_dir = storage.GOVERNANCE_DIR
        storage.GOVERNANCE_DIR = Path(self._gov_tmp.name)

        from orion.business import storage as business_storage

        self._business_tmp = tempfile.TemporaryDirectory()
        self._orig_business_dir = business_storage.BUSINESS_DIR
        business_storage.BUSINESS_DIR = Path(self._business_tmp.name)

        execution_mode.set_mode(execution_mode.MODE_HARDENING, author="test", reason="runtime integration test")

    def tearDown(self) -> None:
        from orion.business import storage as business_storage

        business_storage.BUSINESS_DIR = self._orig_business_dir
        self._business_tmp.cleanup()
        storage.GOVERNANCE_DIR = self._orig_gov_dir
        self._gov_tmp.cleanup()
        self._inner.tearDown()

    def test_breaking_change_mission_is_parked_waiting_never_reaches_pipeline(self) -> None:
        from orion.agents.builder import agent as builder_agent
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate, MissionStatus

        mission = bridge_services.create_mission(
            MissionCreate(
                title="Elimina el endpoint viejo de autenticacion",
                description="Elimina el endpoint viejo de autenticacion, rompe compatibilidad con clientes antiguos",
                mission_type="executor",
            ),
            author="test",
        )
        bridge_services.update_status(mission.id, MissionStatus.READY, author="test")

        finished = builder_agent.run_claimed_mission(mission)
        self.assertEqual(finished.status, MissionStatus.WAITING)

        event_types = [e.type for e in bridge_services.get_events(mission.id)]
        self.assertIn("governance_hard_stop", event_types)
        self.assertNotIn("workspace_created", event_types)  # never reached the Pipeline / touched git

    def test_governance_evaluated_event_is_emitted_exactly_once(self) -> None:
        from orion.agents.builder import agent as builder_agent
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate, MissionStatus

        mission = bridge_services.create_mission(
            MissionCreate(
                title="Elimina el endpoint viejo",
                description="Elimina el endpoint viejo, rompe compatibilidad",
                mission_type="executor",
            ),
            author="test",
        )
        bridge_services.update_status(mission.id, MissionStatus.READY, author="test")
        builder_agent.run_claimed_mission(mission)

        event_types = [e.type for e in bridge_services.get_events(mission.id)]
        self.assertEqual(event_types.count("governance_evaluated"), 1)


if __name__ == "__main__":
    unittest.main()
