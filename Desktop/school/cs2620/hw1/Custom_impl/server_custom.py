import socket
import struct
import fnmatch
import threading
import datetime
import hashlib

from protocol_custom import (
    HEADER_SIZE,
    CMD_LOGIN, CMD_CREATE, CMD_SEND, CMD_READ,
    CMD_DELETE_MSG, CMD_VIEW_CONV, CMD_DELETE_ACC, CMD_LOGOFF, CMD_CLOSE,
    CMD_CHAT, CMD_LIST, CMD_READ_ACK,
    encode_message, decode_message,
    pack_short_string, pack_long_string,
    unpack_short_string, unpack_long_string
)

CMD_DELETE = CMD_DELETE_ACC 

# Data stores for user info, active connections, and conversation history
users = {}         
active_users = {} 
conversations = {} 
next_message_id = 1

def get_matching_users(wildcard="*"):
    # Return list of usernames matching the given wildcard pattern
    return fnmatch.filter(list(users.keys()), wildcard)

def handle_client(conn, addr):
    global next_message_id
    print(f"[NEW CONNECTION] {addr} connected.")
    try:
        while True:
            # Decode the incoming command and its payload from the client
            cmd, payload = decode_message(conn)

            if cmd == CMD_LOGIN:
                offset = 0
                username, offset = unpack_short_string(payload, offset)
                password, offset = unpack_short_string(payload, offset)
                if username not in users:
                    resp = "Username does not exist"
                else:
                    stored_hash = users[username]["password_hash"]
                    hashed = hashlib.sha256(password.encode("utf-8")).hexdigest()
                    if hashed != stored_hash:
                        resp = "Incorrect password"
                    else:
                        active_users[username] = conn
                        unread_count = len(users[username]["messages"])
                        resp = f"Login successful. Unread messages: {unread_count}"
                conn.sendall(encode_message(CMD_LOGIN, pack_short_string(resp)))

            elif cmd == CMD_CREATE:
                # Extract username and password and create new user if not exists
                offset = 0
                username, offset = unpack_short_string(payload, offset)
                password, offset = unpack_short_string(payload, offset)
                if username in users:
                    resp = "Username already exists"
                else:
                    hashed = hashlib.sha256(password.encode("utf-8")).hexdigest()
                    users[username] = {"password_hash": hashed, "messages": []}
                    resp = "Account created"
                conn.sendall(encode_message(CMD_CREATE, pack_short_string(resp)))

            elif cmd == CMD_LIST:
                offset = 0
                wildcard = unpack_short_string(payload, offset)[0] if payload else "*"
                matching = fnmatch.filter(list(users.keys()), wildcard)
                matching_str = ",".join(matching)
                conn.sendall(encode_message(CMD_LIST, pack_long_string(matching_str)))

            elif cmd == CMD_SEND:
                # Get sender, recipient, and message text
                offset = 0
                sender, offset = unpack_short_string(payload, offset)
                recipient, offset = unpack_short_string(payload, offset)
                msg_text, offset = unpack_long_string(payload, offset)
                # Record message in conversation history with timestamp and unique ID
                conv_key = tuple(sorted([sender, recipient]))
                if conv_key not in conversations:
                    conversations[conv_key] = []
                timestamp = datetime.datetime.now().isoformat()
                message_entry = {"id": next_message_id, "sender": sender, "message": msg_text, "timestamp": timestamp}
                next_message_id += 1
                conversations[conv_key].append(message_entry)
                # If recipient exists and is active, deliver message immediately; otherwise, store as unread
                if recipient not in users:
                    resp = "Recipient not found"
                else:
                    if recipient in active_users:
                        try:
                            live_payload = pack_short_string(sender) + pack_long_string(msg_text)
                            active_users[recipient].sendall(encode_message(CMD_CHAT, live_payload))
                        except Exception:
                            users[recipient]["messages"].append({"sender": sender, "message": msg_text})
                    else:
                        users[recipient]["messages"].append({"sender": sender, "message": msg_text})
                    resp = "Message sent"
                conn.sendall(encode_message(CMD_SEND, pack_short_string(resp)))

            elif cmd == CMD_READ:
                # Send unread messages to the user, up to an optional limit
                offset = 0
                username, offset = unpack_short_string(payload, offset)
                limit = struct.unpack_from("!B", payload, offset)[0] if offset < len(payload) else 0
                if username not in users:
                    resp = "User not found"
                    conn.sendall(encode_message(CMD_READ, pack_long_string(resp)))
                else:
                    msgs = users[username]["messages"]
                    msgs_to_send = msgs[:limit] if limit > 0 else msgs
                    users[username]["messages"] = msgs[limit:] if limit > 0 else []
                    if not msgs_to_send:
                        conn.sendall(encode_message(CMD_READ, pack_long_string("NO_MESSAGES")))
                    else:
                        for message in msgs_to_send:
                            one_msg = pack_short_string(message["sender"]) + pack_long_string(message["message"])
                            conn.sendall(encode_message(CMD_READ, one_msg))
                        conn.sendall(encode_message(CMD_READ, pack_long_string("END_OF_MESSAGES")))

            elif cmd == CMD_DELETE_MSG:
                # Supports deleting from conversation or unread messages
                try:
                    offset = 0
                    username, offset = unpack_short_string(payload, offset)
                    if len(payload) - offset >= 1:
                        potential_other_len = payload[offset]
                        if potential_other_len != 0 and (len(payload) - offset >= 1 + potential_other_len):
                            other_user, offset = unpack_short_string(payload, offset)
                            if len(payload) - offset < 1:
                                raise ValueError("Not enough bytes for count")
                            count = struct.unpack_from("!B", payload, offset)[0]
                            offset += 1
                            if len(payload) - offset < count:
                                raise ValueError("Not enough bytes for message IDs")
                            ids_to_delete = [struct.unpack_from("!B", payload, offset + i)[0] for i in range(count)]
                            offset += count
                            conv_key = tuple(sorted([username, other_user]))
                            if conv_key not in conversations:
                                resp = "No conversation found"
                            else:
                                conv = conversations[conv_key]
                                conversations[conv_key] = [msg for msg in conv if msg.get("id") not in ids_to_delete]
                                resp = "Specified conversation messages deleted"
                            conn.sendall(encode_message(CMD_DELETE_MSG, pack_short_string(resp)))
                            continue

                    if len(payload) - offset < 1:
                        raise ValueError("Not enough bytes for count in unread deletion")
                    count = struct.unpack_from("!B", payload, offset)[0]
                    offset += 1
                    indices = [struct.unpack_from("!B", payload, offset + i)[0] for i in range(count)]
                    offset += count
                    if username not in users:
                        resp = "User not found"
                    else:
                        current_msgs = users[username]["messages"]
                        users[username]["messages"] = [msg for i, msg in enumerate(current_msgs) if i not in indices]
                        resp = "Specified messages deleted"
                    conn.sendall(encode_message(CMD_DELETE_MSG, pack_short_string(resp)))
                except Exception as e:
                    print("Error in CMD_DELETE_MSG:", e)
                    resp = "Error processing delete message command"
                    conn.sendall(encode_message(CMD_DELETE_MSG, pack_short_string(resp)))

            elif cmd == CMD_VIEW_CONV:
                # Return formatted conversation history between two users
                offset = 0
                username, offset = unpack_short_string(payload, offset)
                other_user, offset = unpack_short_string(payload, offset)
                if other_user not in users:
                    resp = "User not found"
                    conn.sendall(encode_message(CMD_VIEW_CONV, pack_short_string(resp)))
                else:
                    conv_key = tuple(sorted([username, other_user]))
                    conv = conversations.get(conv_key, [])
                    if not conv:
                        resp = "No conversation history found"
                        conn.sendall(encode_message(CMD_VIEW_CONV, pack_long_string(resp)))
                    else:
                        formatted = ""
                        for msg in conv:
                            formatted += f"[ID {msg.get('id', '?')}] [{msg.get('timestamp', '')}] {msg.get('sender', '')}: {msg.get('message', '')}\n"
                        conn.sendall(encode_message(CMD_VIEW_CONV, pack_long_string(formatted)))

            elif cmd == CMD_DELETE:
                # Remove user from records and active users
                offset = 0
                username, offset = unpack_short_string(payload, offset)
                if username not in users:
                    resp = "User does not exist"
                else:
                    del users[username]
                    if username in active_users:
                        del active_users[username]
                    resp = "Account deleted"
                conn.sendall(encode_message(CMD_DELETE, pack_short_string(resp)))

            elif cmd == CMD_LOGOFF:
                # Log off the user
                offset = 0
                username, offset = unpack_short_string(payload, offset)
                if username in active_users:
                    del active_users[username]
                resp = "User logged off"
                conn.sendall(encode_message(CMD_LOGOFF, pack_short_string(resp)))

            elif cmd == CMD_CLOSE:
                print(f"[DISCONNECT] {addr} requested close.")
                break

            else:
                resp = "Unknown command"
                conn.sendall(encode_message(0, pack_short_string(resp)))
    except Exception as e:
        print(f"Error handling client {addr}: {e}")
    finally:
        conn.close()
        print(f"Connection closed: {addr}")

def main():
    HOST = "0.0.0.0"
    PORT = 56789
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind((HOST, PORT))
    server_sock.listen()
    print(f"Server listening on {HOST}:{PORT}")
    try:
        while True:
            conn, addr = server_sock.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("Server shutting down.")
    finally:
        server_sock.close()

if __name__ == "__main__":
    main()
