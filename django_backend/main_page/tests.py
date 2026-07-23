from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch
from django.utils import timezone

from .models import (
    ExperimentProcess,
    MaterialType,
    MaterialRecipe,
    RecipeStep,
    BatchJob,
    BatchStepExecution,
    CommandOutbox,
    TelemetryIngest,
)
from .mqtt import process_device_reply_envelope, _ensure_device_state
from .views import _dispatch_transport_message
from .orchestration.events import DeviceReplyEvent
from .orchestration.step_executors import default_step_executor_registry
from .orchestration.service import check_internal_waits, check_job_timeouts, get_ready_pending_steps
from .orchestration.transitions import derive_job_status, transition_outbox_status, transition_step_status


def _set_default_device_online():
    """测试辅助：将默认目标设备置为在线/空闲（基于内存状态表）。"""
    state = _ensure_device_state('esp32_1')
    state['is_online'] = True
    state['task_status'] = 'idle'
    state['last_heartbeat'] = __import__('django.utils.timezone').utils.timezone.now()


class ExperimentProcessApiTests(APITestCase):
    def test_experiment_process_crud(self):
        create_payload = {
            "experiment_id": "EXP_1001",
            "experiment_name": "ZnO Trial",
            "dmac_dosage_ml": "20.0",
            "water_dosage_ml": "5.0",
            "solvent_ph": "7.2",
            "reaction_temperature_c": "85.50",
            "stirring_speed_rpm": 600,
            "stirring_duration_min": 30,
        }
        create_resp = self.client.post("/api/v1/experiments/", create_payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_resp.data["experiment_id"], "EXP_1001")

        list_resp = self.client.get("/api/v1/experiments/")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_resp.data), 1)

        detail_resp = self.client.get("/api/v1/experiments/EXP_1001/")
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_resp.data["experiment_name"], "ZnO Trial")

        patch_resp = self.client.patch(
            "/api/v1/experiments/EXP_1001/",
            {"stirring_speed_rpm": 700},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_resp.data["stirring_speed_rpm"], 700)

        delete_resp = self.client.delete("/api/v1/experiments/EXP_1001/")
        self.assertEqual(delete_resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ExperimentProcess.objects.filter(experiment_id="EXP_1001").exists())


class RecipeAndJobApiTests(APITestCase):
    def setUp(self):
        _set_default_device_online()
        self.material = MaterialType.objects.create(name="ZnO", description="Target material")
        self.recipe = MaterialRecipe.objects.create(
            material_type=self.material,
            version=1,
            dmac_dosage_ml="20.0",
            water_dosage_ml="5.0",
            solvent_ph="7.2",
            reaction_temperature_c="85.50",
            stirring_speed_rpm=600,
            stirring_duration_min=30,
        )
        self.step1 = RecipeStep.objects.create(
            recipe=self.recipe,
            step_no=1,
            step_type="MOVE_ARM",
            name="Move to pickup",
            parameters={"topic": "robot/arm/actions", "pose": "pickup"},
            expected_duration_sec=3,
        )
        self.step2 = RecipeStep.objects.create(
            recipe=self.recipe,
            step_no=2,
            step_type="STIR",
            name="Start stir",
            parameters={"topic": "robot/turntable/actions", "rpm_key": "stirring_speed_rpm"},
            expected_duration_sec=10,
        )

    def test_material_list_endpoint(self):
        resp = self.client.get("/api/v1/materials/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["name"], "ZnO")

    def test_recipe_list_and_detail_endpoint(self):
        list_resp = self.client.get("/api/v1/recipes/")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_resp.data), 1)

        detail_resp = self.client.get(f"/api/v1/recipes/{self.recipe.id}/")
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_resp.data["material_type"], self.material.id)

    def test_recipe_step_list_endpoint(self):
        resp = self.client.get(f"/api/v1/recipes/{self.recipe.id}/steps/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)
        self.assertEqual(resp.data[0]["step_no"], 1)
        self.assertEqual(resp.data[1]["step_no"], 2)

    def test_job_create_success_creates_step_executions(self):
        resp = self.client.post(
            "/api/v1/jobs/",
            {
                "recipe_id": self.recipe.id,
                "operator": "operator_a",
                "overrides": {"reaction_temperature_c": 90.0},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job_id = resp.data["id"]

        job = BatchJob.objects.get(id=job_id)
        self.assertEqual(job.status, "PENDING")
        self.assertEqual(job.operator, "operator_a")
        self.assertEqual(BatchStepExecution.objects.filter(job=job).count(), 2)
        first_step = BatchStepExecution.objects.filter(job=job).order_by("id").first()
        self.assertEqual(first_step.command_payload["interface_type"], "action")

    def test_job_create_rejects_invalid_overrides(self):
        resp = self.client.post(
            "/api/v1/jobs/",
            {
                "recipe_id": self.recipe.id,
                "overrides": ["not", "an", "object"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("overrides", resp.data)

    def test_job_create_rejects_recipe_without_steps(self):
        empty_recipe = MaterialRecipe.objects.create(
            material_type=self.material,
            version=2,
            dmac_dosage_ml="10.0",
        )
        resp = self.client.post(
            "/api/v1/jobs/",
            {"recipe_id": empty_recipe.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", resp.data)

    @patch("main_page.views.publish_device_command")
    @patch("main_page.views.mqtt_client_available", return_value=True)
    @patch("main_page.views.dispatch_ros2_bridge_command", return_value={"accepted": True, "bridge_request_id": "req_job_start"})
    def test_job_start_queues_all_pending_steps_and_outbox(self, _mock_bridge, _mock_available, mock_publish):
        create_resp = self.client.post("/api/v1/jobs/", {"recipe_id": self.recipe.id}, format="json")
        job_id = create_resp.data["id"]

        start_resp = self.client.post(f"/api/v1/jobs/{job_id}/start/", {}, format="json")
        self.assertEqual(start_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(start_resp.data["status"], "RUNNING")

        running_count = BatchStepExecution.objects.filter(job_id=job_id, status="RUNNING").count()
        self.assertEqual(running_count, 2)
        self.assertEqual(CommandOutbox.objects.filter(job_id=job_id, status="SENT").count(), 2)
        mock_publish.assert_called()

    @patch("main_page.views.publish_device_command")
    @patch("main_page.views.mqtt_client_available", return_value=True)
    @patch("main_page.views.dispatch_ros2_bridge_command", return_value={"accepted": True, "bridge_request_id": "req_job_status"})
    def test_job_status_returns_counts_and_next_step(self, _mock_bridge, _mock_available, _mock_publish):
        create_resp = self.client.post("/api/v1/jobs/", {"recipe_id": self.recipe.id}, format="json")
        job_id = create_resp.data["id"]
        self.client.post(f"/api/v1/jobs/{job_id}/start/", {}, format="json")

        status_resp = self.client.get(f"/api/v1/jobs/{job_id}/status/")
        self.assertEqual(status_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(status_resp.data["job"]["id"], job_id)
        self.assertEqual(status_resp.data["step_status_counts"]["running"], 2)
        self.assertIsNotNone(status_resp.data["next_step"])

    def test_job_create_maps_step_types_to_interfaces(self):
        wait_step = RecipeStep.objects.create(
            recipe=self.recipe,
            step_no=3,
            step_type="WAIT",
            name="Check heater readiness",
            parameters={"topic": "robot/heater/service", "service_name": "heater.wait_ready"},
            expected_duration_sec=5,
        )

        create_resp = self.client.post("/api/v1/jobs/", {"recipe_id": self.recipe.id}, format="json")
        job = BatchJob.objects.get(id=create_resp.data["id"])
        executions = BatchStepExecution.objects.filter(job=job).order_by("recipe_step__step_no")

        self.assertEqual(executions[0].command_payload["interface_type"], "action")
        self.assertEqual(executions[1].command_payload["interface_type"], "topic")
        self.assertEqual(executions[2].recipe_step_id, wait_step.id)
        self.assertEqual(executions[2].command_payload["interface_type"], "service")


class LegacyCompatibilityTests(APITestCase):
    def test_legacy_api_has_deprecation_headers(self):
        resp = self.client.get("/api/tasks/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp["X-API-Deprecated"], "true")
        self.assertEqual(resp["X-API-Replacement-Prefix"], "/api/v1/")


class CommunicationInterfaceApiTests(APITestCase):
    def setUp(self):
        _set_default_device_online()
        self.material = MaterialType.objects.create(name="ZnO", description="Target material")
        self.recipe = MaterialRecipe.objects.create(
            material_type=self.material,
            version=1,
            stirring_speed_rpm=600,
            stirring_duration_min=30,
        )
        self.step = RecipeStep.objects.create(
            recipe=self.recipe,
            step_no=1,
            step_type="MOVE_ARM",
            name="Move to pickup",
            parameters={"topic": "robot/arm/actions", "pose": "pickup"},
        )
        self.job = BatchJob.objects.create(recipe=self.recipe, status="PENDING")
        self.step_execution = BatchStepExecution.objects.create(
            job=self.job,
            recipe_step=self.step,
            status="PENDING",
            command_payload={"step_type": "MOVE_ARM", "parameters": {"topic": "robot/arm/actions"}},
        )

    @patch("main_page.views.publish_device_command")
    @patch("main_page.views.mqtt_client_available", return_value=True)
    def test_topic_publish_interface_creates_outbox(self, _mock_available, mock_publish):
        resp = self.client.post(
            "/api/v1/communications/topics/publish/",
            {
                "topic": "lab/arm/arm01/cmd",
                "payload": {"action": "MOVE", "pose": "loading"},
                "job_id": self.job.id,
                "step_execution_id": self.step_execution.id,
                "device": "roboarm",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["interface_type"], "topic")
        self.assertTrue(resp.data["dispatched"])
        mock_publish.assert_called_once()

    @patch("main_page.views.publish_device_command")
    @patch("main_page.views.mqtt_client_available", return_value=True)
    def test_service_call_interface_wraps_request(self, _mock_available, mock_publish):
        resp = self.client.post(
            "/api/v1/communications/services/call/",
            {
                "service_name": "device.get_status",
                "topic": "lab/service/dispatcher",
                "request": {"device_id": "tt01"},
                "job_id": self.job.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["interface_type"], "service")
        published_payload = mock_publish.call_args[0][1]
        self.assertEqual(published_payload["service_name"], "device.get_status")

    @patch("main_page.views.publish_device_command")
    @patch("main_page.views.mqtt_client_available", return_value=True)
    def test_action_goal_interface_wraps_goal(self, _mock_available, mock_publish):
        resp = self.client.post(
            "/api/v1/communications/actions/goals/",
            {
                "action_name": "arm.execute_trajectory",
                "topic": "lab/action/dispatcher",
                "goal": {"trajectory": ["safe_a", "pickup", "place_1"]},
                "step_execution_id": self.step_execution.id,
                "expected_duration_sec": 12,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["interface_type"], "action")
        published_payload = mock_publish.call_args[0][1]
        self.assertEqual(published_payload["action_name"], "arm.execute_trajectory")

    @patch("main_page.views.dispatch_ros2_bridge_command", return_value={"accepted": True, "bridge_request_id": "req_001"})
    def test_action_goal_interface_supports_ros2_transport(self, mock_bridge):
        resp = self.client.post(
            "/api/v1/communications/actions/goals/",
            {
                "topic": "bridge/arm01/actions",
                "transport": "ros2",
                "action_name": "arm.execute_trajectory",
                "goal": {"trajectory": ["safe_a", "pickup", "place_1"]},
                "step_execution_id": self.step_execution.id,
                "device": {"type": "roboarm", "id": "arm01"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        outbox = CommandOutbox.objects.get(step_execution=self.step_execution)
        self.assertEqual(outbox.payload["transport"], "ros2")
        mock_bridge.assert_called_once()


class OrchestrationDomainTests(APITestCase):
    def test_step_transition_ack_from_pending_becomes_queued(self):
        event = DeviceReplyEvent(interface_type='action', message_type='ack', status='accepted')
        self.assertEqual(transition_step_status('PENDING', event), 'QUEUED')

    def test_step_transition_result_success_becomes_done(self):
        event = DeviceReplyEvent(interface_type='action', message_type='result', status='succeeded')
        self.assertEqual(transition_step_status('RUNNING', event), 'DONE')

    def test_outbox_transition_error_becomes_failed(self):
        event = DeviceReplyEvent(interface_type='action', message_type='error', status='failed')
        self.assertEqual(transition_outbox_status('SENT', event), 'FAILED')

    def test_job_status_derives_failed_when_any_step_failed(self):
        self.assertEqual(derive_job_status(['DONE', 'FAILED'], 'RUNNING'), 'FAILED')

    def test_job_status_derives_done_when_all_steps_done(self):
        self.assertEqual(derive_job_status(['DONE', 'DONE'], 'RUNNING'), 'DONE')

    def test_step_executor_registry_maps_move_arm_to_ros2_action(self):
        recipe_step = RecipeStep(
            step_no=1,
            step_type='MOVE_ARM',
            name='Move',
            parameters={'action_name': 'arm.execute_trajectory', 'goal': {'trajectory': ['home']}},
        )
        payload = default_step_executor_registry.build_command_payload(
            recipe_step,
            planned_parameters={},
            default_device_id='esp32_1',
        )
        self.assertEqual(payload['transport'], 'ros2')
        self.assertEqual(payload['interface_type'], 'action')

    def test_step_executor_registry_maps_wait_to_service(self):
        recipe_step = RecipeStep(
            step_no=2,
            step_type='WAIT',
            name='Wait',
            parameters={'service_name': 'heater.wait_ready', 'request': {'device_id': 'heater01'}},
        )
        payload = default_step_executor_registry.build_command_payload(
            recipe_step,
            planned_parameters={},
            default_device_id='esp32_1',
        )
        self.assertEqual(payload['transport'], 'mqtt')
        self.assertEqual(payload['interface_type'], 'service')

    def test_get_ready_pending_steps_supports_explicit_dependencies(self):
        material = MaterialType.objects.create(name="Sched", description="Sched")
        recipe = MaterialRecipe.objects.create(material_type=material, version=1)
        step1 = RecipeStep.objects.create(recipe=recipe, step_no=1, step_type='MOVE_ARM', parameters={})
        step2 = RecipeStep.objects.create(
            recipe=recipe,
            step_no=2,
            step_type='WAIT',
            parameters={'depends_on_steps': [1], 'service_name': 'heater.wait_ready'},
        )
        job = BatchJob.objects.create(recipe=recipe, status='RUNNING')
        exec1 = BatchStepExecution.objects.create(
            job=job, recipe_step=step1, status='DONE',
            command_payload={'step_no': 1, 'step_type': 'MOVE_ARM', 'parameters': {}},
        )
        exec2 = BatchStepExecution.objects.create(
            job=job, recipe_step=step2, status='PENDING',
            command_payload={'step_no': 2, 'step_type': 'WAIT', 'parameters': {'depends_on_steps': [1]}},
        )
        ready = get_ready_pending_steps(job)
        self.assertEqual([step.id for step in ready], [exec2.id])

    def test_timeout_check_pauses_job_and_marks_step_failed(self):
        material = MaterialType.objects.create(name="Timeout", description="Timeout")
        recipe = MaterialRecipe.objects.create(material_type=material, version=1)
        step = RecipeStep.objects.create(recipe=recipe, step_no=1, step_type='MOVE_ARM', expected_duration_sec=1)
        job = BatchJob.objects.create(recipe=recipe, status='RUNNING')
        step_execution = BatchStepExecution.objects.create(
            job=job,
            recipe_step=step,
            status='RUNNING',
            started_at=timezone.now() - __import__('datetime').timedelta(seconds=5),
            command_payload={'step_no': 1, 'step_type': 'MOVE_ARM', 'parameters': {}},
        )
        result = check_job_timeouts(job)
        self.assertEqual(result.checked_steps, 1)
        self.assertEqual(len(result.timed_out_steps), 1)
        step_execution.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(step_execution.status, 'FAILED')
        self.assertEqual(job.status, 'PAUSED')

    def test_get_ready_pending_steps_respects_active_resource_lock(self):
        material = MaterialType.objects.create(name="Locks", description="Locks")
        recipe = MaterialRecipe.objects.create(material_type=material, version=1)
        step1 = RecipeStep.objects.create(
            recipe=recipe, step_no=1, step_type='MOVE_ARM',
            parameters={'device': 'roboarm', 'device_id': 'arm01'},
        )
        step2 = RecipeStep.objects.create(
            recipe=recipe, step_no=2, step_type='MOVE_ARM',
            parameters={'device': 'roboarm', 'device_id': 'arm01'},
        )
        job = BatchJob.objects.create(recipe=recipe, status='RUNNING')
        BatchStepExecution.objects.create(
            job=job,
            recipe_step=step1,
            status='RUNNING',
            command_payload={'step_no': 1, 'step_type': 'MOVE_ARM', 'parameters': {'device': 'roboarm', 'device_id': 'arm01'}},
        )
        blocked = BatchStepExecution.objects.create(
            job=job,
            recipe_step=step2,
            status='PENDING',
            command_payload={'step_no': 2, 'step_type': 'MOVE_ARM', 'parameters': {'device': 'roboarm', 'device_id': 'arm01'}},
        )
        ready = get_ready_pending_steps(job)
        self.assertEqual(ready, [])
        blocked.refresh_from_db()
        self.assertEqual(blocked.status, 'PENDING')

    def test_get_ready_pending_steps_dispatches_non_conflicting_parallel_steps(self):
        material = MaterialType.objects.create(name="Parallel", description="Parallel")
        recipe = MaterialRecipe.objects.create(material_type=material, version=1)
        step1 = RecipeStep.objects.create(
            recipe=recipe, step_no=1, step_type='MOVE_ARM',
            parameters={'device': 'roboarm', 'device_id': 'arm01'},
        )
        step2 = RecipeStep.objects.create(
            recipe=recipe, step_no=2, step_type='WAIT',
            parameters={'service_name': 'heater.wait_ready', 'resource_locks': ['heater:heater01']},
        )
        job = BatchJob.objects.create(recipe=recipe, status='RUNNING')
        exec1 = BatchStepExecution.objects.create(
            job=job,
            recipe_step=step1,
            status='PENDING',
            command_payload={'step_no': 1, 'step_type': 'MOVE_ARM', 'parameters': {'device': 'roboarm', 'device_id': 'arm01'}},
        )
        exec2 = BatchStepExecution.objects.create(
            job=job,
            recipe_step=step2,
            status='PENDING',
            command_payload={'step_no': 2, 'step_type': 'WAIT', 'parameters': {'resource_locks': ['heater:heater01']}},
        )
        ready = get_ready_pending_steps(job)
        self.assertEqual([step.id for step in ready], [exec1.id, exec2.id])

    def test_get_ready_pending_steps_reserves_same_lock_within_batch(self):
        material = MaterialType.objects.create(name="Reserve", description="Reserve")
        recipe = MaterialRecipe.objects.create(material_type=material, version=1)
        step1 = RecipeStep.objects.create(
            recipe=recipe, step_no=1, step_type='WAIT',
            parameters={'service_name': 'gripper.close', 'resource_locks': ['gripper:gripper01']},
        )
        step2 = RecipeStep.objects.create(
            recipe=recipe, step_no=2, step_type='WAIT',
            parameters={'service_name': 'gripper.open', 'resource_locks': ['gripper:gripper01']},
        )
        job = BatchJob.objects.create(recipe=recipe, status='RUNNING')
        exec1 = BatchStepExecution.objects.create(
            job=job,
            recipe_step=step1,
            status='PENDING',
            command_payload={'step_no': 1, 'step_type': 'WAIT', 'parameters': {'resource_locks': ['gripper:gripper01']}},
        )
        BatchStepExecution.objects.create(
            job=job,
            recipe_step=step2,
            status='PENDING',
            command_payload={'step_no': 2, 'step_type': 'WAIT', 'parameters': {'resource_locks': ['gripper:gripper01']}},
        )
        ready = get_ready_pending_steps(job)
        self.assertEqual([step.id for step in ready], [exec1.id])

    def test_internal_wait_computes_turntable_angle_lead_duration(self):
        material = MaterialType.objects.create(name="AngleWait", description="Angle wait")
        recipe = MaterialRecipe.objects.create(material_type=material, version=1, stirring_speed_rpm=6)
        wait_step = RecipeStep.objects.create(
            recipe=recipe,
            step_no=1,
            step_type='WAIT',
            parameters={
                'wait_strategy': 'turntable_angle_lead',
                'rpm_key': 'stirring_speed_rpm',
                'target_angle_deg': 180,
                'arm_lead_time_sec': 2,
            },
        )
        job = BatchJob.objects.create(
            recipe=recipe,
            status='RUNNING',
            planned_parameters={'stirring_speed_rpm': 6},
        )
        step_execution = BatchStepExecution.objects.create(
            job=job,
            recipe_step=wait_step,
            status='PENDING',
            command_payload={
                'step_no': 1,
                'step_type': 'WAIT',
                'parameters': wait_step.parameters,
                'planned_parameters': job.planned_parameters,
            },
        )

        from .orchestration.service import dispatch_ready_steps

        dispatched, failed = dispatch_ready_steps(
            job,
            resolve_dispatch_command=lambda _step: None,
            dispatch_transport_message=lambda **_kwargs: {'accepted': True},
            can_dispatch_to_device=lambda _device_id: (True, ''),
            extract_device_id_from_topic=lambda _topic: 'esp32_1',
            default_device_id='esp32_1',
        )
        self.assertEqual(dispatched, [])
        self.assertEqual(failed, [])
        step_execution.refresh_from_db()
        self.assertEqual(step_execution.status, 'RUNNING')
        self.assertAlmostEqual(step_execution.telemetry['computed_wait_sec'], 3.0)
        self.assertIn('wait_until_at', step_execution.telemetry)

    @patch("main_page.views.dispatch_ros2_bridge_command", return_value={"accepted": True, "bridge_request_id": "req_wait_arm"})
    def test_internal_wait_completion_dispatches_dependent_move_arm(self, mock_bridge):
        material = MaterialType.objects.create(name="WaitAdvance", description="Wait advance")
        recipe = MaterialRecipe.objects.create(material_type=material, version=1, stirring_speed_rpm=6)
        wait_step = RecipeStep.objects.create(
            recipe=recipe,
            step_no=1,
            step_type='WAIT',
            parameters={'wait_sec': 1},
        )
        arm_step = RecipeStep.objects.create(
            recipe=recipe,
            step_no=2,
            step_type='MOVE_ARM',
            parameters={
                'transport': 'ros2',
                'device': 'roboarm',
                'device_id': 'arm01',
                'action_name': 'arm.execute_trajectory',
                'goal': {'trajectory': ['reactor_hover']},
                'depends_on_steps': [1],
            },
        )
        job = BatchJob.objects.create(recipe=recipe, status='RUNNING', planned_parameters={'stirring_speed_rpm': 6})
        wait_execution = BatchStepExecution.objects.create(
            job=job,
            recipe_step=wait_step,
            status='RUNNING',
            started_at=timezone.now() - __import__('datetime').timedelta(seconds=2),
            command_payload={'step_no': 1, 'step_type': 'WAIT', 'parameters': wait_step.parameters},
            telemetry={
                'wait_mode': 'internal',
                'computed_wait_sec': 1,
                'wait_until_at': (timezone.now() - __import__('datetime').timedelta(seconds=1)).isoformat(),
            },
        )
        arm_execution = BatchStepExecution.objects.create(
            job=job,
            recipe_step=arm_step,
            status='PENDING',
            command_payload={
                'step_no': 2,
                'step_type': 'MOVE_ARM',
                'transport': 'ros2',
                'interface_type': 'action',
                'route_name': 'arm.execute_trajectory',
                'parameters': arm_step.parameters,
            },
        )

        result = check_internal_waits(
            job,
            resolve_dispatch_command=lambda step: default_step_executor_registry.resolve_dispatch(
                step,
                default_control_topic='esp32_1/control',
            ),
            dispatch_transport_message=_dispatch_transport_message,
            can_dispatch_to_device=lambda _device_id: (True, ''),
            extract_device_id_from_topic=lambda _topic: 'esp32_1',
            default_device_id='esp32_1',
        )
        wait_execution.refresh_from_db()
        arm_execution.refresh_from_db()
        self.assertEqual(result.checked_steps, 1)
        self.assertEqual(len(result.completed_steps), 1)
        self.assertEqual(wait_execution.status, 'DONE')
        self.assertEqual(arm_execution.status, 'RUNNING')
        mock_bridge.assert_called_once()


class Ros2BridgeIntegrationTests(APITestCase):
    def setUp(self):
        self.material = MaterialType.objects.create(name="Bridge Material", description="ROS2 bridge test")
        self.recipe = MaterialRecipe.objects.create(material_type=self.material, version=1)
        self.step = RecipeStep.objects.create(
            recipe=self.recipe,
            step_no=1,
            step_type="MOVE_ARM",
            name="Move by ROS2 bridge",
            parameters={
                "transport": "ros2",
                "device": "roboarm",
                "device_id": "arm01",
                "action_name": "arm.execute_trajectory",
                "goal": {"trajectory": ["safe_a", "pickup", "place_1"]},
                "expected_duration_sec": 12,
            },
        )

    @patch("main_page.views.dispatch_ros2_bridge_command", return_value={"accepted": True, "bridge_request_id": "req_002"})
    def test_job_start_dispatches_move_arm_via_ros2_bridge(self, mock_bridge):
        create_resp = self.client.post("/api/v1/jobs/", {"recipe_id": self.recipe.id}, format="json")
        job_id = create_resp.data["id"]

        start_resp = self.client.post(f"/api/v1/jobs/{job_id}/start/", {}, format="json")
        self.assertEqual(start_resp.status_code, status.HTTP_200_OK)

        step_execution = BatchStepExecution.objects.get(job_id=job_id)
        outbox = CommandOutbox.objects.get(step_execution=step_execution)
        self.assertEqual(step_execution.status, "RUNNING")
        self.assertEqual(outbox.payload["transport"], "ros2")
        mock_bridge.assert_called_once()

    @patch("main_page.views.dispatch_ros2_bridge_command", return_value={"accepted": True, "bridge_request_id": "req_resume"})
    def test_job_resume_requeues_failed_step(self, mock_bridge):
        job = BatchJob.objects.create(recipe=self.recipe, status="FAILED", error_message="boom")
        step_execution = BatchStepExecution.objects.create(
            job=job,
            recipe_step=self.step,
            status="FAILED",
            error_message="boom",
            command_payload={
                "step_no": 1,
                "step_type": "MOVE_ARM",
                "transport": "ros2",
                "interface_type": "action",
                "route_name": "arm.execute_trajectory",
                "parameters": {"transport": "ros2"},
            },
        )
        resp = self.client.post(f"/api/v1/jobs/{job.id}/resume/", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        step_execution.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(job.status, "RUNNING")
        self.assertEqual(step_execution.status, "RUNNING")
        mock_bridge.assert_called_once()

    def test_bridge_reply_ingest_updates_step_and_job(self):
        job = BatchJob.objects.create(recipe=self.recipe, status="RUNNING")
        step_execution = BatchStepExecution.objects.create(
            job=job,
            recipe_step=self.step,
            status="RUNNING",
            command_payload={
                "step_type": "MOVE_ARM",
                "transport": "ros2",
                "interface_type": "action",
                "route_name": "arm.execute_trajectory",
                "parameters": {"transport": "ros2"},
            },
        )
        outbox = CommandOutbox.objects.create(
            job=job,
            step_execution=step_execution,
            topic="bridge/arm01/actions",
            payload={
                "transport": "ros2",
                "interface_type": "action",
                "route_name": "arm.execute_trajectory",
                "body": {"goal": {"trajectory": ["safe_a", "pickup", "place_1"]}},
            },
            status="SENT",
        )

        resp = self.client.post(
            "/api/v1/internal/bridge/replies/",
            {
                "interface_type": "action",
                "message_type": "result",
                "route_name": "arm.execute_trajectory",
                "status": "succeeded",
                "device": {"type": "roboarm", "id": "arm01"},
                "correlation": {
                    "job_id": job.id,
                    "step_execution_id": step_execution.id,
                    "outbox_id": outbox.id,
                },
                "result": {"final_pose": "place_1"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        job.refresh_from_db()
        step_execution.refresh_from_db()
        outbox.refresh_from_db()
        self.assertEqual(step_execution.status, "DONE")
        self.assertEqual(job.status, "DONE")
        self.assertEqual(outbox.status, "ACKED")

    @patch("main_page.mqtt.orchestration_dispatch_transport_message", return_value={"accepted": True, "bridge_request_id": "req_next"})
    def test_bridge_reply_ingest_advances_next_dependent_step(self, mock_bridge):
        job = BatchJob.objects.create(recipe=self.recipe, status="RUNNING")
        first_step = BatchStepExecution.objects.create(
            job=job,
            recipe_step=self.step,
            status="RUNNING",
            command_payload={
                "step_no": 1,
                "step_type": "MOVE_ARM",
                "transport": "ros2",
                "interface_type": "action",
                "route_name": "arm.execute_trajectory",
                "parameters": {"transport": "ros2"},
            },
        )
        second_recipe_step = RecipeStep.objects.create(
            recipe=self.recipe,
            step_no=2,
            step_type="MOVE_ARM",
            name="Move after first",
            parameters={
                "transport": "ros2",
                "device": "roboarm",
                "device_id": "arm01",
                "action_name": "arm.execute_trajectory",
                "goal": {"trajectory": ["place_1"]},
                "depends_on_steps": [1],
            },
        )
        second_step = BatchStepExecution.objects.create(
            job=job,
            recipe_step=second_recipe_step,
            status="PENDING",
            command_payload={
                "step_no": 2,
                "step_type": "MOVE_ARM",
                "transport": "ros2",
                "interface_type": "action",
                "route_name": "arm.execute_trajectory",
                "parameters": {
                    "transport": "ros2",
                    "depends_on_steps": [1],
                    "goal": {"trajectory": ["place_1"]},
                },
            },
        )
        outbox = CommandOutbox.objects.create(
            job=job,
            step_execution=first_step,
            topic="bridge/arm01/actions",
            payload={"transport": "ros2", "interface_type": "action", "route_name": "arm.execute_trajectory", "body": {}},
            status="SENT",
        )
        resp = self.client.post(
            "/api/v1/internal/bridge/replies/",
            {
                "interface_type": "action",
                "message_type": "result",
                "route_name": "arm.execute_trajectory",
                "status": "succeeded",
                "device": {"type": "roboarm", "id": "arm01"},
                "correlation": {
                    "job_id": job.id,
                    "step_execution_id": first_step.id,
                    "outbox_id": outbox.id,
                },
                "result": {"final_pose": "place_1"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        second_step.refresh_from_db()
        self.assertEqual(second_step.status, "RUNNING")


class DeviceReplyEnvelopeTests(APITestCase):
    def setUp(self):
        self.material = MaterialType.objects.create(name="Envelope Material", description="Reply test")
        self.recipe = MaterialRecipe.objects.create(material_type=self.material, version=1)
        self.step = RecipeStep.objects.create(
            recipe=self.recipe,
            step_no=1,
            step_type="MOVE_ARM",
            name="Execute trajectory",
            parameters={"topic": "lab/action/dispatcher", "action_name": "arm.execute_trajectory"},
        )
        self.job = BatchJob.objects.create(recipe=self.recipe, status="RUNNING")
        self.step_execution = BatchStepExecution.objects.create(
            job=self.job,
            recipe_step=self.step,
            status="RUNNING",
            command_payload={
                "step_type": "MOVE_ARM",
                "interface_type": "action",
                "route_name": "arm.execute_trajectory",
                "parameters": {"topic": "lab/action/dispatcher"},
            },
        )
        self.outbox = CommandOutbox.objects.create(
            job=self.job,
            step_execution=self.step_execution,
            topic="lab/action/dispatcher",
            payload={"interface_type": "action", "route_name": "arm.execute_trajectory", "body": {"goal": {}}},
            status="SENT",
        )

    def test_action_progress_reply_updates_step_and_telemetry(self):
        package = process_device_reply_envelope(
            "lab/action/arm01/replies",
            {
                "schema_version": 1,
                "interface_type": "action",
                "message_type": "progress",
                "route_name": "arm.execute_trajectory",
                "status": "running",
                "device": {"type": "roboarm", "id": "arm01"},
                "correlation": {
                    "job_id": self.job.id,
                    "step_execution_id": self.step_execution.id,
                    "outbox_id": self.outbox.id,
                },
                "progress": {"percent": 50, "stage": "moving"},
            },
        )
        self.step_execution.refresh_from_db()
        self.outbox.refresh_from_db()
        self.assertEqual(package["topic"], "device_reply")
        self.assertEqual(self.step_execution.status, "RUNNING")
        self.assertEqual(self.outbox.status, "ACKED")
        self.assertEqual(TelemetryIngest.objects.filter(step_execution=self.step_execution).count(), 1)

    def test_action_result_reply_marks_step_and_job_done(self):
        package = process_device_reply_envelope(
            "lab/action/arm01/replies",
            {
                "schema_version": 1,
                "interface_type": "action",
                "message_type": "result",
                "route_name": "arm.execute_trajectory",
                "status": "succeeded",
                "device": {"type": "roboarm", "id": "arm01"},
                "correlation": {
                    "job_id": self.job.id,
                    "step_execution_id": self.step_execution.id,
                    "outbox_id": self.outbox.id,
                },
                "result": {"final_pose": "place_1"},
            },
        )
        self.step_execution.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(package["status"], "succeeded")
        self.assertEqual(self.step_execution.status, "DONE")
        self.assertEqual(self.job.status, "DONE")

    def test_service_error_reply_marks_failure(self):
        self.step_execution.command_payload["interface_type"] = "service"
        self.step_execution.command_payload["route_name"] = "heater.wait_ready"
        self.step_execution.save(update_fields=["command_payload", "updated_at"])
        self.outbox.payload["interface_type"] = "service"
        self.outbox.payload["route_name"] = "heater.wait_ready"
        self.outbox.save(update_fields=["payload", "updated_at"])

        process_device_reply_envelope(
            "lab/service/heater01/replies",
            {
                "schema_version": 1,
                "interface_type": "service",
                "message_type": "error",
                "route_name": "heater.wait_ready",
                "status": "failed",
                "device": {"type": "heater", "id": "heater01"},
                "correlation": {
                    "job_id": self.job.id,
                    "step_execution_id": self.step_execution.id,
                    "outbox_id": self.outbox.id,
                },
                "error": {"code": "TIMEOUT", "message": "Heater did not reach target in time."},
            },
        )
        self.step_execution.refresh_from_db()
        self.job.refresh_from_db()
        self.outbox.refresh_from_db()
        self.assertEqual(self.step_execution.status, "FAILED")
        self.assertEqual(self.job.status, "FAILED")
        self.assertEqual(self.outbox.status, "FAILED")
