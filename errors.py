from redis_driver import RedisDriver
import json

def send_error(uid: str, error_code:str, error_message: str, error_name: str, error_args: dict):
    """
        Used for registering error on machine module
    """
    # client = RPCCLient.get_client()
    try:
        # client.register_error(
        #     uid,
        #     error_message,
        #     json.dumps(error_args),
        #     error_code,
        #     error_name
        # )
        RedisDriver.publish('error_queue', json.dumps({
            'error_name': error_name,
            'error_code': error_code,
            'error_args': error_args,
            'error_message': error_message,
            "machine_id": uid
        }))
    except Exception as e:
        print(f"Issue while registering error: {e}")