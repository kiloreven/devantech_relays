import re
import socket
from logging import getLogger
from typing import Optional

logger = getLogger()


# Reference table for the ETH8020 (for which this module was originally developed for)
# (source: http://www.robot-electronics.co.uk/htm/eth8020tech.htm)
# +-----+-----+----------------------------------------------------------------+---------------------------+---------+
# |  Command  |                                 Action                         |          Return           | Implem- |
# | dec | hex |                                                                |                           |  ented  |
# +-----+-----+----------------------------------------------------------------+---------------------------+---------+
# | 16  | 10  | Get Module Info - returns 3 bytes. Module Id (21 for ETH8020), | Module ID (1 byte),       |         |
# |     |     | Hardware version, Firmware version.                            | HW version (1 byte)       |    x    |
# |     |     |                                                                | FW version (1 byte)       |         |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 32  | 20  | Digital Active - follow with 1-20 to set relay on, then a time |                           |         |
# |     |     | for pulsed output from 1-255 (100ms resolution) or 0 for       | 1 bit: 1/0 = success/fail |    x    |
# |     |     | permanent                                                      |                           |         |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 33  | 21  | Digital Inactive - follow with 1-20 to turn relay off, then a  | 1 bit: 1/0 = success/fail |         |
# |     |     | time for pulsed output from 1-255 (100ms resolution) or 0 for  |                           |    x    |
# |     |     | permanent                                                      |                           |         |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 35  | 23  | Digital Set Outputs - follow with 3 bytes, first byte will set |                           |         |
# |     |     | relays 1-8, All on = 255 (0xFF), All off = 0, 2nd byte for     | 1 bit: 1/0 = success/fail |         |
# |     |     | relays 9-16, 3rd byte for relays 17-20                         |                           |         |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 36  | 24  | Digital Get Outputs - returns 3 bytes, the first corresponds   | 3 bytes:                  |         |
# |     |     | with relays 1-8, 2nd byte for relays 9-16, 3rd byte for        |     1st: relay 1-8        |         |
# |     |     | relays 17-20                                                   |     2nd; relay 9-16       |         |
# |     |     |                                                                |     3rd: relay 17-20      |         |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 37  | 25  | Digital Get Inputs - returns 4 bytes, the first three bytes    | 4 bytes:                  |         |
# |     |     | are always 0, the 4th bytes bits correspond with the 8 digital |     1st-3rd: 0            |         |
# |     |     | inputs, a high bit meaning input is active (driven low)        |     4th: Digital IO 1-8   |         |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 50  | 32  | Get Analogue Voltage - follow with 1-8 for channel and ETH8020 |                           |         |
# |     |     | will respond with 2 bytes to form an 16-bit integer (high byte |                           |         |
# |     |     | first)                                                         |                           |         |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 58  | 3A  | ASCII text commands (V4+) - allows a text string to switch     |                           |         |
# |     |     | outputs, see section below                                     |                           |         |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 119 | 77  | Get Serial Number - Returns the unique 6 byte MAC address of   |                           |         |
# |     |     | the module.                                                    |                           |         |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 120 | 78  | Get Volts - returns relay supply voltage as byte, 125 being    |                           |         |
# |     |     | 12.5V DC                                                       |                           |         |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 121 | 79  | Password Entry - see TCP/IP password                           |                           |    x    |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 122 | 7A  | Get Unlock Time - see section below                            |                           |    x    |
# +-----+-----+----------------------------------------------------------------+---------------------------+         |
# | 123 | 7B  | Log Out - immediately re-enables TCP/IP password protection    |                           |    x    |
# +-----+-----+----------------------------------------------------------------+---------------------------+---------+

# Will turn off print messages
DEBUG = False

COMMANDS = {
    'get_module_info':  '\x10',
    'set_relay_on':     '\x20',
    'set_relay_off':    '\x21',
    'set_relay_state':  '\x23',
    'get_relay_state':  '\x24',
    'get_analog_value': '\x32',
    'ascii_command':    '\x3a',
    'get_mac_address':  '\x77',
    'get_volts':        '\x78',
    'send_password':    '\x79',
    'get_unlock_time':  '\x7a',
    'log_out':          '\x7b',
}

MODELS = {
    18: {
        'name': 'ETH002',
        'relays': 2,
        'digital_io': 0,
        'analog_input': 0
    },

    19: {
        'name': 'ETH008',
        'relays': 8,
        'digital_io': 0,
        'analog_input': 0
    },

    20: {
        'name': 'ETH484',
        'relays': 4,
        'digital_io': 8,
        'analog_input': 4
    },

    21: {
        'name': 'ETH8020',
        'relays': 20,
        'digital_io': 0,
        'analog_input': 8
    },

    29: {
        'name': 'ETH044',
        'relays': 4,
        'digital_io': 4,
        'analog_input': 0
    }
}


def string_only_contains_bits(string):
    """
    Check if a string only contains bits (0s and 1s)
    """
    search = re.compile(r'^[01]*$').search
    return bool(search(string))


def hex_to_int(data: str) -> int:
    return int(data.encode('utf-8').hex(), 16)


def int_to_hex(data):
    return chr(data)


def bitstring_to_hex(bitstring):
    hex_string = ''

    # Typos to avoid using reserved namespace \o/
    _bytes = [bitstring[x:x+8] for x in range(0, len(bitstring), 8)]
    for byte in _bytes:
        hex_string += chr(int(byte[::-1], 2))

    return hex_string


def hex_to_bitstring(hex_string):
    bitstring = ''
    
    for byte in hex_string:
        bitstring += bin(hex_to_int(byte))[2:].zfill(8)[::-1]

    return bitstring


class ETHRelay:
    model_id: int
    software_version: int
    firmware_version: int

    no_relays: int
    no_digital_io: int
    no_analog_input: int
    model_name: str

    sock: socket.socket
    connected: bool = False

    def __init__(self, ip, port=17494, password=None):
        self.ip = ip
        self.port = port
        self.password = password

        self.connect(ip, port, password)
        self.get_module_info()
        if self.no_relays > 0:
            self.states = self.get_multiple_relays_state()
        else:
            self.states = {}

    def connect(self, ip, port, password=None):
        """
        Try to connect to a module using the inputted parameters.

        Return values:
            True/False: Whether the connection was successful or not
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        # Let's try to connect
        try:
            self.sock.connect((ip, port))
        except Exception as e:
            # The connection could fail for a multitude of reasons, in which
            # we will propagate any exception thrown by socket up the stack
            # by printing the exception
            logger.error(str(e))
            self.sock.close()
            return False
            
        # At this point we have a socket connection, and we must authenticate
        # against the module if it requires so
        if not self.get_unlock_time:
            # If this is false, we need to authenticate with password
            unlocked = self.unlock(password)
            if not unlocked:
                if DEBUG:
                    print("Failed to unlock module. Try again.")
                return False
            
            self.connected = True

        return True

    def disconnect(self):
        try:
            self.lock()
            self.sock.close()
        except Exception as e:
            logger.error(str(e))
        logger.debug("Relay disconnected")
        return True
        
    def bitstring_to_dict(self, bitstring):
        """
        Turn a bitstring (like '10010111') into a dict like {1: True, 2: False ...}
        for easier processing of the bit values based on their position
        """
    
        vals = {}
        for i, val in enumerate(bitstring):
            # Make sure we don't think we have more relays than we actually have
            if i >= self.no_relays:
                break
            vals[i+1] = bool(int(val))
        
        return vals

    def dict_to_bitstring(self, _dict: dict[int, str]):
        """
        Turn a dict (with integers as keys) into a bitstring
        """
        # Dirtily validate the keys
        for k in _dict.keys():
            if not isinstance(k, int):
                logger.warning(f"Value {k} is not integer (it is {type(k)})")
                return False
            elif k > self.no_relays:
                logger.warning("Value {k} too large; number of relays on this module is {self.no_relays}")

        vals = ''
        # We want to iterate through the three bytes of data we might end up sending
        for i in range(1, 25):
            vals += str(int(_dict.get(i, False)))

        return vals

    def send_command(self, command: str, value: Optional[str] = None, number_of_bytes: int = 1):
        """
        number_of_bytes
            This is the number of bytes we should expect back from the read function.
            Most cases, we will expect a 1-byte response (default) but it can also be
            easily overridden to expect a different response length.
        """
        if value:
            command = command + value
        try:
            self.sock.sendall(command.encode("utf-8"))
        except Exception as e:
            logger.error(f"Error sending command to relay ({e})")

        return self.read_command_result(number_of_bytes)

    def read_command_result(self, number_of_bytes: int) -> str:
        """
        Read the number of bytes from the socket
        """
        chunks = []
        number_of_bytes_received = 0
        while number_of_bytes_received < number_of_bytes:
            print(f"Getting byte {number_of_bytes_received+1}")
            chunk = self.sock.recv(min(number_of_bytes - number_of_bytes_received, 2048))
            if chunk == '':
                logger.error("Error reading message - premature end of message")
                raise RuntimeError("socket connection broken")
            print(chunk)
            chunks.append(chunk)
            number_of_bytes_received += len(chunk)
        logger.debug(f"Chunks:, {[x.hex() for x in chunks]}")
        return ''.join([chunk.decode("utf-8") for chunk in chunks])

    def get_module_info(self):
        """
        Get info about our module and store it as attributes of self
        """
        result = self.send_command(COMMANDS['get_module_info'], number_of_bytes=3)
        self.model_id = hex_to_int(result[0])
        self.software_version = hex_to_int(result[1])
        self.firmware_version = hex_to_int(result[2])

        try:
            model = MODELS[self.model_id]
        except AttributeError:
            logger.debug(f"Invalid model: {self.model_id} is not defined in MODELS.")
            return False

        self.no_relays = model['relays']
        self.no_digital_io = model['digital_io']
        self.no_analog_input = model['analog_input']
        self.model_name = model['name']

        return True

    def get_unlock_time(self):
        """
        If locked and require password:
            Returns False
        If unlocked and will not become locked:
            Returns True
        If unlocked and will lock in a number of seconds
            Returns the time before the module will lock
        """
        result = self.send_command(COMMANDS['get_unlock_time'])
        if result[0] == 0:
            # The module is locked and needs to be unlocked
            return False
        elif result[0] == 255:
            # The module does not require password
            return True
        else:
            # The module tends to require password, but is unlocked
            return result[0]

    def unlock(self, password):
        """
        Send a password to the module to unlock it
        """
        result = self.send_command(COMMANDS['send_password'], value=password)
        
        if result[0] == 1:
            if DEBUG:
                print("Wrong password")
            self.sock.close()
            return False
        else:
            return True

    def lock(self):
        """
        Send a command to log out from the module
        """
        result = self.send_command(COMMANDS['log_out'])
        success = result[0]
        if success:
            return True
        else:
            return False

    def set_relay_on(self, relay, pulse=0):
        """
        Set the state of a single relay. This function can also trigger
        pulse the relay. The pulse value is defined in the range of 1-255,
        and translates to multiples of 100ms (100ms to 25.5s)
        """
        if pulse < 0 or pulse > 255:
            return False

        # The set_replay_on-command requires the number of the relay and an
        # optional pulse value in the range of 0 and 255
        values = str(relay) + str(pulse)
        
        # And this is a three-byte command (command + relay + pulse), so we
        # need to specify that to send_command
        result = self.send_command(COMMANDS['set_relay_on'], values)
        
        if result[0]:
            return True
        else:
            return False

    def set_relay_off(self, relay, pulse=0):
        """
        Set the state of a single relay. This function can also trigger
        pulse the relay. The pulse value is defined in the range of 1-255,
        and translates to multiples of 100ms (100ms to 25.5s)
        """
        if pulse < 0 or pulse > 255:
            return False

        # The set_replay_on-command requires the number of the relay and an
        # optional pulse value in the range of 0 and 255
        values = str(relay) + str(pulse)
        result = self.send_command(COMMANDS['set_relay_off'], values)
        
        if result[0]:
            return True
        else:
            return False

    def set_multiple_relays_state(self, _dict):
        """
        Take a dict of relay states, turn it into a bitstring and send it off
        to the relay to turn stuff on or off.
        """
        bitstring = self.dict_to_bitstring(_dict)
        hex_string = bitstring_to_hex(bitstring)
        result = self.send_command(COMMANDS['set_relay_state'], hex_string)
        if DEBUG:
            print("Setting values, bitstring %s" % bitstring)

        if result[0]:
            return True
        else:
            return False

    def set_relay_state(self, relay, state, turn_off_rest=False):
        """
        turn_off_rest:
            Set all the other relays to open. The module usually does
            this by default
        """
        
        if turn_off_rest:
            result = self.set_multiple_relays_state({relay: state})
        else:
            states = self.states
            states[relay] = state
            result = self.set_multiple_relays_state(states)
            self.states = states

        return result

    def get_multiple_relays_state(self):
        """
        Ask the module to tell us about the state of all the relays
        """
        result = self.send_command(COMMANDS['get_relay_state'], number_of_bytes=3)
        bitstring = hex_to_bitstring(result)
        
        if result:
            return self.bitstring_to_dict(bitstring)
        else:
            return False

    def get_relay_state(self, relay):
        """
        Ask the module to tell us about the state of all the relays and find one of the relys
        """
        bitstring = self.get_multiple_relays_state()
        return bool(int(bitstring[relay]))
