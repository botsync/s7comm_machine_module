import os
import xmlrpc.client
import ssl

class RPCCLient():

    ___client = None

    @classmethod
    def get_client(cls):
        if not cls.___client:
            workflow_manager_host = os.environ.get('NGINX_HOST', '0.0.0.0')
            workflow_manager_port = int(os.environ.get('NGINX_PORT', 1028))
            env = os.environ.get("ENV", "DEV")
            if env == "DEV":
                cls.__client = xmlrpc.client.ServerProxy(
                    f'http://{workflow_manager_host}:{workflow_manager_port}', allow_none=True
                )
            else:
                cls.__client = xmlrpc.client.ServerProxy(
                    f'https://{workflow_manager_host}:{workflow_manager_port}', allow_none=True,
                    context=ssl._create_unverified_context()
                )
        return cls.__client