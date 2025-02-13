import time
import struct
import json

# JSON

def json_encode(data):
    # Return JSON plus a newline (simulate text-based framing)
    s = json.dumps(data) + "\n"
    return s.encode('utf-8')

def json_decode(data_bytes):
    # Decode newline-terminated JSON
    s = data_bytes.decode('utf-8').rstrip('\n')
    return json.loads(s)

# BINARY 

def pack_short_string(s):
    b = s.encode('utf-8')
    if len(b) > 255:
        raise ValueError("String too long for a short string")
    return struct.pack("!B", len(b)) + b

def unpack_short_string(b, offset):
    length = b[offset]
    offset += 1
    s = b[offset:offset+length].decode('utf-8')
    offset += length
    return s, offset

def pack_long_string(s):
    b = s.encode('utf-8')
    if len(b) > 65535:
        raise ValueError("String too long for a long string")
    return struct.pack("!H", len(b)) + b

def unpack_long_string(b, offset):
    length = struct.unpack_from("!H", b, offset)[0]
    offset += 2
    s = b[offset:offset+length].decode('utf-8')
    offset += length
    return s, offset

def binary_encode(data: dict):
    cmd = data.get("cmd", 99) & 0xFF  # 1 byte
    username = data.get("from", "")
    to = data.get("to", "")
    message = data.get("body", "")

    # Pack them into a single payload:
    payload = struct.pack("!B", cmd)                # 1 byte for command
    payload += pack_short_string(username)          # short string
    payload += pack_short_string(to)                # short string
    payload += pack_long_string(message)            # long string

    return payload

def binary_decode(payload: bytes):
    offset = 0
    cmd = payload[offset]
    offset += 1
    username, offset = unpack_short_string(payload, offset)
    to, offset = unpack_short_string(payload, offset)
    message, offset = unpack_long_string(payload, offset)
    return {"cmd": cmd, "from": username, "to": to, "body": message}

# Performance comparison

def measure_encoding(data, encode_func, iterations=10000):
    total_size = 0
    start = time.time()
    encoded = None
    for _ in range(iterations):
        encoded = encode_func(data)
        total_size += len(encoded)
    duration = time.time() - start
    avg_size = total_size / iterations
    return avg_size, duration, encoded

def measure_decoding(encoded, decode_func, iterations=10000):
    start = time.time()
    for _ in range(iterations):
        _ = decode_func(encoded)
    duration = time.time() - start
    return duration

def main():
    iterations = 100000
    test_data = {
        "cmd": 3,
        "from": "Alice",
        "to": "Bob",
        "body": "Hello Bob, let's measure how efficient this is!"
    }

    # JSON 
    avg_size_json, enc_time_json, encoded_json = measure_encoding(test_data, json_encode, iterations)
    dec_time_json = measure_decoding(encoded_json, json_decode, iterations)

    # Binary 
    avg_size_bin, enc_time_bin, encoded_bin = measure_encoding(test_data, binary_encode, iterations)
    dec_time_bin = measure_decoding(encoded_bin, binary_decode, iterations)

    print("JSON Implementation:")
    print(f"Average size: {avg_size_json:.2f} bytes")
    print(f"Encoding {iterations} times: {enc_time_json:.6f} seconds")
    print(f"Decoding {iterations} times: {dec_time_json:.6f} seconds")
    print()

    print("Binary (Custom) Implementation:")
    print(f"Average size: {avg_size_bin:.2f} bytes")
    print(f"Encoding {iterations} times: {enc_time_bin:.6f} seconds")
    print(f"Decoding {iterations} times: {dec_time_bin:.6f} seconds")

if __name__ == "__main__":
    main()

#*

# run this file using: python3 comparison.py

# JSON Implementation:
# Average size: 100.00 bytes
# Encoding 100000 times: 0.131819 seconds
# Decoding 100000 times: 0.091265 seconds

# Custom (Binary) Implementation:
# Average size: 60.00 bytes
# Encoding 100000 times: 0.057924 seconds
# Decoding 100000 times: 0.052070 seconds

# In the JSON-based approach, each message encodes fields (like "cmd", "from", "to", and "body")
# into a human-readable text format. While this could be convenient for debugging, it introduces overhead
# from additional punctuation, quotes, and whitespace. As shown in tests, this approach led to 100-byte
# messages on average. Likewise, encoding 100,000 messages took 0.131819 seconds, while decoding them
# took 0.091265 seconds. Although this might be acceptable for small-scale or infrequent communication,
# the overhead becomes more noticeable as messages grow larger or as the system handles a high volume
# of traffic.
#
# By contrast, the fully binary implementation packs the same data with minimal overhead, using only
# short or long length prefixes for each field. This method produced 60-byte messages on average, which is 40%
# smaller than the JSON version, and the encoding and decoding times both improved, at 0.057924 seconds
# and 0.052070 seconds, respectively, for 100,000 messages. In essence, this reduced size lowers bandwidth usage,
# while the faster packing and unpacking can handle more messages with the same resources. Thus, as the
# system scales, the binary solution can serve more users and higher message rates without the additional
# overhead that comes from parsing and generating JSON for several thousands/millions of concurrent users.
#*
