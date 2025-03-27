from logging import getLogger
from threading import Lock
import time
from typing import Dict, Any, Tuple, Union, List
import snap7
from snap7.util import get_bool, get_int, get_real, get_string, set_bool, set_int, set_real, set_string

logger = getLogger(__name__)

class PLCConnectionError(Exception):
    pass

class PLCOperationError(Exception):
    pass

class PLC:
    __instances: Dict[str, 'PLC'] = {}
    __signal_cache: Dict[str, Tuple[float, Any, int]] = {} 
    
    def __new__(cls, host: str, rack: int, slot: int, *args, **kwargs) -> 'PLC':
        key = f"{host}:{rack}:{slot}"
        if key not in cls.__instances:
            instance = super().__new__(cls)
            instance.__initialized = False
            instance._host = host
            instance._rack = rack
            instance._slot = slot
            instance._lock = Lock()
            instance._plc = None
            instance._max_retries = kwargs.get('max_retries', 3)
            instance._retry_delay = kwargs.get('retry_delay', 1.0)
            instance._signal_params = {
                'cache_time': kwargs.get('cache_time', 0.05), 
                'consecutive_reads': kwargs.get('consecutive_reads', 3),
                'max_cache_entries': kwargs.get('max_cache_entries', 1000)  
            }
            
            try:
                instance._initialize_connection()
                cls.__instances[key] = instance
            except PLCConnectionError as e:
                logger.error(f"Failed to initialize PLC connection: {str(e)}")
                raise
            
        return cls.__instances[key]
    
    def _initialize_connection(self) -> None:
        try:
            self._cleanup_connection()
            self._plc = snap7.client.Client()
            self._establish_connection()
        except Exception as e:
            raise PLCConnectionError(f"Failed to initialize connection: {str(e)}")
    
    def _cleanup_connection(self) -> None:
        try:
            if self._plc is not None:
                try:
                    if self._plc.get_connected():
                        self._plc.disconnect()
                except:
                    pass
                finally:
                    try:
                        self._plc.destroy()
                    except:
                        pass
                    self._plc = None
            time.sleep(0.1)
        except Exception as e:
            logger.warning(f"Error during connection cleanup: {str(e)}")
            self._plc = None
    
    def _establish_connection(self) -> None:
        for attempt in range(self._max_retries):
            try:
                if self._plc is None:
                    self._plc = snap7.client.Client()
                
                self._plc.connect(self._host, self._rack, self._slot)
                
                if not self._plc.get_connected():
                    raise PLCConnectionError("Connection failed")
                    
                logger.info(f"Successfully connected to PLC at {self._host}")
                return
                
            except Exception as e:
                if attempt < self._max_retries - 1:
                    logger.warning(f"Connection attempt {attempt + 1} failed: {str(e)}. Retrying in {self._retry_delay} seconds...")
                    self._cleanup_connection()
                    time.sleep(self._retry_delay)
                else:
                    raise PLCConnectionError(f"Failed to connect after {self._max_retries} attempts: {str(e)}")

    def _get_cache_key(self, db_number: int, start_address: int, size: int, bit_address: int = None) -> str:
        return f"{db_number}_{start_address}_{size}_{bit_address if bit_address is not None else 'none'}"
    
    def _cleanup_old_cache(self) -> None:
        current_time = time.time()
        cache_timeout = self._signal_params['cache_time'] * 10  # Keep cache entries for 10x cache time
        
        self.__signal_cache = {
            key: value for key, value in self.__signal_cache.items()
            if current_time - value[0] < cache_timeout
        }
        
        if len(self.__signal_cache) > self._signal_params['max_cache_entries']:
            sorted_cache = sorted(self.__signal_cache.items(), key=lambda x: x[1][0])
            self.__signal_cache = dict(sorted_cache[-self._signal_params['max_cache_entries']:])

    def read_bool(self, db_number: int, start_address: int, bit_address: int) -> bool:
        cache_key = self._get_cache_key(db_number, start_address, 1, bit_address)
        current_time = time.time()
        
        if cache_key in self.__signal_cache:
            timestamp, cached_value, consecutive_reads = self.__signal_cache[cache_key]
            if current_time - timestamp < self._signal_params['cache_time']:
                return cached_value
        
        try:
            self._lock.acquire(timeout=5.0)
            if not self._plc or not self._plc.get_connected():
                self._initialize_connection()
            
            byte_data = self._plc.db_read(db_number, start_address, 1)
            current_value = get_bool(byte_data, 0, bit_address)
            
            if cache_key in self.__signal_cache:
                _, prev_value, consecutive_reads = self.__signal_cache[cache_key]
                
                if current_value != prev_value:
                    self.__signal_cache[cache_key] = (current_time, prev_value, 1)
                    return prev_value
                else:
                    consecutive_reads += 1
                    if consecutive_reads >= self._signal_params['consecutive_reads']:
                        self.__signal_cache[cache_key] = (current_time, current_value, consecutive_reads)
                        return current_value
                    else:
                        self.__signal_cache[cache_key] = (current_time, prev_value, consecutive_reads)
                        return prev_value
            else:
                self.__signal_cache[cache_key] = (current_time, current_value, 1)
                return current_value
            
        except Exception as e:
            logger.error(f"Read bool error: {str(e)}")
            self._cleanup_connection()
            raise PLCOperationError(f"Read bool error: {str(e)}")
        finally:
            try:
                self._lock.release()
            except RuntimeError:
                pass
            self._cleanup_old_cache()

    def write_bool(self, db_number: int, start_address: int, bit_address: int, value: bool, max_retries: int = None) -> None:
        retries = max_retries if max_retries is not None else self._max_retries
        last_error = None
        cache_key = self._get_cache_key(db_number, start_address, 1, bit_address)
        
        for attempt in range(retries):
            try:
                self._lock.acquire(timeout=5.0)
                if not self._plc or not self._plc.get_connected():
                    self._initialize_connection()
                
                # Read current byte to modify the specific bit
                current_data = self._plc.db_read(db_number, start_address, 1)
                set_bool(current_data, 0, bit_address, value)
                self._plc.db_write(db_number, start_address, current_data)
                
                # Invalidate cache
                if cache_key in self.__signal_cache:
                    del self.__signal_cache[cache_key]
                
                return
                
            except Exception as e:
                last_error = e
                logger.warning(f"Write bool attempt {attempt + 1} failed: {str(e)}")
                self._cleanup_connection()
                
                if attempt < retries - 1:
                    time.sleep(self._retry_delay)
                else:
                    logger.error(f"Write bool failed after {retries} attempts: {str(e)}")
                    raise PLCOperationError(f"Write bool failed after {retries} attempts: {str(last_error)}")
            finally:
                try:
                    self._lock.release()
                except RuntimeError:
                    pass

    def read_int(self, db_number: int, start_address: int) -> int:
        """Read 16-bit signed integer (S7 INT type)"""
        cache_key = self._get_cache_key(db_number, start_address, 2, None)
        current_time = time.time()
        
        if cache_key in self.__signal_cache:
            timestamp, cached_value, consecutive_reads = self.__signal_cache[cache_key]
            if current_time - timestamp < self._signal_params['cache_time']:
                return cached_value
        
        try:
            self._lock.acquire(timeout=5.0)
            if not self._plc or not self._plc.get_connected():
                self._initialize_connection()
            
            byte_data = self._plc.db_read(db_number, start_address, 2)
            current_value = get_int(byte_data, 0)
            
            # Apply the same caching logic as for bool
            if cache_key in self.__signal_cache:
                _, prev_value, consecutive_reads = self.__signal_cache[cache_key]
                
                if current_value != prev_value:
                    self.__signal_cache[cache_key] = (current_time, prev_value, 1)
                    return prev_value
                else:
                    consecutive_reads += 1
                    if consecutive_reads >= self._signal_params['consecutive_reads']:
                        self.__signal_cache[cache_key] = (current_time, current_value, consecutive_reads)
                        return current_value
                    else:
                        self.__signal_cache[cache_key] = (current_time, prev_value, consecutive_reads)
                        return prev_value
            else:
                self.__signal_cache[cache_key] = (current_time, current_value, 1)
                return current_value
            
        except Exception as e:
            logger.error(f"Read int error: {str(e)}")
            self._cleanup_connection()
            raise PLCOperationError(f"Read int error: {str(e)}")
        finally:
            try:
                self._lock.release()
            except RuntimeError:
                pass
            self._cleanup_old_cache()

    def read_dint(self, db_number: int, start_address: int) -> int:
        """Read 32-bit signed integer (S7 DINT type)"""
        cache_key = self._get_cache_key(db_number, start_address, 4, None)
        current_time = time.time()
        
        if cache_key in self.__signal_cache:
            timestamp, cached_value, consecutive_reads = self.__signal_cache[cache_key]
            if current_time - timestamp < self._signal_params['cache_time']:
                return cached_value
        
        try:
            self._lock.acquire(timeout=5.0)
            if not self._plc or not self._plc.get_connected():
                self._initialize_connection()
            
            byte_data = self._plc.db_read(db_number, start_address, 4)
            current_value = get_int(byte_data, 0, 'dint')  # dint for 32-bit integer
            
            # Apply caching logic
            if cache_key in self.__signal_cache:
                _, prev_value, consecutive_reads = self.__signal_cache[cache_key]
                
                if current_value != prev_value:
                    self.__signal_cache[cache_key] = (current_time, prev_value, 1)
                    return prev_value
                else:
                    consecutive_reads += 1
                    if consecutive_reads >= self._signal_params['consecutive_reads']:
                        self.__signal_cache[cache_key] = (current_time, current_value, consecutive_reads)
                        return current_value
                    else:
                        self.__signal_cache[cache_key] = (current_time, prev_value, consecutive_reads)
                        return prev_value
            else:
                self.__signal_cache[cache_key] = (current_time, current_value, 1)
                return current_value
            
        except Exception as e:
            logger.error(f"Read dint error: {str(e)}")
            self._cleanup_connection()
            raise PLCOperationError(f"Read dint error: {str(e)}")
        finally:
            try:
                self._lock.release()
            except RuntimeError:
                pass
            self._cleanup_old_cache()

    def write_int(self, db_number: int, start_address: int, value: int, max_retries: int = None, is_dint: bool = False) -> None:
        """Write integer value to PLC (16-bit INT or 32-bit DINT)"""
        size = 4 if is_dint else 2
        retries = max_retries if max_retries is not None else self._max_retries
        last_error = None
        cache_key = self._get_cache_key(db_number, start_address, size, None)
        
        for attempt in range(retries):
            try:
                self._lock.acquire(timeout=5.0)
                if not self._plc or not self._plc.get_connected():
                    self._initialize_connection()
                
                data = bytearray(size)
                if is_dint:
                    set_int(data, 0, value, 'dint')
                else:
                    set_int(data, 0, value)
                
                self._plc.db_write(db_number, start_address, data)
                
                # Invalidate cache
                if cache_key in self.__signal_cache:
                    del self.__signal_cache[cache_key]
                
                return
                
            except Exception as e:
                last_error = e
                logger.warning(f"Write int attempt {attempt + 1} failed: {str(e)}")
                self._cleanup_connection()
                
                if attempt < retries - 1:
                    time.sleep(self._retry_delay)
                else:
                    logger.error(f"Write int failed after {retries} attempts: {str(e)}")
                    raise PLCOperationError(f"Write int failed after {retries} attempts: {str(last_error)}")
            finally:
                try:
                    self._lock.release()
                except RuntimeError:
                    pass

    def read_real(self, db_number: int, start_address: int) -> float:
        """Read 32-bit floating point value (S7 REAL type)"""
        cache_key = self._get_cache_key(db_number, start_address, 4, None)
        current_time = time.time()
        
        if cache_key in self.__signal_cache:
            timestamp, cached_value, consecutive_reads = self.__signal_cache[cache_key]
            if current_time - timestamp < self._signal_params['cache_time']:
                return cached_value
        
        try:
            self._lock.acquire(timeout=5.0)
            if not self._plc or not self._plc.get_connected():
                self._initialize_connection()
            
            byte_data = self._plc.db_read(db_number, start_address, 4)
            current_value = get_real(byte_data, 0)
            
            # Apply caching logic
            if cache_key in self.__signal_cache:
                _, prev_value, consecutive_reads = self.__signal_cache[cache_key]
                
                if abs(current_value - prev_value) > 1e-6:  # Small epsilon for float comparison
                    self.__signal_cache[cache_key] = (current_time, prev_value, 1)
                    return prev_value
                else:
                    consecutive_reads += 1
                    if consecutive_reads >= self._signal_params['consecutive_reads']:
                        self.__signal_cache[cache_key] = (current_time, current_value, consecutive_reads)
                        return current_value
                    else:
                        self.__signal_cache[cache_key] = (current_time, prev_value, consecutive_reads)
                        return prev_value
            else:
                self.__signal_cache[cache_key] = (current_time, current_value, 1)
                return current_value
            
        except Exception as e:
            logger.error(f"Read real error: {str(e)}")
            self._cleanup_connection()
            raise PLCOperationError(f"Read real error: {str(e)}")
        finally:
            try:
                self._lock.release()
            except RuntimeError:
                pass
            self._cleanup_old_cache()

    def write_real(self, db_number: int, start_address: int, value: float, max_retries: int = None) -> None:
        """Write 32-bit floating point value (S7 REAL type)"""
        retries = max_retries if max_retries is not None else self._max_retries
        last_error = None
        cache_key = self._get_cache_key(db_number, start_address, 4, None)
        
        for attempt in range(retries):
            try:
                self._lock.acquire(timeout=5.0)
                if not self._plc or not self._plc.get_connected():
                    self._initialize_connection()
                
                data = bytearray(4)
                set_real(data, 0, value)
                self._plc.db_write(db_number, start_address, data)
                
                # Invalidate cache
                if cache_key in self.__signal_cache:
                    del self.__signal_cache[cache_key]
                
                return
                
            except Exception as e:
                last_error = e
                logger.warning(f"Write real attempt {attempt + 1} failed: {str(e)}")
                self._cleanup_connection()
                
                if attempt < retries - 1:
                    time.sleep(self._retry_delay)
                else:
                    logger.error(f"Write real failed after {retries} attempts: {str(e)}")
                    raise PLCOperationError(f"Write real failed after {retries} attempts: {str(last_error)}")
            finally:
                try:
                    self._lock.release()
                except RuntimeError:
                    pass

    def read_string(self, db_number: int, start_address: int, max_length: int = 254) -> str:
        """Read string value (S7 STRING type)"""
        # S7 strings: 2 bytes header + string content
        # First byte: max length, second byte: actual length
        cache_key = self._get_cache_key(db_number, start_address, max_length + 2, None)
        current_time = time.time()
        
        if cache_key in self.__signal_cache:
            timestamp, cached_value, consecutive_reads = self.__signal_cache[cache_key]
            if current_time - timestamp < self._signal_params['cache_time']:
                return cached_value
        
        try:
            self._lock.acquire(timeout=5.0)
            if not self._plc or not self._plc.get_connected():
                self._initialize_connection()
            
            # Read string header (2 bytes) to get actual length
            header = self._plc.db_read(db_number, start_address, 2)
            actual_length = header[1]  # Second byte contains actual length
            
            # Read the entire string (header + content)
            total_size = min(actual_length + 2, max_length + 2)
            byte_data = self._plc.db_read(db_number, start_address, total_size)
            current_value = get_string(byte_data, 0, actual_length)
            
            # Apply caching logic
            if cache_key in self.__signal_cache:
                _, prev_value, consecutive_reads = self.__signal_cache[cache_key]
                
                if current_value != prev_value:
                    self.__signal_cache[cache_key] = (current_time, prev_value, 1)
                    return prev_value
                else:
                    consecutive_reads += 1
                    if consecutive_reads >= self._signal_params['consecutive_reads']:
                        self.__signal_cache[cache_key] = (current_time, current_value, consecutive_reads)
                        return current_value
                    else:
                        self.__signal_cache[cache_key] = (current_time, prev_value, consecutive_reads)
                        return prev_value
            else:
                self.__signal_cache[cache_key] = (current_time, current_value, 1)
                return current_value
            
        except Exception as e:
            logger.error(f"Read string error: {str(e)}")
            self._cleanup_connection()
            raise PLCOperationError(f"Read string error: {str(e)}")
        finally:
            try:
                self._lock.release()
            except RuntimeError:
                pass
            self._cleanup_old_cache()

    def write_string(self, db_number: int, start_address: int, value: str, max_length: int = 254, max_retries: int = None) -> None:
        """Write string value (S7 STRING type)"""
        retries = max_retries if max_retries is not None else self._max_retries
        last_error = None
        cache_key = self._get_cache_key(db_number, start_address, max_length + 2, None)
        
        for attempt in range(retries):
            try:
                self._lock.acquire(timeout=5.0)
                if not self._plc or not self._plc.get_connected():
                    self._initialize_connection()
                
                # Prepare string data with header
                str_length = min(len(value), max_length)
                data = bytearray(str_length + 2)  # 2 bytes for header
                data[0] = max_length  # First byte: max length
                data[1] = str_length  # Second byte: actual length
                
                # Set string content
                for i, char in enumerate(value[:str_length]):
                    data[i + 2] = ord(char)
                
                self._plc.db_write(db_number, start_address, data)
                
                # Invalidate cache
                if cache_key in self.__signal_cache:
                    del self.__signal_cache[cache_key]
                
                return
                
            except Exception as e:
                last_error = e
                logger.warning(f"Write string attempt {attempt + 1} failed: {str(e)}")
                self._cleanup_connection()
                
                if attempt < retries - 1:
                    time.sleep(self._retry_delay)
                else:
                    logger.error(f"Write string failed after {retries} attempts: {str(e)}")
                    raise PLCOperationError(f"Write string failed after {retries} attempts: {str(last_error)}")
            finally:
                try:
                    self._lock.release()
                except RuntimeError:
                    pass

    def plc_read(self, db_number: int, start_address: int, size: int) -> bytearray:
        try:
            self._lock.acquire(timeout=5.0)
            if not self._plc or not self._plc.get_connected():
                self._initialize_connection()
            
            return self._plc.db_read(db_number, start_address, size)
            
        except Exception as e:
            logger.error(f"Read error: {str(e)}")
            self._cleanup_connection()
            raise PLCOperationError(f"Read error: {str(e)}")
        finally:
            try:
                self._lock.release()
            except RuntimeError:
                pass
    
    def plc_write(self, db_number: int, start_address: int, data: bytearray, max_retries: int = None) -> None:
        retries = max_retries if max_retries is not None else self._max_retries
        last_error = None
        
        for attempt in range(retries):
            try:
                self._lock.acquire(timeout=5.0)
                if not self._plc or not self._plc.get_connected():
                    self._initialize_connection()
                
                self._plc.db_write(db_number, start_address, data)
                
                for cache_key in list(self.__signal_cache.keys()):
                    if cache_key.startswith(f"{db_number}_{start_address}_"):
                        del self.__signal_cache[cache_key]
                        
                return
                
            except Exception as e:
                last_error = e
                logger.warning(f"Write attempt {attempt + 1} failed: {str(e)}")
                self._cleanup_connection()
                
                if attempt < retries - 1:
                    time.sleep(self._retry_delay)
                else:
                    logger.error(f"Write failed after {retries} attempts: {str(e)}")
                    raise PLCOperationError(f"Write failed after {retries} attempts: {str(last_error)}")
            finally:
                try:
                    self._lock.release()
                except RuntimeError:
                    pass
    
    def __del__(self):
        """Cleanup method to properly disconnect from PLC"""
        try:
            self._cleanup_connection()
        except Exception as e:
            logger.error(f"Error during PLC cleanup: {str(e)}")