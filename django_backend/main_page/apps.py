from django.apps import AppConfig


class MyAppConfig(AppConfig):
    name = 'main_page'

    def ready(self):
        from . import mqtt
        if mqtt.client is not None:
            mqtt.client.loop_start()

        # 仅在需要 MQTT 客户端的进程中启动定时调度器
        if mqtt._should_init_mqtt_client():
            from .scheduler import SpinningScheduler
            from .orchestration.scheduler import OrchestrationScheduler
            SpinningScheduler.start()
            OrchestrationScheduler.start()
