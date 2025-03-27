import logging
import os

# path = os.path.dirname(os.path.realpath(__file__))

# file_path = f"/system.log"
# if os.environ.get("ENV") == "LOCAL":
#     file_path = "./system.log"
file_path = "./system.log"


class LoggerSetup:

    __logger = logging.getLogger(
        name='s7comm_logger'
    )
    __stream_handler = logging.FileHandler(
        filename=file_path,
        mode='w'
    )

    @classmethod
    def get_logger(cls):
        return cls.__logger

    @classmethod
    def setup(cls):
        current_level = os.environ.get('LOG_LEVEL')
        if current_level == "DEBUG":
            cls.__logger.setLevel(logging.DEBUG)
        else:
            cls.__logger.setLevel(logging.INFO)
        cls.__stream_handler.setFormatter(
            logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%d/%m/%Y %I:%M:%S %p'
            )
        )
        cls.__logger.addHandler(cls.__stream_handler)
