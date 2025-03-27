import json
import time
from app import app
from response import create_response
from logger_setup import LoggerSetup
from typing import Dict, Any, Union, List, Tuple
from plc import PLC, PLCConnectionError, PLCOperationError

logger = LoggerSetup.get_logger()

def write_helper(signal_config, plc, value):
    try:
        db_number = signal_config.get("db_number")
        offset = signal_config.get("offset")
        signal_type = signal_config.get("type")
        bit_pos = signal_config.get("bit_pos")
        max_string_length = signal_config.get("max_length", 254) 

        if db_number is None or offset is None or signal_type is None:
            raise ValueError(f"Invalid signal configuration: {signal_config}")
        
        db_number = int(db_number)
        offset = int(offset)
        
        if signal_type == "bool":
            if bit_pos is None:
                raise ValueError("Bit position not specified for boolean signal")
            bit_pos = int(bit_pos)
            value = bool(value)
            plc.write_bool(db_number, offset, bit_pos, value)
        elif signal_type == "int":
            value = int(value)
            plc.write_int(db_number, offset, value, is_dint=False)
        elif signal_type == "dint":
            value = int(value)
            plc.write_int(db_number, offset, value, is_dint=True)
        elif signal_type == "real":   
            value = float(value)
            plc.write_real(db_number, offset, value)
        elif signal_type == "string":
            value = str(value)
            plc.write_string(db_number, offset, value, max_length=max_string_length)
        else:
            raise ValueError(f"Unsupported signal type: {signal_type}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error in write_helper: {e}")
        raise

def read_helper(signal_config, plc):
    try:
        db_number = signal_config.get("db_number")
        offset = signal_config.get("offset")
        signal_type = signal_config.get("type")
        bit_pos = signal_config.get("bit_pos")
        max_string_length = signal_config.get("max_length", 254) 

        if db_number is None or offset is None or signal_type is None:
            raise ValueError(f"Invalid signal configuration: {signal_config}")
        
        db_number = int(db_number)
        offset = int(offset)
        
        if signal_type == "bool":
            if bit_pos is None:
                raise ValueError("Bit position not specified for boolean signal")
            bit_pos = int(bit_pos)
            value = plc.read_bool(db_number, offset, bit_pos)
        elif signal_type == "int":
            value = plc.read_int(db_number, offset)
        elif signal_type == "dint":
            value = plc.read_dint(db_number, offset)
        elif signal_type == "real":
            value = plc.read_real(db_number, offset)
        elif signal_type == "string":
            value = plc.read_string(db_number, offset, max_length=max_string_length)
        else:
            raise ValueError(f"Unsupported signal type: {signal_type}")
        
        return value
        
    except Exception as e:
        logger.error(f"Error in read_helper: {e}")
        raise

def send_signal(uid, kargs):
    machine_config = app.get_machine_config(uid)
    if machine_config is None:
        raise Exception("Machine configuration is missing")
    
    try:
        host = machine_config['host']
        rack = int(machine_config.get('rack', 0))
        slot = int(machine_config.get('slot', 1))
        signals_config = json.loads(machine_config["signals_configuration"])
        
        signal_name = kargs.get("signal")
        value = kargs.get("value")
        
        if isinstance(value, str) and value.lower() in ("true", "false"):
            value = value.lower() == "true"
        elif isinstance(value, (int, float)):
            pass
        else:
            try:
                value = int(value)
            except (ValueError, TypeError):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = bool(value)
        
        plc = PLC(host, rack, slot)
        
        signal_config = signals_config.get(signal_name)
        if signal_config is None:
            raise ValueError(f"Invalid signal: {signal_name}")

        success = write_helper(signal_config, plc, value)
        
        response_json = {
            "signal": str(signal_name),
            "success": bool(success)
        }
        
        return create_response("send_signal_response", response=response_json, uid=uid)
    
    except Exception as e:
        logger.error(f"Error sending signal: {e}")
        response_json = {
            "signal": str(kargs.get("signal", "")),
            "success": False,
            "error": str(e)
        }
        return create_response("send_signal_response", response=response_json, uid=uid)

def read_signal(uid, kargs):
    machine_config = app.get_machine_config(uid)
    if machine_config is None:
        raise Exception("Machine configuration is missing")
    
    try:
        host = machine_config['host']
        rack = int(machine_config.get('rack', 0)) 
        slot = int(machine_config.get('slot', 1)) 
        signals_config = json.loads(machine_config["signals_configuration"])
        
        signal_name = kargs.get("signal")
        
        plc = PLC(host, rack, slot)
        
        signal_config = signals_config.get(signal_name)
        if signal_config is None:
            raise ValueError(f"Invalid signal: {signal_name}")
        
        value = read_helper(signal_config, plc)
        
        response_json = {
            "signal": str(signal_name),
            "value": value
        }
        
        return create_response("read_signal_response", response=response_json, uid=uid)
    
    except Exception as e:
        logger.error(f"Error reading signal: {e}")
        response_json = {
            "signal": str(kargs.get("signal", "")),
            "value": None,
            "error": str(e)
        }
        return create_response("read_signal_response", response=response_json, uid=uid)

def send_multiple_signals(uid, kargs):
    machine_config = app.get_machine_config(uid)
    if machine_config is None:
        raise Exception("Machine configuration is missing")
    
    try:
        signals = kargs.get("signals")
        values = kargs.get("values")
        
        if isinstance(values, str):
            values = json.loads(values)
        if isinstance(signals, str):
            signals = json.loads(signals)
        if not isinstance(signals, list):
            signals = [signals]
        if not isinstance(values, list):
            values = [values]
        
        if len(signals) != len(values):
            raise ValueError("Number of signals must match number of values")
        
        host = machine_config['host']
        rack = int(machine_config.get('rack', 0))
        slot = int(machine_config.get('slot', 1))
        signals_config = json.loads(machine_config["signals_configuration"])
        
        plc = PLC(host, rack, slot)
        
        results = {}
        for signal_name, value in zip(signals, values):
            try:
                signal_config = signals_config.get(signal_name)
                if signal_config is None:
                    raise ValueError(f"Invalid signal: {signal_name}")

                success = write_helper(signal_config, plc, value)
                results[signal_name] = success
            except Exception as e:
                logger.error(f"Error sending signal {signal_name}: {e}")
                results[signal_name] = False
        
        success = all(results.values())
        
        response_json = {
            "success": success,
            "results": results
        }
        
        return create_response("send_multiple_signals_response", response=response_json, uid=uid)
    
    except Exception as e:
        logger.error(f"Error sending multiple signals: {e}")
        response_json = {
            "success": False,
            "error": str(e)
        }
        return create_response("send_multiple_signals_response", response=response_json, uid=uid)

def read_multiple_signals(uid, kargs):
    machine_config = app.get_machine_config(uid)
    if machine_config is None:
        raise Exception("Machine configuration is missing")
    
    try:
        signals = kargs.get("signals")
        
        if isinstance(signals, str):
            signals = json.loads(signals)
        if not isinstance(signals, list):
            signals = [signals]
        
        host = machine_config['host']
        rack = int(machine_config.get('rack', 0))
        slot = int(machine_config.get('slot', 1))
        signals_config = json.loads(machine_config["signals_configuration"])
        
        plc = PLC(host, rack, slot)
        
        results = {}
        for signal_name in signals:
            try:
                signal_config = signals_config.get(signal_name)
                if signal_config is None:
                    raise ValueError(f"Invalid signal: {signal_name}")

                value = read_helper(signal_config, plc)
                results[signal_name] = value
            except Exception as e:
                logger.error(f"Error reading signal {signal_name}: {e}")
                results[signal_name] = None
        
        response_json = results
        
        return create_response("read_multiple_signals_response", response=response_json, uid=uid)
    
    except Exception as e:
        logger.error(f"Error reading multiple signals: {e}")
        response_json = {
            "error": str(e)
        }
        return create_response("read_multiple_signals_response", response=response_json, uid=uid)

CALL_FUNCTIONS_MAP = {
    "send_signal": send_signal,
    "read_signal": read_signal,
    "send_multiple_signals": send_multiple_signals,
    "read_multiple_signals": read_multiple_signals
}