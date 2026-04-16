from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

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
from .mqtt import process_device_reply_envelope


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

    def test_job_start_queues_all_pending_steps_and_outbox(self):
        create_resp = self.client.post("/api/v1/jobs/", {"recipe_id": self.recipe.id}, format="json")
        job_id = create_resp.data["id"]

        start_resp = self.client.post(f"/api/v1/jobs/{job_id}/start/", {}, format="json")
        self.assertEqual(start_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(start_resp.data["status"], "RUNNING")

        queued_count = BatchStepExecution.objects.filter(job_id=job_id, status="QUEUED").count()
        self.assertEqual(queued_count, 2)
        self.assertEqual(CommandOutbox.objects.filter(job_id=job_id, status="QUEUED").count(), 2)

    def test_job_status_returns_counts_and_next_step(self):
        create_resp = self.client.post("/api/v1/jobs/", {"recipe_id": self.recipe.id}, format="json")
        job_id = create_resp.data["id"]
        self.client.post(f"/api/v1/jobs/{job_id}/start/", {}, format="json")

        status_resp = self.client.get(f"/api/v1/jobs/{job_id}/status/")
        self.assertEqual(status_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(status_resp.data["job"]["id"], job_id)
        self.assertEqual(status_resp.data["step_status_counts"]["queued"], 2)
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
