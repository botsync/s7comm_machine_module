from dotenv import load_dotenv
import os
import redis
from logger_setup import LoggerSetup
import time
import json

load_dotenv()

logger = LoggerSetup.get_logger()

class RedisDriver(object):
    HOSTNAME = os.environ.get('REDIS_HOSTNAME', "localhost")
    PORT = os.environ.get('REDIS_PORT', "6379")

    @classmethod
    def get_server(cls):
        if not hasattr(cls, 'server'):
            env = os.environ.get("ENV")
            if env == "TEST":
                cls.HOSTNAME = "0.0.0.0"
                cls.PORT = 6379
            #Initialize Neo4j server
            cls.server = redis.Redis(
                host=cls.HOSTNAME,
                port=cls.PORT,
                decode_responses=True
            )
        return cls.server


    @classmethod
    def publish(cls, channel: str, message: str):
        serv = cls.get_server()
        serv.publish(channel, message)

    @classmethod
    def thread_subscribe(cls, channel: str, callback):
        """
            Thread Subscriber function for redis pubsub
            Run it in thread pool or seperate thread
        """

        try:
            pubsub = cls.server.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(f'{channel}')
            while True:
                try:
                    message = pubsub.get_message(timeout=0.01)
                    if message and message.get('data'):
                        logger.error(message['data'])
                        json.loads(message['data'])
                        callback(json.loads(message['data']))
                except Exception as e:
                    logger.critical(f"Error in RedisDriver.thread_subscribe: {str(e)}")
                time.sleep(0.00001)
        except Exception as e:
            logger.critical(f"============= CRITICAL ERROR ===============  ")
            logger.critical(f"=======================MAIN EVENT LISTENER STOPPED=========================")
            logger.critical(f"======RESTART SYSTEM NOW ===================")
            logger.error(f"Error in RedisDriver.thread_subscribe: {str(e)}")

        return

    @classmethod
    def close_server(cls):
        if hasattr(cls, 'server'):
            cls.server.close()