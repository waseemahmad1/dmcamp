import socket
import json
import fnmatch
import threading
import hashlib
from collections import OrderedDict

class ChatServer:
    MSGLEN = 409600

    def create_msg(self, cmd, src="", to="", body="", err=False):
        
        msg = {
            "cmd": cmd,
            "from": src,
            "to": to,
            "body": body,
            "error": err
        }
        return (json.dumps(msg) + "\n").encode()

    def __init__(self, host='0.0.0.0', port=56789):
        self.host = socket.gethostbyname(socket.gethostname())
        self.port = port

        # maps users to their hashed password and undelivered messages, which is a tuple [sender: messsage]
        self.users = OrderedDict()
        self.active_users = {}
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((host, port))
        self.running = True

    def start(self):
        self.server.listen()
        print(f"Server is listening on {self.host}:{self.port}")
        while self.running:
            conn, addr = self.server.accept()
            thread = threading.Thread(target=self.handle_client, args=(conn, addr))
            thread.start()

    def stop(self):
        self.running = False
        self.server.close()

    def read_messages(self, conn):
        """
        Generator that buffers incoming data from 'conn' and yields complete messages.
        Messages are assumed to be delimited by newline characters.
        """
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

    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

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

                if cmd == "login":
                    # Expecting a "password" field in the login command.
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

                elif cmd == "create":
                    # Expecting a "password" field for account creation.
                    password = parts.get("password", "")
                    if username in self.users:
                        conn.send(self.create_msg(cmd, body="Username already exists", err=True))
                    else:
                        self.users[username] = {"password_hash": self.hash_password(password), "messages": []}
                        conn.send(self.create_msg(cmd, body="Account created", to=username))

                elif cmd == "list":
                    # List accounts matching a wildcard pattern. Default is '*' (all accounts).
                    wildcard = parts.get("body", "*")
                    matching_users = fnmatch.filter(list(self.users.keys()), wildcard)
                    matching_str = ",".join(matching_users)
                    conn.send(self.create_msg(cmd, body=matching_str))

                elif cmd == "send":
                    recipient = parts.get("to")
                    message = parts.get("body")
                    if recipient not in self.users:
                        conn.send(self.create_msg(cmd, body="Recipient not found", err=True))
                    else:
                        if recipient in self.active_users:
                            try:
                                self.active_users[recipient].send(self.create_msg("deliver", src=username, body=message))
                            except Exception as e:
                                print(f"Error sending to active user {recipient}: {e}")
                                self.users[recipient]["messages"].append((username, message))
                        else:
                            self.users[recipient]["messages"].append((username, message))
                        conn.send(self.create_msg(cmd, body="Message sent"))

                elif cmd == "deliver":
                    # The "deliver" command may include an optional limit (number of messages) in "body".
                    if username not in self.users:
                        conn.send(self.create_msg(cmd, body="User not found", err=True))
                    else:
                        limit = None
                        body_field = parts.get("body", "")
                        if body_field:
                            try:
                                limit = int(body_field)
                            except ValueError:
                                limit = None  # If conversion fails, deliver all.
                        user_messages = self.users[username]["messages"]
                        if limit is not None:
                            messages_to_deliver = user_messages[:limit]
                            remaining_messages = user_messages[limit:]
                        else:
                            messages_to_deliver = user_messages
                            remaining_messages = []
                        for (sender, msg_text) in messages_to_deliver:
                            conn.send(self.create_msg("deliver", src=sender, body=msg_text))
                        self.users[username]["messages"] = remaining_messages

                elif cmd == "delete_msg":
                    # The "delete_msg" command expects the "body" to contain a list of indices to delete.
                    if username not in self.users:
                        conn.send(self.create_msg(cmd, body="User not found", err=True))
                    else:
                        raw_indices = parts.get("body", "")
                        indices = []
                        if isinstance(raw_indices, list):
                            indices = raw_indices
                        else:
                            try:
                                indices = [int(x.strip()) for x in raw_indices.split(",") if x.strip().isdigit()]
                            except Exception as e:
                                conn.send(self.create_msg(cmd, body="Invalid indices", err=True))
                                continue
                        current_msgs = self.users[username]["messages"]
                        # Build a new list excluding the messages at the specified indices.
                        new_msgs = [msg for idx, msg in enumerate(current_msgs) if idx not in indices]
                        self.users[username]["messages"] = new_msgs
                        conn.send(self.create_msg(cmd, body="Specified messages deleted"))

                elif cmd == "delete":
                    # Delete an account only if there are no undelivered messages.
                    if username not in self.users:
                        conn.send(self.create_msg(cmd, body="User does not exist", err=True))
                    elif len(self.users[username]["messages"]) > 0:
                        conn.send(self.create_msg(cmd, body="Undelivered messages exist", err=True))
                    else:
                        del self.users[username]
                        if username in self.active_users:
                            del self.active_users[username]
                        conn.send(self.create_msg(cmd, body="Account deleted"))

                elif cmd == "logoff":
                    if username in self.active_users:
                        del self.active_users[username]
                    conn.send(self.create_msg(cmd, body="User logged off"))

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
    server = ChatServer(host='localhost', port=56789)
    try:
        server.start()
    except KeyboardInterrupt:
        print("[SHUTDOWN] Server is shutting down.")
        server.stop()
