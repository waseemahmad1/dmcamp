import socket
import json
import fnmatch
import threading
import hashlib
import datetime
from collections import OrderedDict

class ChatServer:
    MSGLEN = 409600

    # Create a JSON message, add a newline delimiter, and encode to bytes
    def create_msg(self, cmd, src="", to="", body="", err=False):
        msg = {
            "cmd": cmd,
            "from": src,
            "to": to,
            "body": body,
            "error": err
        }
        return (json.dumps(msg) + "\n").encode()

    def __init__(self, host='localhost', port=12345):
        self.host = socket.gethostbyname(socket.gethostname())
        self.port = port
        # Maps usernames to their data (password hash and unread messages)
        self.users = OrderedDict()     
        # Maps usernames to their active connection objects
        self.active_users = {}         
        # Maps a sorted tuple of two usernames to a list of message entries (conversation history)
        self.conversations = {}        
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(('0.0.0.0', port))
        self.running = True
        self.next_msg_id = 1  # Global counter for assigning unique message IDs

    def start(self):
        # Start listening for incoming client connections
        self.server.listen()
        print(f"[LISTENING] Server is listening on {self.host}:{self.port}")
        while self.running:
            conn, addr = self.server.accept()
            thread = threading.Thread(target=self.handle_client, args=(conn, addr))
            thread.start()

    def stop(self):
        self.running = False
        self.server.close()

    def read_messages(self, conn):
        buffer = ""
        while True:
            try:
                data = conn.recv(ChatServer.MSGLEN).decode()
            except Exception as e:
                print("Error reading from connection:", e)
                break
            if not data:
                break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                yield line
        return

    # Hash a password using SHA256
    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    # Main function to handle a connected client
    def handle_client(self, conn, addr):
        print(f"[NEW CONNECTION] {addr} connected.")
        try:
            for raw_msg in self.read_messages(conn):
                if not raw_msg:
                    continue
                try:
                    parts = json.loads(raw_msg)
                except json.JSONDecodeError:
                    conn.send(self.create_msg("error", body="Invalid JSON", err=True))
                    continue

                cmd = parts.get("cmd")
                username = parts.get("from")

                # Ceck credentials and add user to active_users if valid
                if cmd == "login":
                    password = parts.get("password", "")
                    if username not in self.users:
                        conn.send(self.create_msg(cmd, body="Username does not exist", err=True))
                    else:
                        stored_hash = self.users[username]["password_hash"]
                        if stored_hash != self.hash_password(password):
                            conn.send(self.create_msg(cmd, body="Incorrect password", err=True))
                        elif username in self.active_users:
                            conn.send(self.create_msg(cmd, body="Already logged in elsewhere", err=True))
                        else:
                            self.active_users[username] = conn
                            unread_count = len(self.users[username]["messages"])
                            conn.send(self.create_msg(cmd, body=f"Login successful. Unread messages: {unread_count}", to=username))

                # Register a new account if the username is not already taken
                elif cmd == "create":
                    password = parts.get("password", "")
                    if username in self.users:
                        conn.send(self.create_msg(cmd, body="Username already exists", err=True))
                    else:
                        self.users[username] = {"password_hash": self.hash_password(password), "messages": []}
                        conn.send(self.create_msg(cmd, body="Account created", to=username))

                # Ccomma-separated list of usernames matching the wildcard
                elif cmd == "list":
                    wildcard = parts.get("body", "*")
                    matching_users = fnmatch.filter(list(self.users.keys()), wildcard)
                    matching_str = ",".join(matching_users)
                    conn.send(self.create_msg(cmd, body=matching_str))

                # Send a message from one user to another and record it in conversation history
                elif cmd == "send":
                    recipient = parts.get("to")
                    message = parts.get("body")
                    timestamp = datetime.datetime.now().isoformat()
                    conv_key = tuple(sorted([username, recipient]))
                    if conv_key not in self.conversations:
                        self.conversations[conv_key] = []
                    msg_id = self.next_msg_id
                    self.next_msg_id += 1
                    message_entry = {
                        "id": msg_id,
                        "sender": username,
                        "message": message,
                        "timestamp": timestamp
                    }
                    self.conversations[conv_key].append(message_entry)

                    if recipient not in self.users:
                        conn.send(self.create_msg(cmd, body="Recipient not found", err=True))
                    else:
                        if recipient in self.active_users:
                            try:
                                # Immediately push the message if the recipient is online
                                payload = json.dumps([message_entry])
                                self.active_users[recipient].send(self.create_msg("chat", src=username, body=payload))
                            except Exception as e:
                                print(f"Error sending to active user {recipient}: {e}")
                                self.users[recipient]["messages"].append(message_entry)
                        else:
                            self.users[recipient]["messages"].append(message_entry)
                        conn.send(self.create_msg(cmd, body="Message sent"))

                # Return unread messages for a user, optionally limited by a count
                elif cmd == "read":
                    if username not in self.users:
                        conn.send(self.create_msg(cmd, body="User not found", err=True))
                    else:
                        limit = None
                        body_field = parts.get("body", "")
                        if body_field:
                            try:
                                limit = int(body_field)
                            except ValueError:
                                limit = None
                        user_messages = self.users[username]["messages"]
                        if limit is not None and limit > 0:
                            messages_to_view = user_messages[:limit]
                            self.users[username]["messages"] = user_messages[limit:]
                        else:
                            messages_to_view = user_messages
                            self.users[username]["messages"] = []
                        msgs_with_index = []
                        for msg_entry in messages_to_view:
                            msgs_with_index.append({
                                "id": msg_entry["id"],
                                "sender": msg_entry["sender"],
                                "message": msg_entry["message"]
                            })
                        composite_body = json.dumps(msgs_with_index, indent=2)
                        conn.send(self.create_msg(cmd, body=composite_body))

                # Delete messages by their IDs from unread and conversation histories
                elif cmd == "delete_msg":
                    if username not in self.users:
                        conn.send(self.create_msg(cmd, body="User not found", err=True))
                    else:
                        raw_ids = parts.get("body", "")
                        if not raw_ids.strip():
                            conn.send(self.create_msg(cmd, body="No message ID provided", err=True))
                            continue
                        try:
                            ids_to_delete = [int(x.strip()) for x in raw_ids.split(",") if x.strip().isdigit()]
                        except Exception as e:
                            conn.send(self.create_msg(cmd, body="Invalid message IDs", err=True))
                            continue
                        if not ids_to_delete:
                            conn.send(self.create_msg(cmd, body="No valid message IDs provided", err=True))
                            continue

                        message_exists = False
                        for msg in self.users[username]["messages"]:
                            if msg["id"] in ids_to_delete:
                                message_exists = True
                                break
                        if not message_exists:
                            for conv_key in self.conversations:
                                if username in conv_key:
                                    for msg in self.conversations[conv_key]:
                                        if msg["id"] in ids_to_delete:
                                            message_exists = True
                                            break
                                    if message_exists:
                                        break
                        if not message_exists:
                            conn.send(self.create_msg(cmd, body="No matching message found to delete", err=True))
                            continue

                        current_unread = self.users[username]["messages"]
                        self.users[username]["messages"] = [msg for msg in current_unread if msg["id"] not in ids_to_delete]
                        for conv_key in self.conversations:
                            if username in conv_key:
                                conv = self.conversations[conv_key]
                                self.conversations[conv_key] = [msg for msg in conv if msg["id"] not in ids_to_delete]
                        conn.send(self.create_msg(cmd, body="Specified messages deleted"))

                # Show the full conversation history between two users
                elif cmd == "view_conv":
                    other_user = parts.get("to", "")
                    if other_user not in self.users:
                        conn.send(self.create_msg(cmd, body="User not found", err=True))
                    else:
                        conv_key = tuple(sorted([username, other_user]))
                        conversation = self.conversations.get(conv_key, [])
                        # Mark unread messages from the other user as read
                        if username in self.users:
                            current_unread = self.users[username]["messages"]
                            self.users[username]["messages"] = [msg for msg in current_unread if msg["sender"] != other_user]
                        if not conversation:
                            conn.send(self.create_msg(cmd, body="No conversation history found"))
                        else:
                            conv_with_index = []
                            for msg_entry in conversation:
                                conv_with_index.append({
                                    "id": msg_entry["id"],
                                    "sender": msg_entry["sender"],
                                    "message": msg_entry["message"],
                                    "timestamp": msg_entry["timestamp"]
                                })
                            conv_str = json.dumps(conv_with_index, indent=2)
                            conn.send(self.create_msg(cmd, to=other_user, body=conv_str))

                # Delete a user account 
                elif cmd == "delete":
                    if username not in self.users:
                        conn.send(self.create_msg(cmd, body="User does not exist", err=True))
                    else:
                        del self.users[username]
                        if username in self.active_users:
                            del self.active_users[username]
                        conn.send(self.create_msg(cmd, body="Account deleted"))

                elif cmd == "logoff":
                    if username in self.active_users:
                        del self.active_users[username]
                    conn.send(self.create_msg(cmd, body="User logged off"))

                # Disconnect the client
                elif cmd == "close":
                    print(f"[DISCONNECT] {addr} disconnected.")
                    break
                else:
                    conn.send(self.create_msg("error", body="Unknown command", err=True))
        except Exception as e:
            print(f"[ERROR] Exception handling client {addr}: {e}")
        finally:
            conn.close()
            print(f"[DISCONNECT] {addr} connection closed.")

if __name__ == "__main__":
    server = ChatServer(host='localhost', port=12345)
    try:
        server.start()
    except KeyboardInterrupt:
        print("[SHUTDOWN] Server is shutting down.")
        server.stop()