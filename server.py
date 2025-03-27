import xmlrpc.server, socketserver
import os, json,yaml
from connection.config import add_machine_config, get_machine_config, delete_machine_config
from response import create_response
from monitor_functions import stop_thread, StoppableThread, MONITOR_FUNCTIONS_MAP
from call_functions import CALL_FUNCTIONS_MAP
from errors import send_error
from logger_setup import LoggerSetup
from app import app
logger = LoggerSetup.get_logger()

class RPCThreading(socketserver.ThreadingMixIn, xmlrpc.server.SimpleXMLRPCServer): 
    pass

class S7commServer():
    
    detail_json = None 
    server = None
    
    def create_server(self):
        port = int(os.environ.get("S7comm_MACHINE_MODULE_PORT", 1029))
        self.server = RPCThreading(("0.0.0.0", port), allow_none=True)
        print("xmlrpc server running at", port)
        
    def yaml_loader():
        if not S7commServer.detail_json:
            with open("machine_detail.yml", "r") as f:
                try:
                    S7commServer.detail_json = yaml.safe_load(f)
                except yaml.YAMLError as exc:
                    print(exc)
        return
    
    @staticmethod
    def get_machine_details(function_type = None, function_name = None):
        S7commServer.yaml_loader()
        details = S7commServer.detail_json
        if function_type:
            if function_name:
                return details.get(function_type).get(function_name)
            else:
                return details.get(function_type)
        return details
    
    @staticmethod
    def get_error_details():
        S7commServer.yaml_loader()
        details = S7commServer.detail_json
        return details.get('errors')
    
    @staticmethod
    def get_options(machine_uid: str, event_name: str, event_type: str, context: str):
        S7commServer.yaml_loader()
        details = S7commServer.detail_json

        if event_type in ["call_events", "monitor_events"]:
            args_key = "rargs"
        elif event_type in ["call_functions", "monitor_functions"]:
            args_key = "kwargs"
        options = (
            details.get(event_type, {})
                   .get(event_name, {})
                   .get(args_key, {})
                   .get(context, {})
                   .get("options", [])
        )
        return json.dumps(options)
    
    @staticmethod
    def add_machine(uid: str, machine_name: str, config: str):
        resp = add_machine_config(uid, machine_name, config)
        StoppableThread.reconnect(uid)
        return [resp, "achine added Successfully"]
    
    @staticmethod
    def delete_machine(uid: str):
        resp = delete_machine_config(uid)
        return [True, resp]
    
    @staticmethod
    def get_machine(uid: str):
        return get_machine_config(uid)
    
    @staticmethod
    def disable_monitor(monitor_name: str, uid: str):
        return stop_thread(uid, function_name=monitor_name)
    
    @staticmethod
    def execute(function_name: str, kargs: str, uid: str):
        machine_config = get_machine_config(uid)
        if len(machine_config.keys()) <= 0:
            raise Exception(f"Machine not found {uid}")
        kargs = json.loads(kargs)
        try:
            func = CALL_FUNCTIONS_MAP.get(function_name)
            if func:
                return func(uid, kargs, machine_config)
            else:
                raise Exception(f"Function not found: {function_name}")
        except Exception as e:
            send_error(uid=uid,error_code="1.1.4",error_message=str(e),error_name="error_executing_function_call")
            create_response(f"{function_name}_response",json.dumps({"success":False}),uid,{})

    @staticmethod
    def execute_monitor(monitor_name: str, kargs: dict, uid:str):
        machine_config = get_machine_config(uid)
        if len(machine_config.keys()) <= 0:
            raise Exception(f"Machine not found: {uid}")
        kargs = json.loads(kargs)
        
        func = MONITOR_FUNCTIONS_MAP.get(monitor_name)
        if func:
            return func(uid, kargs, machine_config)
        else:
            raise Exception(f"Function not found: {monitor_name}")
        
    @staticmethod
    def ping(uid: str):
        if not uid:
            return False
        else:
            config = get_machine_config(uid)
            if config and type(config) == dict:
                return True
            else:
                return False



    def register_function(self):
        if self.server:
            self.server.register_function(self.get_machine_details)
            self.server.register_function(self.get_error_details)
            self.server.register_function(self.execute)
            self.server.register_function(self.execute_monitor)
            self.server.register_function(self.add_machine)
            self.server.register_function(self.delete_machine)
            self.server.register_function(self.ping)
            self.server.register_function(self.get_options)
            self.server.register_function(self.disable_monitor)
            self.server.register_function(self.get_machine)
            
    def start_server(self):
        self.server.serve_forever()

if __name__ == "__main__":

    for key,fun in CALL_FUNCTIONS_MAP.items():
        app.register_call_function(key,fun)
    for key,fun in MONITOR_FUNCTIONS_MAP.items():
        app.register_monitor_function(key,fun)
    
    app.start()