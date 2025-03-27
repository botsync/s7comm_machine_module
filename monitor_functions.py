import json
import time
import threading
import logging
from plc import PLC, PLCConnectionError, PLCOperationError
from call_functions import read_helper, write_helper
from sdk_machine_module.integrator_manager import IntegratorManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StoppableThread(threading.Thread):
    __monitor_threads = {}
    __lock = threading.Lock()
    
    def __init__(self, uid, stop_event, refresh_event, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.uid = uid
        self.stop_event = stop_event
        self.refresh_event = refresh_event
    
    @classmethod
    def check_thread(cls, key):
        with cls.__lock:
            return key in cls.__monitor_threads
    
    @classmethod
    def set_thread(cls, key, thread):
        with cls.__lock:
            cls.__monitor_threads[key] = thread
    
    @classmethod
    def discard_thread(cls, key):
        with cls.__lock:
            thread = cls.__monitor_threads[key]
            thread.stop_event.set()
            del cls.__monitor_threads[key]
    
    @staticmethod
    def reconnect(uid):
        print(uid, "========")
        with StoppableThread.__lock:
            print("acquire lock")
            for thread in StoppableThread.__monitor_threads.values():
                print(thread, "=======", thread.uid)
                thread.refresh_event.set()

def stop_thread(uid, function_name, signal=None):
    key = uid + function_name
    if signal:
        key += signal
        
    if StoppableThread.check_thread(key):
        StoppableThread.discard_thread(key)
        return [True, f"Thread {key} stopped"]
    return [False, f"Thread {key} not found"]

def stop_all_threads(uid):
    with StoppableThread.__lock:
        keys_to_remove = [key for key, thread in StoppableThread.__monitor_threads.items() 
                          if thread.uid == uid]
    
    stopped_count = 0
    for key in keys_to_remove:
        StoppableThread.discard_thread(key)
        stopped_count += 1
    
    return [True, f"Stopped {stopped_count} threads"]

def monitor_on_change(app: IntegratorManager, uid, kargs):
    machine_config = app.get_machine_config(uid=uid)

    def __monitor_on_change(stop_event, refresh_event, uid, kargs, machine_config):
        app.log_statement(f"Monitoring On Change")
        try:
            host = machine_config["host"]
            rack = int(machine_config.get("rack", 0))  
            slot = int(machine_config.get("slot", 1))  
            signals_config = json.loads(machine_config["signals_configuration"])
            
            plc = PLC(host, rack, slot)
            
            monitor_config = signals_config.get("monitor_signals", {})
            if not monitor_config:
                logger.error("No monitor_on_change configuration found")
                return
                
            monitor_on_change_signals = monitor_config.get("on_change")
            prev_values = {}
            
            while not stop_event.is_set():
                try:
                    if refresh_event.is_set():
                        logger.info("Refreshing Connection")
                        plc = PLC(host, rack, slot)
                        refresh_event.clear()
                        
                    response = {}
                    for signal, config in monitor_on_change_signals.items():
                        signal_config = signals_config.get(signal)
                        result = read_helper(signal_config, plc)
                        prev_value = prev_values.get(signal)
                        
                        if prev_value is None or prev_value != result:
                            prev_values[signal] = result
                            response[signal] = result
                            
                            if config.get('ack'):
                                ack_signal = config.get("ack_signal")
                                ack_value = config.get("ack_value", "same")
                                value = ack_value
                                
                                if ack_value == "same":
                                    value = result
                                    
                                ack_signal_config = signals_config.get(ack_signal)
                                write_helper(ack_signal_config, plc, value)
                                
                    if response:
                        app.send_event(event_name="monitor_on_change_response", 
                                      response=json.dumps(response), 
                                      machine_id=uid)
                    time.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Error monitoring on change: {e}")
                    print(f"Error monitoring on change: {e}")
                    time.sleep(1)
                    
        except (PLCConnectionError, PLCOperationError) as e:
            logger.error(f"PLC connection error: {e}")
            print(f"PLC connection error: {e}")
            time.sleep(1)
            
    try:
        key = uid + "monitor_on_change"
        if not StoppableThread.check_thread(key):
            stop_event, refresh_event = threading.Event(), threading.Event()
            thread = StoppableThread(
                uid=uid,
                stop_event=stop_event,
                refresh_event=refresh_event,
                target=__monitor_on_change,
                kwargs={
                    "stop_event": stop_event,
                    "refresh_event": refresh_event,
                    "uid": uid,
                    "kargs": kargs,
                    "machine_config": machine_config
                }
            )
            StoppableThread.set_thread(key, thread)
            thread.daemon = True
            thread.start()
            logger.info(f"Started Monitoring thread for {uid}")
        else:
            logger.info(f"Monitoring thread for {uid} already running")
            StoppableThread.reconnect(uid)
    except Exception as e:
        logger.error(f"Error starting monitoring thread: {e}")
        print(f"Error starting monitoring thread: {e}")
        return [False, str(e)]
        
    return [True, f"Monitoring thread started for {uid}"]

def monitor_continuously(app: IntegratorManager, uid, kargs):
    machine_config = app.get_machine_config(uid=uid)
    print("monitor_continuously_running==================================")
    
    def __monitor_continuously(stop_event, refresh_event, uid, kargs, machine_config):
        app.log_statement(f"Monitoring Continuously")
        try:
            host = machine_config["host"]
            rack = int(machine_config.get("rack", 0))
            slot = int(machine_config.get("slot", 1)) 
            signals_config = json.loads(machine_config["signals_configuration"])
            
            plc = PLC(host, rack, slot)
            
            monitor_config = signals_config.get("monitor_signals", {})
            if not monitor_config:
                logger.error("No monitor_continuous configuration found")
                return
                
            monitor_continuous_signals = monitor_config.get("continuous")
            
            while not stop_event.is_set():
                try:
                    if refresh_event.is_set():
                        logger.info("Refreshing Connection")
                        plc = PLC(host, rack, slot)
                        refresh_event.clear()
                        
                    response = {}
                    for signal, config in monitor_continuous_signals.items():
                        signal_config = signals_config.get(signal)
                        result = read_helper(signal_config, plc)
                        response[signal] = result
                        
                        if config.get('ack'):
                            ack_signal = config.get("ack_signal")
                            ack_value = config.get("ack_value", "same")
                            value = ack_value
                            
                            if ack_value == "same":
                                value = result
                                
                            ack_signal_config = signals_config.get(ack_signal)
                            write_helper(ack_signal_config, plc, value)
                            
                    print("sending event----------", response)
                    app.send_event(event_name="monitor_continuously_response", 
                                  response=json.dumps(response), 
                                  machine_id=uid)
                    time.sleep(5)
                    
                except Exception as e:
                    logger.error(f"Error monitoring continuously: {e}")
                    print(f"Error monitoring continuously: {e}")
                    time.sleep(1)
                    
        except (PLCConnectionError, PLCOperationError) as e:
            logger.error(f"PLC connection error: {e}")
            print(f"PLC connection error: {e}")
            time.sleep(1)
            
    try:
        key = uid + "monitor_continuously"
        if not StoppableThread.check_thread(key):
            stop_event, refresh_event = threading.Event(), threading.Event()
            thread = StoppableThread(
                uid=uid,
                stop_event=stop_event,
                refresh_event=refresh_event,
                target=__monitor_continuously,
                kwargs={
                    "stop_event": stop_event,
                    "refresh_event": refresh_event,
                    "uid": uid,
                    "kargs": kargs,
                    "machine_config": machine_config
                }
            )
            StoppableThread.set_thread(key, thread)
            thread.daemon = True
            thread.start()
            logger.info(f"Started Monitoring thread for {uid}")
        else:
            logger.info(f"Monitoring thread for {uid} already running")
            StoppableThread.reconnect(uid)
    except Exception as e:
        logger.error(f"Error starting monitoring thread: {e}")
        print(f"Error starting monitoring thread: {e}")
        return [False, str(e)]
        
    return [True, f"Monitoring thread started for {uid}"]

MONITOR_FUNCTIONS_MAP = {
    "monitor_on_change": monitor_on_change,
    "monitor_continuously": monitor_continuously,
}