from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns
from . import views

app_name = 'main_page_v1'

urlpatterns = [
    path('tasks/', views.task_list, name='tasks'),
    path('motor-controls/', views.motor_control_list, name='motor_controls'),
    path('auth/login/', views.login, name='auth_login'),
    path('auth/signup/', views.sign_up, name='auth_signup'),
    path('auth/token/validate/', views.token_validation, name='auth_token_validate'),
    path('users/me/', views.get_user_data, name='users_me'),
    path('users/me/password/', views.change_password, name='users_me_password'),
    path('motors/', views.get_motors, name='motors'),
    path('spinning-jobs/', views.spinning, name='spinning_jobs'),
    path('mqtt/messages/', views.mqtt_msg, name='mqtt_messages'),
    path('devices/', views.device_list, name='devices'),
    path('experiments/', views.experiment_process_list, name='experiments'),
    path('experiments/<str:experiment_id>/', views.experiment_process_detail, name='experiment_detail'),
    path('materials/', views.material_type_list, name='materials'),
    path('recipes/', views.material_recipe_list, name='recipes'),
    path('recipes/<int:recipe_id>/', views.material_recipe_detail, name='recipe_detail'),
    path('recipes/<int:recipe_id>/steps/', views.recipe_step_list_create, name='recipe_steps'),
    path('jobs/', views.batch_job_create, name='jobs_create'),
    path('jobs/<int:job_id>/start/', views.batch_job_start, name='jobs_start'),
    path('jobs/<int:job_id>/status/', views.batch_job_status, name='jobs_status'),
    path('communications/topics/publish/', views.communication_topic_publish, name='communications_topic_publish'),
    path('communications/services/call/', views.communication_service_call, name='communications_service_call'),
    path('communications/actions/goals/', views.communication_action_goal, name='communications_action_goal'),
    path('internal/spinning-metrics/', views.test, name='internal_spinning_metrics'),
]

urlpatterns = format_suffix_patterns(urlpatterns)
