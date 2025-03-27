import json
import traceback
from logger_setup import LoggerSetup
from redis_driver import RedisDriver

logger = LoggerSetup.get_logger()


def send_event(event_name, response, uid, event_type):
    try:
        # client = RPCCLient.get_client()
        # if client:
            # resp = client.register_event_call(
            #     uid,
            #     event_name,
            #     event_type,
            #     json.dumps(response)
            # )
            RedisDriver.publish('event_queue', json.dumps({
                 'event_name': event_name,
                 'event_data': response,
                 'machine_id': uid,
                 'event_type': event_type,
            }))
            # logger.error(f"Sending event: {resp}")
    except Exception as e:
        logger.critical(f"Error sending event for {event_name}")
        traceback_str = ''.join(traceback.format_tb(e.__traceback__))
        logger.error(traceback_str)
        logger.critical(f"Error sending event: {e} ------ {response} ------ {uid} ------ {event_type}")


