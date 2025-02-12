import struct

HEADER_FORMAT = "!BH"  
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  

CMD_LOGIN        = 1
CMD_CREATE       = 2
CMD_SEND         = 3
CMD_READ         = 4
CMD_DELETE_MSG   = 5
CMD_VIEW_CONV    = 6
CMD_DELETE_ACC   = 7
CMD_LOGOFF       = 8
CMD_CLOSE        = 9  
CMD_CHAT         = 10
CMD_LIST         = 11
CMD_READ_ACK     = 12  

# Helper functions for packing and unpacking strings

def pack_short_string(s):
    b = s.encode('utf-8')  # Convert the string to bytes using UTF-8 encoding
    if len(b) > 255:
        raise ValueError("String too long for short string (exceeds 255 bytes).")
    # Pack the length as one byte followed by the actual bytes of the string
    return struct.pack("!B", len(b)) + b

def pack_list(wildcard="*"):
    return pack_short_string(wildcard)

def unpack_short_string(data, offset):
    length = struct.unpack_from("!B", data, offset)[0]
    offset += 1
    s = data[offset:offset+length].decode('utf-8') 
    # Update offset past the string bytes
    offset += length  
    return s, offset

def pack_long_string(s):
    b = s.encode('utf-8')  
    if len(b) > 65535:
        raise ValueError("String too long for long string (exceeds 65535 bytes).")
    # Pack the length as two bytes followed by the string bytes
    return struct.pack("!H", len(b)) + b

def unpack_long_string(data, offset):
    length = struct.unpack_from("!H", data, offset)[0]
    offset += 2  
    s = data[offset:offset+length].decode('utf-8') 
    offset += length
    return s, offset

def encode_message(cmd, payload_bytes):
    # Build the header by packing the command and the length of the payload
    header = struct.pack(HEADER_FORMAT, cmd, len(payload_bytes))
    return header + payload_bytes

def decode_message(sock):
    # Read the header from the socket
    header = b""
    while len(header) < HEADER_SIZE:
        chunk = sock.recv(HEADER_SIZE - len(header))
        if not chunk:
            raise Exception("Connection closed while reading header.")
        header += chunk

    cmd, payload_len = struct.unpack(HEADER_FORMAT, header)
    
    # Read the payload based on the length specified in the header
    payload = b""
    while len(payload) < payload_len:
        # Receive remaining payload bytes from the socket
        chunk = sock.recv(payload_len - len(payload))
        if not chunk:
            raise Exception("Connection closed while reading payload.")
        payload += chunk
    return cmd, payload
