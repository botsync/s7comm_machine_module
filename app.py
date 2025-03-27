import os
from sdk_machine_module.integrator_manager import IntegratorManager

env = os.environ.get("ENV", "dev")
port = 1029
cd = os.getcwd()
if env == "dev" or env ==  "LOCAL":
    port  = 1030
REDIS_HOSTNAME = os.environ.get('REDIS_HOSTNAME', "localhost")
REDIS_PORT = os.environ.get('REDIS_PORT', "6379")
app = IntegratorManager(
    module_name='s7comm',
    module_setup_file_path=f'{cd}/machine_detail.yml',
    machine_config_file_path=f'{cd}/config.json',
    port=port,
    redis_hostname=REDIS_HOSTNAME,
    redis_port=REDIS_PORT,
    logger_identifier='s7comm',
    logger_file_path=f"{cd}/system.log",
    log_level='DEBUG',
    run_call_function_rate=0.001
)